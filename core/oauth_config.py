"""OAuth configuration and provider management"""

import os
import json
import secrets
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv
import httpx
from urllib.parse import urlencode, parse_qs

load_dotenv()


class OAuthProvider(Enum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    APPLE = "apple"
    DEMO = "demo"


@dataclass
class OAuthConfig:
    """OAuth provider configuration"""
    client_id: str
    client_secret: str
    redirect_uri: str
    auth_url: str
    token_url: str
    user_info_url: str
    scopes: list
    name: str
    icon: str


class OAuthStateManager:
    """Manage OAuth state for CSRF protection"""
    
    def __init__(self):
        self.states: Dict[str, Dict[str, Any]] = {}
        self.max_age_minutes = 10
    
    def create_state(self, provider: str, redirect_to: Optional[str] = None) -> str:
        """Create a new state token"""
        state = secrets.token_urlsafe(32)
        self.states[state] = {
            "provider": provider,
            "created_at": datetime.utcnow(),
            "redirect_to": redirect_to,
            "used": False
        }
        self._cleanup_old_states()
        return state
    
    def verify_state(self, state: str, provider: str) -> bool:
        """Verify a state token"""
        if state not in self.states:
            return False
        
        state_data = self.states[state]
        
        # Check if already used
        if state_data["used"]:
            return False
        
        # Check provider matches
        if state_data["provider"] != provider:
            return False
        
        # Check age
        age = datetime.utcnow() - state_data["created_at"]
        if age > timedelta(minutes=self.max_age_minutes):
            del self.states[state]
            return False
        
        # Mark as used
        self.states[state]["used"] = True
        return True
    
    def get_redirect(self, state: str) -> Optional[str]:
        """Get redirect URL for state"""
        if state in self.states:
            return self.states[state].get("redirect_to")
        return None
    
    def _cleanup_old_states(self):
        """Remove expired states"""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=self.max_age_minutes)
        
        expired = [
            state for state, data in self.states.items()
            if data["created_at"] < cutoff
        ]
        
        for state in expired:
            del self.states[state]


class OAuthManager:
    """Manage OAuth providers and authentication flow"""
    
    def __init__(self):
        self.state_manager = OAuthStateManager()
        self.providers = self._initialize_providers()
    
    def _initialize_providers(self) -> Dict[str, OAuthConfig]:
        """Initialize OAuth provider configurations"""
        providers = {}
        
        # Google OAuth
        if os.getenv("GMAIL_CLIENT_ID"):
            providers[OAuthProvider.GOOGLE.value] = OAuthConfig(
                client_id=os.getenv("GMAIL_CLIENT_ID"),
                client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
                redirect_uri=os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"),
                auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
                user_info_url="https://www.googleapis.com/oauth2/v2/userinfo",
                scopes=[
                    "openid",
                    "email",
                    "profile",
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/gmail.compose",
                    "https://www.googleapis.com/auth/gmail.send"
                ],
                name="Google",
                icon="google"
            )
        
        # Microsoft OAuth
        if os.getenv("MICROSOFT_CLIENT_ID"):
            providers[OAuthProvider.MICROSOFT.value] = OAuthConfig(
                client_id=os.getenv("MICROSOFT_CLIENT_ID"),
                client_secret=os.getenv("MICROSOFT_CLIENT_SECRET"),
                redirect_uri=os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/api/auth/microsoft/callback"),
                auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
                user_info_url="https://graph.microsoft.com/v1.0/me",
                scopes=[
                    "openid",
                    "email",
                    "profile",
                    "offline_access",
                    "https://graph.microsoft.com/Mail.ReadWrite",
                    "https://graph.microsoft.com/Mail.Send"
                ],
                name="Microsoft",
                icon="microsoft"
            )
        
        return providers
    
    def get_provider(self, provider_name: str) -> Optional[OAuthConfig]:
        """Get OAuth provider configuration"""
        return self.providers.get(provider_name)
    
    def get_auth_url(self, provider_name: str, redirect_to: Optional[str] = None) -> Optional[str]:
        """Generate OAuth authorization URL"""
        provider = self.get_provider(provider_name)
        if not provider:
            return None
        
        state = self.state_manager.create_state(provider_name, redirect_to)
        
        params = {
            "client_id": provider.client_id,
            "redirect_uri": provider.redirect_uri,
            "response_type": "code",
            "scope": " ".join(provider.scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent"
        }
        
        # Provider-specific parameters
        if provider_name == OAuthProvider.GOOGLE.value:
            params["include_granted_scopes"] = "true"
        
        return f"{provider.auth_url}?{urlencode(params)}"
    
    async def exchange_code(self, provider_name: str, code: str, state: str) -> Optional[Dict]:
        """Exchange authorization code for tokens"""
        # Verify state
        if not self.state_manager.verify_state(state, provider_name):
            raise ValueError("Invalid or expired state")
        
        provider = self.get_provider(provider_name)
        if not provider:
            return None
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                provider.token_url,
                data={
                    "code": code,
                    "client_id": provider.client_id,
                    "client_secret": provider.client_secret,
                    "redirect_uri": provider.redirect_uri,
                    "grant_type": "authorization_code"
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Token exchange failed: {response.text}")
            
            tokens = response.json()
            
            # Get redirect URL if stored
            redirect_to = self.state_manager.get_redirect(state)
            if redirect_to:
                tokens["redirect_to"] = redirect_to
            
            return tokens
    
    async def get_user_info(self, provider_name: str, access_token: str) -> Optional[Dict]:
        """Get user information from OAuth provider"""
        provider = self.get_provider(provider_name)
        if not provider:
            return None
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                provider.user_info_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get user info: {response.text}")
            
            user_info = response.json()
            
            # Normalize user info across providers
            normalized = {
                "provider": provider_name,
                "id": None,
                "email": None,
                "name": None,
                "picture": None,
                "raw": user_info
            }
            
            if provider_name == OAuthProvider.GOOGLE.value:
                normalized.update({
                    "id": user_info.get("id"),
                    "email": user_info.get("email"),
                    "name": user_info.get("name"),
                    "picture": user_info.get("picture")
                })
            elif provider_name == OAuthProvider.MICROSOFT.value:
                normalized.update({
                    "id": user_info.get("id"),
                    "email": user_info.get("mail") or user_info.get("userPrincipalName"),
                    "name": user_info.get("displayName"),
                    "picture": None  # Microsoft doesn't provide picture in basic info
                })
            
            return normalized
    
    async def refresh_token(self, provider_name: str, refresh_token: str) -> Optional[Dict]:
        """Refresh access token using refresh token"""
        provider = self.get_provider(provider_name)
        if not provider:
            return None
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                provider.token_url,
                data={
                    "refresh_token": refresh_token,
                    "client_id": provider.client_id,
                    "client_secret": provider.client_secret,
                    "grant_type": "refresh_token"
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Token refresh failed: {response.text}")
            
            return response.json()
    
    def list_providers(self) -> list:
        """List available OAuth providers"""
        return [
            {
                "name": config.name,
                "id": provider_id,
                "icon": config.icon,
                "available": True
            }
            for provider_id, config in self.providers.items()
        ]


# Global OAuth manager instance
oauth_manager = OAuthManager()