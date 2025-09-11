from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
import logging

from api.auth import get_current_user
from api.models import Email, ActionItem
from core.database import get_db, User, Email as EmailModel, ActionItem as ActionItemModel
from core.urgency_detector import UrgencyDetector
from core.action_optimizer import ActionOptimizer
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/emails")
async def get_urgent_emails(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all urgent emails for the current user"""
    try:
        # Get urgent emails from database
        urgent_emails = db.query(EmailModel).filter(
            EmailModel.user_id == current_user.id,
            EmailModel.is_urgent == True,
            EmailModel.deleted_at.is_(None)
        ).order_by(EmailModel.received_at.desc()).all()
        
        # Convert to Pydantic models
        result = []
        for email in urgent_emails:
            try:
                email_model = Email.model_validate(email)
                result.append(email_model)
            except Exception as e:
                logger.error(f"Error validating email {email.id}: {e}")
                # Fix common issues and retry
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
                try:
                    email_model = Email.model_validate(email)
                    result.append(email_model)
                except:
                    continue
        
        return {
            "count": len(result),
            "emails": result
        }
    except Exception as e:
        logger.error(f"Error getting urgent emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from pydantic import BaseModel

class ProcessEmailsRequest(BaseModel):
    email_ids: List[str] = []

@router.post("/process")
async def process_emails_for_urgency(
    request: ProcessEmailsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Process emails to detect urgency and create action items"""
    try:
        detector = UrgencyDetector(db)
        optimizer = ActionOptimizer(db)
        
        # Get emails to process
        query = db.query(EmailModel).filter(
            EmailModel.user_id == current_user.id,
            EmailModel.deleted_at.is_(None)
        )
        
        if request.email_ids:
            query = query.filter(EmailModel.id.in_(request.email_ids))
        else:
            # Process recent emails that haven't been checked
            query = query.filter(EmailModel.urgency_score == 0)
        
        emails = query.limit(100).all()  # Process max 100 at a time
        
        urgent_count = 0
        action_count = 0
        
        for email in emails:
            # Check urgency
            is_urgent, score, reason = detector.should_mark_urgent(email, current_user)
            
            if is_urgent and not email.is_urgent:
                email.is_urgent = True
                email.urgency_score = score
                email.urgency_reason = reason
                urgent_count += 1
                
                # Try to create action items for urgent emails
                try:
                    sender_context = await optimizer.get_sender_context(email.sender, current_user.id)
                    action_data = await optimizer.smart_extract_action(
                        email, 
                        sender_context,
                        current_user
                    )
                    
                    if action_data and action_data['confidence'] >= 50:
                        # Check if action item already exists
                        existing = db.query(ActionItemModel).filter(
                            ActionItemModel.email_id == email.id
                        ).first()
                        
                        if not existing:
                            action = ActionItemModel(
                                id=str(uuid.uuid4()),
                                user_id=current_user.id,
                                email_id=email.id,
                                title=action_data['title'],
                                description=action_data['description'],
                                due_date=action_data.get('due_date'),
                                priority=action_data.get('priority', 2),
                                status='pending',
                                auto_created=True,
                                confidence_score=action_data['confidence'],
                                source_quote=action_data.get('source_quote'),
                                created_at=datetime.utcnow()
                            )
                            db.add(action)
                            action_count += 1
                except Exception as e:
                    logger.error(f"Error creating action item for email {email.id}: {e}")
        
        db.commit()
        
        return {
            "success": True,
            "processed": len(emails),
            "urgent_marked": urgent_count,
            "actions_created": action_count
        }
    except Exception as e:
        logger.error(f"Error processing emails for urgency: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_urgency_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get urgency statistics for the current user"""
    try:
        total_emails = db.query(EmailModel).filter(
            EmailModel.user_id == current_user.id,
            EmailModel.deleted_at.is_(None)
        ).count()
        
        urgent_emails = db.query(EmailModel).filter(
            EmailModel.user_id == current_user.id,
            EmailModel.is_urgent == True,
            EmailModel.deleted_at.is_(None)
        ).count()
        
        pending_actions = db.query(ActionItemModel).filter(
            ActionItemModel.user_id == current_user.id,
            ActionItemModel.status == 'pending'
        ).count()
        
        return {
            "total_emails": total_emails,
            "urgent_emails": urgent_emails,
            "pending_actions": pending_actions,
            "urgency_rate": round((urgent_emails / total_emails * 100) if total_emails > 0 else 0, 1)
        }
    except Exception as e:
        logger.error(f"Error getting urgency stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))