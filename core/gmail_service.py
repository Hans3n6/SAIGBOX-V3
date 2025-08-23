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
        self.client_id = os.getenv("GMAIL_CLIENT_ID")
        self.client_secret = os.getenv("GMAIL_CLIENT_SECRET")
        self.redirect_uri = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/auth/callback")
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
    
    def get_auth_url(self) -> str:
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        return auth_url
    
    def exchange_code(self, code: str) -> Dict[str, Any]:
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        return {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_expiry': credentials.expiry.isoformat() if credentials.expiry else None
        }
    
    def get_service(self, user: User):
        if not user.access_token:
            raise ValueError("User has no access token")
        
        credentials = Credentials(
            token=user.access_token,
            refresh_token=user.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes
        )
        
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
                   cc: List[str] = None, bcc: List[str] = None) -> Dict[str, Any]:
        try:
            service = self.get_service(user)
            
            # Create message
            message = self._create_message(user.email, to, subject, body, cc, bcc)
            
            # Send message
            result = service.users().messages().send(
                userId='me',
                body={'raw': message}
            ).execute()
            
            return result
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            raise
    
    def _create_message(self, sender: str, to: List[str], subject: str, 
                       body: str, cc: List[str] = None, bcc: List[str] = None) -> str:
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
        
        message.attach(MIMEText(body, 'plain'))
        
        return base64.urlsafe_b64encode(message.as_bytes()).decode()