import os
import base64
from datetime import datetime
from typing import List, Dict, Any, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session
import logging

from core.database import Email, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GmailService:
    def __init__(self):
        # OAuth app credentials for token refresh
        self.client_id = os.getenv("GMAIL_CLIENT_ID")
        self.client_secret = os.getenv("GMAIL_CLIENT_SECRET")
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.scopes = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.modify',
            'https://www.googleapis.com/auth/gmail.labels',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
            'openid',
            'https://mail.google.com/'
        ]
    
    def create_service_from_tokens(self, access_token: str, refresh_token: str = None):
        """Create Gmail service directly from OAuth tokens"""
        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes
        )
        
        return build('gmail', 'v1', credentials=credentials)
    
    def get_service(self, user: User):
        """Get Gmail service using user's OAuth tokens"""
        # Use OAuth tokens from the user's OAuth flow
        if user.oauth_access_token:
            # User authenticated via OAuth (Google/Microsoft)
            access_token = user.oauth_access_token
            refresh_token = user.oauth_refresh_token
        elif user.access_token:
            # Legacy support
            access_token = user.access_token
            refresh_token = user.refresh_token
        else:
            raise ValueError("User has no access token. Please re-authenticate.")
        
        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes
        )
        
        # Check if token needs refresh
        if credentials.expired and credentials.refresh_token:
            from google.auth.transport.requests import Request
            credentials.refresh(Request())
            
            # Update stored tokens
            user.oauth_access_token = credentials.token
            if credentials.expiry:
                user.oauth_token_expires = credentials.expiry
        
        return build('gmail', 'v1', credentials=credentials)
    
    def fetch_emails(self, db: Session, user: User, max_results: int = 50, page_token: str = None) -> Dict[str, Any]:
        try:
            service = self.get_service(user)
            
            # Get last sync token if exists (for incremental sync)
            last_history_id = getattr(user, 'last_history_id', None) if not page_token else None
            
            # Fetch messages
            results = service.users().messages().list(
                userId='me',
                maxResults=max_results,
                pageToken=page_token,
                q='-in:trash'  # Exclude trashed emails
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for msg in messages:
                try:
                    # Get full message details
                    message = service.users().messages().get(
                        userId='me',
                        id=msg['id']
                    ).execute()
                    
                    # Parse email
                    email_data = self._parse_email(message)
                    
                    # Save or update in database
                    existing = db.query(Email).filter(
                        Email.gmail_id == email_data['gmail_id'],
                        Email.user_id == user.id
                    ).first()
                    
                    if existing:
                        for key, value in email_data.items():
                            setattr(existing, key, value)
                        email_obj = existing
                    else:
                        email_obj = Email(user_id=user.id, **email_data)
                        db.add(email_obj)
                    
                    emails.append(email_obj)
                    
                except Exception as e:
                    logger.error(f"Error processing email {msg['id']}: {e}")
                    continue
            
            db.commit()
            
            return {
                'emails': emails,
                'next_page_token': results.get('nextPageToken'),
                'total': results.get('resultSizeEstimate', len(emails))
            }
            
        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            raise
    
    def _parse_email(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message['payload']
        headers = payload.get('headers', [])
        
        # Extract headers
        header_dict = {h['name']: h['value'] for h in headers}
        
        # Parse body
        body_text, body_html = self._get_body(payload)
        
        # Parse attachments
        attachments = self._get_attachments(payload)
        
        # Parse labels
        labels = message.get('labelIds', [])
        is_read = 'UNREAD' not in labels
        is_starred = 'STARRED' in labels
        
        # Parse timestamp
        timestamp = int(message.get('internalDate', 0)) / 1000
        received_at = datetime.fromtimestamp(timestamp) if timestamp else None
        
        return {
            'gmail_id': message['id'],
            'thread_id': message.get('threadId'),
            'subject': header_dict.get('Subject', ''),
            'sender': header_dict.get('From', ''),
            'sender_name': self._extract_name(header_dict.get('From', '')),
            'recipients': self._parse_recipients(header_dict.get('To', '')),
            'cc': self._parse_recipients(header_dict.get('Cc', '')),
            'bcc': self._parse_recipients(header_dict.get('Bcc', '')),
            'body_text': body_text,
            'body_html': body_html,
            'snippet': message.get('snippet', ''),
            'labels': labels,
            'is_read': is_read,
            'is_starred': is_starred,
            'has_attachments': len(attachments) > 0,
            'attachments': attachments,
            'received_at': received_at
        }
    
    def _get_body(self, payload: Dict[str, Any]) -> tuple:
        body_text = ""
        body_html = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    body_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif part['mimeType'] == 'text/html':
                    data = part['body'].get('data', '')
                    body_html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        else:
            body = payload.get('body', {})
            data = body.get('data', '')
            if data:
                decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                if payload.get('mimeType') == 'text/html':
                    body_html = decoded
                else:
                    body_text = decoded
        
        return body_text, body_html
    
    def _get_attachments(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        attachments = []
        
        if 'parts' in payload:
            for part in payload['parts']:
                filename = part.get('filename')
                if filename:
                    attachments.append({
                        'filename': filename,
                        'mimeType': part.get('mimeType'),
                        'size': part.get('body', {}).get('size', 0),
                        'attachmentId': part.get('body', {}).get('attachmentId')
                    })
        
        return attachments
    
    def _extract_name(self, from_header: str) -> str:
        if '<' in from_header:
            return from_header.split('<')[0].strip().strip('"')
        return from_header
    
    def _parse_recipients(self, header_value: str) -> List[str]:
        if not header_value:
            return []
        return [r.strip() for r in header_value.split(',')]
    
    def mark_as_read(self, user: User, email_id: str) -> bool:
        try:
            service = self.get_service(user)
            service.users().messages().modify(
                userId='me',
                id=email_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Error marking email as read: {e}")
            return False
    
    def mark_as_unread(self, user: User, email_id: str) -> bool:
        try:
            service = self.get_service(user)
            service.users().messages().modify(
                userId='me',
                id=email_id,
                body={'addLabelIds': ['UNREAD']}
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Error marking email as unread: {e}")
            return False
    
    def star_email(self, user: User, email_id: str) -> bool:
        try:
            service = self.get_service(user)
            service.users().messages().modify(
                userId='me',
                id=email_id,
                body={'addLabelIds': ['STARRED']}
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Error starring email: {e}")
            return False
    
    def unstar_email(self, user: User, email_id: str) -> bool:
        try:
            service = self.get_service(user)
            service.users().messages().modify(
                userId='me',
                id=email_id,
                body={'removeLabelIds': ['STARRED']}
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Error unstarring email: {e}")
            return False
    
    def move_to_trash(self, user: User, email_id: str) -> bool:
        try:
            service = self.get_service(user)
            service.users().messages().trash(userId='me', id=email_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error moving email to trash: {e}")
            return False
    
    def restore_from_trash(self, user: User, email_id: str) -> bool:
        try:
            service = self.get_service(user)
            service.users().messages().untrash(userId='me', id=email_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error restoring email from trash: {e}")
            return False
    
    def send_email(self, user: User, to: List[str], subject: str, body: str, 
                   cc: List[str] = None, bcc: List[str] = None, thread_id: str = None,
                   message_id: str = None) -> Dict[str, Any]:
        try:
            service = self.get_service(user)
            
            # Create message with proper headers for threading
            message = self._create_message(user.email, to, subject, body, cc, bcc, 
                                          thread_id=thread_id, message_id=message_id)
            
            # Prepare send body
            send_body = {'raw': message}
            if thread_id:
                send_body['threadId'] = thread_id
            
            # Send message
            result = service.users().messages().send(
                userId='me',
                body=send_body
            ).execute()
            
            return result
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            raise
    
    def reply_to_email(self, user: User, original_message_id: str, thread_id: str,
                      to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send a reply in the same thread"""
        try:
            service = self.get_service(user)
            
            # Get the original message to extract headers
            original = service.users().messages().get(
                userId='me',
                id=original_message_id,
                format='metadata',
                metadataHeaders=['Message-ID']
            ).execute()
            
            # Extract Message-ID for In-Reply-To header
            message_id = None
            for header in original.get('payload', {}).get('headers', []):
                if header['name'] == 'Message-ID':
                    message_id = header['value']
                    break
            
            # Send reply with thread context
            return self.send_email(
                user=user,
                to=[to],
                subject=subject,
                body=body,
                thread_id=thread_id,
                message_id=message_id
            )
        except Exception as e:
            logger.error(f"Error replying to email: {e}")
            raise
    
    def _create_message(self, sender: str, to: List[str], subject: str, 
                       body: str, cc: List[str] = None, bcc: List[str] = None,
                       thread_id: str = None, message_id: str = None) -> str:
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        message = MIMEMultipart()
        message['From'] = sender
        message['To'] = ', '.join(to)
        message['Subject'] = subject
        
        if cc:
            message['Cc'] = ', '.join(cc)
        if bcc:
            message['Bcc'] = ', '.join(bcc)
        
        # Add threading headers for replies
        if message_id:
            message['In-Reply-To'] = message_id
            message['References'] = message_id
        
        message.attach(MIMEText(body, 'plain'))
        
        return base64.urlsafe_b64encode(message.as_bytes()).decode()