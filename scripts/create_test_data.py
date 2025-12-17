#!/usr/bin/env python3
"""
Create test user with sample email data for testing SAIGBOX workflows
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import uuid
from core.database import SessionLocal, User, Email, ActionItem, Base, engine

# Ensure tables exist
Base.metadata.create_all(engine)

def create_test_data():
    db = SessionLocal()

    try:
        # Check if test user already exists
        existing_user = db.query(User).filter(User.email == "testuser@demo.saigbox.com").first()
        if existing_user:
            print(f"Test user already exists: {existing_user.email}")
            print("Deleting existing test data to recreate...")
            # Delete associated data
            db.query(ActionItem).filter(ActionItem.user_id == existing_user.id).delete()
            db.query(Email).filter(Email.user_id == existing_user.id).delete()
            db.query(User).filter(User.id == existing_user.id).delete()
            db.commit()

        # Create test user
        test_user = User(
            id=str(uuid.uuid4()),
            email="testuser@demo.saigbox.com",
            name="Test User",
            provider="demo",
            oauth_access_token="demo-token-12345",
            oauth_refresh_token="demo-refresh-token",
            oauth_token_expires=datetime.utcnow() + timedelta(days=365),
            last_login=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db.add(test_user)
        db.flush()  # Get the user ID

        print(f"Created test user: {test_user.email} (ID: {test_user.id})")

        # Create sample emails from different senders
        emails_data = [
            # Sarah Chen - Multiple emails (for testing View Emails feature)
            {
                "sender": "sarah.chen@techcorp.com",
                "sender_name": "Sarah Chen",
                "subject": "Q4 Planning Meeting - Action Required",
                "body_text": """Hi Team,

Please prepare the following for our Q4 planning meeting next Friday:
1. Submit your Q3 results by Wednesday
2. Review the budget proposal attached
3. Schedule a pre-meeting with your direct reports

Let me know if you have any questions.

Best,
Sarah""",
                "is_urgent": True,
                "urgency_score": 75,
                "urgency_reason": "Contains deadline and action items",
                "hours_ago": 2
            },
            {
                "sender": "sarah.chen@techcorp.com",
                "sender_name": "Sarah Chen",
                "subject": "Re: Q4 Planning Meeting - Updated Agenda",
                "body_text": """Hi everyone,

I've updated the agenda based on your feedback:

1. Q3 Review (30 min)
2. Budget Discussion (45 min)
3. Q4 Goals Setting (45 min)
4. Team Announcements (15 min)

Please confirm your attendance by EOD today.

Thanks,
Sarah""",
                "is_urgent": False,
                "urgency_score": 45,
                "hours_ago": 1
            },
            {
                "sender": "sarah.chen@techcorp.com",
                "sender_name": "Sarah Chen",
                "subject": "Quick question about the proposal",
                "body_text": """Hey,

Just wanted to follow up on the proposal you sent last week.
Can we schedule a quick 15-minute call tomorrow to discuss the pricing section?

Let me know your availability.

Thanks!
Sarah""",
                "is_urgent": False,
                "urgency_score": 30,
                "hours_ago": 5
            },

            # John Boss - Urgent requests
            {
                "sender": "john.boss@company.com",
                "sender_name": "John Boss",
                "subject": "URGENT: Client Presentation Tomorrow",
                "body_text": """URGENT

The client presentation has been moved to tomorrow at 2 PM.

I need you to:
- Update the slides with the latest numbers
- Prepare the demo environment
- Send me the final deck by 6 PM today

This is critical for closing the deal.

John""",
                "is_urgent": True,
                "urgency_score": 95,
                "urgency_reason": "Marked URGENT, tight deadline, high-stakes client meeting",
                "hours_ago": 3
            },
            {
                "sender": "john.boss@company.com",
                "sender_name": "John Boss",
                "subject": "Weekly Check-in Reminder",
                "body_text": """Hi,

Don't forget our weekly check-in tomorrow at 10 AM.

Please come prepared with:
- Status update on current projects
- Any blockers or issues
- Plans for next week

See you then,
John""",
                "is_urgent": False,
                "urgency_score": 25,
                "hours_ago": 24
            },

            # Vendor Billing - Invoice
            {
                "sender": "billing@acmevendor.com",
                "sender_name": "ACME Vendor Billing",
                "subject": "Invoice #INV-2024-1234 - Payment Due",
                "body_text": """Dear Customer,

Please find attached invoice #INV-2024-1234 for $5,000.00

Payment Details:
- Amount Due: $5,000.00
- Due Date: January 15, 2025
- Invoice Period: December 2024

Payment can be made via:
- Bank Transfer (details attached)
- Credit Card (link in attachment)

Thank you for your business.

Regards,
ACME Vendor Billing Team""",
                "has_attachments": True,
                "is_urgent": False,
                "urgency_score": 40,
                "hours_ago": 48
            },

            # Newsletter - No action items
            {
                "sender": "newsletter@technews.io",
                "sender_name": "Tech News Weekly",
                "subject": "This Week in Tech - AI Breakthroughs & More",
                "body_text": """This week in tech:

🤖 AI & Machine Learning
- OpenAI announces GPT-5 preview
- Google's Gemini 2.0 released
- Meta's new research on AI agents

💼 Business News
- Tech layoffs continue in Q4
- Startup funding rebounds
- M&A activity picks up

📱 Product Launches
- Apple's Vision Pro 2 rumors
- Samsung Galaxy S25 specs leaked
- Tesla's new Optimus robot demo

Click here to read more: https://technews.io/weekly

Unsubscribe | Manage Preferences""",
                "is_urgent": False,
                "urgency_score": 0,
                "hours_ago": 72
            },

            # Client Follow-up - Hot lead
            {
                "sender": "mike.johnson@bigclient.com",
                "sender_name": "Mike Johnson",
                "subject": "Re: Project Proposal - Ready to Move Forward",
                "body_text": """Hi,

Thanks for the detailed proposal. We've reviewed it with our team and we're ready to move forward.

A few questions before we sign:
1. Can you match the competitor's pricing of $45k?
2. Is the implementation timeline of 6 weeks realistic?
3. Can we get references from similar-sized companies?

If you can address these by Friday, we can finalize the contract next week.

Looking forward to working together!

Best,
Mike Johnson
VP of Operations, BigClient Inc.""",
                "is_urgent": True,
                "urgency_score": 85,
                "urgency_reason": "Hot lead ready to close, time-sensitive questions",
                "hours_ago": 6
            },

            # Support ticket
            {
                "sender": "support@saasplatform.com",
                "sender_name": "SaaS Platform Support",
                "subject": "Re: Ticket #45678 - Login Issue Resolved",
                "body_text": """Hello,

Thank you for contacting SaaS Platform Support.

We've resolved the login issue you reported. The problem was caused by a recent security update that invalidated some session tokens.

What was fixed:
- Session token validation updated
- Your account access has been restored
- No data was affected

If you experience any further issues, please don't hesitate to reach out.

Best regards,
Support Team
SaaS Platform""",
                "is_urgent": False,
                "urgency_score": 10,
                "hours_ago": 12
            },

            # HR Announcement
            {
                "sender": "hr@company.com",
                "sender_name": "Human Resources",
                "subject": "Important: Benefits Enrollment Deadline - Dec 31",
                "body_text": """Dear Team,

This is a reminder that the annual benefits enrollment period ends on December 31st.

Action Required:
- Log into the benefits portal
- Review your current selections
- Make any changes by 11:59 PM on Dec 31

If you don't make changes, your current selections will continue into next year.

Key dates:
- Open enrollment ends: December 31
- New benefits effective: January 1

Questions? Contact hr@company.com or visit the HR portal.

Thank you,
Human Resources""",
                "is_urgent": True,
                "urgency_score": 70,
                "urgency_reason": "Benefits deadline approaching",
                "hours_ago": 8
            },

            # Cold outreach (for sales dashboard testing)
            {
                "sender": "alex.startup@newventure.io",
                "sender_name": "Alex Startup",
                "subject": "Partnership Opportunity - NewVenture x Your Company",
                "body_text": """Hi there,

I'm Alex, founder of NewVenture. We're building an AI-powered analytics platform and I think there could be a great synergy between our companies.

We've recently closed our Series A ($5M) and are looking for strategic partners in the enterprise space.

Would you be open to a 15-minute call next week to explore potential collaboration?

Here's my calendar: https://calendly.com/alex-startup

Looking forward to connecting!

Best,
Alex
Founder & CEO, NewVenture
alex.startup@newventure.io""",
                "is_urgent": False,
                "urgency_score": 35,
                "hours_ago": 36
            },

            # Another cold outreach
            {
                "sender": "lisa.sales@competitor.com",
                "sender_name": "Lisa Sales",
                "subject": "Quick question about your current solution",
                "body_text": """Hi,

I noticed your company is in the same space as us and wanted to reach out.

We've been helping companies like yours improve their email productivity by 40%.

Would you be interested in seeing a quick demo of how we could help your team?

No pressure - just thought it might be valuable.

Best,
Lisa
Account Executive, Competitor Inc.""",
                "is_urgent": False,
                "urgency_score": 15,
                "hours_ago": 96
            },
        ]

        # Create emails
        for i, email_data in enumerate(emails_data):
            hours_ago = email_data.pop("hours_ago", 0)
            email = Email(
                id=str(uuid.uuid4()),
                user_id=test_user.id,
                gmail_id=f"demo-gmail-{i+1:04d}",
                subject=email_data["subject"],
                sender=email_data["sender"],
                sender_name=email_data["sender_name"],
                body_text=email_data["body_text"],
                snippet=email_data["body_text"][:100] + "...",
                is_urgent=email_data.get("is_urgent", False),
                urgency_score=email_data.get("urgency_score", 0),
                urgency_reason=email_data.get("urgency_reason"),
                has_attachments=email_data.get("has_attachments", False),
                is_read=email_data.get("is_read", hours_ago > 24),
                received_at=datetime.utcnow() - timedelta(hours=hours_ago),
                created_at=datetime.utcnow()
            )
            db.add(email)

        db.flush()

        # NOTE: Action items are NOT pre-created here
        # They will be extracted automatically by AI when you call /api/actions/extract-all
        # Or during background sync when urgent emails are detected

        db.commit()

        # Print summary
        email_count = db.query(Email).filter(Email.user_id == test_user.id).count()
        action_count = db.query(ActionItem).filter(ActionItem.user_id == test_user.id).count()
        urgent_count = db.query(Email).filter(
            Email.user_id == test_user.id,
            Email.is_urgent == True
        ).count()

        print(f"\n✅ Test data created successfully!")
        print(f"   - Emails: {email_count}")
        print(f"   - Urgent emails: {urgent_count}")
        print(f"   - Action items: {action_count}")
        print(f"\n📧 Test User Credentials:")
        print(f"   Email: testuser@demo.saigbox.com")
        print(f"   Provider: demo")
        print(f"\n🔑 To login, use the demo auth endpoint or set a session cookie.")

        # List senders for testing View Emails
        senders = db.query(Email.sender, Email.sender_name).filter(
            Email.user_id == test_user.id
        ).distinct().all()

        print(f"\n📬 Email senders for testing 'View Emails':")
        for sender, name in senders:
            count = db.query(Email).filter(
                Email.user_id == test_user.id,
                Email.sender == sender
            ).count()
            print(f"   - {name} ({sender}): {count} emails")

        return test_user

    except Exception as e:
        db.rollback()
        print(f"❌ Error creating test data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_test_data()
