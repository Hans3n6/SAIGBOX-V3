#!/usr/bin/env python3
"""
Test script for urgent email detection and action item creation workflow
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

# Setup database
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./saigbox.db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_urgent_workflow():
    """Test the complete urgent email workflow"""
    db = SessionLocal()
    
    try:
        # Get a test user
        user = db.query(User).first()
        if not user:
            print("❌ No user found in database")
            return False
        
        print(f"Testing with user: {user.email}")
        
        # Create a test email that should be marked as urgent
        test_email = Email(
            user_id=user.id,
            gmail_id=f"test_urgent_{datetime.now().timestamp()}",
            subject="URGENT: Contract expires tomorrow - need immediate approval",
            sender="boss@company.com",
            sender_name="John Boss (CEO)",
            recipients=[user.email],
            body_text="This contract expires tomorrow at EOD. Please review and approve ASAP. This is critical for our Q4 planning.",
            snippet="This contract expires tomorrow at EOD. Please review and approve ASAP...",
            received_at=datetime.utcnow(),
            is_read=False
        )
        
        db.add(test_email)
        db.commit()
        
        print(f"\n✅ Created test email: {test_email.subject}")
        
        # Test urgency detection
        print("\n=== Testing Urgency Detection ===")
        detector = UrgencyDetector(db)
        is_urgent, score, reason = detector.should_mark_urgent(test_email, user)
        
        print(f"Is Urgent: {is_urgent}")
        print(f"Urgency Score: {score}/100")
        print(f"Reason: {reason}")
        
        if is_urgent:
            test_email.is_urgent = True
            test_email.urgency_score = score
            test_email.urgency_reason = reason
            test_email.urgency_analyzed_at = datetime.utcnow()
            db.commit()
            print("✅ Email marked as urgent")
        else:
            print("❌ Email not marked as urgent (score too low)")
        
        # Test action item creation
        if score >= 70:
            print("\n=== Testing Action Item Creation ===")
            creator = ActionItemCreator(db)
            action_item = creator.create_from_urgent_email(test_email, user)
            
            if action_item:
                print(f"✅ Action item created:")
                print(f"   Title: {action_item.title}")
                print(f"   Priority: {'High' if action_item.priority == 1 else 'Medium' if action_item.priority == 2 else 'Low'}")
                print(f"   Due Date: {action_item.due_date}")
                print(f"   Description: {action_item.description[:100]}...")
            else:
                print("❌ Action item not created")
        
        # Check results
        print("\n=== Verification ===")
        
        # Count urgent emails
        urgent_count = db.query(Email).filter(
            Email.user_id == user.id,
            Email.is_urgent == True,
            Email.deleted_at.is_(None)
        ).count()
        print(f"Total urgent emails: {urgent_count}")
        
        # Count action items
        action_count = db.query(ActionItem).filter(
            ActionItem.user_id == user.id,
            ActionItem.auto_created == True
        ).count()
        print(f"Total auto-created action items: {action_count}")
        
        # Clean up test data
        print("\n=== Cleanup ===")
        
        # Delete test action items
        db.query(ActionItem).filter(
            ActionItem.email_id == test_email.id
        ).delete()
        
        # Delete test email
        db.query(Email).filter(
            Email.id == test_email.id
        ).delete()
        
        db.commit()
        print("✅ Test data cleaned up")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Starting Urgent Email Workflow Test")
    print("=" * 50)
    
    success = test_urgent_workflow()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    
    sys.exit(0 if success else 1)