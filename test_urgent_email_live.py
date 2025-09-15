#!/usr/bin/env python3
"""
Test urgent email detection with a simulated new email
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from core.database import User, Email
from core.urgency_detector import UrgencyDetector
from core.action_item_creator import ActionItemCreator
import uuid

# Setup database
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./saigbox.db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def simulate_urgent_email():
    """Simulate receiving a new urgent email"""
    db = SessionLocal()
    
    try:
        # Get user
        user = db.query(User).first()
        if not user:
            print("❌ No user found")
            return False
        
        print(f"Simulating urgent email for: {user.email}")
        
        # Create a highly urgent test email
        test_email = Email(
            user_id=user.id,
            gmail_id=f"urgent_test_{uuid.uuid4().hex[:8]}",
            subject="URGENT: Server is down - CRITICAL production issue needs immediate attention!!!",
            sender="cto@yourcompany.com",
            sender_name="Jane Smith (CTO)",
            recipients=[user.email],
            body_text="""URGENT - PLEASE RESPOND IMMEDIATELY!
            
Our production server is completely down and customers cannot access the service.
This is a CRITICAL blocker that needs your immediate attention.

We need you to:
1. Review the error logs ASAP
2. Approve the emergency deployment by EOD today
3. Join the crisis meeting in 15 minutes

This is affecting 10,000+ customers and we're losing $1000/minute.

Please respond within the next 30 minutes or we'll need to escalate to the CEO.

Thanks,
Jane Smith
CTO
""",
            snippet="URGENT - PLEASE RESPOND IMMEDIATELY! Our production server is completely down...",
            received_at=datetime.utcnow(),
            is_read=False,
            labels=["INBOX", "IMPORTANT"]
        )
        
        # Add to database
        db.add(test_email)
        db.commit()
        
        print(f"✅ Created test email: {test_email.subject}")
        
        # Run urgency detection
        detector = UrgencyDetector(db)
        is_urgent, score, reason = detector.should_mark_urgent(test_email, user)
        
        print(f"\n=== Urgency Detection Results ===")
        print(f"Is Urgent: {is_urgent}")
        print(f"Score: {score}/100")
        print(f"Reason: {reason}")
        
        if is_urgent:
            test_email.is_urgent = True
            test_email.urgency_score = score
            test_email.urgency_reason = reason
            test_email.urgency_analyzed_at = datetime.utcnow()
            
            # Create action item if score >= 70
            if score >= 70:
                creator = ActionItemCreator(db)
                action_item = creator.create_from_urgent_email(test_email, user)
                if action_item:
                    print(f"\n✅ Action item auto-created:")
                    print(f"   Title: {action_item.title}")
                    print(f"   Due: {action_item.due_date}")
        
        db.commit()
        
        # Verify in database
        print(f"\n=== Verification ===")
        urgent_emails = db.query(Email).filter(
            Email.user_id == user.id,
            Email.is_urgent == True,
            Email.urgency_score >= 90
        ).order_by(Email.urgency_score.desc()).limit(3).all()
        
        print(f"Top 3 most urgent emails:")
        for e in urgent_emails:
            print(f"  • [{e.urgency_score}] {e.subject[:60]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("🚨 Simulating Urgent Email Reception")
    print("=" * 50)
    
    success = simulate_urgent_email()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Urgent email created and processed!")
        print("\n👀 Check your inbox - you should see:")
        print("   1. A red-bordered urgent email at the top")
        print("   2. An action item in your action items list")
    else:
        print("❌ Test failed")
    
    sys.exit(0 if success else 1)