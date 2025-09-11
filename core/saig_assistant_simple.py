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
    
    def find_emails_to_delete_from_provider(self, db: Session, user: User, params: Dict[str, Any], gmail_service) -> List[Email]:
        """
        Search emails directly from Gmail/Outlook provider instead of local database
        This ensures we get ALL emails, not just synced ones
        """
        try:
            service = gmail_service.get_service(user)
            
            # Build Gmail search query
            gmail_query_parts = []
            
            # Add sender filter
            if params.get('sender'):
                gmail_query_parts.append(f'from:{params["sender"]}')
            
            # Add time period filter
            if params.get('time_period'):
                period = params['time_period']
                if period == 'today':
                    gmail_query_parts.append('newer_than:1d')
                elif period == 'yesterday':
                    gmail_query_parts.append('newer_than:2d older_than:1d')
                elif period == 'week':
                    gmail_query_parts.append('newer_than:7d')
                elif period == 'month':
                    gmail_query_parts.append('newer_than:30d')
            
            # Exclude spam and trash
            gmail_query_parts.append('-in:spam')
            gmail_query_parts.append('-in:trash')
            
            gmail_query = ' '.join(gmail_query_parts) if gmail_query_parts else '-in:spam -in:trash'
            
            # Determine how many to fetch
            max_results = params.get('count', 1000)
            if max_results > 2000:
                max_results = 2000  # Safety limit
            
            logger.info(f"Searching Gmail with query: {gmail_query}, max_results: {max_results}")
            
            # Fetch messages from Gmail
            results = service.users().messages().list(
                userId='me',
                q=gmail_query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            logger.info(f"Gmail returned {len(messages)} messages")
            
            if not messages:
                return []
            
            # Batch fetch message details for better performance
            emails = []
            batch_size = 50  # Process in batches to avoid timeouts
            
            for batch_start in range(0, min(len(messages), max_results), batch_size):
                batch_end = min(batch_start + batch_size, len(messages), max_results)
                batch_messages = messages[batch_start:batch_end]
                
                logger.info(f"Processing batch {batch_start//batch_size + 1}: emails {batch_start+1} to {batch_end}")
                
                for msg in batch_messages:
                    try:
                        # First check if email exists in database
                        existing = db.query(Email).filter(
                            Email.gmail_id == msg['id'],
                            Email.user_id == user.id
                        ).first()
                        
                        if existing:
                            # Email already synced, just use it
                            emails.append(existing)
                        else:
                            # Fetch minimal details for new emails
                            message = service.users().messages().get(
                                userId='me',
                                id=msg['id'],
                                format='metadata',  # Faster - only get metadata
                                metadataHeaders=['From', 'Subject', 'Date']
                            ).execute()
                            
                            # Parse minimal email data manually since we don't have gmail_service here
                            headers = {}
                            if 'payload' in message and 'headers' in message['payload']:
                                headers = {h['name']: h['value'] for h in message['payload']['headers']}
                            
                            # Parse received date
                            timestamp = int(message.get('internalDate', 0)) / 1000
                            received_at = datetime.fromtimestamp(timestamp) if timestamp else datetime.utcnow()
                            
                            email_data = {
                                'gmail_id': message['id'],
                                'thread_id': message.get('threadId'),
                                'subject': headers.get('Subject', 'No Subject'),
                                'sender': headers.get('From', 'Unknown'),
                                'sender_name': headers.get('From', '').split('<')[0].strip().strip('"') if '<' in headers.get('From', '') else headers.get('From', 'Unknown'),
                                'snippet': message.get('snippet', ''),
                                'received_at': received_at,
                                'is_read': 'UNREAD' not in message.get('labelIds', []),
                                'labels': message.get('labelIds', [])
                            }
                            
                            # Create new email record
                            new_email = Email(
                                user_id=user.id,
                                **email_data
                            )
                            db.add(new_email)
                            emails.append(new_email)
                            
                    except Exception as e:
                        logger.error(f"Error processing Gmail message {msg['id']}: {e}")
                        continue
                
                # Commit after each batch
                db.commit()
            
            # Commit database changes
            db.commit()
            
            logger.info(f"Fetched and synced {len(emails)} emails from Gmail")
            return emails
            
        except Exception as e:
            logger.error(f"Error searching Gmail: {e}")
            # Fall back to local database search
            logger.info("Falling back to local database search")
            return self.find_emails_to_delete(db, user, params)
    
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
            limit = min(params['count'], 2000)  # Increased cap to 2000
            emails = query.limit(limit).all()
            logger.info(f"Requested {params['count']} emails, applying limit {limit}, actually found {len(emails)} emails")
        else:
            # Default limit for safety when no count specified
            emails = query.limit(1000).all()  # Increased default to 1000
            logger.info(f"No specific count requested, using default limit 1000, actually found {len(emails)} emails")
        
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
        # Show all emails but limit display for performance
        display_limit = 1000  # Increased limit to show more emails
        emails_to_display = emails[:display_limit] if len(emails) > display_limit else emails
        
        logger.info(f"Creating preview for {len(emails)} emails, displaying {len(emails_to_display)} in UI")
        
        email_items = []
        for i, email in enumerate(emails_to_display):
            email_items.append(f"""
    <div class="flex items-start gap-2 p-2 bg-white rounded border mb-1 hover:bg-gray-50">
      <input type="checkbox" 
             id="saig-trash-{i}" 
             data-email-id="{email.id}" 
             checked 
             class="saig-trash-checkbox mt-1"
             onchange="saigPreviewUpdateCount()">
      <div class="flex-1 cursor-pointer" onclick="saigPreviewViewEmail('{email.id}')">
        <div class="font-medium text-sm">{email.subject[:50] + '...' if len(email.subject or '') > 50 else email.subject or 'No Subject'}</div>
        <div class="text-xs text-gray-600">From: {email.sender_name or email.sender}</div>
        <div class="text-xs text-gray-500">{email.received_at.strftime('%Y-%m-%d %H:%M')}</div>
      </div>
    </div>""")
        
        # Add indicator if there are more emails not shown in preview
        if len(emails) > display_limit:
            email_items.append(f"""
    <div class="p-2 text-center text-sm text-gray-500 italic">
      ... and {len(emails) - display_limit} more emails (all will be deleted)
    </div>""")
        
        # Determine scroll height based on number of emails
        if len(emails) > 50:
            scroll_height = "max-h-[32rem]"  # Extra tall for many emails
        elif len(emails) > 10:
            scroll_height = "max-h-96"  # Taller for moderate amount
        else:
            scroll_height = "max-h-64"  # Standard for few emails
        
        return f"""<div class="p-4 border border-amber-300 rounded-lg bg-amber-50">
  <div class="text-lg font-semibold mb-3">🗑️ Move <span id="saig-selected-count">{len(emails)}</span> Emails to Trash?</div>
  <div class="text-sm mb-2">
    <div class="text-gray-900 font-medium">Total emails found: {len(emails)}</div>
    <div class="text-gray-600"><span id="trash-count-display">{len(emails)} of {len(emails)}</span> emails selected</div>
    {f'<div class="text-amber-600 text-xs mt-1">⚠️ Showing {len(emails_to_display)} of {len(emails)} emails in preview (display limit: {display_limit})</div>' if len(emails) > display_limit else f'<div class="text-gray-500 text-xs mt-1">Showing all {len(emails)} emails</div>'}
  </div>
  <div class="mb-2 flex gap-2">
    <button onclick="saigPreviewSelectAll(true)" class="text-xs px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50">Select All</button>
    <button onclick="saigPreviewSelectAll(false)" class="text-xs px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50">Deselect All</button>
  </div>
  <div class="{scroll_height} overflow-y-auto border rounded p-2 bg-gray-50 mb-3">
    {''.join(email_items)}
  </div>
  <div class="text-sm text-amber-700 mb-3">
    ⚠️ Selected emails will be moved to trash (can be restored within 30 days)
    <div class="text-xs text-gray-500 mt-1">💡 Click on an email to view its content{' • Scroll to see all' if len(emails) > 5 else ''}</div>
  </div>
  <div class="flex gap-2 justify-end">
    <button onclick="sendMessage('cancel')" class="px-4 py-2 border rounded">Cancel</button>
    <button onclick="saigPreviewMoveToTrash()" class="px-4 py-2 bg-red-500 text-white rounded">Move <span id="saig-button-count">{len(emails)}</span> Selected to Trash</button>
  </div>
</div>
<script>
// Store the email list with more details for viewing
// Store ALL emails that will be deleted (not just displayed ones)
window.trashEmailList = {json.dumps([{'id': str(e.id), 'subject': e.subject, 'sender': e.sender_name or e.sender, 'date': e.received_at.strftime('%Y-%m-%d %H:%M'), 'snippet': e.snippet[:200] if e.snippet else ''} for e in emails])};
// Store displayed emails separately for UI
window.displayedEmails = {json.dumps([str(e.id) for e in emails_to_display])};

// Initialize the count display after a short delay to ensure DOM is ready
// The functions are defined in index.html to ensure they're available globally
setTimeout(function() {{
    if (typeof saigPreviewUpdateCount === 'function') {{
        saigPreviewUpdateCount();
    }}
}}, 100);
</script>"""
    
    def execute_deletion(self, db: Session, user: User, email_ids: List[str], email_service, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Actually delete the emails with batch processing to avoid timeouts
        Processes in chunks to handle large deletions
        """
        logger.info(f"Execute deletion called with {len(email_ids)} email IDs")
        logger.info(f"Email IDs to delete: {email_ids[:5]}..." if len(email_ids) > 5 else f"Email IDs to delete: {email_ids}")
        if params:
            logger.info(f"Original search params: {params}")
        
        # Process in batches to avoid timeouts
        BATCH_SIZE = 30  # Process 30 emails at a time
        total_success = 0
        total_failed = 0
        total_skipped = 0
        all_results = []
        all_deleted_details = []
        
        # Process emails in batches
        for batch_start in range(0, len(email_ids), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(email_ids))
            batch_ids = email_ids[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_start//BATCH_SIZE + 1}: emails {batch_start+1} to {batch_end} of {len(email_ids)}")
            
            success_count = 0
            failed_count = 0
            skipped_count = 0
            
            for email_id in batch_ids:
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
                    
                    # If params are provided, verify email matches the original criteria
                    if params and params.get('sender'):
                        sender_term = params['sender'].lower()
                        email_sender = (email.sender_name or email.sender or '').lower()
                        
                        if sender_term not in email_sender:
                            logger.warning(f"Skipping email {email_id} - sender '{email_sender}' doesn't match filter '{sender_term}'")
                            skipped_count += 1
                            continue
                    
                    # Log what we're about to delete
                    all_deleted_details.append(f"{email.sender_name or email.sender}: {email.subject[:30]}")
                    logger.debug(f"Deleting: ID={email_id}, From={email.sender_name or email.sender}, Subject={email.subject[:50]}")
                    
                    # Move to trash in email provider (Gmail or Outlook)
                    if email.gmail_id and email_service:
                        try:
                            # Gmail
                            email_service.move_to_trash(user, email.gmail_id)
                            logger.debug(f"Moved {email.gmail_id} to Gmail trash")
                        except Exception as e:
                            logger.warning(f"Gmail API error for {email.gmail_id}: {e}")
                            # Continue anyway - we'll mark as deleted locally
                    elif email.outlook_id and email_service:
                        try:
                            # Outlook - need to pass db for token management
                            from core.outlook_service import OutlookService
                            if isinstance(email_service, OutlookService):
                                email_service.move_to_trash(user, email.outlook_id, db)
                                logger.debug(f"Moved {email.outlook_id} to Outlook trash")
                        except Exception as e:
                            logger.warning(f"Outlook API error for {email.outlook_id}: {e}")
                            # Continue anyway - we'll mark as deleted locally
                    
                    # Mark as deleted in our database
                    email.deleted_at = datetime.utcnow()
                    success_count += 1
                    all_results.append({
                        'id': email.id,
                        'subject': email.subject,
                        'status': 'deleted'
                    })
                    
                except Exception as e:
                    logger.error(f"Error deleting email {email_id}: {e}")
                    failed_count += 1
            
            # Commit after each batch to save progress
            try:
                db.commit()
                logger.info(f"Batch {batch_start//BATCH_SIZE + 1} committed: {success_count} deleted, {failed_count} failed, {skipped_count} skipped")
            except Exception as e:
                logger.error(f"Database commit error for batch: {e}")
                db.rollback()
                # Don't fail entire operation - continue with next batch
            
            total_success += success_count
            total_failed += failed_count
            total_skipped += skipped_count
            
            # Small delay between batches to avoid overwhelming the server
            if batch_end < len(email_ids):
                import time
                time.sleep(0.1)  # 100ms delay between batches
        
        # Log summary of what was deleted
        if all_deleted_details:
            logger.info(f"Successfully deleted {total_success} emails total:")
            for detail in all_deleted_details[:5]:
                logger.info(f"  - {detail}")
            if len(all_deleted_details) > 5:
                logger.info(f"  ... and {len(all_deleted_details) - 5} more")
        
        if total_skipped > 0:
            logger.warning(f"Skipped {total_skipped} emails that didn't match original search criteria")
        
        return {
            'success': total_success > 0,
            'success_count': total_success,
            'failed_count': total_failed,
            'skipped_count': total_skipped,
            'results': all_results[:100]  # Limit results to avoid huge responses
        }