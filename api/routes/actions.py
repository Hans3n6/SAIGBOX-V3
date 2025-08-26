from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from api.auth import get_current_user
from api.models import *
from core.database import get_db, User, ActionItem as ActionItemModel, Email

router = APIRouter()

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
    
    # Get all items
    items = query.order_by(ActionItemModel.priority, ActionItemModel.created_at).all()
    
    # Convert to response model
    result = []
    for item in items:
        # Map numeric priority to enum string
        priority_map = {1: "high", 2: "medium", 3: "low"}
        priority_str = priority_map.get(item.priority, "medium")
        
        # Map status string to enum
        status_str = item.status if item.status in ["pending", "completed", "overdue"] else "pending"
        
        result.append(ActionItem(
            id=item.id,
            user_id=item.user_id,
            email_id=item.email_id,
            title=item.title,
            description=item.description,
            due_date=item.due_date,
            priority=ActionItemPriority(priority_str),
            status=ActionItemStatus(status_str),
            created_at=item.created_at,
            completed_at=item.completed_at,
            updated_at=item.updated_at
        ))
    
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
    
    # For now, create a sample action item
    # In production, this would use AI to extract real action items
    sample_item = ActionItemModel(
        user_id=current_user.id,
        email_id=email_id,
        title=f"Follow up on: {email.subject[:50]}",
        description=f"Action item extracted from email",
        priority=2,
        status="pending"
    )
    
    db.add(sample_item)
    db.commit()
    db.refresh(sample_item)
    
    return [ActionItem(
        id=sample_item.id,
        user_id=sample_item.user_id,
        email_id=sample_item.email_id,
        title=sample_item.title,
        description=sample_item.description,
        due_date=sample_item.due_date,
        priority=ActionItemPriority.MEDIUM,
        status=ActionItemStatus.PENDING,
        created_at=sample_item.created_at,
        completed_at=sample_item.completed_at,
        updated_at=sample_item.updated_at
    )]

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