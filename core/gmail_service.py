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
        # OAuth app credentials for token refresh (uses GOOGLE_ prefix, falls back to GMAIL_)
        self.client_id = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GMAIL_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("GMAIL_CLIENT_SECRET")
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
    
    def fetch_recent_emails(self, user: User, limit: int = 50) -> List[Dict]:
        """Fetch recent emails from Gmail - stub implementation"""
        # For now, return empty list to avoid errors
        # This needs to be implemented with actual Gmail API calls
        return []
    
    def get_service(self, user: User):
        """Get Gmail service using user's OAuth tokens"""
        # Use OAuth tokens from the user's OAuth flow
        if user.oauth_access_token:
            # User authenticated via OAuth (Google/Microsoft)
            access_token = user.oauth_access_token
            refresh_token = user.oauth_refresh_token
            logger.info(f"Using OAuth tokens for user {user.email}")
        elif user.access_token:
            # Legacy support
            access_token = user.access_token
            refresh_token = user.refresh_token
            logger.info(f"Using legacy tokens for user {user.email}")
        else:
            logger.error(f"User {user.email} has no access token")
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
        """Primary email sync method with retry logic"""
        logger.info(f"Starting fetch_emails for user {user.email}, max_results={max_results}, page_token={page_token}")
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                service = self.get_service(user)
                logger.info(f"Gmail service created successfully for {user.email}")
                
                # Get last sync token if exists (for incremental sync)
                last_history_id = getattr(user, 'last_history_id', None) if not page_token else None
                
                # Fetch messages including trash to maintain sync
                # We'll handle spam exclusion but include trash for proper synchronization
                query = '-in:spam'  # Exclude only spam, include trash for sync
                
                logger.info(f"Calling Gmail API with query: {query}, maxResults: {max_results}")
                results = service.users().messages().list(
                    userId='me',
                    maxResults=max_results,
                    pageToken=page_token,
                    q=query
                ).execute()
                
                messages = results.get('messages', [])
                next_page_token = results.get('nextPageToken')
                logger.info(f"Gmail API returned {len(messages)} messages, next_page_token: {next_page_token if next_page_token else 'None'}")
                logger.info(f"Total result size estimate: {results.get('resultSizeEstimate', 'unknown')}")
                emails = []
                failed_count = 0
                
                for msg in messages:
                    try:
                        # Get full message details with retry
                        message = self._fetch_message_with_retry(service, msg['id'])
                        if not message:
                            failed_count += 1
                            continue
                        
                        # Parse email
                        email_data = self._parse_email(message)
                        
                        # Save or update in database
                        existing = db.query(Email).filter(
                            Email.gmail_id == email_data['gmail_id'],
                            Email.user_id == user.id
                        ).first()
                        
                        if existing:
                            # Update email data including trash status
                            # Check if trash status has changed
                            is_trashed = 'TRASH' in email_data.get('labels', [])
                            
                            # Update deleted_at based on current Gmail trash status
                            if is_trashed and not existing.deleted_at:
                                # Email was moved to trash in Gmail
                                existing.deleted_at = datetime.utcnow()
                                logger.info(f"Email {existing.gmail_id} moved to trash in Gmail, syncing to SAIGBOX")
                            elif not is_trashed and existing.deleted_at:
                                # Email was restored from trash in Gmail
                                existing.deleted_at = None
                                logger.info(f"Email {existing.gmail_id} restored from trash in Gmail, syncing to SAIGBOX")
                            
                            # Update other fields
                            for key, value in email_data.items():
                                if key != 'deleted_at':  # Don't override our logic above
                                    setattr(existing, key, value)
                            
                            email_obj = existing
                        else:
                            email_obj = Email(user_id=user.id, **email_data)
                            db.add(email_obj)
                        
                        emails.append(email_obj)
                        
                    except Exception as e:
                        logger.error(f"Error processing email {msg['id']}: {e}")
                        failed_count += 1
                        if failed_count > 5:  # Too many failures, use fallback
                            logger.warning("Too many failures, switching to fallback sync")
                            return self._fallback_sync(db, user, messages, service)
                        continue
                
                db.commit()
                
                result = {
                    'emails': emails,
                    'next_page_token': next_page_token,
                    'total': results.get('resultSizeEstimate', len(emails)),
                    'failed': failed_count
                }
                logger.info(f"Returning result with {len(emails)} emails, has more: {bool(next_page_token)}")
                return result
                
            except HttpError as e:
                if e.resp.status == 401:  # Token expired
                    logger.info(f"Token expired, refreshing... (attempt {retry_count + 1})")
                    try:
                        # Force token refresh
                        service = self.get_service(user)
                        retry_count += 1
                        continue
                    except Exception as refresh_error:
                        logger.error(f"Token refresh failed: {refresh_error}")
                        raise
                elif e.resp.status == 429:  # Rate limit
                    logger.warning(f"Rate limited, waiting before retry... (attempt {retry_count + 1})")
                    import time
                    time.sleep(2 ** retry_count)  # Exponential backoff
                    retry_count += 1
                    continue
                else:
                    logger.error(f"Gmail API error: {e}")
                    raise
            except Exception as e:
                logger.error(f"Error fetching emails (attempt {retry_count + 1}): {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    # Use fallback sync as last resort
                    return self._fallback_basic_sync(db, user)
        
        # If all retries failed
        logger.error("All retry attempts failed")
        return self._fallback_basic_sync(db, user)
    
    def _fetch_message_with_retry(self, service, message_id: str, max_retries: int = 2):
        """Fetch individual message with retry logic"""
        for attempt in range(max_retries):
            try:
                return service.users().messages().get(
                    userId='me',
                    id=message_id
                ).execute()
            except Exception as e:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.5)  # Brief pause before retry
                    continue
                logger.error(f"Failed to fetch message {message_id}: {e}")
                return None
        return None
    
    def _fallback_sync(self, db: Session, user: User, messages: list, service) -> Dict[str, Any]:
        """Fallback sync method for partial failures"""
        logger.info("Using fallback sync method")
        emails = []
        
        # Process only message headers (lighter weight)
        for msg in messages[:20]:  # Limit to 20 for fallback
            try:
                # Get only metadata, not full message
                message = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'To', 'Subject', 'Date']
                ).execute()
                
                # Create minimal email record
                email_data = self._parse_minimal_email(message)
                
                existing = db.query(Email).filter(
                    Email.gmail_id == email_data['gmail_id'],
                    Email.user_id == user.id
                ).first()
                
                if existing:
                    # Update trash status for existing emails
                    is_trashed = 'TRASH' in email_data.get('labels', [])
                    if is_trashed and not existing.deleted_at:
                        existing.deleted_at = datetime.utcnow()
                    elif not is_trashed and existing.deleted_at:
                        existing.deleted_at = None
                    
                    # Update other fields
                    for key, value in email_data.items():
                        if key != 'deleted_at':
                            setattr(existing, key, value)
                    emails.append(existing)
                else:
                    email_obj = Email(user_id=user.id, **email_data)
                    db.add(email_obj)
                    emails.append(email_obj)
                    
            except Exception as e:
                logger.error(f"Fallback sync error for {msg['id']}: {e}")
                continue
        
        db.commit()
        
        return {
            'emails': emails,
            'next_page_token': None,
            'total': len(emails),
            'fallback': True
        }
    
    def _fallback_basic_sync(self, db: Session, user: User) -> Dict[str, Any]:
        """Most basic fallback - return existing emails from database"""
        logger.warning("Using basic fallback - returning cached emails")
        
        # Return most recent emails from database (including trashed for sync purposes)
        emails = db.query(Email).filter(
            Email.user_id == user.id
        ).order_by(Email.received_at.desc()).limit(50).all()
        
        return {
            'emails': emails,
            'next_page_token': None,
            'total': len(emails),
            'cached': True,
            'message': 'Returning cached emails due to sync issues'
        }
    
    def _parse_minimal_email(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse minimal email data from metadata"""
        headers = {}
        if 'payload' in message and 'headers' in message['payload']:
            headers = {h['name']: h['value'] for h in message['payload']['headers']}
        
        # Parse timestamp
        timestamp = int(message.get('internalDate', 0)) / 1000
        received_at = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
        
        # Check if email is trashed
        labels = message.get('labelIds', [])
        is_trashed = 'TRASH' in labels
        deleted_at = datetime.utcnow() if is_trashed else None
        
        return {
            'gmail_id': message['id'],
            'thread_id': message.get('threadId'),
            'subject': headers.get('Subject', 'No Subject'),
            'sender': headers.get('From', 'Unknown'),
            'snippet': message.get('snippet', ''),
            'received_at': received_at,
            'is_read': 'UNREAD' not in labels,
            'labels': labels,
            'deleted_at': deleted_at  # Add deleted_at for minimal parsing too
        }
    
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
        is_trashed = 'TRASH' in labels  # Check if email is in Gmail trash
        
        # Parse timestamp
        timestamp = int(message.get('internalDate', 0)) / 1000
        received_at = datetime.fromtimestamp(timestamp) if timestamp else None
        
        # Set deleted_at if email is in trash
        deleted_at = datetime.utcnow() if is_trashed else None
        
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
            'deleted_at': deleted_at,  # Add deleted_at field
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
    
    def create_label(self, user: User, label_name: str) -> Optional[str]:
        """Create a new Gmail label/folder"""
        try:
            service = self.get_service(user)
            label_object = {
                'name': label_name,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }
            created_label = service.users().labels().create(
                userId='me',
                body=label_object
            ).execute()
            logger.info(f"Created label: {label_name} with ID: {created_label['id']}")
            return created_label['id']
        except Exception as e:
            if 'already exists' in str(e):
                # Label already exists, get its ID
                try:
                    labels = service.users().labels().list(userId='me').execute()
                    for label in labels.get('labels', []):
                        if label['name'] == label_name:
                            return label['id']
                except:
                    pass
            logger.error(f"Error creating label: {e}")
            return None
    
    def move_to_label(self, user: User, email_id: str, label_name: str) -> bool:
        """Move email to a specific label/folder"""
        try:
            service = self.get_service(user)
            
            # First ensure the label exists
            label_id = self.create_label(user, label_name)
            if not label_id:
                logger.error(f"Could not create or find label: {label_name}")
                return False
            
            # Add label to email
            service.users().messages().modify(
                userId='me',
                id=email_id,
                body={'addLabelIds': [label_id]}
            ).execute()
            
            logger.info(f"Moved email {email_id} to label {label_name}")
            return True
        except Exception as e:
            logger.error(f"Error moving email to label: {e}")
            return False
    
    def list_labels(self, user: User) -> List[Dict[str, str]]:
        """List all labels/folders for a user"""
        try:
            service = self.get_service(user)
            results = service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])
            
            # Filter out system labels and return user labels
            user_labels = []
            system_labels = ['INBOX', 'SENT', 'DRAFT', 'SPAM', 'TRASH', 'UNREAD', 
                           'STARRED', 'IMPORTANT', 'CHAT', 'CATEGORY_PERSONAL',
                           'CATEGORY_SOCIAL', 'CATEGORY_PROMOTIONS', 'CATEGORY_UPDATES',
                           'CATEGORY_FORUMS']
            
            for label in labels:
                if label['name'] not in system_labels and not label['name'].startswith('CATEGORY_'):
                    user_labels.append({
                        'id': label['id'],
                        'name': label['name']
                    })
            
            return user_labels
        except Exception as e:
            logger.error(f"Error listing labels: {e}")
            return []
    
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