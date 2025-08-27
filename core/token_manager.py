"""Token management and refresh service"""

import os
import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import Session
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from core.database import User

logger = logging.getLogger(__name__)


class TokenManager:
    """Manage OAuth tokens and handle refresh"""
    
    def __init__(self):
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GMAIL_CLIENT_ID")
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("GMAIL_CLIENT_SECRET")
        self.microsoft_client_id = os.getenv("MICROSOFT_CLIENT_ID")
        self.microsoft_client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
    
    def check_and_refresh_tokens(self, db: Session, user: User) -> bool:
        """Check if tokens are expired and refresh if needed"""
        try:
            # Check which provider the user is using
            if user.oauth_provider == "google":
                return self._refresh_google_tokens(db, user)
            elif user.oauth_provider == "microsoft":
                return self._refresh_microsoft_tokens(db, user)
            else:
                logger.warning(f"Unknown OAuth provider for user {user.email}")
                return False
        except Exception as e:
            logger.error(f"Error refreshing tokens for user {user.email}: {e}")
            return False
    
    def _refresh_google_tokens(self, db: Session, user: User) -> bool:
        """Refresh Google OAuth tokens"""
        try:
            # Check if token is expired or will expire soon
            if user.oauth_token_expires:
                time_until_expiry = user.oauth_token_expires - datetime.utcnow()
                if time_until_expiry > timedelta(minutes=5):
                    # Token is still valid
                    return True
            
            if not user.oauth_refresh_token:
                logger.error(f"No refresh token for user {user.email}")
                return False
            
            # Create credentials object
            credentials = Credentials(
                token=user.oauth_access_token,
                refresh_token=user.oauth_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.google_client_id,
                client_secret=self.google_client_secret
            )
            
            # Refresh the token
            credentials.refresh(Request())
            
            # Update user tokens
            user.oauth_access_token = credentials.token
            user.oauth_token_expires = credentials.expiry
            db.commit()
            
            logger.info(f"Successfully refreshed Google tokens for user {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh Google tokens for user {user.email}: {e}")
            return False
    
    async def _refresh_microsoft_tokens(self, db: Session, user: User) -> bool:
        """Refresh Microsoft OAuth tokens"""
        try:
            # Check if token is expired or will expire soon
            if user.oauth_token_expires:
                time_until_expiry = user.oauth_token_expires - datetime.utcnow()
                if time_until_expiry > timedelta(minutes=5):
                    # Token is still valid
                    return True
            
            if not user.oauth_refresh_token:
                logger.error(f"No refresh token for user {user.email}")
                return False
            
            # Refresh Microsoft token
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": user.oauth_refresh_token,
                        "client_id": self.microsoft_client_id,
                        "client_secret": self.microsoft_client_secret,
                        "scope": "openid email profile offline_access https://graph.microsoft.com/Mail.ReadWrite"
                    }
                )
                
                if response.status_code == 200:
                    tokens = response.json()
                    
                    # Update user tokens
                    user.oauth_access_token = tokens['access_token']
                    if 'refresh_token' in tokens:
                        user.oauth_refresh_token = tokens['refresh_token']
                    
                    # Calculate expiry time
                    expires_in = tokens.get('expires_in', 3600)
                    user.oauth_token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
                    
                    db.commit()
                    
                    logger.info(f"Successfully refreshed Microsoft tokens for user {user.email}")
                    return True
                else:
                    logger.error(f"Failed to refresh Microsoft tokens: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to refresh Microsoft tokens for user {user.email}: {e}")
            return False
    
    def is_token_valid(self, user: User) -> bool:
        """Check if user's token is still valid"""
        if not user.oauth_access_token:
            return False
        
        if user.oauth_token_expires:
            # Check if token has expired
            if datetime.utcnow() >= user.oauth_token_expires:
                return False
        
        return True
    
    def get_valid_token(self, db: Session, user: User) -> Optional[str]:
        """Get a valid access token, refreshing if necessary"""
        if self.is_token_valid(user):
            return user.oauth_access_token
        
        # Try to refresh
        if self.check_and_refresh_tokens(db, user):
            return user.oauth_access_token
        
        return None


# Global token manager instance
token_manager = TokenManager()