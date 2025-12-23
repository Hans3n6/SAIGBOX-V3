from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging

from api.auth import get_current_user
from api.models import *
from core.database import get_db, User, ActionItem as ActionItemModel, Email
from core.action_extractor import action_extractor, ActionableContentChecker

logger = logging.getLogger(__name__)
router = APIRouter()


def build_action_item_response(item: ActionItemModel, email_cache: Dict[str, Email] = None) -> ActionItem:
    """Build ActionItem response with email info"""
    priority_map = {1: "high", 2: "medium", 3: "low"}
    priority_str = priority_map.get(item.priority, "medium")
    status_str = item.status if item.status in ["pending", "completed", "overdue"] else "pending"

    # Get email info if available
    email_subject = None
    email_sender = None
    if item.email_id and email_cache and item.email_id in email_cache:
        email = email_cache[item.email_id]
        email_subject = email.subject
        email_sender = email.sender_name or email.sender

    return ActionItem(
        id=item.id,
        user_id=item.user_id,
        email_id=item.email_id,
        email_subject=email_subject,
        email_sender=email_sender,
        title=item.title,
        description=item.description,
        due_date=item.due_date,
        priority=ActionItemPriority(priority_str),
        status=ActionItemStatus(status_str),
        auto_created=item.auto_created or False,
        confidence_score=item.confidence_score,
        source_quote=item.source_quote,
        created_at=item.created_at,
        completed_at=item.completed_at,
        updated_at=item.updated_at
    )

@router.get("/", response_model=List[ActionItem])
async def list_action_items(
    status: Optional[ActionItemStatus] = None,
    priority: Optional[ActionItemPriority] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List action items with optional filters"""
    query = db.query(ActionItemModel).filter(ActionItemModel.user_id == current_user.id)
    
    if status:
        # Map status to database values
        status_map = {
            ActionItemStatus.PENDING: "pending",
            ActionItemStatus.COMPLETED: "completed",
            ActionItemStatus.OVERDUE: "overdue"
        }
        query = query.filter(ActionItemModel.status == status_map[status])
    
    if priority:
        # Map priority to database values
        priority_map = {
            ActionItemPriority.HIGH: 1,
            ActionItemPriority.MEDIUM: 2,
            ActionItemPriority.LOW: 3
        }
        query = query.filter(ActionItemModel.priority == priority_map[priority])
    
    # Check for overdue items and update status
    now = datetime.utcnow()
    overdue_items = query.filter(
        ActionItemModel.status == "pending",
        ActionItemModel.due_date < now
    ).all()
    
    for item in overdue_items:
        item.status = "overdue"
    
    if overdue_items:
        db.commit()
    
    # Get all items, ordered by email_id to group by email, then by priority
    items = query.order_by(
        ActionItemModel.email_id.desc(),  # Group by email
        ActionItemModel.priority,          # Then by priority
        ActionItemModel.created_at.desc()  # Then by creation date
    ).all()

    # Fetch email info for all related emails
    email_ids = list(set(item.email_id for item in items if item.email_id))
    email_cache = {}
    if email_ids:
        emails = db.query(Email).filter(Email.id.in_(email_ids)).all()
        email_cache = {email.id: email for email in emails}

    # Convert to response model with email info
    result = [build_action_item_response(item, email_cache) for item in items]

    return result

@router.get("/{action_id}", response_model=ActionItem)
async def get_action_item(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get action item details"""
    item = db.query(ActionItemModel).filter(
        ActionItemModel.id == action_id,
        ActionItemModel.user_id == current_user.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")
    
    return ActionItem(
        id=item.id,
        user_id=item.user_id,
        email_id=item.email_id,
        title=item.title,
        description=item.description,
        due_date=item.due_date,
        priority=ActionItemPriority(
            {1: "high", 2: "medium", 3: "low"}.get(item.priority, "medium")
        ),
        status=ActionItemStatus(item.status),
        created_at=item.created_at,
        completed_at=item.completed_at,
        updated_at=item.updated_at
    )

@router.post("/", response_model=ActionItem)
async def create_action_item(
    action_data: ActionItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new action item"""
    # Verify email belongs to user if email_id provided
    if action_data.email_id:
        email = db.query(Email).filter(
            Email.id == action_data.email_id,
            Email.user_id == current_user.id
        ).first()
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
    
    # Map priority to database value
    priority_map = {
        ActionItemPriority.HIGH: 1,
        ActionItemPriority.MEDIUM: 2,
        ActionItemPriority.LOW: 3
    }
    
    # Create action item
    new_item = ActionItemModel(
        user_id=current_user.id,
        email_id=action_data.email_id,
        title=action_data.title,
        description=action_data.description,
        due_date=action_data.due_date,
        priority=priority_map[action_data.priority],
        status="pending"
    )
    
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    
    return ActionItem(
        id=new_item.id,
        user_id=new_item.user_id,
        email_id=new_item.email_id,
        title=new_item.title,
        description=new_item.description,
        due_date=new_item.due_date,
        priority=action_data.priority,
        status=ActionItemStatus.PENDING,
        created_at=new_item.created_at,
        completed_at=new_item.completed_at,
        updated_at=new_item.updated_at
    )

@router.put("/{action_id}", response_model=ActionItem)
async def update_action_item(
    action_id: str,
    update_data: ActionItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an action item"""
    item = db.query(ActionItemModel).filter(
        ActionItemModel.id == action_id,
        ActionItemModel.user_id == current_user.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")
    
    # Update fields if provided
    if update_data.title is not None:
        item.title = update_data.title
    
    if update_data.description is not None:
        item.description = update_data.description
    
    if update_data.due_date is not None:
        item.due_date = update_data.due_date
    
    if update_data.priority is not None:
        priority_map = {
            ActionItemPriority.HIGH: 1,
            ActionItemPriority.MEDIUM: 2,
            ActionItemPriority.LOW: 3
        }
        item.priority = priority_map[update_data.priority]
    
    if update_data.status is not None:
        status_map = {
            ActionItemStatus.PENDING: "pending",
            ActionItemStatus.COMPLETED: "completed",
            ActionItemStatus.OVERDUE: "overdue"
        }
        item.status = status_map[update_data.status]
        
        # Set completed_at if completing
        if update_data.status == ActionItemStatus.COMPLETED:
            item.completed_at = datetime.utcnow()
        else:
            item.completed_at = None
    
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    
    return ActionItem(
        id=item.id,
        user_id=item.user_id,
        email_id=item.email_id,
        title=item.title,
        description=item.description,
        due_date=item.due_date,
        priority=ActionItemPriority(
            {1: "high", 2: "medium", 3: "low"}.get(item.priority, "medium")
        ),
        status=ActionItemStatus(item.status),
        created_at=item.created_at,
        completed_at=item.completed_at,
        updated_at=item.updated_at
    )

@router.delete("/{action_id}")
async def delete_action_item(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an action item"""
    item = db.query(ActionItemModel).filter(
        ActionItemModel.id == action_id,
        ActionItemModel.user_id == current_user.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")
    
    db.delete(item)
    db.commit()
    
    return {"success": True, "message": "Action item deleted"}

@router.post("/extract", response_model=List[ActionItem])
async def extract_action_items(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Extract action items from an email using AI"""
    # Get email
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    # Use AI to extract action items
    created_items = await action_extractor.create_action_items(
        db, email, current_user
    )

    if not created_items:
        # Return empty list - no actionable items found
        return []

    # Convert to response model
    priority_map = {1: ActionItemPriority.HIGH, 2: ActionItemPriority.MEDIUM, 3: ActionItemPriority.LOW}
    status_map = {
        'pending': ActionItemStatus.PENDING,
        'completed': ActionItemStatus.COMPLETED,
        'overdue': ActionItemStatus.OVERDUE
    }

    result = []
    for item in created_items:
        result.append(ActionItem(
            id=item.id,
            user_id=item.user_id,
            email_id=item.email_id,
            title=item.title,
            description=item.description,
            due_date=item.due_date,
            priority=priority_map.get(item.priority, ActionItemPriority.MEDIUM),
            status=status_map.get(item.status, ActionItemStatus.PENDING),
            created_at=item.created_at,
            completed_at=item.completed_at,
            updated_at=item.updated_at
        ))

    return result

@router.post("/extract-all")
async def extract_all_action_items(
    min_score: int = Query(default=2, ge=1, le=10, description="Minimum actionable content score (1-10)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Extract action items from emails with actionable content.

    Uses smart content detection (keywords, questions, deadlines) instead of
    just looking at 'urgent' flag. Adjust min_score for sensitivity:
    - 1: Very sensitive (more emails, more false positives)
    - 2: Balanced (default, good for most cases)
    - 3+: Conservative (fewer emails, higher precision)
    """
    # Find unprocessed emails (not in trash, not already processed)
    unprocessed_emails = db.query(Email).filter(
        Email.user_id == current_user.id,
        Email.auto_actions_created != True,
        Email.deleted_at.is_(None)
    ).all()

    if not unprocessed_emails:
        return {
            "success": True,
            "message": "No unprocessed emails found",
            "emails_processed": 0,
            "emails_checked": 0,
            "actions_created": 0
        }

    # Use content-based checker to filter actionable emails
    actionable_emails = ActionableContentChecker.get_actionable_emails(
        unprocessed_emails, min_score=min_score
    )

    logger.info(
        f"Content check: {len(actionable_emails)} actionable out of "
        f"{len(unprocessed_emails)} unprocessed emails (min_score={min_score})"
    )

    if not actionable_emails:
        return {
            "success": True,
            "message": f"No actionable emails found (checked {len(unprocessed_emails)} emails)",
            "emails_processed": 0,
            "emails_checked": len(unprocessed_emails),
            "actions_created": 0
        }

    total_actions = 0
    processed_emails = 0

    for email in actionable_emails:
        try:
            created_items = await action_extractor.create_action_items(
                db, email, current_user
            )
            total_actions += len(created_items)

            # Mark email as processed
            email.auto_actions_created = True
            email.action_count = len(created_items)
            processed_emails += 1
        except Exception as e:
            logger.error(f"Error extracting actions from email {email.id}: {e}")

    db.commit()

    return {
        "success": True,
        "message": f"Processed {processed_emails} emails, created {total_actions} action items",
        "emails_processed": processed_emails,
        "emails_checked": len(unprocessed_emails),
        "actionable_found": len(actionable_emails),
        "actions_created": total_actions
    }

@router.put("/{action_id}/complete")
async def complete_action_item(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark an action item as complete"""
    item = db.query(ActionItemModel).filter(
        ActionItemModel.id == action_id,
        ActionItemModel.user_id == current_user.id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")

    item.status = "completed"
    item.completed_at = datetime.utcnow()
    item.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "Action item completed"}


@router.put("/{action_id}/reopen")
async def reopen_action_item(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reopen a completed action item"""
    item = db.query(ActionItemModel).filter(
        ActionItemModel.id == action_id,
        ActionItemModel.user_id == current_user.id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")

    item.status = "pending"
    item.completed_at = None
    item.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "Action item reopened"}


@router.post("/cleanup-orphaned")
async def cleanup_orphaned_actions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove action items that reference deleted/non-existent emails"""
    # Find action items with email_id that don't have matching emails
    action_items_with_email = db.query(ActionItemModel).filter(
        ActionItemModel.user_id == current_user.id,
        ActionItemModel.email_id.isnot(None)
    ).all()

    orphaned_count = 0
    for action in action_items_with_email:
        # Check if email exists
        email = db.query(Email).filter(Email.id == action.email_id).first()
        if not email:
            db.delete(action)
            orphaned_count += 1

    db.commit()

    return {
        "success": True,
        "orphaned_removed": orphaned_count,
        "message": f"Removed {orphaned_count} orphaned action items"
    }