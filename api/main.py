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

from api.auth import get_current_user, get_or_create_user, create_access_token
from api.models import *
from api.routes import emails, actions, huddles, trash, saig
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
async def root():
    """Serve the main application"""
    try:
        with open("static/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>SAIGBOX V3</h1><p>Please create static/index.html</p>")

@app.get("/auth/login")
async def login():
    """Redirect to Gmail OAuth"""
    auth_url = gmail_service.get_auth_url()
    return RedirectResponse(url=auth_url)

@app.get("/auth/callback")
async def auth_callback(code: str, db: Session = Depends(get_db)):
    """Handle OAuth callback"""
    try:
        # Exchange code for tokens
        tokens = gmail_service.exchange_code(code)
        
        # Get user info from token
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        credentials = Credentials(
            token=tokens['access_token'],
            refresh_token=tokens.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=gmail_service.client_id,
            client_secret=gmail_service.client_secret
        )
        
        # Get user email from Gmail API
        service = build('gmail', 'v1', credentials=credentials)
        profile = service.users().getProfile(userId='me').execute()
        email = profile['emailAddress']
        
        # Get or create user
        user = get_or_create_user(db, email, email)
        
        # Update tokens
        user.access_token = tokens['access_token']
        user.refresh_token = tokens.get('refresh_token')
        if tokens.get('token_expiry'):
            user.token_expiry = datetime.fromisoformat(tokens['token_expiry'])
        
        db.commit()
        
        # Create JWT token
        access_token = create_access_token(data={"sub": user.email})
        
        # Redirect to app with token
        return RedirectResponse(url=f"/?token={access_token}")
        
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        # Try to handle scope change error gracefully
        if "Scope has changed" in str(e):
            # Re-initiate auth flow with correct scopes
            return RedirectResponse(url="/auth/login")
        return RedirectResponse(url=f"/?error={str(e)}")

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