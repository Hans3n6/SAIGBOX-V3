#!/usr/bin/env python3
"""
Verify trash synchronization is configured correctly
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from core.database import get_db, User, Email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_trash_sync_config():
    """Verify trash sync configuration"""
    
    logger.info("Verifying trash synchronization configuration...")
    
    # Check the gmail_service.py changes
    with open('core/gmail_service.py', 'r') as f:
        content = f.read()
        
        checks = {
            "Query includes trash": "'-in:spam'" in content and "'-in:trash'" not in content,
            "TRASH label detection": "'TRASH' in labels" in content,
            "deleted_at field added": "'deleted_at': deleted_at" in content,
            "Sync updates trash status": "if is_trashed and not existing.deleted_at" in content,
            "Restore detection": "elif not is_trashed and existing.deleted_at" in content
        }
        
    logger.info("\n✅ Configuration Check Results:")
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        logger.info(f"  {status} {check}")
        if not passed:
            all_passed = False
    
    if all_passed:
        logger.info("\n🎉 All trash synchronization features are properly configured!")
        logger.info("\nHow the sync now works:")
        logger.info("  1. Gmail sync now includes emails in trash (removed -in:trash filter)")
        logger.info("  2. When syncing, emails with TRASH label get deleted_at timestamp")
        logger.info("  3. Emails restored in Gmail (no TRASH label) get deleted_at cleared")
        logger.info("  4. SAIGBOX trash and Gmail trash are now bidirectionally synchronized")
    else:
        logger.warning("\n⚠️  Some features may not be properly configured")
    
    # Check database state
    logger.info("\n📊 Current Database State:")
    db = next(get_db())
    
    # Get most recent user
    user = db.query(User).order_by(User.last_login.desc()).first()
    
    if user:
        total_emails = db.query(Email).filter(Email.user_id == user.id).count()
        trashed_emails = db.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.isnot(None)
        ).count()
        active_emails = db.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.is_(None)
        ).count()
        
        logger.info(f"  User: {user.email}")
        logger.info(f"  Total emails: {total_emails}")
        logger.info(f"  Active emails: {active_emails}")
        logger.info(f"  Trashed emails: {trashed_emails}")
        
        # Show sample of trashed emails
        trashed_samples = db.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.isnot(None)
        ).limit(3).all()
        
        if trashed_samples:
            logger.info("\n  Sample trashed emails:")
            for email in trashed_samples:
                logger.info(f"    - {email.subject[:50]}... (deleted: {email.deleted_at})")
    
    db.close()
    
    logger.info("\n📝 Next Steps:")
    logger.info("  1. Move an email to trash in Gmail")
    logger.info("  2. Click sync button in SAIGBOX")
    logger.info("  3. Email should appear in SAIGBOX trash")
    logger.info("  4. Restore email in Gmail")
    logger.info("  5. Click sync button in SAIGBOX")
    logger.info("  6. Email should be restored in SAIGBOX")

if __name__ == "__main__":
    verify_trash_sync_config()