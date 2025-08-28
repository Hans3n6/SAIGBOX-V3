#!/usr/bin/env python3
"""
Force sync ALL emails from Gmail to local database
Run this to fetch all emails, not just recent ones
"""

import os
import sys
import logging
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from core.database import get_db, User
from core.gmail_service import GmailService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def force_sync_all_emails(user_email: str = None):
    """Force sync ALL emails from Gmail"""
    
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
    
    logger.info(f"Starting full sync for user: {user.email}")
    
    # Initialize Gmail service
    gmail_service = GmailService()
    
    # Sync emails with pagination
    total_synced = 0
    page_token = None
    page_num = 1
    
    while True:
        logger.info(f"Fetching page {page_num}...")
        
        try:
            result = gmail_service.fetch_emails(
                db=db,
                user=user,
                max_results=100,  # Fetch 100 at a time
                page_token=page_token
            )
            
            emails = result.get('emails', [])
            total_synced += len(emails)
            page_token = result.get('next_page_token')
            
            logger.info(f"Page {page_num}: Synced {len(emails)} emails. Total: {total_synced}")
            
            if not page_token:
                logger.info("No more pages. Sync complete!")
                break
            
            page_num += 1
            
            # Prevent infinite loops
            if page_num > 100:
                logger.warning("Reached maximum page limit (100 pages)")
                break
                
        except Exception as e:
            logger.error(f"Error during sync: {e}")
            break
    
    logger.info(f"Total emails synced: {total_synced}")
    db.close()

if __name__ == "__main__":
    # You can pass an email as argument, or it will use the most recent user
    user_email = sys.argv[1] if len(sys.argv) > 1 else None
    force_sync_all_emails(user_email)