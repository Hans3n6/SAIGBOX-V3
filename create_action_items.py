#!/usr/bin/env python3
"""
Script to create action items from urgent emails
"""
import sys
import asyncio
sys.path.append('/Users/marcushansen/SAIGBOX-V3')

from sqlalchemy.orm import Session
from core.database import get_db, Email, User, ActionItem
from core.action_optimizer import ActionOptimizer
import uuid
from datetime import datetime, timedelta

async def create_action_items():
    db = next(get_db())
    
    # Get the user
    user = db.query(User).first()
    if not user:
        print("No user found")
        return
    
    print(f"Processing urgent emails for user: {user.email}")
    
    # Initialize action optimizer
    optimizer = ActionOptimizer(db)
    
    # Get urgent emails without action items
    urgent_emails = db.query(Email).filter(
        Email.user_id == user.id,
        Email.is_urgent == True,
        Email.deleted_at.is_(None)
    ).all()
    
    print(f"Found {len(urgent_emails)} urgent emails")
    
    action_count = 0
    for email in urgent_emails:
        # Check if action item already exists for this email
        existing = db.query(ActionItem).filter(
            ActionItem.email_id == email.id
        ).first()
        
        if existing:
            continue
            
        # Extract action item
        sender_context = await optimizer.get_sender_context(email.sender, user.id)
        action_data = await optimizer.smart_extract_action(
            email, 
            sender_context,
            user
        )
        
        if action_data and action_data['confidence'] >= 50:
            # Create action item
            action = ActionItem(
                id=str(uuid.uuid4()),
                user_id=user.id,
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
            print(f"✓ Created action: {action.title}")
            print(f"  Priority: {action.priority}, Confidence: {action_data['confidence']}")
    
    db.commit()
    print(f"\nCreated {action_count} action items")
    
    # Show action items
    print("\n=== Current Action Items ===")
    all_actions = db.query(ActionItem).filter(
        ActionItem.user_id == user.id,
        ActionItem.status == 'pending'
    ).all()
    
    for action in all_actions:
        email = db.query(Email).filter(Email.id == action.email_id).first()
        print(f"• {action.title}")
        if email:
            print(f"  From: {email.sender_name or email.sender}")
        if action.due_date:
            print(f"  Due: {action.due_date}")
    
    db.close()

if __name__ == "__main__":
    asyncio.run(create_action_items())