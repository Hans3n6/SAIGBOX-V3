"""
User API Routes - Unified user management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from api.auth import get_current_user
from core.database import get_db, User
from core.unified_auth import UnifiedAuthService

router = APIRouter(prefix="/api/user", tags=["user"])
unified_auth = UnifiedAuthService()

@router.get("/profile")
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get unified user profile including storage info"""
    user_info = await unified_auth.get_unified_user_info(db, current_user)
    return user_info

@router.get("/storage")
async def get_storage_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's S3 storage usage"""
    if not current_user.cognito_sub:
        # User not synced to Cognito yet, trigger sync
        oauth_data = {
            'email': current_user.email,
            'name': current_user.name,
            'picture': current_user.picture
        }
        await unified_auth.sync_oauth_user_to_cognito(db, current_user, oauth_data)
        db.refresh(current_user)
    
    if current_user.cognito_sub:
        storage_usage = await unified_auth.storage.get_user_storage_usage(current_user.cognito_sub)
        return {
            "status": "active",
            "cognito_id": current_user.cognito_sub,
            **storage_usage
        }
    else:
        return {
            "status": "not_initialized",
            "message": "Storage initialization in progress"
        }

@router.post("/sync-to-cloud")
async def sync_to_cloud(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger sync to Cognito and S3"""
    oauth_data = {
        'email': current_user.email,
        'name': current_user.name,
        'picture': current_user.picture
    }
    
    success = await unified_auth.sync_oauth_user_to_cognito(db, current_user, oauth_data)
    
    if success:
        # Sync existing emails to S3
        from core.database import Email
        emails = db.query(Email).filter(
            Email.user_id == current_user.id,
            Email.deleted_at.is_(None)
        ).limit(500).all()  # Start with recent 500
        
        if emails and current_user.cognito_sub:
            await unified_auth.save_emails_to_s3(current_user, emails)
        
        return {
            "status": "success",
            "message": "User synced to cloud storage",
            "cognito_id": current_user.cognito_sub,
            "emails_synced": len(emails) if emails else 0
        }
    else:
        return {
            "status": "partial",
            "message": "Sync initiated but may require manual verification"
        }

@router.post("/backup")
async def create_backup(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a backup of user data"""
    if not current_user.cognito_sub:
        raise HTTPException(status_code=400, detail="Cloud storage not initialized")
    
    backup_url = await unified_auth.backup_user_data(current_user)
    
    if backup_url:
        return {
            "status": "success",
            "download_url": backup_url,
            "expires_in": "24 hours"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to create backup")

@router.get("/settings")
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user settings from S3"""
    if not current_user.cognito_sub:
        return {
            "email_sync_enabled": True,
            "notification_preferences": {
                "urgent_emails": True,
                "daily_summary": True,
                "action_items": True
            },
            "storage_status": "local_only"
        }
    
    settings = await unified_auth.storage.get_user_settings(current_user.cognito_sub)
    return settings or {
        "email_sync_enabled": True,
        "notification_preferences": {
            "urgent_emails": True,
            "daily_summary": True,
            "action_items": True
        }
    }

@router.post("/settings")
async def update_user_settings(
    settings: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user settings in S3"""
    if not current_user.cognito_sub:
        return {
            "status": "local_only",
            "message": "Settings saved locally, cloud sync pending"
        }
    
    success = await unified_auth.storage.save_user_settings(current_user.cognito_sub, settings)
    
    if success:
        return {
            "status": "success",
            "message": "Settings updated"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to update settings")

@router.delete("/delete-account")
async def delete_account(
    confirm: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete user account and all data (GDPR compliance)"""
    if not confirm:
        raise HTTPException(status_code=400, detail="Please confirm account deletion")
    
    # Create backup first
    backup_url = None
    if current_user.cognito_sub:
        backup_url = await unified_auth.backup_user_data(current_user)
    
    # Delete all data
    success = await unified_auth.delete_user_data(db, current_user)
    
    if success:
        # Delete user from database
        db.delete(current_user)
        db.commit()
        
        return {
            "status": "success",
            "message": "Account deleted successfully",
            "backup_url": backup_url
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to delete account")