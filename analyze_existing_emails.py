#!/usr/bin/env python3
"""
Analyze existing emails for urgency and create action items
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from core.database import User, Email, ActionItem
from core.urgency_detector import UrgencyDetector
from core.action_item_creator import ActionItemCreator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup database
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./saigbox.db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def analyze_existing_emails(limit=None):
    """Analyze existing emails that haven't been checked for urgency"""
    db = SessionLocal()
    
    try:
        # Get user
        user = db.query(User).first()
        if not user:
            print("❌ No user found in database")
            return False
        
        print(f"Analyzing emails for user: {user.email}")
        
        # Get emails that haven't been analyzed for urgency
        query = db.query(Email).filter(
            Email.user_id == user.id,
            Email.urgency_analyzed_at.is_(None),
            Email.deleted_at.is_(None)
        ).order_by(Email.received_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        emails_to_analyze = query.all()
        
        print(f"\nFound {len(emails_to_analyze)} emails to analyze for urgency")
        
        if len(emails_to_analyze) == 0:
            print("✅ All emails have already been analyzed")
            return True
        
        # Initialize detectors
        urgency_detector = UrgencyDetector(db)
        action_creator = ActionItemCreator(db)
        
        # Counters
        urgent_count = 0
        action_count = 0
        
        print("\nAnalyzing emails...")
        for i, email in enumerate(emails_to_analyze):
            if i % 100 == 0:
                print(f"  Progress: {i}/{len(emails_to_analyze)}")
            
            # Check urgency
            is_urgent, score, reason = urgency_detector.should_mark_urgent(email, user)
            
            # Always mark as analyzed
            email.urgency_analyzed_at = datetime.utcnow()
            
            if is_urgent:
                email.is_urgent = True
                email.urgency_score = score
                email.urgency_reason = reason
                urgent_count += 1
                
                # Log high-urgency emails
                if score >= 70:
                    print(f"  🔴 HIGH URGENCY ({score}): {email.subject[:60]}...")
                    
                    # Create action item for very urgent emails
                    if not email.auto_actions_created:
                        action_item = action_creator.create_from_urgent_email(email, user)
                        if action_item:
                            action_count += 1
                            print(f"     ✅ Created action item: {action_item.title[:50]}...")
                elif score >= 50:
                    print(f"  🟡 MEDIUM URGENCY ({score}): {email.subject[:60]}...")
            else:
                email.is_urgent = False
                email.urgency_score = 0
        
        # Commit all changes
        db.commit()
        
        print(f"\n=== Analysis Complete ===")
        print(f"Emails analyzed: {len(emails_to_analyze)}")
        print(f"Urgent emails found: {urgent_count}")
        print(f"Action items created: {action_count}")
        
        # Show statistics
        total_urgent = db.query(Email).filter(
            Email.user_id == user.id,
            Email.is_urgent == True,
            Email.deleted_at.is_(None)
        ).count()
        
        total_actions = db.query(ActionItem).filter(
            ActionItem.user_id == user.id,
            ActionItem.auto_created == True
        ).count()
        
        print(f"\n=== Total Statistics ===")
        print(f"Total urgent emails: {total_urgent}")
        print(f"Total auto-created action items: {total_actions}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Analyze existing emails for urgency')
    parser.add_argument('--limit', type=int, help='Limit number of emails to analyze')
    parser.add_argument('--all', action='store_true', help='Analyze all unanalyzed emails')
    args = parser.parse_args()
    
    print("🚀 Starting Urgency Analysis for Existing Emails")
    print("=" * 50)
    
    # Determine limit
    limit = None if args.all else (args.limit or 100)
    
    if limit:
        print(f"Analyzing up to {limit} emails")
    else:
        print("Analyzing ALL unanalyzed emails")
    
    success = analyze_existing_emails(limit)
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Analysis completed successfully!")
    else:
        print("❌ Analysis failed")
    
    sys.exit(0 if success else 1)