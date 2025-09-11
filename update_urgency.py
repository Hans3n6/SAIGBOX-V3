#!/usr/bin/env python3
"""
Script to update urgency scores for existing emails
"""
import sys
sys.path.append('/Users/marcushansen/SAIGBOX-V3')

from sqlalchemy.orm import Session
from core.database import get_db, Email, User
from core.urgency_detector import UrgencyDetector

def update_urgency_scores():
    db = next(get_db())
    
    # Get the user
    user = db.query(User).first()
    if not user:
        print("No user found")
        return
    
    print(f"Processing emails for user: {user.email}")
    
    # Initialize urgency detector
    detector = UrgencyDetector(db)
    
    # Get all emails without urgency scores
    emails = db.query(Email).filter(
        Email.user_id == user.id,
        Email.urgency_score == 0,
        Email.deleted_at.is_(None)
    ).all()
    
    print(f"Found {len(emails)} emails to process")
    
    urgent_count = 0
    for email in emails:
        is_urgent, score, reason = detector.should_mark_urgent(email, user)
        
        if is_urgent:
            email.is_urgent = True
            email.urgency_score = score
            email.urgency_reason = reason
            urgent_count += 1
            print(f"✓ Marked urgent: {email.subject[:50]} (score: {score})")
            print(f"  Reason: {reason}")
    
    db.commit()
    print(f"\nUpdated {urgent_count} emails as urgent")
    
    # Check specific emails from johnsoms66
    print("\n=== Checking emails from johnsoms66 ===")
    john_emails = db.query(Email).filter(
        Email.sender.like('%johnsoms66%')
    ).all()
    
    for email in john_emails:
        is_urgent, score, reason = detector.should_mark_urgent(email, user)
        print(f"Email: {email.subject[:50]}")
        print(f"  Score: {score}, Urgent: {is_urgent}")
        print(f"  Reason: {reason}")
        
        if is_urgent and not email.is_urgent:
            email.is_urgent = True
            email.urgency_score = score
            email.urgency_reason = reason
            print(f"  → Updated as urgent!")
    
    db.commit()
    db.close()

if __name__ == "__main__":
    update_urgency_scores()