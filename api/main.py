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
from api.routes import emails, actions, huddles, trash, saig, intelligence, urgent, cognito_auth, user, dashboard, sales_dashboard, prospecting
from api.middleware import AuthMiddleware
from core.database import get_db, User, Email
from core.gmail_service import GmailService
from core.outlook_service import OutlookService
from core.unified_auth import UnifiedAuthService
from core.background_sync import background_sync

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

# CORS middleware - using FastAPI's built-in CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://saigbox.com",
        "https://www.saigbox.com",  # Added www subdomain
        "https://api.saigbox.com",
        "http://localhost:3000",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(dashboard.router, tags=["dashboard"])  # Note: prefix is in the router
app.include_router(sales_dashboard.router, tags=["sales-dashboard"])  # Note: prefix is in the router
app.include_router(emails.router, prefix="/api/emails", tags=["emails"])
app.include_router(actions.router, prefix="/api/actions", tags=["actions"])
app.include_router(huddles.router, prefix="/api/huddles", tags=["huddles"])
app.include_router(trash.router, prefix="/api/trash", tags=["trash"])
app.include_router(saig.router, prefix="/api/saig", tags=["saig"])
app.include_router(intelligence.router, prefix="/api/intelligence", tags=["intelligence"])
app.include_router(urgent.router, prefix="/api/urgent", tags=["urgent"])
app.include_router(cognito_auth.router, tags=["cognito-auth"])  # Note: prefix is in the router
app.include_router(user.router, tags=["user"])  # Note: prefix is in the router
app.include_router(prospecting.router, tags=["prospecting"])  # Note: prefix is in the router

# Email service instances
gmail_service = GmailService()
outlook_service = OutlookService()
unified_auth = UnifiedAuthService()

# Background sync task - uses the background_sync service
async def sync_emails_background():
    """Background task to sync emails for all active users"""
    await background_sync.start_background_loop()

@app.on_event("startup")
async def startup_event():
    """Start background tasks on app startup"""
    asyncio.create_task(sync_emails_background())
    logger.info("SAIGBOX V3 started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on app shutdown"""
    background_sync.stop()
    logger.info("SAIGBOX V3 shutdown complete")

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
    """Demo login - uses test user with sample farm equipment emails"""
    demo_email = "testuser@demo.saigbox.com"

    # Find existing test user (created by create_farm_equipment_demo.py script)
    demo_user = db.query(User).filter(User.email == demo_email).first()

    if not demo_user:
        # Fall back to creating a demo user if test data not loaded
        demo_user = get_or_create_user(db, demo_email, "Jake Morrison", provider="demo")

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

@app.post("/api/auth/test")
async def test_login(db: Session = Depends(get_db)):
    """Test login with pre-populated sample data (12 emails, 4 action items)"""
    test_email = "testuser@demo.saigbox.com"

    # Find existing test user (created by create_test_data.py script)
    test_user = db.query(User).filter(User.email == test_email).first()

    if not test_user:
        # Create test user if not exists
        test_user = get_or_create_user(db, test_email, "Test User", provider="demo")

    # Create both access and refresh tokens
    access_token = create_access_token(data={"sub": test_email})
    refresh_token = create_refresh_token(data={"sub": test_email})

    # Get counts for info
    from core.database import Email as EmailModel, ActionItem
    email_count = db.query(EmailModel).filter(EmailModel.user_id == test_user.id).count()
    action_count = db.query(ActionItem).filter(ActionItem.user_id == test_user.id).count()

    response = JSONResponse(content={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "email": test_user.email,
            "name": test_user.name
        },
        "test_data": {
            "emails": email_count,
            "action_items": action_count,
            "note": "Run 'python scripts/create_test_data.py' to populate test data"
        }
    })

    # Set cookie for session
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400
    )

    return response

@app.get("/api/auth/google/callback")
async def google_auth_callback(
    request: Request,
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
        
        # Sync with Cognito and S3 (async, non-blocking)
        asyncio.create_task(unified_auth.handle_oauth_login(db, user_info, "google"))
        
        # Trigger initial email sync
        try:
            logger.info(f"Starting initial email sync for user {user.email}")
            result = gmail_service.fetch_emails(db, user, max_results=100)
            logger.info(f"Initial sync completed: {len(result['emails'])} emails fetched")
            
            # Save emails to S3 if user has Cognito account
            if user.cognito_sub:
                asyncio.create_task(unified_auth.save_emails_to_s3(user, result['emails']))
        except Exception as sync_error:
            logger.error(f"Initial sync failed: {sync_error}")
            # Don't fail the login if sync fails
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(data={"sub": user.email})
        
        # Redirect to the appropriate frontend URL based on environment
        redirect_url = "/" if "localhost" in str(request.url) else "https://api.saigbox.com/"
        response = RedirectResponse(url=redirect_url)
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
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Handle Microsoft OAuth callback"""
    try:
        # Check for OAuth errors
        if error:
            logger.error(f"Microsoft OAuth error: {error} - {error_description}")
            return RedirectResponse(url=f"/login?error={error}&description={error_description or ''}")
        
        # Check for required parameters
        if not code or not state:
            logger.error(f"Missing required parameters - code: {code}, state: {state}")
            return RedirectResponse(url="/login?error=missing_parameters")
        
        # State verification is handled in exchange_microsoft_code
        
        # Exchange code for tokens
        tokens = await exchange_microsoft_code(code, state)
        
        # Get user info
        user_info = await get_microsoft_user_info(tokens['access_token'])
        
        # Create or update user - use normalized fields
        user = get_or_create_user(
            db,
            email=user_info.get('email'),  # This is already normalized by oauth_config
            name=user_info.get('name'),
            picture=user_info.get('picture'),
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
        
        # Sync with Cognito and S3 (async, non-blocking)
        asyncio.create_task(unified_auth.handle_oauth_login(db, user_info, "microsoft"))
        
        # Trigger initial email sync
        try:
            logger.info(f"Starting initial email sync for user {user.email}")
            result = await outlook_service.fetch_emails(db, user, max_results=100)
            logger.info(f"Initial sync completed: {len(result.get('emails', []))} emails fetched")
            
            # Save emails to S3 if user has Cognito account
            if user.cognito_sub:
                asyncio.create_task(unified_auth.save_emails_to_s3(user, result.get('emails', [])))
        except Exception as sync_error:
            logger.error(f"Initial sync failed: {sync_error}")
            # Don't fail the login if sync fails
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(data={"sub": user.email})
        
        # Redirect to the appropriate frontend URL based on environment
        redirect_url = "/" if "localhost" in str(request.url) else "https://api.saigbox.com/"
        response = RedirectResponse(url=redirect_url)
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

# Full sync removed - using only incremental sync

@app.post("/api/emails/sync")
async def trigger_sync(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger email sync with pagination and fallback support"""
    try:
        # Parse request body if JSON
        body = {}
        content_type = request.headers.get('content-type', '')
        if 'application/json' in content_type:
            try:
                body = await request.json()
            except (ValueError, TypeError):
                body = {}
        
        max_results = body.get('max_results', 50)
        page_token = body.get('page_token', None)
        logger.info(f"Sync request from {current_user.email}: max_results={max_results}, page_token={page_token}")
        
        # Determine which email service to use based on user's provider
        email_service = gmail_service  # Default to Gmail
        if current_user.provider == 'microsoft':
            email_service = outlook_service
            logger.info(f"Using Outlook service for {current_user.email}")
        else:
            logger.info(f"Using Gmail service for {current_user.email}")
        
        # Store page tokens in session for continuous fetching
        if not hasattr(app.state, 'email_tokens'):
            app.state.email_tokens = {}
        
        user_token_key = current_user.email
        
        # Use provided page token or get from session
        token = page_token or app.state.email_tokens.get(user_token_key)
        
        # Fetch emails with fallback support
        result = email_service.fetch_emails(db, current_user, max_results=max_results, page_token=token)
        
        # Check if fallback was used
        if result.get('fallback') or result.get('cached'):
            logger.warning(f"Sync used fallback mode for user {current_user.email}")
            # Still return success but indicate fallback
            return {
                "success": True,
                "emails_synced": len(result.get('emails', [])),
                "has_more": False,
                "fallback": True,
                "message": result.get('message', 'Sync completed with fallback')
            }
        
        # Store next page token for continuous fetching
        if result.get('next_page_token'):
            app.state.email_tokens[user_token_key] = result['next_page_token']
        else:
            # Clear token if no more pages
            app.state.email_tokens.pop(user_token_key, None)
        
        # Check for partial failures
        failed_count = result.get('failed', 0)
        if failed_count > 0:
            logger.warning(f"Sync had {failed_count} failed emails for user {current_user.email}")
        
        synced_count = len(result.get('emails', []))
        logger.info(f"Sync completed for {current_user.email}: {synced_count} emails synced, has_more={bool(result.get('next_page_token'))}")
        
        return {
            "success": True,
            "emails_synced": synced_count,
            "has_more": bool(result.get('next_page_token')),
            "failed": failed_count,
            "message": f"Synced {synced_count} emails" + (f" ({failed_count} failed)" if failed_count else "")
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Sync error for user {current_user.email}: {e}")
        # Try fallback sync on any error
        try:
            logger.info("Attempting fallback sync after error")
            fallback_result = gmail_service._fallback_basic_sync(db, current_user)
            return {
                "success": True,
                "emails_synced": len(fallback_result.get('emails', [])),
                "has_more": False,
                "fallback": True,
                "message": "Using cached emails due to sync error"
            }
        except Exception as fallback_error:
            logger.error(f"Fallback sync also failed: {fallback_error}")
            raise HTTPException(status_code=500, detail="Email sync temporarily unavailable")

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