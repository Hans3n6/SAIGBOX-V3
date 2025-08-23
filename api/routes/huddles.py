from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from api.auth import get_current_user
from api.models import *
from core.database import (
    get_db, User, 
    Huddle as HuddleModel,
    HuddleMember as HuddleMemberModel,
    HuddleMessage as HuddleMessageModel,
    HuddleEmail as HuddleEmailModel,
    Email
)

router = APIRouter()

@router.get("/", response_model=List[Huddle])
async def list_huddles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all huddles user is part of"""
    # Get huddles created by user
    created_huddles = db.query(HuddleModel).filter(
        HuddleModel.created_by == current_user.id
    ).all()
    
    # Get huddles user is member of
    member_huddles = db.query(HuddleModel).join(HuddleMemberModel).filter(
        HuddleMemberModel.user_email == current_user.email
    ).all()
    
    # Combine and deduplicate
    all_huddles = list(set(created_huddles + member_huddles))
    
    # Convert to response model with members
    huddles = []
    for huddle in all_huddles:
        members = db.query(HuddleMemberModel).filter(
            HuddleMemberModel.huddle_id == huddle.id
        ).all()
        
        huddles.append(Huddle(
            id=huddle.id,
            name=huddle.name,
            description=huddle.description,
            created_by=huddle.created_by,
            status=huddle.status,
            created_at=huddle.created_at,
            updated_at=huddle.updated_at,
            members=[{
                "email": m.user_email,
                "role": m.role,
                "joined_at": m.joined_at.isoformat()
            } for m in members]
        ))
    
    return huddles

@router.get("/{huddle_id}", response_model=Huddle)
async def get_huddle(
    huddle_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get huddle details"""
    huddle = db.query(HuddleModel).filter(HuddleModel.id == huddle_id).first()
    
    if not huddle:
        raise HTTPException(status_code=404, detail="Huddle not found")
    
    # Check if user is member or creator
    is_member = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id,
        HuddleMemberModel.user_email == current_user.email
    ).first()
    
    if not is_member and huddle.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this huddle")
    
    # Get members
    members = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id
    ).all()
    
    return Huddle(
        id=huddle.id,
        name=huddle.name,
        description=huddle.description,
        created_by=huddle.created_by,
        status=huddle.status,
        created_at=huddle.created_at,
        updated_at=huddle.updated_at,
        members=[{
            "email": m.user_email,
            "role": m.role,
            "joined_at": m.joined_at.isoformat()
        } for m in members]
    )

@router.post("/", response_model=Huddle)
async def create_huddle(
    huddle_data: HuddleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new huddle"""
    # Create huddle
    new_huddle = HuddleModel(
        name=huddle_data.name,
        description=huddle_data.description,
        created_by=current_user.id,
        status="active"
    )
    db.add(new_huddle)
    db.flush()  # Get the ID before commit
    
    # Add creator as owner
    creator_member = HuddleMemberModel(
        huddle_id=new_huddle.id,
        user_email=current_user.email,
        role="owner"
    )
    db.add(creator_member)
    
    # Add other members
    for email in huddle_data.member_emails:
        if email != current_user.email:  # Skip if already added as owner
            member = HuddleMemberModel(
                huddle_id=new_huddle.id,
                user_email=email,
                role="member"
            )
            db.add(member)
    
    db.commit()
    db.refresh(new_huddle)
    
    # Get all members for response
    members = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == new_huddle.id
    ).all()
    
    return Huddle(
        id=new_huddle.id,
        name=new_huddle.name,
        description=new_huddle.description,
        created_by=new_huddle.created_by,
        status=new_huddle.status,
        created_at=new_huddle.created_at,
        updated_at=new_huddle.updated_at,
        members=[{
            "email": m.user_email,
            "role": m.role,
            "joined_at": m.joined_at.isoformat()
        } for m in members]
    )

@router.put("/{huddle_id}", response_model=Huddle)
async def update_huddle(
    huddle_id: str,
    update_data: HuddleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update huddle details"""
    huddle = db.query(HuddleModel).filter(HuddleModel.id == huddle_id).first()
    
    if not huddle:
        raise HTTPException(status_code=404, detail="Huddle not found")
    
    # Check if user is owner
    if huddle.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only huddle owner can update")
    
    # Update fields
    if update_data.name is not None:
        huddle.name = update_data.name
    if update_data.description is not None:
        huddle.description = update_data.description
    if update_data.status is not None:
        huddle.status = update_data.status
    
    huddle.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(huddle)
    
    # Get members for response
    members = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id
    ).all()
    
    return Huddle(
        id=huddle.id,
        name=huddle.name,
        description=huddle.description,
        created_by=huddle.created_by,
        status=huddle.status,
        created_at=huddle.created_at,
        updated_at=huddle.updated_at,
        members=[{
            "email": m.user_email,
            "role": m.role,
            "joined_at": m.joined_at.isoformat()
        } for m in members]
    )

@router.post("/{huddle_id}/members")
async def add_member(
    huddle_id: str,
    member_data: HuddleMemberAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add member to huddle"""
    huddle = db.query(HuddleModel).filter(HuddleModel.id == huddle_id).first()
    
    if not huddle:
        raise HTTPException(status_code=404, detail="Huddle not found")
    
    # Check if user is owner or admin
    user_member = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id,
        HuddleMemberModel.user_email == current_user.email
    ).first()
    
    if not user_member and huddle.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if user_member and user_member.role not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Only owner/admin can add members")
    
    # Check if member already exists
    existing = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id,
        HuddleMemberModel.user_email == member_data.email
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Member already exists")
    
    # Add new member
    new_member = HuddleMemberModel(
        huddle_id=huddle_id,
        user_email=member_data.email,
        role=member_data.role
    )
    db.add(new_member)
    db.commit()
    
    return {"success": True, "message": f"Added {member_data.email} to huddle"}

@router.delete("/{huddle_id}/members/{email}")
async def remove_member(
    huddle_id: str,
    email: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove member from huddle"""
    huddle = db.query(HuddleModel).filter(HuddleModel.id == huddle_id).first()
    
    if not huddle:
        raise HTTPException(status_code=404, detail="Huddle not found")
    
    # Check if user is owner
    if huddle.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only owner can remove members")
    
    # Find and remove member
    member = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id,
        HuddleMemberModel.user_email == email
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    if member.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove owner")
    
    db.delete(member)
    db.commit()
    
    return {"success": True, "message": f"Removed {email} from huddle"}

@router.get("/{huddle_id}/messages", response_model=List[HuddleMessage])
async def get_messages(
    huddle_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get huddle messages"""
    # Check if user is member
    is_member = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id,
        HuddleMemberModel.user_email == current_user.email
    ).first()
    
    huddle = db.query(HuddleModel).filter(HuddleModel.id == huddle_id).first()
    
    if not huddle:
        raise HTTPException(status_code=404, detail="Huddle not found")
    
    if not is_member and huddle.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get messages
    messages = db.query(HuddleMessageModel).filter(
        HuddleMessageModel.huddle_id == huddle_id
    ).order_by(HuddleMessageModel.created_at.desc()).limit(50).all()
    
    return messages

@router.post("/{huddle_id}/messages", response_model=HuddleMessage)
async def send_message(
    huddle_id: str,
    message_data: HuddleMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send message to huddle"""
    # Check if user is member
    is_member = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id,
        HuddleMemberModel.user_email == current_user.email
    ).first()
    
    huddle = db.query(HuddleModel).filter(HuddleModel.id == huddle_id).first()
    
    if not huddle:
        raise HTTPException(status_code=404, detail="Huddle not found")
    
    if not is_member and huddle.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Create message
    new_message = HuddleMessageModel(
        huddle_id=huddle_id,
        sender_email=current_user.email,
        message=message_data.message
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    
    return new_message

@router.post("/{huddle_id}/emails")
async def share_email(
    huddle_id: str,
    share_data: HuddleEmailShare,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Share email with huddle"""
    # Verify email exists and belongs to user
    email = db.query(Email).filter(
        Email.id == share_data.email_id,
        Email.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Check if user is member
    is_member = db.query(HuddleMemberModel).filter(
        HuddleMemberModel.huddle_id == huddle_id,
        HuddleMemberModel.user_email == current_user.email
    ).first()
    
    huddle = db.query(HuddleModel).filter(HuddleModel.id == huddle_id).first()
    
    if not huddle:
        raise HTTPException(status_code=404, detail="Huddle not found")
    
    if not is_member and huddle.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check if email already shared
    existing = db.query(HuddleEmailModel).filter(
        HuddleEmailModel.huddle_id == huddle_id,
        HuddleEmailModel.email_id == share_data.email_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Email already shared")
    
    # Share email
    shared_email = HuddleEmailModel(
        huddle_id=huddle_id,
        email_id=share_data.email_id,
        shared_by=current_user.email
    )
    db.add(shared_email)
    db.commit()
    
    return {"success": True, "message": "Email shared with huddle"}