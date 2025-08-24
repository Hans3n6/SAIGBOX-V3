#!/usr/bin/env python3
"""Test script for SAIG email functionality"""

import asyncio
import json
from core.saig_assistant import SAIGAssistant
from core.database import get_db, User
from sqlalchemy.orm import Session

async def test_saig_compose():
    """Test SAIG email composition with draft preview"""
    saig = SAIGAssistant()
    
    # Create mock user
    class MockUser:
        id = 1
        email = "test@example.com"
        name = "Test User"
    
    # Create mock db session
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
    
    # Test compose email
    print("Testing compose email with draft preview...")
    result = await saig.process_message(
        db, 
        user,
        "Send an email to john@example.com with subject 'Meeting Tomorrow' saying 'Hi John, let's meet at 3pm tomorrow to discuss the project. Thanks!'",
        None
    )
    
    print("\nResult:")
    print(json.dumps(result, indent=2))
    
    # Test reply email with proper context
    print("\n\nTesting reply email...")
    reply_context = {
        "email_id": "test-123"
    }
    
    # First, let's update _get_email_context to return our test email
    original_context = await saig._get_email_context(db, user, "", reply_context)
    original_context["selected_email"] = {
        "id": "test-123",
        "gmail_id": "gmail-123",
        "subject": "Project Update",
        "sender": "jane@example.com",
        "body": "Hi, how is the project going? Can you send me an update?",
        "received_at": "2025-01-23T10:00:00"
    }
    
    result = await saig.process_message(
        db,
        user, 
        "Reply saying the project is going well and we're on track to finish by Friday",
        reply_context
    )
    
    print("\nResult:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test_saig_compose())