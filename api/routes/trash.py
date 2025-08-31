from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta

from api.auth import get_current_user
from api.models import Email, TrashEmptyResponse
from core.database import get_db, User, Email as EmailModel
from core.gmail_service import GmailService

router = APIRouter()
gmail_service = GmailService()

def clean_email_data(emails):
    """Clean email data to ensure lists are not None"""
    for email in emails:
        if email.labels is None:
            email.labels = []
        if email.attachments is None:
            email.attachments = []
        if email.recipients is None:
            email.recipients = []
        if email.cc is None:
            email.cc = []
        if email.bcc is None:
            email.bcc = []
    return emails

@router.get("/", response_model=List[Email])
async def list_trashed_emails(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all emails in trash"""
    emails = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.isnot(None)
    ).order_by(EmailModel.received_at.desc()).all()
    
    # Clean email data to ensure all list fields are not None
    emails = clean_email_data(emails)
    
    return emails

@router.post("/{email_id}/restore")
async def restore_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore email from trash"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.isnot(None)
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Trashed email not found")
    
    # Restore in Gmail
    if email.gmail_id:
        success = gmail_service.restore_from_trash(current_user, email.gmail_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to restore email in Gmail")
    
    # Restore in database
    email.deleted_at = None
    db.commit()
    
    return {"success": True, "message": "Email restored from trash"}

@router.delete("/{email_id}")
async def permanently_delete_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Permanently delete an email"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.isnot(None)
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Trashed email not found")
    
    # Permanently delete from database
    db.delete(email)
    db.commit()
    
    return {"success": True, "message": "Email permanently deleted"}

@router.delete("/empty", response_model=TrashEmptyResponse)
async def empty_trash(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Empty all trash"""
    # Get all trashed emails
    trashed_emails = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.isnot(None)
    ).all()
    
    deleted_count = len(trashed_emails)
    
    # Delete all trashed emails
    for email in trashed_emails:
        db.delete(email)
    
    db.commit()
    
    return TrashEmptyResponse(
        deleted_count=deleted_count,
        success=True,
        message=f"Permanently deleted {deleted_count} email(s)"
    )

@router.post("/auto-clean")
async def auto_clean_trash(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Auto-delete emails that have been in trash for 30+ days"""
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    
    # Find old trashed emails
    old_emails = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.isnot(None),
        EmailModel.deleted_at < cutoff_date
    ).all()
    
    deleted_count = len(old_emails)
    
    # Delete old emails
    for email in old_emails:
        db.delete(email)
    
    db.commit()
    
    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"Auto-cleaned {deleted_count} old email(s) from trash"
    }