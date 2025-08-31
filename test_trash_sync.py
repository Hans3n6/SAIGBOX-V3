#!/usr/bin/env python3
"""
Test script to verify trash synchronization between Gmail and SAIGBOX
"""

import os
import sys
import logging
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from core.database import get_db, User, Email
from core.gmail_service import GmailService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_trash_sync(user_email: str = None):
    """Test trash synchronization"""
    
    # Get database session
    db = next(get_db())
    
    # Get user
    if user_email:
        user = db.query(User).filter(User.email == user_email).first()
    else:
        # Get the most recent logged in user
        user = db.query(User).order_by(User.last_login.desc()).first()
    
    if not user:
        logger.error("No user found")
        return
    
    logger.info(f"Testing trash sync for user: {user.email}")
    
    # Initialize Gmail service
    gmail_service = GmailService()
    
    # Step 1: Fetch emails including trash
    logger.info("Step 1: Fetching emails including trash...")
    result = gmail_service.fetch_emails(db=db, user=user, max_results=20)
    
    emails = result.get('emails', [])
    logger.info(f"Fetched {len(emails)} emails")
    
    # Step 2: Check for emails with TRASH label
    trashed_in_gmail = []
    restored_in_gmail = []
    
    for email in emails:
        if hasattr(email, 'labels') and email.labels:
            if 'TRASH' in email.labels:
                trashed_in_gmail.append(email)
                logger.info(f"  - Email in Gmail trash: {email.subject[:50]}... (deleted_at: {email.deleted_at})")
        
        # Check if email was restored (no TRASH label but has deleted_at)
        if hasattr(email, 'deleted_at') and email.deleted_at:
            if not (hasattr(email, 'labels') and email.labels and 'TRASH' in email.labels):
                restored_in_gmail.append(email)
                logger.info(f"  - Email needs restoration in SAIGBOX: {email.subject[:50]}...")
    
    logger.info(f"\nSummary:")
    logger.info(f"  - Total emails fetched: {len(emails)}")
    logger.info(f"  - Emails in Gmail trash: {len(trashed_in_gmail)}")
    logger.info(f"  - Emails needing restoration: {len(restored_in_gmail)}")
    
    # Step 3: Check database state
    logger.info("\nStep 3: Checking database state...")
    
    # Count trashed emails in database
    db_trashed = db.query(Email).filter(
        Email.user_id == user.id,
        Email.deleted_at.isnot(None)
    ).count()
    
    # Count non-trashed emails
    db_active = db.query(Email).filter(
        Email.user_id == user.id,
        Email.deleted_at.is_(None)
    ).count()
    
    logger.info(f"  - Emails in SAIGBOX trash: {db_trashed}")
    logger.info(f"  - Active emails in SAIGBOX: {db_active}")
    
    # Step 4: Verify sync worked
    logger.info("\nStep 4: Verification...")
    
    sync_issues = []
    
    # Check each trashed email in Gmail has deleted_at in SAIGBOX
    for email in trashed_in_gmail:
        if not email.deleted_at:
            sync_issues.append(f"Email {email.gmail_id} is in Gmail trash but not marked as deleted in SAIGBOX")
    
    # Check restored emails
    for email in restored_in_gmail:
        sync_issues.append(f"Email {email.gmail_id} was restored in Gmail but still marked as deleted in SAIGBOX")
    
    if sync_issues:
        logger.warning("Sync issues found:")
        for issue in sync_issues:
            logger.warning(f"  - {issue}")
    else:
        logger.info("✅ Trash synchronization is working correctly!")
    
    # Step 5: Test specific scenarios
    logger.info("\nStep 5: Testing specific scenarios...")
    
    # Find an email that's not in trash
    test_email = db.query(Email).filter(
        Email.user_id == user.id,
        Email.deleted_at.is_(None),
        Email.gmail_id.isnot(None)
    ).first()
    
    if test_email:
        logger.info(f"Test email: {test_email.subject[:50]}...")
        logger.info(f"  - Gmail ID: {test_email.gmail_id}")
        logger.info(f"  - Current deleted_at: {test_email.deleted_at}")
        logger.info(f"  - Labels: {test_email.labels}")
        logger.info("\nTo test bidirectional sync:")
        logger.info("  1. Move this email to trash in Gmail")
        logger.info("  2. Run this script again to verify it syncs to SAIGBOX")
        logger.info("  3. Restore it from trash in Gmail")
        logger.info("  4. Run this script again to verify restoration syncs")
    
    db.close()
    logger.info("\nTest complete!")

if __name__ == "__main__":
    # You can pass an email as argument, or it will use the most recent user
    user_email = sys.argv[1] if len(sys.argv) > 1 else None
    test_trash_sync(user_email)