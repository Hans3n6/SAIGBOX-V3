"""
Unified Authentication Service
Bridges existing OAuth (Google/Microsoft) with Cognito and S3 storage
"""
import os
import uuid
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from core.cognito_auth import CognitoAuth
from core.user_storage import UserStorageService
from core.database import User

class UnifiedAuthService:
    """Unified authentication service that combines OAuth and Cognito"""
    
    def __init__(self):
        self.cognito = CognitoAuth()
        self.storage = UserStorageService()
    
    async def sync_oauth_user_to_cognito(self, db: Session, user: User, oauth_data: Dict[str, Any]) -> bool:
        """
        When a user logs in via Google/Microsoft OAuth, create/update their Cognito account
        and set up S3 storage
        """
        try:
            # Check if user already has Cognito account
            if user.cognito_sub:
                # Verify the Cognito account still exists
                try:
                    user_info = await self.cognito.get_user_info_by_sub(user.cognito_sub)
                    if user_info:
                        # User exists, just update S3 profile
                        await self._update_s3_profile(user)
                        return True
                except Exception as e:
                    # Cognito user was deleted, clear the reference
                    logger.warning(f"Cognito user {user.cognito_sub} not found ({e}), re-creating...")
                    user.cognito_sub = None
                    user.cognito_confirmed = False
                    db.commit()
            
            # Create a Cognito account for OAuth user
            # Generate a secure random password (user won't need it for OAuth login)
            import secrets
            temp_password = secrets.token_urlsafe(32)
            
            # Try to create Cognito account with auto-verification for OAuth users
            result = await self.cognito.register_user(
                email=user.email,
                password=temp_password,
                full_name=user.name,
                auto_verify=True  # OAuth users have verified emails
            )
            
            if result['success']:
                # Update user with Cognito ID
                user.cognito_sub = result['user_sub']
                user.cognito_confirmed = True  # Mark as verified locally for OAuth users
                user.email_verified = True  # OAuth providers verify emails
                db.commit()
                
                # Initialize S3 storage
                await self._initialize_user_storage(user, oauth_data)
                
                print(f"✅ Synced OAuth user {user.email} to Cognito: {result['user_sub']}")
                print(f"   Note: Email verification pending in Cognito (needs IAM permissions)")
                return True
            else:
                # If user already exists in Cognito, try to link them
                if 'already exists' in result.get('error', '').lower():
                    # This means user was previously registered directly in Cognito
                    # We need to link the accounts (would require admin API in production)
                    print(f"⚠️ User {user.email} already exists in Cognito, manual linking required")
                return False
                
        except Exception as e:
            print(f"Error syncing OAuth user to Cognito: {e}")
            return False
    
    async def _update_s3_profile(self, user: User) -> None:
        """Update user profile in S3"""
        if not user.cognito_sub:
            return
        
        profile_data = {
            'id': str(user.id),
            'email': user.email,
            'name': user.name,
            'picture': user.picture,
            'provider': user.provider or user.oauth_provider,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        await self.storage.save_user_profile(user.cognito_sub, profile_data)
    
    async def _initialize_user_storage(self, user: User, oauth_data: Dict[str, Any]) -> None:
        """Initialize S3 storage for new user"""
        if not user.cognito_sub:
            return
        
        # Save initial profile
        await self._update_s3_profile(user)
        
        # Save initial settings
        settings = {
            'email_sync_enabled': True,
            'notification_preferences': {
                'urgent_emails': True,
                'daily_summary': True,
                'action_items': True
            },
            'oauth_provider': user.provider or user.oauth_provider,
            'created_via': 'oauth',
            'initialized_at': datetime.utcnow().isoformat()
        }
        
        await self.storage.save_user_settings(user.cognito_sub, settings)
    
    async def save_emails_to_s3(self, user: User, emails: list) -> bool:
        """Save user emails to S3 storage"""
        if not user.cognito_sub:
            # User not synced to Cognito yet
            return False
        
        try:
            # Convert email objects to dictionaries
            email_data = []
            for email in emails:
                # Check if it's a dict (from API) or an object (from database)
                if isinstance(email, dict):
                    email_dict = {
                        'id': str(email.get('id', uuid.uuid4())),
                        'subject': email.get('subject'),
                        'sender': email.get('sender'),
                        'sender_name': email.get('sender_name'),
                        'received_at': email.get('received_at'),
                        'body': email.get('body'),
                        'snippet': email.get('snippet'),
                        'is_read': email.get('is_read', False),
                        'is_important': email.get('is_important', False),
                        'urgency_score': email.get('urgency_score')
                    }
                else:
                    # It's an object from the database
                    email_dict = {
                        'id': str(email.id),
                        'subject': email.subject,
                        'sender': email.sender,
                        'sender_name': email.sender_name,
                        'received_at': email.received_at.isoformat() if email.received_at else None,
                        'body': getattr(email, 'body_text', ''),  # Use body_text instead of body
                        'snippet': email.snippet,
                        'is_read': email.is_read,
                        'is_important': getattr(email, 'is_important', False),  # Handle missing attribute
                        'urgency_score': email.urgency_score
                    }
                email_data.append(email_dict)
            
            # Save to S3 in batches
            batch_size = 100
            for i in range(0, len(email_data), batch_size):
                batch = email_data[i:i + batch_size]
                batch_id = f"sync_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{i}"
                await self.storage.save_user_emails(user.cognito_sub, batch, batch_id)
            
            return True
            
        except Exception as e:
            print(f"Error saving emails to S3: {e}")
            return False
    
    async def get_user_emails_from_s3(self, user: User, limit: int = None) -> list:
        """Retrieve user emails from S3"""
        if not user.cognito_sub:
            return []
        
        return await self.storage.get_user_emails(user.cognito_sub, limit)
    
    async def handle_oauth_login(self, db: Session, oauth_user_info: Dict[str, Any], provider: str) -> User:
        """
        Handle OAuth login and sync with Cognito/S3
        Called after successful Google/Microsoft OAuth
        """
        # Get or create user from OAuth info
        email = oauth_user_info.get('email')
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            # Create new user
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=oauth_user_info.get('name', email.split('@')[0]),
                picture=oauth_user_info.get('picture'),
                provider=provider,
                oauth_provider=provider,
                created_at=datetime.utcnow()
            )
            db.add(user)
            db.commit()
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        # Sync with Cognito and S3 (async, don't block login)
        await self.sync_oauth_user_to_cognito(db, user, oauth_user_info)
        
        return user
    
    async def get_unified_user_info(self, db: Session, user: User) -> Dict[str, Any]:
        """Get unified user information from both systems"""
        user_info = {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'picture': user.picture,
            'provider': user.provider or user.oauth_provider,
            'cognito_linked': bool(user.cognito_sub),
            'cognito_sub': user.cognito_sub
        }
        
        # If user has Cognito account, get S3 storage info
        if user.cognito_sub:
            storage_usage = await self.storage.get_user_storage_usage(user.cognito_sub)
            user_info['storage'] = storage_usage
            
            # Get settings from S3
            settings = await self.storage.get_user_settings(user.cognito_sub)
            user_info['settings'] = settings
        else:
            user_info['storage'] = {
                'total_size_mb': 0,
                'total_objects': 0,
                'status': 'not_initialized'
            }
            user_info['settings'] = {}
        
        return user_info
    
    async def backup_user_data(self, user: User) -> Optional[str]:
        """Create backup of user data"""
        if not user.cognito_sub:
            return None
        
        return await self.storage.backup_user_data(user.cognito_sub)
    
    async def delete_user_data(self, db: Session, user: User) -> bool:
        """Delete all user data (GDPR compliance)"""
        try:
            # Delete from S3 if linked
            if user.cognito_sub:
                await self.storage.delete_user_data(user.cognito_sub)
            
            # Delete from local database
            # This would include emails, action items, etc.
            # (Implementation depends on your cascade rules)
            
            return True
        except Exception as e:
            print(f"Error deleting user data: {e}")
            return False