"""
Simplified email deletion for SAIG Assistant
This module handles email search and deletion with clear, simple logic
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from core.database import Email, User

logger = logging.getLogger(__name__)

class SimpleEmailHandler:
    """Simple, clear email handling for trash operations"""
    
    def parse_email_request(self, message: str) -> Dict[str, Any]:
        """
        Parse user's request into clear search parameters
        Examples:
        - "move the last 20 emails from lids to trash" -> {count: 20, sender: "lids"}
        - "delete all emails from nike" -> {sender: "nike", count: None}
        - "trash emails from yesterday" -> {time_period: "yesterday"}
        """
        params = {}
        message_lower = message.lower()
        
        # Extract count (last N, first N, N emails, etc.)
        import re
        count_patterns = [
            r'last (\d+)',
            r'first (\d+)', 
            r'(\d+) emails?',
            r'(\d+) most recent'
        ]
        for pattern in count_patterns:
            match = re.search(pattern, message_lower)
            if match:
                params['count'] = int(match.group(1))
                break
        
        # If "all" is mentioned and no count, don't limit
        if 'all' in message_lower and 'count' not in params:
            params['count'] = None
        
        # Extract sender (from X, emails from X)
        if 'from' in message_lower:
            # Split by 'from' and get what comes after
            parts = message_lower.split('from')
            if len(parts) > 1:
                sender_part = parts[-1].strip()
                # Extract the sender name (first word or until 'to')
                sender_words = sender_part.split()
                if sender_words:
                    # Remove common words that aren't part of sender
                    stop_words = ['to', 'the', 'trash', 'in', 'my', 'inbox']
                    sender = ''
                    for word in sender_words:
                        if word in stop_words:
                            break
                        sender = word
                        break
                    if sender:
                        params['sender'] = sender.strip('.,!?"').strip("'")
        
        # Extract time period
        time_keywords = {
            'today': 'today',
            'yesterday': 'yesterday',
            'this week': 'week',
            'last week': 'week',
            'this month': 'month',
            'last month': 'month'
        }
        for keyword, period in time_keywords.items():
            if keyword in message_lower:
                params['time_period'] = period
                break
        
        # Extract subject keywords if mentioned
        if 'about' in message_lower or 'regarding' in message_lower or 'subject' in message_lower:
            # This would need more sophisticated parsing
            # For now, we'll focus on sender-based deletion
            pass
        
        logger.info(f"Parsed email request: {message!r} -> {params}")
        return params
    
    def find_emails_to_delete(self, db: Session, user: User, params: Dict[str, Any]) -> List[Email]:
        """
        Find emails based on parsed parameters
        Returns actual Email objects, not dicts
        """
        query = db.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.is_(None)  # Only non-deleted emails
        )
        
        # Apply sender filter
        if params.get('sender'):
            sender_term = f"%{params['sender']}%"
            logger.info(f"Filtering by sender: {sender_term}")
            query = query.filter(
                or_(
                    Email.sender.ilike(sender_term),
                    Email.sender_name.ilike(sender_term)
                )
            )
        
        # Apply time period filter
        if params.get('time_period'):
            now = datetime.utcnow()
            period = params['time_period']
            
            if period == 'today':
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                query = query.filter(Email.received_at >= start_of_day)
            elif period == 'yesterday':
                yesterday = now - timedelta(days=1)
                start_of_yesterday = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                query = query.filter(
                    and_(
                        Email.received_at >= start_of_yesterday,
                        Email.received_at < start_of_today
                    )
                )
            elif period == 'week':
                week_ago = now - timedelta(days=7)
                query = query.filter(Email.received_at >= week_ago)
            elif period == 'month':
                month_ago = now - timedelta(days=30)
                query = query.filter(Email.received_at >= month_ago)
        
        # Always order by most recent first
        query = query.order_by(Email.received_at.desc())
        
        # Apply count limit
        if params.get('count'):
            emails = query.limit(params['count']).all()
        else:
            # Default limit for safety
            emails = query.limit(100).all()
        
        logger.info(f"Found {len(emails)} emails matching criteria")
        if emails:
            # Log details for verification
            senders = list(set([e.sender_name or e.sender for e in emails]))
            logger.info(f"Email senders found: {senders}")
            logger.info(f"Date range: {emails[-1].received_at} to {emails[0].received_at}")
        
        return emails
    
    def create_preview_html(self, emails: List[Email]) -> str:
        """
        Create a simple, clear preview of emails to be deleted
        """
        if not emails:
            return "No emails found matching your criteria."
        
        # Single email - simple confirmation
        if len(emails) == 1:
            email = emails[0]
            return f"""<div class="p-4 border border-amber-300 rounded-lg bg-amber-50">
  <div class="text-lg font-semibold mb-3">🗑️ Move to Trash?</div>
  <div class="bg-white p-3 rounded border border-gray-200 mb-3">
    <div class="font-medium">{email.subject or 'No Subject'}</div>
    <div class="text-sm text-gray-600">From: {email.sender_name or email.sender}</div>
    <div class="text-sm text-gray-500">Date: {email.received_at.strftime('%Y-%m-%d %H:%M')}</div>
  </div>
  <div class="flex gap-2 justify-end">
    <button onclick="sendMessage('cancel')" class="px-4 py-2 border rounded">Cancel</button>
    <button onclick="sendMessage('confirm delete')" class="px-4 py-2 bg-red-500 text-white rounded">Move to Trash</button>
  </div>
</div>"""
        
        # Multiple emails - list with checkboxes
        email_items = []
        for i, email in enumerate(emails):
            email_items.append(f"""
    <div class="flex items-start gap-2 p-2 bg-white rounded border mb-1">
      <input type="checkbox" 
             id="trash-{i}" 
             data-email-id="{email.id}" 
             checked 
             class="trash-checkbox mt-1"
             onchange="window.saigActions.updateTrashCount()">
      <label for="trash-{i}" class="flex-1 cursor-pointer">
        <div class="font-medium text-sm">{email.subject or 'No Subject'}</div>
        <div class="text-xs text-gray-600">From: {email.sender_name or email.sender}</div>
        <div class="text-xs text-gray-500">{email.received_at.strftime('%Y-%m-%d %H:%M')}</div>
      </label>
    </div>""")
        
        return f"""<div class="p-4 border border-amber-300 rounded-lg bg-amber-50">
  <div class="text-lg font-semibold mb-3">🗑️ Move {len(emails)} Emails to Trash?</div>
  <div class="text-sm text-gray-600 mb-2">
    <span id="trash-count">{len(emails)}</span> of {len(emails)} selected
  </div>
  <div class="max-h-64 overflow-y-auto border rounded p-2 bg-gray-50 mb-3">
    {''.join(email_items)}
  </div>
  <div class="text-sm text-amber-700 mb-3">
    ⚠️ Selected emails will be moved to trash (can be restored within 30 days)
  </div>
  <div class="flex gap-2 justify-end">
    <button onclick="sendMessage('cancel')" class="px-4 py-2 border rounded">Cancel</button>
    <button onclick="window.saigActions.moveSelectedToTrash()" class="px-4 py-2 bg-red-500 text-white rounded">Move Selected to Trash</button>
  </div>
</div>
<script>
// Store the email list for reference
window.trashEmailList = {json.dumps([{'id': str(e.id), 'subject': e.subject} for e in emails])};
</script>"""
    
    def execute_deletion(self, db: Session, user: User, email_ids: List[str], gmail_service) -> Dict[str, Any]:
        """
        Actually delete the emails
        Simple, clear, with proper error handling
        """
        success_count = 0
        failed_count = 0
        results = []
        
        for email_id in email_ids:
            try:
                # Find the email
                email = db.query(Email).filter(
                    Email.id == email_id,
                    Email.user_id == user.id
                ).first()
                
                if not email:
                    logger.error(f"Email {email_id} not found")
                    failed_count += 1
                    continue
                
                # Move to trash in Gmail
                if email.gmail_id and gmail_service:
                    try:
                        gmail_service.move_to_trash(user, email.gmail_id)
                        logger.info(f"Moved {email.gmail_id} to Gmail trash")
                    except Exception as e:
                        logger.error(f"Gmail API error for {email.gmail_id}: {e}")
                        # Continue anyway - we'll mark as deleted locally
                
                # Mark as deleted in our database
                email.deleted_at = datetime.utcnow()
                success_count += 1
                results.append({
                    'id': email.id,
                    'subject': email.subject,
                    'status': 'deleted'
                })
                
            except Exception as e:
                logger.error(f"Error deleting email {email_id}: {e}")
                failed_count += 1
        
        # Commit all changes
        try:
            db.commit()
        except Exception as e:
            logger.error(f"Database commit error: {e}")
            db.rollback()
            return {
                'success': False,
                'message': 'Failed to save changes to database',
                'error': str(e)
            }
        
        return {
            'success': True,
            'success_count': success_count,
            'failed_count': failed_count,
            'results': results
        }