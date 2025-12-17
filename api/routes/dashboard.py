from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from typing import List, Dict, Any
import os
import json

from core.database import get_db, User, Email, ActionItem, Huddle
from api.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/stats")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get dashboard statistics for the current user"""
    try:
        user_id = current_user.id
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        week_start = today_start - timedelta(days=today_start.weekday())
        
        # Email statistics
        total_emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.deleted_at.is_(None)
        ).count()
        
        today_emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.deleted_at.is_(None),
            Email.received_at >= today_start
        ).count()
        
        week_emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.deleted_at.is_(None),
            Email.received_at >= week_start
        ).count()
        
        unread_emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.deleted_at.is_(None),
            Email.is_read == False
        ).count()
        
        # Action items statistics
        active_actions = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status != "completed"
        ).count()
        
        # Huddles statistics
        active_huddles = db.query(Huddle).filter(
            Huddle.created_by == user_id,
            Huddle.status == "active"
        ).count()
        
        return {
            "total_emails": total_emails,
            "today_emails": today_emails,
            "week_emails": week_emails,
            "unread_emails": unread_emails,
            "active_actions": active_actions,
            "active_huddles": active_huddles,
            "storage_used": 0  # Placeholder, storage calculation removed
        }
        
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard statistics")


@router.get("/activity")
async def get_recent_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10
):
    """Get recent activity for the dashboard"""
    try:
        user_id = current_user.id
        activities = []
        
        # Get recent emails
        recent_emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.deleted_at.is_(None)
        ).order_by(Email.received_at.desc()).limit(5).all()
        
        for email in recent_emails:
            activities.append({
                "type": "email",
                "description": f"New email from {email.sender_name or email.sender}",
                "timestamp": email.received_at.isoformat()
            })
        
        # Get recent action items
        recent_actions = db.query(ActionItem).filter(
            ActionItem.user_id == user_id
        ).order_by(ActionItem.created_at.desc()).limit(3).all()
        
        for action in recent_actions:
            status = "completed" if action.status == "completed" else "created"
            activities.append({
                "type": "action",
                "description": f"Action item {status}: {action.title[:50]}",
                "timestamp": action.completed_at.isoformat() if action.completed_at else action.created_at.isoformat()
            })
        
        # Get recent huddles
        recent_huddles = db.query(Huddle).filter(
            Huddle.created_by == user_id
        ).order_by(Huddle.created_at.desc()).limit(2).all()
        
        for huddle in recent_huddles:
            activities.append({
                "type": "huddle",
                "description": f"Huddle updated: {huddle.name[:50]}",
                "timestamp": huddle.updated_at.isoformat() if huddle.updated_at else huddle.created_at.isoformat()
            })
        
        # Sort activities by timestamp (newest first)
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return activities[:limit]
        
    except Exception as e:
        print(f"Error getting recent activity: {e}")
        return []


