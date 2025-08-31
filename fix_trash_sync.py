#!/usr/bin/env python3
"""
Fix trash synchronization between Gmail and SAIGBOX
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

def fix_trash_sync():
    """Fix trash sync issues"""
    
    # Get database session
    db = next(get_db())
    
    # Get the most recent user
    user = db.query(User).order_by(User.last_login.desc()).first()
    
    if not user:
        logger.error("No user found")
        return
    
    logger.info(f"Fixing trash sync for user: {user.email}")
    
    # Initialize Gmail service
    gmail_service = GmailService()
    
    # Step 1: Fix emails in SAIGBOX trash that aren't in Gmail trash
    logger.info("\n=== Fixing SAIGBOX Trash ===")
    saigbox_trash = db.query(Email).filter(
        Email.user_id == user.id,
        Email.deleted_at.isnot(None)
    ).all()
    
    logger.info(f"Found {len(saigbox_trash)} emails in SAIGBOX trash")
    
    fixed = 0
    failed = 0
    
    for email in saigbox_trash:
        # Check if email has TRASH label
        if email.labels and 'TRASH' in email.labels:
            logger.info(f"✅ {email.subject[:30]}... already has TRASH label")
            continue
        
        # Email is marked as deleted in SAIGBOX but not in Gmail trash
        logger.info(f"Fixing: {email.subject[:50]}...")
        
        if email.gmail_id:
            # Try to move to Gmail trash
            try:
                success = gmail_service.move_to_trash(user, email.gmail_id)
                if success:
                    # Update labels in database
                    if not email.labels:
                        email.labels = []
                    
                    # Remove INBOX if present
                    if 'INBOX' in email.labels:
                        email.labels.remove('INBOX')
                    
                    # Add TRASH label
                    if 'TRASH' not in email.labels:
                        email.labels.append('TRASH')
                    
                    db.commit()
                    logger.info(f"  ✅ Moved to Gmail trash")
                    fixed += 1
                else:
                    logger.error(f"  ❌ Failed to move to Gmail trash")
                    failed += 1
            except Exception as e:
                logger.error(f"  ❌ Error: {e}")
                failed += 1
        else:
            # No Gmail ID, just ensure it has proper labels
            if not email.labels:
                email.labels = []
            if 'TRASH' not in email.labels:
                email.labels.append('TRASH')
            if 'INBOX' in email.labels:
                email.labels.remove('INBOX')
            db.commit()
            logger.info(f"  ⚠️ No Gmail ID, updated labels only")
    
    # Step 2: Now do a full sync to get emails from Gmail trash
    logger.info("\n=== Running Full Sync ===")
    try:
        result = gmail_service.fetch_emails(db, user, max_results=50)
        logger.info(f"Synced {len(result.get('emails', []))} emails")
        
        # Check how many are in trash now
        trash_count = db.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.isnot(None)
        ).count()
        
        logger.info(f"Total emails in SAIGBOX trash after sync: {trash_count}")
        
    except Exception as e:
        logger.error(f"Sync error: {e}")
    
    # Step 3: Clean up - remove deleted_at from emails not in Gmail trash
    logger.info("\n=== Cleaning Up ===")
    emails_with_deleted = db.query(Email).filter(
        Email.user_id == user.id,
        Email.deleted_at.isnot(None)
    ).all()
    
    cleaned = 0
    for email in emails_with_deleted:
        if email.labels and 'TRASH' not in email.labels:
            # Email is marked as deleted but not in Gmail trash
            logger.info(f"Restoring: {email.subject[:50]}... (not in Gmail trash)")
            email.deleted_at = None
            cleaned += 1
    
    db.commit()
    
    logger.info(f"\n=== Summary ===")
    logger.info(f"Fixed (moved to Gmail trash): {fixed}")
    logger.info(f"Failed to fix: {failed}")
    logger.info(f"Restored (not in Gmail trash): {cleaned}")
    
    db.close()

if __name__ == "__main__":
    fix_trash_sync()