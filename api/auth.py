from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import os
import secrets
import httpx
from urllib.parse import urlencode
import json
from dotenv import load_dotenv

from core.database import get_db, User
from core.oauth_config import oauth_manager, OAuthProvider
from api.models import TokenData

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# Google OAuth settings
GOOGLE_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

# Microsoft OAuth settings (optional)
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/api/auth/microsoft/callback")

# OAuth state storage (in production, use Redis or database)
oauth_states = {}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        return email
    except JWTError:
        return None

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Try to get token from Authorization header first
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # If no Authorization header, try cookie
    if not token:
        token = request.cookies.get("access_token")
    
    # If still no token, raise exception
    if not token:
        raise credentials_exception
    
    email = verify_token(token)
    if email is None:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    
    return user

def get_or_create_user(db: Session, email: str, name: Optional[str] = None, 
                       picture: Optional[str] = None, provider: Optional[str] = None) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email, 
            name=name,
            picture=picture,
            provider=provider,
            created_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update user info if changed
        if name and user.name != name:
            user.name = name
        if picture and user.picture != picture:
            user.picture = picture
        user.last_login = datetime.utcnow()
        db.commit()
    return user

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_refresh_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        email: str = payload.get("sub")
        if email is None:
            return None
        return email
    except JWTError:
        return None

def generate_oauth_state() -> str:
    """Generate a secure random state for OAuth"""
    state = secrets.token_urlsafe(32)
    oauth_states[state] = {
        "created_at": datetime.utcnow(),
        "used": False
    }
    # Clean up old states (older than 10 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    for key in list(oauth_states.keys()):
        if oauth_states[key]["created_at"] < cutoff:
            del oauth_states[key]
    return state

def verify_oauth_state(state: str) -> bool:
    """Verify OAuth state to prevent CSRF"""
    if state not in oauth_states:
        return False
    state_data = oauth_states[state]
    if state_data["used"]:
        return False
    if datetime.utcnow() - state_data["created_at"] > timedelta(minutes=10):
        del oauth_states[state]
        return False
    oauth_states[state]["used"] = True
    return True

def get_google_oauth_url() -> str:
    """Generate Google OAuth URL"""
    url = oauth_manager.get_auth_url(OAuthProvider.GOOGLE.value)
    if not url:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    return url

def get_microsoft_oauth_url() -> str:
    """Generate Microsoft OAuth URL"""
    url = oauth_manager.get_auth_url(OAuthProvider.MICROSOFT.value)
    if not url:
        raise HTTPException(status_code=500, detail="Microsoft OAuth not configured")
    return url

async def exchange_google_code(code: str, state: str) -> Dict:
    """Exchange authorization code for tokens"""
    tokens = await oauth_manager.exchange_code(OAuthProvider.GOOGLE.value, code, state)
    if not tokens:
        raise HTTPException(status_code=400, detail="Failed to exchange code for tokens")
    return tokens

async def exchange_microsoft_code(code: str, state: str) -> Dict:
    """Exchange Microsoft authorization code for tokens"""
    tokens = await oauth_manager.exchange_code(OAuthProvider.MICROSOFT.value, code, state)
    if not tokens:
        raise HTTPException(status_code=400, detail="Failed to exchange code for tokens")
    return tokens

async def get_google_user_info(access_token: str) -> Dict:
    """Get user info from Google"""
    user_info = await oauth_manager.get_user_info(OAuthProvider.GOOGLE.value, access_token)
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to get user info")
    return user_info

async def get_microsoft_user_info(access_token: str) -> Dict:
    """Get user info from Microsoft"""
    user_info = await oauth_manager.get_user_info(OAuthProvider.MICROSOFT.value, access_token)
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to get user info")
    return user_info

def store_oauth_tokens(db: Session, user_id: str, provider: str, 
                      access_token: str, refresh_token: Optional[str] = None,
                      expires_in: Optional[int] = None):
    """Store OAuth tokens securely in database"""
    # In production, encrypt these tokens before storing
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.oauth_provider = provider
        user.oauth_access_token = access_token
        if refresh_token:
            user.oauth_refresh_token = refresh_token
        if expires_in:
            user.oauth_token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
        db.commit()

async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None"""
    # Check for token in Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        email = verify_token(token)
        if email:
            return db.query(User).filter(User.email == email).first()
    
    # Check for token in cookie
    token = request.cookies.get("access_token")
    if token:
        email = verify_token(token)
        if email:
            return db.query(User).filter(User.email == email).first()
    
    return None