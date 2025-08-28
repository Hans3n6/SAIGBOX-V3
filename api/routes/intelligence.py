"""
Intelligence API endpoints for advanced SAIG features
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from datetime import datetime

from api.auth import get_current_user
from core.database import get_db, User, Email
from core.saig_intelligence import SAIGIntelligence
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize intelligence module
saig_intelligence = SAIGIntelligence()

@router.get("/patterns")
async def analyze_email_patterns(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze user's email patterns and get proactive suggestions"""
    try:
        patterns = await saig_intelligence.analyze_email_patterns(db, current_user)
        return {
            "success": True,
            "patterns": patterns
        }
    except Exception as e:
        logger.error(f"Error analyzing patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/extract-actions")
async def extract_action_items(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Extract action items from a specific email"""
    try:
        # Get the email
        email = db.query(Email).filter(
            Email.id == email_id,
            Email.user_id == current_user.id
        ).first()
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        # Extract action items
        content = email.body_text or email.snippet or ""
        action_items = await saig_intelligence.extract_action_items(
            content, 
            email.subject or ""
        )
        
        return {
            "success": True,
            "email_id": email_id,
            "action_items": action_items
        }
    except Exception as e:
        logger.error(f"Error extracting action items: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/thread-summary/{thread_id}")
async def get_thread_summary(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get AI-generated summary of an email thread"""
    try:
        summary = await saig_intelligence.summarize_thread(db, thread_id, current_user)
        return {
            "success": True,
            "thread_id": thread_id,
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error summarizing thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/predict-importance")
async def predict_email_importance(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Predict the importance of an email"""
    try:
        # Get the email
        email = db.query(Email).filter(
            Email.id == email_id,
            Email.user_id == current_user.id
        ).first()
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        # Predict importance
        importance = await saig_intelligence.predict_email_importance(
            email, current_user, db
        )
        
        return {
            "success": True,
            "email_id": email_id,
            "importance": importance
        }
    except Exception as e:
        logger.error(f"Error predicting importance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/learn-preference")
async def record_user_preference(
    preference_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record user action to learn preferences"""
    try:
        email_id = preference_data.get("email_id")
        action = preference_data.get("action")
        
        if not email_id or not action:
            raise HTTPException(status_code=400, detail="email_id and action required")
        
        # Get the email
        email = db.query(Email).filter(
            Email.id == email_id,
            Email.user_id == current_user.id
        ).first()
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        # Learn from the action
        await saig_intelligence.learn_user_preferences(db, current_user, action, email)
        
        return {
            "success": True,
            "message": "Preference recorded"
        }
    except Exception as e:
        logger.error(f"Error recording preference: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/smart-compose")
async def get_smart_compose_suggestions(
    context: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get smart compose suggestions based on context"""
    try:
        suggestions = await saig_intelligence.smart_compose_suggestions(
            db, current_user, context
        )
        
        return {
            "success": True,
            "suggestions": suggestions
        }
    except Exception as e:
        logger.error(f"Error getting suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/categorize")
async def categorize_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Categorize an email using AI"""
    try:
        # Get the email
        email = db.query(Email).filter(
            Email.id == email_id,
            Email.user_id == current_user.id
        ).first()
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        # Detect category
        category = await saig_intelligence.detect_email_category(email)
        
        # Update email with category
        if not email.labels:
            email.labels = []
        if category not in email.labels:
            email.labels.append(f"CATEGORY/{category.upper()}")
            db.commit()
        
        return {
            "success": True,
            "email_id": email_id,
            "category": category
        }
    except Exception as e:
        logger.error(f"Error categorizing email: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/insights")
async def get_email_insights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive email insights and analytics"""
    try:
        # Analyze patterns
        patterns = await saig_intelligence.analyze_email_patterns(db, current_user)
        
        # Get additional insights
        from sqlalchemy import func
        from datetime import timedelta
        
        # Email statistics
        total_emails = db.query(Email).filter(
            Email.user_id == current_user.id,
            Email.deleted_at.is_(None)
        ).count()
        
        unread_emails = db.query(Email).filter(
            Email.user_id == current_user.id,
            Email.is_read == False,
            Email.deleted_at.is_(None)
        ).count()
        
        starred_emails = db.query(Email).filter(
            Email.user_id == current_user.id,
            Email.is_starred == True,
            Email.deleted_at.is_(None)
        ).count()
        
        # Recent activity
        recent_date = datetime.utcnow() - timedelta(days=7)
        recent_received = db.query(Email).filter(
            Email.user_id == current_user.id,
            Email.received_at >= recent_date,
            Email.deleted_at.is_(None)
        ).count()
        
        insights = {
            "statistics": {
                "total_emails": total_emails,
                "unread_emails": unread_emails,
                "starred_emails": starred_emails,
                "recent_received": recent_received,
                "read_rate": ((total_emails - unread_emails) / total_emails * 100) if total_emails > 0 else 0
            },
            "patterns": patterns,
            "recommendations": []
        }
        
        # Add recommendations based on patterns
        if patterns['unread_buildup'] > 50:
            insights["recommendations"].append({
                "type": "inbox_management",
                "message": f"You have {patterns['unread_buildup']} unread emails. Consider setting aside time for inbox zero.",
                "priority": "high"
            })
        
        if patterns['email_categories'].get('newsletters', 0) > 20:
            insights["recommendations"].append({
                "type": "newsletter_management",
                "message": "You have many newsletters. Consider creating filters or unsubscribing from unwanted ones.",
                "priority": "medium"
            })
        
        return {
            "success": True,
            "insights": insights
        }
    except Exception as e:
        logger.error(f"Error getting insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch-categorize")
async def batch_categorize_emails(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Categorize multiple uncategorized emails"""
    try:
        # Get uncategorized emails
        emails = db.query(Email).filter(
            Email.user_id == current_user.id,
            Email.deleted_at.is_(None)
        ).limit(limit).all()
        
        categorized_count = 0
        categories_applied = {}
        
        for email in emails:
            # Check if already categorized
            if email.labels and any(label.startswith("CATEGORY/") for label in email.labels):
                continue
            
            # Detect category
            category = await saig_intelligence.detect_email_category(email)
            
            # Update email
            if not email.labels:
                email.labels = []
            email.labels.append(f"CATEGORY/{category.upper()}")
            
            categorized_count += 1
            categories_applied[category] = categories_applied.get(category, 0) + 1
        
        db.commit()
        
        return {
            "success": True,
            "categorized": categorized_count,
            "categories": categories_applied
        }
    except Exception as e:
        logger.error(f"Error batch categorizing: {e}")
        raise HTTPException(status_code=500, detail=str(e))