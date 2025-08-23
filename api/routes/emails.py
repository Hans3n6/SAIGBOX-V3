from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from api.auth import get_current_user
from api.models import *
from core.database import get_db, User, Email as EmailModel
from core.gmail_service import GmailService
from core.token_manager import token_manager

router = APIRouter()
gmail_service = GmailService()

@router.get("/", response_model=EmailListResponse)
async def list_emails(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List emails with pagination and search"""
    query = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.is_(None)
    )
    
    # Apply search filter
    if search:
        query = query.filter(
            (EmailModel.subject.contains(search)) |
            (EmailModel.sender.contains(search)) |
            (EmailModel.body_text.contains(search))
        )
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    emails = query.order_by(EmailModel.received_at.desc()).offset(offset).limit(limit).all()
    
    # Calculate pagination info
    pages = (total + limit - 1) // limit
    
    return EmailListResponse(
        emails=emails,
        total=total,
        page=page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1
    )

@router.get("/{email_id}", response_model=Email)
async def get_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get email details"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    return email

@router.put("/{email_id}/read")
async def mark_as_read(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark email as read"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Update in Gmail
    if email.gmail_id and not email.is_read:
        success = gmail_service.mark_as_read(current_user, email.gmail_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update Gmail")
    
    # Update in database
    email.is_read = True
    db.commit()
    
    return {"success": True, "message": "Email marked as read"}

@router.put("/{email_id}/unread")
async def mark_as_unread(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark email as unread"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Update in Gmail
    if email.gmail_id and email.is_read:
        success = gmail_service.mark_as_unread(current_user, email.gmail_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update Gmail")
    
    # Update in database
    email.is_read = False
    db.commit()
    
    return {"success": True, "message": "Email marked as unread"}

@router.put("/{email_id}/star")
async def star_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Star/unstar email"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Toggle star status
    new_status = not email.is_starred
    
    # Update in Gmail
    if email.gmail_id:
        if new_status:
            success = gmail_service.star_email(current_user, email.gmail_id)
        else:
            success = gmail_service.unstar_email(current_user, email.gmail_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update Gmail")
    
    # Update in database
    email.is_starred = new_status
    db.commit()
    
    return {
        "success": True,
        "message": f"Email {'starred' if new_status else 'unstarred'}",
        "is_starred": new_status
    }

@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Move email to trash"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.is_(None)
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Move to trash in Gmail
    if email.gmail_id:
        success = gmail_service.move_to_trash(current_user, email.gmail_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to trash email in Gmail")
    
    # Soft delete in database
    email.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "message": "Email moved to trash"}

@router.post("/compose", response_model=dict)
async def compose_email(
    email_data: EmailCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a new email"""
    try:
        # Send via Gmail
        result = gmail_service.send_email(
            current_user,
            email_data.to,
            email_data.subject,
            email_data.body,
            email_data.cc,
            email_data.bcc
        )
        
        # Save to database
        new_email = EmailModel(
            user_id=current_user.id,
            gmail_id=result.get('id'),
            subject=email_data.subject,
            sender=current_user.email,
            recipients=email_data.to,
            cc=email_data.cc or [],
            bcc=email_data.bcc or [],
            body_text=email_data.body,
            is_read=True,
            received_at=datetime.utcnow()
        )
        db.add(new_email)
        db.commit()
        
        return {
            "success": True,
            "message": "Email sent successfully",
            "email_id": new_email.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reply", response_model=dict)
async def reply_to_email(
    reply_data: EmailReply,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reply to an email"""
    # Get original email
    original = db.query(EmailModel).filter(
        EmailModel.id == reply_data.email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not original:
        raise HTTPException(status_code=404, detail="Original email not found")
    
    # Prepare reply
    to = [original.sender]
    if reply_data.reply_all and original.recipients:
        to.extend([r for r in original.recipients if r != current_user.email])
    
    subject = original.subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    
    try:
        # Send via Gmail
        result = gmail_service.send_email(
            current_user,
            to,
            subject,
            reply_data.body
        )
        
        return {
            "success": True,
            "message": "Reply sent successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search", response_model=List[Email])
async def search_emails(
    search_query: SearchQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search emails"""
    query = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.is_(None)
    )
    
    # Build search conditions
    conditions = []
    if search_query.in_subject:
        conditions.append(EmailModel.subject.contains(search_query.query))
    if search_query.in_body:
        conditions.append(EmailModel.body_text.contains(search_query.query))
    if search_query.in_sender:
        conditions.append(EmailModel.sender.contains(search_query.query))
    
    if conditions:
        from sqlalchemy import or_
        query = query.filter(or_(*conditions))
    
    emails = query.order_by(EmailModel.received_at.desc()).limit(50).all()
    
    return emails