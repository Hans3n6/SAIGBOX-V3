"""
Cognito Authentication API Routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import asyncio

from core.database import get_db, User
from core.cognito_auth import CognitoAuth
from core.user_storage import UserStorageService
from datetime import datetime

router = APIRouter(prefix="/api/auth/cognito", tags=["cognito-auth"])
security = HTTPBearer()

# Initialize services
cognito_service = CognitoAuth()
storage_service = UserStorageService()

# Request models
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ConfirmEmailRequest(BaseModel):
    email: EmailStr
    confirmation_code: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str
    email: EmailStr

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    confirmation_code: str
    new_password: str

@router.post("/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user with Cognito"""
    
    # Check if user already exists in local DB
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user and existing_user.cognito_sub:
        raise HTTPException(status_code=400, detail="User already registered")
    
    # Register with Cognito
    result = await cognito_service.register_user(
        email=request.email,
        password=request.password,
        full_name=request.full_name
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    # Create or update user in local database
    if existing_user:
        existing_user.cognito_sub = result['user_sub']
        existing_user.cognito_confirmed = not result.get('confirmation_required', True)
    else:
        new_user = User(
            email=request.email,
            name=request.full_name or request.email.split('@')[0],
            cognito_sub=result['user_sub'],
            cognito_confirmed=not result.get('confirmation_required', True),
            created_at=datetime.utcnow()
        )
        db.add(new_user)
    
    db.commit()
    
    # Initialize user storage in S3
    await storage_service.save_user_profile(result['user_sub'], {
        'email': request.email,
        'name': request.full_name,
        'created_at': datetime.utcnow().isoformat()
    })
    
    return {
        "message": "Registration successful",
        "confirmation_required": result.get('confirmation_required', False),
        "user_sub": result['user_sub']
    }

@router.post("/confirm-email")
async def confirm_email(request: ConfirmEmailRequest, db: Session = Depends(get_db)):
    """Confirm email with verification code"""
    
    result = await cognito_service.confirm_registration(
        email=request.email,
        confirmation_code=request.confirmation_code
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    # Update user confirmation status in local DB
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        user.cognito_confirmed = True
        db.commit()
    
    return {"message": "Email confirmed successfully"}

@router.post("/login")
async def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Login with Cognito credentials"""
    
    result = await cognito_service.authenticate_user(
        email=request.email,
        password=request.password
    )
    
    if not result['success']:
        if result.get('confirmation_required'):
            raise HTTPException(
                status_code=400,
                detail="Email confirmation required",
                headers={"X-Confirmation-Required": "true"}
            )
        raise HTTPException(status_code=401, detail=result['error'])
    
    # Update user last login in local DB
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        user.last_login = datetime.utcnow()
        user.cognito_access_token = result['access_token']
        user.cognito_refresh_token = result['refresh_token']
        db.commit()
    else:
        # Get user info from token and create local user
        user_info_result = await cognito_service.get_user_info(result['access_token'])
        if user_info_result['success']:
            user_attrs = user_info_result['user']['attributes']
            new_user = User(
                email=request.email,
                name=user_attrs.get('name', request.email.split('@')[0]),
                cognito_sub=user_attrs.get('sub'),
                cognito_confirmed=True,
                cognito_access_token=result['access_token'],
                cognito_refresh_token=result['refresh_token'],
                last_login=datetime.utcnow(),
                created_at=datetime.utcnow()
            )
            db.add(new_user)
            db.commit()
            user = new_user
    
    # Set auth cookie
    response.set_cookie(
        key="cognito_access_token",
        value=result['access_token'],
        httponly=True,
        secure=True,
        samesite='lax',
        max_age=result['expires_in']
    )
    
    return {
        "message": "Login successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        },
        "access_token": result['access_token'],
        "expires_in": result['expires_in']
    }

@router.post("/refresh")
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token"""
    
    result = await cognito_service.refresh_token(
        refresh_token=request.refresh_token,
        email=request.email
    )
    
    if not result['success']:
        raise HTTPException(status_code=401, detail=result['error'])
    
    return {
        "access_token": result['access_token'],
        "expires_in": result['expires_in']
    }

@router.get("/user")
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user information"""
    
    result = await cognito_service.get_user_info(credentials.credentials)
    
    if not result['success']:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_attrs = result['user']['attributes']
    
    # Get user from local DB
    user = db.query(User).filter(User.cognito_sub == user_attrs.get('sub')).first()
    
    # Get storage usage
    storage_usage = await storage_service.get_user_storage_usage(user_attrs.get('sub'))
    
    return {
        "user": {
            "id": user.id if user else None,
            "email": user_attrs.get('email'),
            "name": user_attrs.get('name'),
            "email_verified": user_attrs.get('email_verified') == 'true',
            "sub": user_attrs.get('sub')
        },
        "storage": storage_usage
    }

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Change user password"""
    
    result = await cognito_service.change_password(
        access_token=credentials.credentials,
        old_password=request.old_password,
        new_password=request.new_password
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return {"message": "Password changed successfully"}

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Initiate forgot password flow"""
    
    result = await cognito_service.forgot_password(email=request.email)
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return {"message": "Password reset code sent to email"}

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password with confirmation code"""
    
    result = await cognito_service.reset_password(
        email=request.email,
        confirmation_code=request.confirmation_code,
        new_password=request.new_password
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return {"message": "Password reset successfully"}

@router.post("/logout")
async def logout(
    response: Response,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Logout user"""
    
    # Sign out from Cognito
    await cognito_service.sign_out(credentials.credentials)
    
    # Clear tokens from local DB
    # Get user from token
    user_info = await cognito_service.get_user_info(credentials.credentials)
    if user_info['success']:
        user = db.query(User).filter(
            User.cognito_sub == user_info['user']['attributes'].get('sub')
        ).first()
        if user:
            user.cognito_access_token = None
            user.cognito_refresh_token = None
            db.commit()
    
    # Clear cookie
    response.delete_cookie("cognito_access_token")
    
    return {"message": "Logout successful"}

@router.delete("/delete-account")
async def delete_account(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Delete user account and all associated data"""
    
    # Get user info
    user_info = await cognito_service.get_user_info(credentials.credentials)
    if not user_info['success']:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_sub = user_info['user']['attributes'].get('sub')
    
    # Delete from S3
    await storage_service.delete_user_data(user_sub)
    
    # Delete from local DB
    user = db.query(User).filter(User.cognito_sub == user_sub).first()
    if user:
        db.delete(user)
        db.commit()
    
    # Note: Cognito user deletion requires admin privileges
    # This would typically be done through an admin API or Lambda function
    
    return {"message": "Account deletion initiated"}

@router.get("/backup")
async def create_backup(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a backup of all user data"""
    
    # Get user info
    user_info = await cognito_service.get_user_info(credentials.credentials)
    if not user_info['success']:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_sub = user_info['user']['attributes'].get('sub')
    
    # Create backup
    backup_url = await storage_service.backup_user_data(user_sub)
    
    if not backup_url:
        raise HTTPException(status_code=500, detail="Failed to create backup")
    
    return {
        "message": "Backup created successfully",
        "download_url": backup_url,
        "expires_in": "24 hours"
    }