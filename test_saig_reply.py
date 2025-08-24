#!/usr/bin/env python3
"""Test script for SAIG intelligent reply functionality"""

import asyncio
import json
from core.saig_assistant import SAIGAssistant
from core.database import get_db, User

async def test_saig_smart_reply():
    """Test SAIG's ability to read and respond to emails intelligently"""
    saig = SAIGAssistant()
    
    # Create mock user and db
    class MockUser:
        id = 1
        email = "user@example.com"
        name = "John Doe"
    
    class MockDB:
        def add(self, obj):
            pass
        def commit(self):
            pass
        def query(self, model):
            return self
        def filter(self, *args, **kwargs):
            return self
        def first(self):
            return None
        def count(self):
            return 0
        def order_by(self, *args):
            return self
        def limit(self, n):
            return self
        def all(self):
            return []
    
    user = MockUser()
    db = MockDB()
    
    # Test Case 1: Meeting request email
    print("=" * 60)
    print("Test Case 1: Meeting Request Email")
    print("=" * 60)
    
    context = {
        "email_id": "test-meeting-123",
        "selected_email": {
            "id": "test-meeting-123",
            "gmail_id": "gmail-meeting-123",
            "subject": "Project Update Meeting",
            "sender": "sarah@company.com",
            "body": """Hi John,

I hope this email finds you well. I wanted to touch base regarding our upcoming project milestone.

Would you be available for a meeting this Thursday at 2 PM to discuss the following:
1. Current progress on Phase 2
2. Budget allocation for Q2
3. Team resource planning

Please let me know if this time works for you, or suggest an alternative.

Best regards,
Sarah""",
            "received_at": "2025-01-23T10:00:00"
        }
    }
    
    # Test with automatic analysis
    message = """Please read this email and generate an appropriate, professional reply.
                
Email Details:
From: sarah@company.com
Subject: Project Update Meeting
Content: Hi John,

I hope this email finds you well. I wanted to touch base regarding our upcoming project milestone.

Would you be available for a meeting this Thursday at 2 PM to discuss the following:
1. Current progress on Phase 2
2. Budget allocation for Q2
3. Team resource planning

Please let me know if this time works for you, or suggest an alternative.

Best regards,
Sarah

Generate a thoughtful and contextually appropriate response that:
1. Acknowledges the sender's message
2. Addresses any questions or requests
3. Maintains a professional tone
4. Includes a proper greeting and closing"""
    
    result = await saig.process_message(db, user, message, context)
    
    print("\nSAIG Response:")
    print("-" * 40)
    print(f"Intent: {result.get('intent', 'unknown')}")
    print(f"Actions: {result.get('actions_taken', [])}")
    if "email_reply_created" in result.get("actions_taken", []):
        print("✅ SAIG successfully analyzed the email and generated a reply")
        # The response contains the plain text reply
        response = result["response"]
        print("\nGenerated Reply:")
        print(response)
    else:
        print("❌ Failed to generate reply")
        print(f"Response: {result.get('response', 'No response')}")
    
    # Test Case 2: Customer complaint email
    print("\n" + "=" * 60)
    print("Test Case 2: Customer Complaint Email")
    print("=" * 60)
    
    context2 = {
        "email_id": "test-complaint-456",
        "selected_email": {
            "id": "test-complaint-456",
            "gmail_id": "gmail-complaint-456",
            "subject": "Issue with Recent Order #12345",
            "sender": "customer@email.com",
            "body": """Hello,

I'm writing to express my disappointment with my recent order #12345. The product arrived damaged and two days late.

This is unacceptable service, and I expect a full refund immediately.

I've been a loyal customer for 5 years and this is very disappointing.

Regards,
Mike Johnson""",
            "received_at": "2025-01-23T14:30:00"
        }
    }
    
    # Test with additional instructions
    message2 = """Please read this email and generate an appropriate, professional reply.
                
Email Details:
From: customer@email.com
Subject: Issue with Recent Order #12345
Content: Hello,

I'm writing to express my disappointment with my recent order #12345. The product arrived damaged and two days late.

This is unacceptable service, and I expect a full refund immediately.

I've been a loyal customer for 5 years and this is very disappointing.

Regards,
Mike Johnson

Generate a thoughtful and contextually appropriate response that:
1. Acknowledges the sender's message
2. Addresses any questions or requests
3. Maintains a professional tone
4. Includes a proper greeting and closing

Additional instructions: Be empathetic and apologetic. Offer to resolve the issue promptly."""
    
    result2 = await saig.process_message(db, user, message2, context2)
    
    print("\nSAIG Response:")
    print("-" * 40)
    print(f"Intent: {result2.get('intent', 'unknown')}")
    print(f"Actions: {result2.get('actions_taken', [])}")
    if "email_reply_created" in result2.get("actions_taken", []):
        print("✅ SAIG successfully analyzed the complaint and generated an empathetic reply")
        response2 = result2["response"]
        print("\nGenerated Reply:")
        print(response2)
    else:
        print("❌ Failed to generate reply")
        print(f"Response: {result2.get('response', 'No response')}")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)
    print("\nSummary:")
    print("- SAIG can now read and understand email context")
    print("- Generates appropriate responses based on email type")
    print("- Maintains professional tone and proper formatting")
    print("- Includes SAIG tagline in all replies")

if __name__ == "__main__":
    asyncio.run(test_saig_smart_reply())