from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import asyncio
import logging
import os

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.auth import (get_current_user, get_or_create_user, create_access_token,
                      get_current_user_optional, get_google_oauth_url, 
                      get_microsoft_oauth_url, exchange_google_code,
                      exchange_microsoft_code, get_google_user_info,
                      get_microsoft_user_info, verify_oauth_state,
                      store_oauth_tokens, create_refresh_token)
from api.models import *
from api.routes import emails, actions, huddles, trash, saig
from api.middleware import AuthMiddleware
from core.database import get_db, User, Email
from core.gmail_service import GmailService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SAIGBOX V3",
    description="Email Management Platform with AI Assistant",
    version="3.0.0"
)

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(emails.router, prefix="/api/emails", tags=["emails"])
app.include_router(actions.router, prefix="/api/actions", tags=["actions"])
app.include_router(huddles.router, prefix="/api/huddles", tags=["huddles"])
app.include_router(trash.router, prefix="/api/trash", tags=["trash"])
app.include_router(saig.router, prefix="/api/saig", tags=["saig"])

# Gmail service instance
gmail_service = GmailService()

# Background sync task
async def sync_emails_background():
    """Background task to sync emails every 30 seconds"""
    while True:
        try:
            logger.info("Starting email sync...")
            # This would be implemented with proper user session management
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Sync error: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    """Start background tasks on app startup"""
    asyncio.create_task(sync_emails_background())
    logger.info("SAIGBOX V3 started successfully")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    """Serve the main application or redirect to login"""
    if not current_user:
        return RedirectResponse(url="/login")
    try:
        with open("static/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>SAIGBOX V3</h1><p>Please create static/index.html</p>")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    """Serve the login page"""
    if current_user:
        return RedirectResponse(url="/")
    try:
        with open("static/auth.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        try:
            with open("static/login.html", "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(content="<h1>Login</h1><p>Please create static/auth.html or login.html</p>")

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    """Serve the auth page"""
    if current_user:
        return RedirectResponse(url="/")
    try:
        with open("static/auth.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Authentication</h1><p>Please create static/auth.html</p>")

@app.get("/api/auth/check")
async def check_auth(current_user: Optional[User] = Depends(get_current_user_optional)):
    """Check if user is authenticated"""
    if current_user:
        return {
            "authenticated": True,
            "email": current_user.email,
            "name": current_user.name
        }
    return {"authenticated": False}

@app.get("/api/auth/google/url")
async def get_google_auth_url():
    """Get Google OAuth URL"""
    url = get_google_oauth_url()
    return {"url": url}

@app.get("/api/auth/microsoft/url")
async def get_microsoft_auth_url():
    """Get Microsoft OAuth URL"""
    url = get_microsoft_oauth_url()
    return {"url": url}

@app.post("/api/auth/demo")
async def demo_login(db: Session = Depends(get_db)):
    """Demo login for testing"""
    demo_email = "demo@saigbox.com"
    demo_user = get_or_create_user(db, demo_email, "Demo User", provider="demo")
    
    # Create both access and refresh tokens
    access_token = create_access_token(data={"sub": demo_email})
    refresh_token = create_refresh_token(data={"sub": demo_email})
    
    response = JSONResponse(content={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "email": demo_user.email,
            "name": demo_user.name
        }
    })
    
    # Set cookie for session
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=86400  # 1 day
    )
    
    return response

@app.get("/api/auth/google/callback")
async def google_auth_callback(
    code: str, 
    state: str,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback"""
    try:
        # State verification is handled in exchange_google_code
        
        # Exchange code for tokens
        tokens = await exchange_google_code(code, state)
        
        # Get user info
        user_info = await get_google_user_info(tokens['access_token'])
        
        # Create or update user
        user = get_or_create_user(
            db, 
            email=user_info['email'],
            name=user_info.get('name'),
            picture=user_info.get('picture'),
            provider="google"
        )
        
        # Store OAuth tokens
        store_oauth_tokens(
            db,
            user.id,
            "google",
            tokens['access_token'],
            tokens.get('refresh_token'),
            tokens.get('expires_in')
        )
        
        # Trigger initial email sync
        try:
            logger.info(f"Starting initial email sync for user {user.email}")
            result = gmail_service.fetch_emails(db, user, max_results=50)
            logger.info(f"Initial sync completed: {len(result['emails'])} emails fetched")
        except Exception as sync_error:
            logger.error(f"Initial sync failed: {sync_error}")
            # Don't fail the login if sync fails
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(data={"sub": user.email})
        
        # Redirect directly to the inbox with authentication cookie set
        response = RedirectResponse(url="https://api.saigbox.com/")
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,  # Use HTTPS in production
            samesite="lax",
            max_age=86400
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,  # Use HTTPS in production
            samesite="lax",
            max_age=2592000  # 30 days
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Google auth callback error: {e}")
        return RedirectResponse(url=f"/login?error=auth_failed")

@app.get("/api/auth/microsoft/callback")
async def microsoft_auth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Handle Microsoft OAuth callback"""
    try:
        # State verification is handled in exchange_microsoft_code
        
        # Exchange code for tokens
        tokens = await exchange_microsoft_code(code, state)
        
        # Get user info
        user_info = await get_microsoft_user_info(tokens['access_token'])
        
        # Create or update user
        user = get_or_create_user(
            db,
            email=user_info.get('mail') or user_info.get('userPrincipalName'),
            name=user_info.get('displayName'),
            provider="microsoft"
        )
        
        # Store OAuth tokens
        store_oauth_tokens(
            db,
            user.id,
            "microsoft",
            tokens['access_token'],
            tokens.get('refresh_token'),
            tokens.get('expires_in')
        )
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(data={"sub": user.email})
        
        # Redirect directly to the inbox with authentication cookie set
        response = RedirectResponse(url="https://api.saigbox.com/")
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,  # Use HTTPS in production
            samesite="lax",
            max_age=86400
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,  # Use HTTPS in production
            samesite="lax",
            max_age=2592000  # 30 days
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Microsoft auth callback error: {e}")
        return RedirectResponse(url=f"/login?error=auth_failed")

@app.post("/api/auth/logout")
async def logout():
    """Logout user"""
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response

@app.post("/api/auth/refresh")
async def refresh_token(
    request: Request,
    db: Session = Depends(get_db)
):
    """Refresh access token"""
    from api.auth import verify_refresh_token
    
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token not found")
    
    email = verify_refresh_token(refresh_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # Create new access token
    access_token = create_access_token(data={"sub": email})
    
    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer"
    })
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400
    )
    
    return response

@app.get("/api/user/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name
    }

@app.post("/api/emails/sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    max_results: int = 50,
    page_token: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger email sync with pagination support"""
    try:
        # Store page tokens in session for continuous fetching
        if not hasattr(app.state, 'gmail_tokens'):
            app.state.gmail_tokens = {}
        
        user_token_key = current_user.email
        
        # Use provided page token or get from session
        token = page_token or app.state.gmail_tokens.get(user_token_key)
        
        # Fetch emails
        result = gmail_service.fetch_emails(db, current_user, max_results=max_results, page_token=token)
        
        # Store next page token for continuous fetching
        if result.get('next_page_token'):
            app.state.gmail_tokens[user_token_key] = result['next_page_token']
        else:
            # Clear token if no more pages
            app.state.gmail_tokens.pop(user_token_key, None)
        
        return {
            "success": True,
            "emails_synced": len(result['emails']),
            "has_more": bool(result.get('next_page_token')),
            "message": f"Synced {len(result['emails'])} emails"
        }
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )