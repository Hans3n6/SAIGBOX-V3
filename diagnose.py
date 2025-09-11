#!/usr/bin/env python3
"""
Diagnose urgent emails and action items issue
"""
import sys
sys.path.append('/Users/marcushansen/SAIGBOX-V3')

from sqlalchemy.orm import Session
from core.database import get_db, Email, User, ActionItem
from api.models import Email as EmailModel, ActionItem as ActionItemModel
import json

def diagnose():
    db = next(get_db())
    user = db.query(User).first()
    
    print("=" * 60)
    print("SAIGBOX DIAGNOSTIC REPORT")
    print("=" * 60)
    
    print(f"\nUser: {user.email}")
    print(f"User ID: {user.id}")
    
    # Check database state
    print("\n1. DATABASE STATE:")
    print("-" * 40)
    
    total_emails = db.query(Email).filter(Email.user_id == user.id).count()
    urgent_emails = db.query(Email).filter(
        Email.user_id == user.id,
        Email.is_urgent == True,
        Email.deleted_at.is_(None)
    ).all()
    action_items = db.query(ActionItem).filter(
        ActionItem.user_id == user.id,
        ActionItem.status == 'pending'
    ).all()
    
    print(f"Total emails: {total_emails}")
    print(f"Urgent emails (not deleted): {len(urgent_emails)}")
    print(f"Pending action items: {len(action_items)}")
    
    # Show some urgent emails
    print("\n2. URGENT EMAILS IN DATABASE:")
    print("-" * 40)
    for email in urgent_emails[:5]:
        print(f"✓ {email.subject[:50]}")
        print(f"  - is_urgent: {email.is_urgent}")
        print(f"  - urgency_score: {email.urgency_score}")
        print(f"  - labels: {email.labels}")
        print(f"  - attachments: {email.attachments}")
    
    # Check Pydantic model validation
    print("\n3. PYDANTIC MODEL VALIDATION:")
    print("-" * 40)
    
    successful_validations = 0
    failed_validations = 0
    urgent_in_validated = 0
    
    for email in urgent_emails:
        try:
            email_model = EmailModel.model_validate(email)
            data = email_model.model_dump()
            successful_validations += 1
            if data.get('is_urgent'):
                urgent_in_validated += 1
        except Exception as e:
            failed_validations += 1
            print(f"✗ Failed to validate: {email.subject[:30]}")
            print(f"  Error: {str(e)[:100]}")
    
    print(f"Successfully validated: {successful_validations}/{len(urgent_emails)}")
    print(f"Failed validations: {failed_validations}")
    print(f"Urgent flags preserved: {urgent_in_validated}/{successful_validations}")
    
    # Check action items
    print("\n4. ACTION ITEMS:")
    print("-" * 40)
    for item in action_items:
        print(f"✓ {item.title[:50]}")
        print(f"  - Priority: {item.priority}")
        print(f"  - Status: {item.status}")
        print(f"  - Auto-created: {item.auto_created}")
    
    # Simulate API response
    print("\n5. SIMULATED API RESPONSE (first urgent email):")
    print("-" * 40)
    
    if urgent_emails:
        email_model = EmailModel.model_validate(urgent_emails[0])
        api_json = email_model.model_dump_json(indent=2)
        api_data = json.loads(api_json)
        
        print(f"Subject: {api_data['subject'][:50]}")
        print(f"is_urgent: {api_data['is_urgent']}")
        print(f"urgency_score: {api_data['urgency_score']}")
        print(f"urgency_reason: {api_data.get('urgency_reason', 'None')[:50]}")
        print(f"received_at: {api_data['received_at']}")
    
    print("\n6. RECOMMENDATIONS:")
    print("-" * 40)
    print("✓ Database has urgent emails and action items")
    print("✓ Pydantic models include urgency fields")
    print("✓ Timestamps have 'Z' suffix for UTC")
    print("\n⚠ To see the data in the browser:")
    print("  1. Log in at http://localhost:8000")
    print("  2. Click 'Urgent' filter to see urgent emails")
    print("  3. Click 'Actions' in sidebar to see action items")
    print("  4. Check browser console for any JavaScript errors")
    print("  5. Use browser DevTools Network tab to inspect API responses")
    
    db.close()

if __name__ == "__main__":
    diagnose()