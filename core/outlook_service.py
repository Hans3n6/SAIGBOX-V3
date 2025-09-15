"""
Outlook/Microsoft Graph API email service
Handles email operations for Microsoft/Outlook accounts
"""
import os
import base64
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy.orm import Session
import logging

from core.database import Email, User
from core.urgency_detector import UrgencyDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OutlookService:
    def __init__(self):
        # Microsoft app credentials
        self.client_id = os.getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        self.tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")  # 'common' for multi-tenant
        self.redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "https://api.saigbox.com/api/auth/microsoft/callback")
        
        # Microsoft Graph API base URL
        self.graph_api_base = "https://graph.microsoft.com/v1.0"
        
        # OAuth URLs
        self.auth_base_url = f"https://login.microsoftonline.com/{self.tenant_id}"
        
    def get_access_token(self, user: User, db: Session) -> Optional[str]:
        """Get valid access token for user, refreshing if necessary"""
        try:
            # Get stored OAuth token
            oauth_token = db.query(OAuthToken).filter(
                OAuthToken.user_id == user.id,
                OAuthToken.provider == "microsoft"
            ).first()
            
            if not oauth_token:
                logger.error(f"No Microsoft OAuth token found for user {user.email}")
                return None
            
            # Check if token is expired
            if oauth_token.expires_at and oauth_token.expires_at < datetime.utcnow():
                # Token expired, refresh it
                logger.info(f"Refreshing expired token for user {user.email}")
                new_token = self.refresh_access_token(oauth_token.refresh_token, db, user)
                if new_token:
                    return new_token
                else:
                    logger.error(f"Failed to refresh token for user {user.email}")
                    return None
            
            return oauth_token.access_token
            
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            return None
    
    def refresh_access_token(self, refresh_token: str, db: Session, user: User) -> Optional[str]:
        """Refresh the access token using refresh token"""
        try:
            token_url = f"{self.auth_base_url}/oauth2/v2.0/token"
            
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
                'scope': 'Mail.ReadWrite Mail.Send User.Read offline_access'
            }
            
            with httpx.Client() as client:
                response = client.post(token_url, data=data)
                response.raise_for_status()
                
                token_data = response.json()
                
                # Update stored token
                oauth_token = db.query(OAuthToken).filter(
                    OAuthToken.user_id == user.id,
                    OAuthToken.provider == "microsoft"
                ).first()
                
                if oauth_token:
                    oauth_token.access_token = token_data['access_token']
                    if 'refresh_token' in token_data:
                        oauth_token.refresh_token = token_data['refresh_token']
                    oauth_token.expires_at = datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 3600))
                    db.commit()
                
                return token_data['access_token']
                
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return None
    
    def fetch_emails(self, db: Session, user: User, max_results: int = 50, page_token: Optional[str] = None) -> Dict[str, Any]:
        """Fetch emails from Microsoft Graph API"""
        try:
            access_token = self.get_access_token(user, db)
            if not access_token:
                logger.error(f"No valid access token for user {user.email}")
                return self._fallback_basic_sync(db, user)
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Build query parameters
            params = {
                '$top': min(max_results, 100),  # Microsoft Graph limits to 100 per request
                '$orderby': 'receivedDateTime desc',
                '$select': 'id,subject,from,toRecipients,ccRecipients,bccRecipients,receivedDateTime,bodyPreview,body,hasAttachments,isRead,flag,conversationId,parentFolderId,importance'
            }
            
            # Add pagination if we have a token
            if page_token:
                # Microsoft uses skiptoken or @odata.nextLink
                params['$skiptoken'] = page_token
            
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.graph_api_base}/me/messages",
                    headers=headers,
                    params=params
                )
                
                if response.status_code == 401:
                    # Token might be invalid, try refreshing
                    logger.info("Got 401, attempting to refresh token")
                    oauth_token = db.query(OAuthToken).filter(
                        OAuthToken.user_id == user.id,
                        OAuthToken.provider == "microsoft"
                    ).first()
                    
                    if oauth_token and oauth_token.refresh_token:
                        new_token = self.refresh_access_token(oauth_token.refresh_token, db, user)
                        if new_token:
                            headers['Authorization'] = f'Bearer {new_token}'
                            response = client.get(
                                f"{self.graph_api_base}/me/messages",
                                headers=headers,
                                params=params
                            )
                
                response.raise_for_status()
                data = response.json()
                
                # Process messages
                messages = data.get('value', [])
                emails = []
                urgency_detector = UrgencyDetector(db)
                
                for msg in messages:
                    try:
                        email_data = self._parse_outlook_message(msg)
                        
                        # Check if email already exists
                        existing = db.query(Email).filter(
                            Email.outlook_id == email_data['outlook_id'],
                            Email.user_id == user.id
                        ).first()
                        
                        if existing:
                            # Update existing email
                            for key, value in email_data.items():
                                if hasattr(existing, key):
                                    setattr(existing, key, value)
                            email_obj = existing
                        else:
                            # Create new email
                            email_obj = Email(user_id=user.id, **email_data)
                            db.add(email_obj)
                            
                            # Check urgency for new emails
                            is_urgent, score, reason = urgency_detector.should_mark_urgent(email_obj, user)
                            if is_urgent:
                                email_obj.is_urgent = True
                                email_obj.urgency_score = score
                                email_obj.urgency_reason = reason
                                logger.info(f"Email marked as urgent: {email_obj.subject} (score: {score})")
                        
                        emails.append(email_obj)
                        
                    except Exception as e:
                        logger.error(f"Error processing Outlook message {msg.get('id')}: {e}")
                        continue
                
                db.commit()
                
                # Extract next page token from @odata.nextLink
                next_link = data.get('@odata.nextLink')
                next_page_token = None
                if next_link:
                    # Extract skiptoken from the URL
                    import urllib.parse
                    parsed = urllib.parse.urlparse(next_link)
                    query_params = urllib.parse.parse_qs(parsed.query)
                    next_page_token = query_params.get('$skiptoken', [None])[0]
                
                logger.info(f"Fetched {len(emails)} emails from Outlook for user {user.email}")
                
                return {
                    'emails': emails,
                    'next_page_token': next_page_token,
                    'total': len(emails)
                }
                
        except Exception as e:
            logger.error(f"Error fetching Outlook emails: {e}")
            return self._fallback_basic_sync(db, user)
    
    def _parse_outlook_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Outlook message into our Email model format"""
        # Parse sender
        from_field = message.get('from', {})
        sender_email = from_field.get('emailAddress', {}).get('address', '')
        sender_name = from_field.get('emailAddress', {}).get('name', '')
        
        # Parse recipients
        to_recipients = [r['emailAddress']['address'] for r in message.get('toRecipients', [])]
        cc_recipients = [r['emailAddress']['address'] for r in message.get('ccRecipients', [])]
        bcc_recipients = [r['emailAddress']['address'] for r in message.get('bccRecipients', [])]
        
        # Parse dates
        received_at = None
        if message.get('receivedDateTime'):
            try:
                # Outlook returns ISO format with timezone
                received_at = datetime.fromisoformat(message['receivedDateTime'].replace('Z', '+00:00'))
            except:
                received_at = datetime.utcnow()
        
        # Parse body
        body_content = message.get('body', {})
        body_text = ''
        body_html = ''
        if body_content.get('contentType') == 'html':
            body_html = body_content.get('content', '')
            # Simple HTML to text conversion
            import re
            body_text = re.sub('<[^<]+?>', '', body_html)
        else:
            body_text = body_content.get('content', '')
        
        # Parse importance/priority
        importance = message.get('importance', 'normal')
        is_important = importance == 'high'
        
        # Check if in deleted folder (need to check parentFolderId)
        # This would need additional API call to check folder details
        is_deleted = False
        
        return {
            'outlook_id': message.get('id'),
            'conversation_id': message.get('conversationId'),
            'subject': message.get('subject', ''),
            'sender': sender_email,
            'sender_name': sender_name,
            'recipients': to_recipients,
            'cc': cc_recipients,
            'bcc': bcc_recipients,
            'snippet': message.get('bodyPreview', ''),
            'body_text': body_text,
            'body_html': body_html,
            'has_attachments': message.get('hasAttachments', False),
            'is_read': message.get('isRead', False),
            'is_starred': message.get('flag', {}).get('flagStatus') == 'flagged',
            'is_important': is_important,
            'received_at': received_at,
            'deleted_at': datetime.utcnow() if is_deleted else None,
            'labels': [],  # Outlook uses folders, not labels
            'attachments': []  # Would need separate API call to fetch
        }
    
    def move_to_trash(self, user: User, message_id: str, db: Session) -> bool:
        """Move email to Deleted Items folder"""
        try:
            access_token = self.get_access_token(user, db)
            if not access_token:
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # First, get the Deleted Items folder ID
            with httpx.Client(timeout=30.0) as client:
                # Get well-known folders
                response = client.get(
                    f"{self.graph_api_base}/me/mailFolders/deleteditems",
                    headers=headers
                )
                response.raise_for_status()
                deleted_folder = response.json()
                
                # Move message to Deleted Items
                data = {
                    'destinationId': deleted_folder['id']
                }
                
                response = client.post(
                    f"{self.graph_api_base}/me/messages/{message_id}/move",
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                
                logger.info(f"Moved Outlook message {message_id} to trash")
                return True
                
        except Exception as e:
            logger.error(f"Error moving Outlook email to trash: {e}")
            return False
    
    def restore_from_trash(self, user: User, message_id: str, db: Session) -> bool:
        """Restore email from Deleted Items to Inbox"""
        try:
            access_token = self.get_access_token(user, db)
            if not access_token:
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            with httpx.Client(timeout=30.0) as client:
                # Get Inbox folder ID
                response = client.get(
                    f"{self.graph_api_base}/me/mailFolders/inbox",
                    headers=headers
                )
                response.raise_for_status()
                inbox_folder = response.json()
                
                # Move message to Inbox
                data = {
                    'destinationId': inbox_folder['id']
                }
                
                response = client.post(
                    f"{self.graph_api_base}/me/messages/{message_id}/move",
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                
                logger.info(f"Restored Outlook message {message_id} from trash")
                return True
                
        except Exception as e:
            logger.error(f"Error restoring Outlook email from trash: {e}")
            return False
    
    def permanently_delete(self, user: User, message_id: str, db: Session) -> bool:
        """Permanently delete an email"""
        try:
            access_token = self.get_access_token(user, db)
            if not access_token:
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}'
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.delete(
                    f"{self.graph_api_base}/me/messages/{message_id}",
                    headers=headers
                )
                response.raise_for_status()
                
                logger.info(f"Permanently deleted Outlook message {message_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error permanently deleting Outlook email: {e}")
            return False
    
    def send_email(self, user: User, to: List[str], subject: str, body: str, 
                   cc: List[str] = None, bcc: List[str] = None, 
                   attachments: List[Dict] = None, db: Session = None) -> bool:
        """Send an email via Outlook"""
        try:
            access_token = self.get_access_token(user, db)
            if not access_token:
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Build message
            message = {
                'subject': subject,
                'body': {
                    'contentType': 'HTML' if '<' in body else 'Text',
                    'content': body
                },
                'toRecipients': [{'emailAddress': {'address': addr}} for addr in to]
            }
            
            if cc:
                message['ccRecipients'] = [{'emailAddress': {'address': addr}} for addr in cc]
            
            if bcc:
                message['bccRecipients'] = [{'emailAddress': {'address': addr}} for addr in bcc]
            
            # Add attachments if provided
            if attachments:
                message['attachments'] = []
                for att in attachments:
                    message['attachments'].append({
                        '@odata.type': '#microsoft.graph.fileAttachment',
                        'name': att.get('name', 'attachment'),
                        'contentBytes': att.get('content')  # Should be base64 encoded
                    })
            
            # Send email
            data = {
                'message': message,
                'saveToSentItems': True
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.graph_api_base}/me/sendMail",
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                
                logger.info(f"Sent email via Outlook: {subject}")
                return True
                
        except Exception as e:
            logger.error(f"Error sending Outlook email: {e}")
            return False
    
    def create_folder(self, user: User, folder_name: str, db: Session) -> Optional[str]:
        """Create a new mail folder"""
        try:
            access_token = self.get_access_token(user, db)
            if not access_token:
                return None
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'displayName': folder_name,
                'isHidden': False
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.graph_api_base}/me/mailFolders",
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                
                folder = response.json()
                logger.info(f"Created Outlook folder: {folder_name}")
                return folder['id']
                
        except Exception as e:
            logger.error(f"Error creating Outlook folder: {e}")
            return None
    
    def move_to_folder(self, user: User, message_id: str, folder_id: str, db: Session) -> bool:
        """Move email to a specific folder"""
        try:
            access_token = self.get_access_token(user, db)
            if not access_token:
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'destinationId': folder_id
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.graph_api_base}/me/messages/{message_id}/move",
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                
                logger.info(f"Moved Outlook message {message_id} to folder {folder_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error moving Outlook email to folder: {e}")
            return False
    
    def _fallback_basic_sync(self, db: Session, user: User) -> Dict[str, Any]:
        """Fallback to return cached emails when API fails"""
        try:
            # Return emails from database
            emails = db.query(Email).filter(
                Email.user_id == user.id,
                Email.deleted_at.is_(None)
            ).order_by(Email.received_at.desc()).limit(50).all()
            
            logger.info(f"Fallback sync returned {len(emails)} cached emails for {user.email}")
            
            return {
                'emails': emails,
                'next_page_token': None,
                'total': len(emails),
                'cached': True,
                'message': 'Using cached emails due to sync error'
            }
        except Exception as e:
            logger.error(f"Fallback sync also failed: {e}")
            return {
                'emails': [],
                'next_page_token': None,
                'total': 0,
                'error': str(e)
            }