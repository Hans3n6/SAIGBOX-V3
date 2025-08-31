#!/usr/bin/env python3
"""
Diagnose trash synchronization issues between Gmail and SAIGBOX
"""

import os
import sys
import logging
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from core.database import get_db, User, Email
from core.gmail_service import GmailService
from core.token_manager import token_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def diagnose_trash_sync():
    """Diagnose trash sync issues"""
    
    # Get database session
    db = next(get_db())
    
    # Get the most recent user
    user = db.query(User).order_by(User.last_login.desc()).first()
    
    if not user:
        logger.error("No user found")
        return
    
    logger.info(f"Diagnosing trash sync for user: {user.email}")
    
    # Step 1: Check SAIGBOX trash
    logger.info("\n=== SAIGBOX Trash ===")
    saigbox_trash = db.query(Email).filter(
        Email.user_id == user.id,
        Email.deleted_at.isnot(None)
    ).all()
    
    logger.info(f"Found {len(saigbox_trash)} emails in SAIGBOX trash")
    for email in saigbox_trash[:5]:  # Show first 5
        logger.info(f"  - {email.subject[:50]}... (gmail_id: {email.gmail_id}, deleted_at: {email.deleted_at})")
        if email.labels:
            logger.info(f"    Labels: {email.labels}")
    
    # Step 2: Check Gmail trash directly
    logger.info("\n=== Gmail Trash (Direct API) ===")
    gmail_service = GmailService()
    
    try:
        # Get OAuth tokens from user object
        if not user.oauth_access_token:
            logger.error("No OAuth tokens found")
            return
        
        # Create credentials
        creds = Credentials(
            token=user.oauth_access_token,
            refresh_token=user.oauth_refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.getenv('GOOGLE_CLIENT_ID'),
            client_secret=os.getenv('GOOGLE_CLIENT_SECRET')
        )
        
        # Build service
        service = build('gmail', 'v1', credentials=creds)
        
        # Query for emails in trash
        results = service.users().messages().list(
            userId='me',
            q='in:trash',
            maxResults=20
        ).execute()
        
        gmail_trash_ids = []
        messages = results.get('messages', [])
        logger.info(f"Found {len(messages)} emails in Gmail trash")
        
        for msg in messages[:5]:  # Show first 5
            msg_detail = service.users().messages().get(
                userId='me',
                id=msg['id']
            ).execute()
            
            gmail_trash_ids.append(msg['id'])
            
            # Get subject
            headers = msg_detail['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            labels = msg_detail.get('labelIds', [])
            
            logger.info(f"  - {subject[:50]}... (id: {msg['id']})")
            logger.info(f"    Labels: {labels}")
            
            # Check if this email exists in SAIGBOX
            exists_in_saigbox = db.query(Email).filter(
                Email.gmail_id == msg['id'],
                Email.user_id == user.id
            ).first()
            
            if exists_in_saigbox:
                if exists_in_saigbox.deleted_at:
                    logger.info(f"    ✅ Exists in SAIGBOX trash")
                else:
                    logger.warning(f"    ⚠️ Exists in SAIGBOX but NOT in trash (deleted_at: {exists_in_saigbox.deleted_at})")
            else:
                logger.warning(f"    ❌ NOT in SAIGBOX database at all")
        
        # Step 3: Compare
        logger.info("\n=== Comparison ===")
        saigbox_gmail_ids = set(e.gmail_id for e in saigbox_trash if e.gmail_id)
        gmail_trash_set = set(gmail_trash_ids)
        
        # Emails in SAIGBOX trash but not Gmail trash
        only_in_saigbox = saigbox_gmail_ids - gmail_trash_set
        if only_in_saigbox:
            logger.warning(f"Emails in SAIGBOX trash but NOT in Gmail trash: {len(only_in_saigbox)}")
            for gmail_id in list(only_in_saigbox)[:3]:
                email = next((e for e in saigbox_trash if e.gmail_id == gmail_id), None)
                if email:
                    logger.warning(f"  - {email.subject[:50]}... (deleted_at: {email.deleted_at})")
        
        # Emails in Gmail trash but not SAIGBOX trash
        only_in_gmail = gmail_trash_set - saigbox_gmail_ids
        if only_in_gmail:
            logger.warning(f"Emails in Gmail trash but NOT in SAIGBOX trash: {len(only_in_gmail)}")
        
        # Step 4: Check sync query
        logger.info("\n=== Testing Sync Query ===")
        # Test what our sync would fetch
        sync_results = service.users().messages().list(
            userId='me',
            q='-in:spam',  # Our current sync query
            maxResults=10
        ).execute()
        
        sync_messages = sync_results.get('messages', [])
        trash_in_sync = 0
        
        for msg in sync_messages:
            msg_detail = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='minimal'
            ).execute()
            
            if 'TRASH' in msg_detail.get('labelIds', []):
                trash_in_sync += 1
        
        logger.info(f"Sync query would fetch {trash_in_sync} trashed emails out of {len(sync_messages)}")
        
        # Step 5: Check for issues
        logger.info("\n=== Diagnosis ===")
        issues = []
        
        if only_in_saigbox:
            issues.append("SAIGBOX has emails marked as deleted that aren't in Gmail trash")
        
        if only_in_gmail:
            issues.append("Gmail has trashed emails that aren't marked as deleted in SAIGBOX")
        
        if trash_in_sync == 0:
            issues.append("Sync query is NOT fetching trashed emails")
        
        if issues:
            logger.error("Issues found:")
            for issue in issues:
                logger.error(f"  ❌ {issue}")
        else:
            logger.info("✅ Trash folders appear to be in sync")
        
    except Exception as e:
        logger.error(f"Error during diagnosis: {e}")
        import traceback
        traceback.print_exc()
    
    db.close()

if __name__ == "__main__":
    diagnose_trash_sync()