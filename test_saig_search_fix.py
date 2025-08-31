#!/usr/bin/env python3
"""
Test script to verify the SAIG email search format specifier fix
"""

import asyncio
import os
import sys
import logging
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from core.database import get_db, User
from core.saig_assistant import SAIGAssistant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_saig_search():
    """Test SAIG search with problematic strings"""
    
    # Get database session
    db = next(get_db())
    
    # Get the most recent user
    user = db.query(User).order_by(User.last_login.desc()).first()
    
    if not user:
        logger.error("No user found")
        return
    
    logger.info(f"Testing SAIG search for user: {user.email}")
    
    # Initialize SAIG Assistant
    saig = SAIGAssistant()
    
    # Test cases that previously caused format specifier errors
    test_cases = [
        'delete all emails from "Lids"',
        'move emails from {Nike} to trash',
        'delete emails from %s sender',
        'find emails from {sender}',
        'delete all emails from "Amazon {order}"',
        'search for emails from user@{domain}.com'
    ]
    
    logger.info("\n🧪 Testing email search descriptions that could cause format errors:")
    
    for i, description in enumerate(test_cases, 1):
        logger.info(f"\nTest {i}: {description}")
        try:
            # This would previously fail with format specifier error
            emails = await saig._find_emails_by_description(db, user, description)
            logger.info(f"  ✅ Success! Found {len(emails)} emails")
            if emails and len(emails) > 0:
                logger.info(f"  Sample: {emails[0].get('subject', 'No subject')[:50]}...")
        except Exception as e:
            logger.error(f"  ❌ Error: {e}")
            import traceback
            logger.error(f"  Traceback: {traceback.format_exc()}")
    
    db.close()
    logger.info("\n✅ Test complete!")

if __name__ == "__main__":
    asyncio.run(test_saig_search())