import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.database import Email, User, ChatHistory, ActionItem
from core.gmail_service import GmailService
from core.urgency_detector import UrgencyDetector
from core.saig_intelligence import SAIGIntelligence

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SAIGAssistant:
    def __init__(self):
        # Load Anthropic API key from environment
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
        
        if not self.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set. SAIG functionality will be limited.")
        else:
            logger.info("SAIG Assistant initialized with Anthropic API")
        
        self.gmail_service = GmailService()
        self.intelligence = SAIGIntelligence()  # Initialize intelligence module
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.http_client = httpx.AsyncClient(timeout=30.0)
        # Use Claude 3.5 Haiku for faster responses
        self.model = "claude-3-5-haiku-20241022"
    
    async def process_message(self, db: Session, user: User, message: str, 
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            logger.info(f"=== SAIG process_message ===")
            logger.info(f"User: {user.email}")
            logger.info(f"Message: {message}")
            logger.info("Context received: %s", json.dumps(context, default=str) if context else 'None')
            
            # Save user message to history
            user_msg = ChatHistory(user_id=user.id, role="user", message=message)
            db.add(user_msg)
            
            # Get email context if needed
            email_context = await self._get_email_context(db, user, message, context)
            logger.info("Email context built: %s", json.dumps(email_context, default=str) if email_context else 'None')
            
            # CRITICAL: Check if this is a confirmation for pending delete BEFORE analyzing intent
            if email_context.get('pending_delete'):
                logger.info("=== PENDING DELETE DETECTED - CHECKING FOR CONFIRMATION ===")
                # Check if this is a confirmation or cancellation
                message_lower = message.lower().strip()
                confirmation_keywords = ['yes', 'confirm', 'proceed', 'go ahead', 'sure', 'ok', 'move', 'trash', 'delete']
                cancellation_keywords = ['no', 'cancel', 'stop', 'wait', 'never', "don't", 'abort']
                
                # Check for confirmation
                if any(keyword in message_lower for keyword in confirmation_keywords):
                    logger.info("CONFIRMATION DETECTED - Using delete_email intent directly")
                    intent = 'delete_email'
                # Check for cancellation
                elif any(keyword in message_lower for keyword in cancellation_keywords):
                    logger.info("CANCELLATION DETECTED - Using delete_email intent to handle cancellation")
                    intent = 'delete_email'
                else:
                    # If unclear, still route to delete_email to handle the pending state
                    logger.info("UNCLEAR RESPONSE - Routing to delete_email to handle")
                    intent = 'delete_email'
            else:
                # Normal intent analysis
                intent = await self._analyze_intent(message, email_context)
            
            # Execute action based on intent
            response, actions = await self._execute_intent(db, user, intent, message, email_context)
            
            # Save assistant response to history
            assistant_msg = ChatHistory(user_id=user.id, role="assistant", message=response)
            db.add(assistant_msg)
            db.commit()
            
            # Return response with updated context
            result = {
                "response": response,
                "actions_taken": actions,
                "intent": intent,
                "context": email_context  # Return the context for frontend to maintain state
            }
            
            logger.info(f"=== Returning from process_message ===")
            logger.info(f"Intent: {intent}")
            logger.info(f"Actions taken: {actions}")
            logger.info("Context being returned: %s", json.dumps(email_context, default=str) if email_context else 'None')
            logger.info(f"Response length: {len(response)}")
            
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"Error processing SAIG message: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "response": f"I encountered an error: {str(e)}. Please try again.",
                "actions_taken": [],
                "intent": "error"
            }
    
    async def _get_email_context(self, db: Session, user: User, message: str, 
                                context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        email_context = {
            "recent_emails": [],
            "selected_email": None,
            "total_unread": 0,
            "total_emails": 0
        }
        
        # Preserve pending_delete if it exists in the context
        if context and 'pending_delete' in context:
            email_context['pending_delete'] = context['pending_delete']
            logger.info(f"Preserved pending_delete in email_context: {len(context['pending_delete'].get('emails', []))} emails")
        
        # Get email statistics
        email_context["total_emails"] = db.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.is_(None)
        ).count()
        
        email_context["total_unread"] = db.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.is_(None),
            Email.is_read == False
        ).count()
        
        # Get recent emails for context
        recent_emails = db.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.is_(None)
        ).order_by(Email.received_at.desc()).limit(10).all()
        
        email_context["recent_emails"] = [
            {
                "id": e.id,
                "subject": e.subject,
                "sender": e.sender_name or e.sender,
                "snippet": e.snippet,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "is_read": e.is_read
            }
            for e in recent_emails
        ]
        
        # Get selected email if provided in context
        if context and context.get("email_id"):
            email = db.query(Email).filter(
                Email.id == context["email_id"],
                Email.user_id == user.id
            ).first()
            if email:
                email_context["selected_email"] = {
                    "id": email.id,
                    "gmail_id": email.gmail_id,
                    "thread_id": email.thread_id,
                    "subject": email.subject,
                    "sender": email.sender,
                    "sender_name": email.sender_name,
                    "body": email.body_text or email.body_html or email.snippet,
                    "received_at": email.received_at.isoformat() if email.received_at else None
                }
            # If email not found in DB but context has selected_email, preserve it
            elif context.get("selected_email"):
                email_context["selected_email"] = context["selected_email"]
                logger.info(f"Preserved selected_email from context (DB lookup failed): {email_context['selected_email'].get('subject', 'Unknown')}")
        # If context already has selected_email (e.g., from frontend), preserve it
        elif context and context.get("selected_email"):
            email_context["selected_email"] = context["selected_email"]
            logger.info(f"Preserved selected_email from context: {email_context['selected_email'].get('subject', 'Unknown')}")
        
        # Preserve any other context keys that might be needed
        if context:
            for key in context:
                if key not in email_context and key not in ['email_id', 'selected_email']:
                    email_context[key] = context[key]
                    logger.info(f"Preserved additional context key: {key}")
        
        return email_context
    
    async def _call_anthropic(self, prompt: str, max_tokens: int = 300, temperature: float = 0.3) -> str:
        """Helper method to call Anthropic API with Claude 3.5 Haiku"""
        if not self.anthropic_api_key:
            return "Anthropic API not configured. Please set ANTHROPIC_API_KEY in your .env file."
        
        try:
            headers = {
                "x-api-key": self.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            
            data = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            response = await self.http_client.post(
                self.api_url,
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                return result['content'][0]['text']
            else:
                error_msg = f"API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return f"Error calling Anthropic API: {error_msg}"
                
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            return f"Error processing request: {str(e)}"
    
    async def _analyze_intent(self, message: str, context: Dict[str, Any]) -> str:
        # Check for explicit reply intent
        if "Please read this email and generate" in message or "Reply to this email" in message.lower():
            return 'reply_email'
            
        prompt = f"""Analyze the user's message and determine their intent.
        
User message: {message}

Available intents:
- search_emails: User wants to find specific emails
- compose_email: User wants to write/send a new email
- reply_email: User wants to reply to a specific email
- mark_read: User wants to mark emails as read
- mark_unread: User wants to mark emails as unread
- summarize: User wants a summary of emails or a specific email
- create_action: User wants to create an action item
- list_actions: User wants to see action items
- delete_email: User wants to delete/trash emails
- move_to_folder: User wants to move emails to a folder/label
- create_folder: User wants to create a new folder/label
- list_folders: User wants to see available folders/labels
- star_email: User wants to star/favorite emails
- general_question: General question about emails or the system
- help: User needs help or instructions

Context:
- Total emails: {context['total_emails']}
- Unread emails: {context['total_unread']}
- Has selected email: {context['selected_email'] is not None}

Return only the intent name, nothing else."""

        try:
            intent = await self._call_anthropic(prompt, max_tokens=50, temperature=0.3)
            intent = intent.strip().lower()
            
            # Validate intent
            valid_intents = ['search_emails', 'compose_email', 'reply_email', 'mark_read', 'mark_unread', 
                           'summarize', 'create_action', 'list_actions', 'delete_email', 
                           'move_to_folder', 'create_folder', 'list_folders',
                           'star_email', 'general_question', 'help',
                           'analyze_patterns', 'extract_actions', 'categorize_emails', 'show_insights']
            
            if intent not in valid_intents:
                intent = 'general_question'
            
            return intent
            
        except Exception as e:
            logger.error(f"Error analyzing intent: {e}")
            return 'general_question'
    
    async def _execute_intent(self, db: Session, user: User, intent: str, 
                             message: str, context: Dict[str, Any]) -> tuple:
        actions = []
        logger.info(f"Executing intent: {intent}, Context has selected_email: {'selected_email' in context}")
        
        if intent == 'search_emails':
            response, actions = await self._search_emails(db, user, message)
        elif intent == 'compose_email':
            response, actions = await self._compose_email(db, user, message, context)
        elif intent == 'reply_email':
            response, actions = await self._reply_email(db, user, message, context)
        elif intent == 'mark_read':
            response, actions = await self._mark_emails_read(db, user, message, context)
        elif intent == 'summarize':
            response = await self._summarize_emails(context)
        elif intent == 'create_action':
            response, actions = await self._create_action_item(db, user, message, context)
        elif intent == 'list_actions':
            response = await self._list_action_items(db, user)
        elif intent == 'delete_email':
            response, actions = await self._delete_email(db, user, message, context)
        elif intent == 'move_to_folder':
            response, actions = await self._move_to_folder(db, user, message, context)
        elif intent == 'create_folder':
            response, actions = await self._create_folder(db, user, message)
        elif intent == 'list_folders':
            response = await self._list_folders(user)
        elif intent == 'analyze_patterns':
            response = await self._analyze_patterns(db, user)
        elif intent == 'extract_actions':
            response, actions = await self._extract_actions_from_emails(db, user, message, context)
        elif intent == 'categorize_emails':
            response, actions = await self._categorize_emails(db, user)
        elif intent == 'show_insights':
            response = await self._show_insights(db, user)
        elif intent == 'help':
            response = self._get_help_message()
        else:
            response = await self._generate_response(message, context)
        
        return response, actions
    
    async def _search_emails(self, db: Session, user: User, message: str) -> tuple:
        # Extract search query
        prompt = f"""Extract the search query from this message: {message!r}
Return only the search terms, nothing else."""
        
        try:
            search_query = await self._call_anthropic(prompt, max_tokens=100, temperature=0.3)
            search_query = search_query.strip()
            
            # Search emails
            emails = db.query(Email).filter(
                Email.user_id == user.id,
                Email.deleted_at.is_(None),
                (Email.subject.contains(search_query) | 
                 Email.sender.contains(search_query) |
                 Email.body_text.contains(search_query))
            ).limit(5).all()
            
            if emails:
                response = f"I found {len(emails)} email(s) matching '{search_query}':\n\n"
                for email in emails:
                    response += f"• {email.subject} - from {email.sender_name or email.sender}\n"
            else:
                response = f"No emails found matching '{search_query}'."
            
            return response, ["searched_emails"]
            
        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            return "I encountered an error while searching. Please try again.", []
    
    async def _mark_emails_read(self, db: Session, user: User, message: str, 
                               context: Dict[str, Any]) -> tuple:
        if context.get('selected_email'):
            email = db.query(Email).filter(
                Email.id == context['selected_email']['id'],
                Email.user_id == user.id
            ).first()
            
            if email and not email.is_read:
                # Mark in Gmail
                if self.gmail_service.mark_as_read(user, email.gmail_id):
                    email.is_read = True
                    db.commit()
                    return f"Marked '{email.subject}' as read.", ["marked_read"]
                else:
                    return "Failed to mark email as read. Please try again.", []
            else:
                return "This email is already marked as read.", []
        else:
            # Mark all unread emails as read
            unread_count = context['total_unread']
            if unread_count > 0:
                return f"You have {unread_count} unread emails. Would you like to mark all as read?", []
            else:
                return "You have no unread emails.", []
    
    async def _summarize_emails(self, context: Dict[str, Any]) -> str:
        if context.get('selected_email'):
            email = context['selected_email']
            prompt = f"""Summarize this email in 2-3 sentences:
Subject: {email['subject']}
From: {email['sender']}
Body: {email['body'][:1000]}"""
        else:
            recent = context['recent_emails'][:5]
            if not recent:
                return "You have no recent emails to summarize."
            
            prompt = f"""Summarize these recent emails in bullet points:
{json.dumps(recent, indent=2)}"""
        
        try:
            summary = await self._call_anthropic(prompt, max_tokens=300, temperature=0.5)
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "I couldn't generate a summary at this time."
    
    async def _create_action_item(self, db: Session, user: User, message: str, 
                                 context: Dict[str, Any]) -> tuple:
        # Extract action item details from message
        prompt = f"""Extract action item details from this message: {message!r}
Return as JSON with keys: title, description, priority (high/medium/low), due_date (ISO format or null)"""
        
        try:
            action_json = await self._call_anthropic(prompt, max_tokens=200, temperature=0.3)
            action_data = json.loads(action_json.strip())
            
            # Map priority
            priority_map = {'high': 1, 'medium': 2, 'low': 3}
            priority = priority_map.get(action_data.get('priority', 'medium'), 2)
            
            # Create action item
            action = ActionItem(
                user_id=user.id,
                title=action_data.get('title', 'New Action Item'),
                description=action_data.get('description'),
                priority=priority,
                email_id=context.get('selected_email', {}).get('id')
            )
            
            if action_data.get('due_date'):
                try:
                    action.due_date = datetime.fromisoformat(action_data['due_date'])
                except:
                    pass
            
            db.add(action)
            db.commit()
            
            return f"Created action item: {action.title}", ["created_action"]
            
        except Exception as e:
            logger.error(f"Error creating action item: {e}")
            return "I couldn't create the action item. Please provide more details.", []
    
    async def _list_action_items(self, db: Session, user: User) -> str:
        actions = db.query(ActionItem).filter(
            ActionItem.user_id == user.id,
            ActionItem.status == 'pending'
        ).order_by(ActionItem.priority, ActionItem.created_at).limit(10).all()
        
        if not actions:
            return "You have no pending action items."
        
        response = f"You have {len(actions)} pending action item(s):\n\n"
        for action in actions:
            priority = {1: "High", 2: "Medium", 3: "Low"}.get(action.priority, "Medium")
            response += f"• [{priority}] {action.title}"
            if action.due_date:
                response += f" (Due: {action.due_date.strftime('%Y-%m-%d')})"
            response += "\n"
        
        return response
    
    async def _find_emails_by_description(self, db: Session, user: User, description: str) -> List[Dict]:
        """Find emails based on natural language description
        
        IMPORTANT: When searching for emails FROM a specific sender, ONLY search sender fields.
        """
        
        # Extract search criteria from description
        # Use format() to avoid issues with braces in the description
        prompt = """Extract email search criteria from this description: {desc}
        
IMPORTANT RULES:
1. If the description mentions "from [sender]" or "emails from [sender]" or "all emails from [sender]", 
   ONLY return the sender field. DO NOT include subject or content fields.
2. If the description mentions "about [topic]" or "regarding [topic]", search subject and content.
3. If both sender AND topic are mentioned, include both.

Return as JSON with any of these fields that apply:
- sender: email address or name of sender (ONLY if "from" is mentioned)
- subject: keywords from subject line (ONLY if topic/about/regarding is mentioned, NOT for sender searches)
- time_period: recent/today/yesterday/last_week/last_month/older_than_X
- read_status: read/unread
- has_attachments: true/false
- content: keywords from email body (ONLY if searching for content, NOT for sender searches)
- count: number of emails if specified (e.g. "last 5 emails", "last 20 emails", "10 most recent")

Examples:
- "delete all emails from Lids" → {"sender": "Lids"}
- "move the last 20 emails from Lids to trash" → {"sender": "Lids", "count": 20}
- "delete emails about promotions" → {"subject": "promotions", "content": "promotions"}
- "delete recent emails from Nike about sales" → {"sender": "Nike", "subject": "sales"}
- "move all emails from john@example.com to trash" → {"sender": "john@example.com"}

If the description mentions "all" or doesn't specify a limit, set count to null.
If a specific number is mentioned (e.g., "last 20", "first 10"), set count to that number.
Return only the fields that are clearly mentioned.
NEVER include subject or content when only searching for sender."""
        # Replace the placeholder with the description safely
        prompt = prompt.replace("{desc}", repr(description))

        try:
            criteria_json = await self._call_anthropic(prompt, max_tokens=200, temperature=0.3)
            
            # Check if this is an error response
            if criteria_json.startswith("Error"):
                logger.warning(f"API error response: {criteria_json}")
                # Fallback: try to extract sender from the description directly
                criteria = {}
                description_lower = description.lower()
                if 'from' in description_lower:
                    # Extract sender after "from"
                    parts = description_lower.split('from')
                    if len(parts) > 1:
                        sender_part = parts[1].strip()
                        # Remove quotes and get first word/email
                        sender = sender_part.split()[0].strip('"\'{}')
                        criteria['sender'] = sender
                        logger.info(f"Fallback: extracted sender '{sender}' from description")
            else:
                # Try to parse the JSON response
                try:
                    parsed = json.loads(criteria_json.strip())
                    # Check if the parsed result is a dictionary
                    if isinstance(parsed, dict):
                        criteria = parsed
                    else:
                        # API returned a non-dict (like a plain string)
                        logger.warning(f"API returned non-dict JSON: {parsed!r} (type: {type(parsed)})")
                        # Use fallback extraction
                        criteria = {}
                        description_lower = description.lower()
                        if 'from' in description_lower:
                            parts = description_lower.split('from')
                            if len(parts) > 1:
                                sender_part = parts[1].strip()
                                sender = sender_part.split()[0].strip('"\'{}')
                                criteria['sender'] = sender
                                logger.info(f"Fallback: extracted sender '{sender}' from description")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse AI response as JSON: {e}")
                    # Fallback extraction
                    criteria = {}
                    description_lower = description.lower()
                    if 'from' in description_lower:
                        parts = description_lower.split('from')
                        if len(parts) > 1:
                            sender_part = parts[1].strip()
                            sender = sender_part.split()[0].strip('"\'{}')
                            criteria['sender'] = sender
                            logger.info(f"Fallback: extracted sender '{sender}' from description")
            
            logger.info("=== Email Search Criteria ===")
            logger.info("Description: %r", description)
            logger.info("Extracted criteria: %s", json.dumps(criteria, indent=2))
            
            # Build query
            query = db.query(Email).filter(
                Email.user_id == user.id,
                Email.deleted_at.is_(None)
            )
            
            # Apply filters based on criteria
            if criteria.get('sender'):
                sender_term = f"%{criteria['sender']}%"
                logger.info("Searching for sender: %r (ONLY in sender fields)", sender_term)
                query = query.filter(
                    or_(
                        Email.sender.ilike(sender_term),
                        Email.sender_name.ilike(sender_term)
                    )
                )
                # Log warning if subject/content were incorrectly included
                if criteria.get('subject') or criteria.get('content'):
                    logger.warning(f"⚠️ Subject/content fields ignored for sender-only search")
            
            if criteria.get('subject'):
                query = query.filter(Email.subject.ilike(f"%{criteria['subject']}%"))
            
            if criteria.get('content'):
                content_term = f"%{criteria['content']}%"
                query = query.filter(
                    or_(
                        Email.body_text.ilike(content_term),
                        Email.snippet.ilike(content_term)
                    )
                )
            
            if criteria.get('read_status'):
                if criteria['read_status'] == 'read':
                    query = query.filter(Email.is_read == True)
                elif criteria['read_status'] == 'unread':
                    query = query.filter(Email.is_read == False)
            
            if criteria.get('has_attachments'):
                query = query.filter(Email.has_attachments == True)
            
            # Handle time periods
            if criteria.get('time_period'):
                now = datetime.utcnow()
                time_period = criteria['time_period'].lower()
                
                if 'today' in time_period:
                    query = query.filter(Email.received_at >= now.replace(hour=0, minute=0, second=0))
                elif 'yesterday' in time_period:
                    yesterday = now - timedelta(days=1)
                    query = query.filter(
                        Email.received_at >= yesterday.replace(hour=0, minute=0, second=0),
                        Email.received_at < now.replace(hour=0, minute=0, second=0)
                    )
                elif 'last_week' in time_period or 'last week' in time_period:
                    query = query.filter(Email.received_at >= now - timedelta(days=7))
                elif 'last_month' in time_period or 'last month' in time_period:
                    query = query.filter(Email.received_at >= now - timedelta(days=30))
                elif 'older_than' in time_period:
                    # Extract number of days
                    import re
                    days_match = re.search(r'\d+', time_period)
                    if days_match:
                        days = int(days_match.group())
                        query = query.filter(Email.received_at < now - timedelta(days=days))
            
            # Apply count limit if specified
            if criteria.get('count'):
                emails = query.order_by(Email.received_at.desc()).limit(criteria['count']).all()
            else:
                # Default to reasonable limit for safety
                # User will see exactly what will be deleted in the preview
                emails = query.order_by(Email.received_at.desc()).limit(50).all()
                logger.info(f"Found {len(emails)} emails (limited to 50 for safety)")
            
            logger.info(f"Search found {len(emails)} emails")
            if emails:
                logger.info("Sample results (first 3):")
                for i, email in enumerate(emails[:3]):
                    logger.info("  %d. From: %r | Subject: %r", 
                               i+1, email.sender_name or email.sender, email.subject)
            
            # Convert to dict format
            return [
                {
                    'id': e.id,
                    'gmail_id': e.gmail_id,
                    'subject': e.subject,
                    'sender': e.sender_name or e.sender,
                    'date': e.received_at,
                    'is_read': e.is_read
                }
                for e in emails
            ]
            
        except Exception as e:
            logger.error(f"Error finding emails by description: {e}", exc_info=True)
            # Don't raise the exception, just return empty list
            return []
    
    async def _delete_email(self, db: Session, user: User, message: str, 
                           context: Dict[str, Any]) -> tuple:
        """Move email to trash - SINGLE PATHWAY for all trash operations
        
        This is the ONLY method that should handle email deletion/trash operations.
        All trash requests must go through this method with proper context.
        """
        
        logger.info(f"=== _delete_email called (SINGLE TRASH PATHWAY) ===")
        logger.info(f"Message: {message!r}")
        logger.info(f"Context has pending_delete: {'pending_delete' in context}")
        if 'pending_delete' in context:
            logger.info("Pending delete content: %s", json.dumps(context['pending_delete'], default=str))
        
        # Check if user is confirming a previous delete request
        if context.get('pending_delete'):
            # Log the confirmation attempt
            logger.info(f"=== CONFIRMATION PATH ENTERED ===")
            logger.info(f"Processing trash confirmation: {message!r}")
            logger.info(f"Number of emails in pending_delete: {len(context['pending_delete'].get('emails', []))}")
            logger.info(f"First 3 emails to delete: {context['pending_delete']['emails'][:3] if context['pending_delete'].get('emails') else 'None'}")
            
            # Check for various confirmation messages
            confirmation_phrases = [
                'yes', 'confirm', 'proceed', 'go ahead', 'sure', 'ok',
                'move to trash', 'move all to trash', 'yes, move', 'yes move',
                'move them', 'delete', 'trash them', 'yes, move all', 'yes move all to trash',
                'move selected to trash', 'selected email', 'selected emails to trash'
            ]
            message_lower = message.lower().strip().replace(',', '').replace('.', '')
            
            # Log for debugging
            logger.info(f"Checking confirmation - Original message: '{message}'")
            logger.info(f"Checking confirmation - Normalized message: '{message_lower}'")
            
            # Check if message contains any confirmation phrase or pattern for selected emails
            is_confirmed = any(phrase in message_lower for phrase in confirmation_phrases)
            
            # Also check for the pattern "Move X selected email(s) to trash"
            if not is_confirmed:
                import re
                selected_pattern = r'move \d+ selected email[s]? to trash'
                is_confirmed = bool(re.search(selected_pattern, message_lower))
            
            # Also check for exact matches
            if not is_confirmed:
                is_confirmed = message_lower in confirmation_phrases
            
            logger.info(f"Confirmation result: {is_confirmed} for message: '{message_lower}'")
            
            if is_confirmed:
                # Execute the pending delete
                pending = context['pending_delete']
                success_count = 0
                failed_count = 0
                
                logger.info(f"=== EXECUTING TRASH ACTION (VALIDATED) ====")
                logger.info(f"Processing trash request for {len(pending['emails'])} emails")
                logger.info(f"User confirmed with message: {message!r}")
                
                # Validate email list
                if not pending.get('emails') or len(pending['emails']) == 0:
                    logger.error("No emails in pending_delete list!")
                    return "Error: No emails to delete. Please select emails first.", ["error"]
                
                for i, email_data in enumerate(pending['emails']):
                    logger.info(f"=== Processing email {i+1}/{len(pending['emails'])} ===")
                    logger.info(f"Looking for email with ID: {email_data['id']}")
                    logger.info("Email data from pending: %s", json.dumps(email_data, default=str))
                    
                    email = db.query(Email).filter(
                        Email.id == email_data['id'],
                        Email.user_id == user.id
                    ).first()
                    
                    if email:
                        # VALIDATION: Ensure this email matches what was shown in preview
                        if email.subject != email_data.get('subject'):
                            logger.warning(f"⚠️ Subject mismatch! DB: '{email.subject}' vs Preview: '{email_data.get('subject')}'")
                        
                        logger.info(f"Moving email {email.id} to trash (gmail_id: {email.gmail_id})")
                        logger.info(f"Email subject: {email.subject}")
                        logger.info(f"Email sender: {email.sender}")
                        
                        # Try to move to trash in Gmail with comprehensive error handling
                        try:
                            if not email.gmail_id:
                                logger.error(f"Email {email.id} has no gmail_id!")
                                failed_count += 1
                                continue
                                
                            gmail_result = self.gmail_service.move_to_trash(user, email.gmail_id)
                            logger.info(f"Gmail move_to_trash result for {email.gmail_id}: {gmail_result}")
                            
                            # Always update local database, even if Gmail API fails
                            email.deleted_at = datetime.utcnow()
                            
                            # Update labels to reflect trash status
                            if not email.labels:
                                email.labels = []
                            
                            # Add TRASH label
                            if 'TRASH' not in email.labels:
                                email.labels.append('TRASH')
                            
                            # Remove INBOX label if present
                            if 'INBOX' in email.labels:
                                email.labels.remove('INBOX')
                            
                            if gmail_result:
                                success_count += 1
                                logger.info(f"✅ Successfully moved email {email.id} to trash at {email.deleted_at}")
                            else:
                                # Still mark as success since we updated locally
                                success_count += 1
                                logger.warning(f"⚠️ Gmail API failed but locally moved email {email.id} to trash")
                        except Exception as e:
                            logger.error(f"❌ Exception moving email {email.id} to trash: {e}")
                            
                            # Still update locally even if Gmail API throws exception
                            try:
                                email.deleted_at = datetime.utcnow()
                                
                                # Update labels
                                if not email.labels:
                                    email.labels = []
                                if 'TRASH' not in email.labels:
                                    email.labels.append('TRASH')
                                if 'INBOX' in email.labels:
                                    email.labels.remove('INBOX')
                                
                                success_count += 1
                                logger.warning(f"⚠️ Gmail API exception but locally moved email {email.id} to trash")
                            except Exception as db_error:
                                failed_count += 1
                                logger.error(f"❌ Failed to update database: {db_error}")
                                # Store error for potential recovery
                                if 'failed_emails' not in context:
                                    context['failed_emails'] = []
                                context['failed_emails'].append({
                                    'id': email.id,
                                    'gmail_id': email.gmail_id,
                                    'error': str(e)
                                })
                    else:
                        failed_count += 1
                        logger.error(f"❌ Email not found in database: {email_data['id']}")
                        logger.error("Was looking for: %s", json.dumps(email_data, default=str))
                
                db.commit()
                logger.info(f"Database commit completed. Success: {success_count}, Failed: {failed_count}")
                
                # Clear the pending delete from context after processing
                if 'pending_delete' in context:
                    del context['pending_delete']
                
                if success_count > 0:
                    # Create a success message with better formatting
                    if success_count == 1:
                        result = f"""<div class="rounded-lg border border-green-200 bg-green-50 p-3">
  <div class="flex">
    <div class="flex-shrink-0">
      <svg class="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
      </svg>
    </div>
    <div class="ml-3">
      <p class="text-sm text-green-800">
        Email moved to trash successfully. You can restore it from trash within 30 days.
      </p>
    </div>
  </div>
</div>"""
                    else:
                        result = f"""<div class="rounded-lg border border-green-200 bg-green-50 p-3">
  <div class="flex">
    <div class="flex-shrink-0">
      <svg class="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
      </svg>
    </div>
    <div class="ml-3">
      <p class="text-sm text-green-800">
        Successfully moved {success_count} emails to trash. You can restore them within 30 days.
        {f'<br/><span class="text-orange-600">{failed_count} email(s) could not be moved.</span>' if failed_count > 0 else ''}
      </p>
    </div>
  </div>
</div>"""
                    return result, ["emails_moved_to_trash"]
                else:
                    # Clear pending delete from context even on failure
                    if 'pending_delete' in context:
                        del context['pending_delete']
                    return """<div class="rounded-lg border border-red-200 bg-red-50 p-3">
  <div class="flex">
    <div class="flex-shrink-0">
      <svg class="h-5 w-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
      </svg>
    </div>
    <div class="ml-3">
      <p class="text-sm text-red-800">
        Failed to move emails to trash. Please try again.
      </p>
    </div>
  </div>
</div>""", []
            else:
                # Clear pending delete from context on cancel
                logger.info(f"User cancelled trash action with message: {message!r}")
                if 'pending_delete' in context:
                    del context['pending_delete']
                return """<div class="rounded-lg border border-gray-200 bg-gray-50 p-3">
  <div class="flex">
    <div class="flex-shrink-0">
      <svg class="h-5 w-5 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.293l-3-3a1 1 0 00-1.414 1.414L10.586 9.5H5a1 1 0 100 2h5.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clip-rule="evenodd"/>
      </svg>
    </div>
    <div class="ml-3">
      <p class="text-sm text-gray-700">
        Action cancelled. No emails were moved.
      </p>
    </div>
  </div>
</div>""", []
        
        # First try to find emails based on the message
        logger.info(f"=== Finding emails to delete based on: {message!r} ===")
        emails_to_delete = await self._find_emails_by_description(db, user, message)
        logger.info(f"Found {len(emails_to_delete) if emails_to_delete else 0} emails to delete")
        if emails_to_delete:
            logger.info("First 3 emails to delete: %s", json.dumps(emails_to_delete[:3], default=str))
            # Log the senders to verify we got the right emails
            senders = list(set([e.get('sender', 'Unknown') for e in emails_to_delete]))
            logger.info(f"Senders of emails to delete: {senders}")
        
        # If no emails found by description and there's a selected email, use that
        if not emails_to_delete and context.get('selected_email'):
            selected_email = context['selected_email']
            email = db.query(Email).filter(
                Email.id == selected_email['id'],
                Email.user_id == user.id
            ).first()
            if email:
                emails_to_delete = [{
                    'id': email.id,
                    'subject': email.subject,
                    'sender': email.sender_name or email.sender,
                    'date': email.received_at
                }]
        
        if not emails_to_delete:
            # Be specific about what was searched
            if 'from' in message.lower():
                parts = message.lower().split('from')
                if len(parts) > 1:
                    sender = parts[1].strip().split()[0]
                    return f"I couldn't find any emails from '{sender}'. Please check the sender name and try again.", []
            return "I couldn't find any emails matching that description. Please be more specific or select an email first.", []
        
        # Create simple, compact confirmation message
        if len(emails_to_delete) == 1:
            email = emails_to_delete[0]
            
            confirm_msg = f"""<div class="p-4 border border-amber-300 rounded-lg bg-amber-50" style="width: 100%; box-sizing: border-box;">
  <div class="text-base font-semibold text-gray-900 mb-3">🗑️ Move to Trash?</div>
  <div class="text-sm text-gray-600 mb-3">This email will be moved to trash:</div>
  <div class="bg-white p-3 rounded border border-gray-200 mb-3" style="overflow: hidden;">
    <div class="text-sm font-medium text-gray-900 truncate">{email['subject'] or 'No Subject'}</div>
    <div class="text-sm text-gray-500 truncate">From: {email['sender']}</div>
  </div>
  <div class="text-sm text-amber-700 mb-4">↩️ You can restore within 30 days</div>
  <div class="flex gap-3 justify-end">
    <button data-action="send-message" data-message="Cancel" onclick="sendMessage('Cancel')" class="px-4 py-2 text-sm border border-gray-300 rounded bg-white hover:bg-gray-50">Cancel</button>
    <button data-action="send-message" data-message="Yes, move to trash" onclick="sendMessage('Yes, move to trash')" class="px-4 py-2 text-sm rounded text-white bg-red-500 hover:bg-red-600">Move to Trash</button>
  </div>
</div>"""
        else:
            # Multiple emails - show ALL emails in scrollable list with checkboxes
            email_items_html = ""
            for i, email in enumerate(emails_to_delete):
                # Generate unique ID for checkbox
                checkbox_id = f"trash-email-{i}"
                email_items_html += f"""
    <div class="bg-white p-2 mb-1.5 rounded border border-gray-200 hover:bg-gray-50 transition-colors" style="overflow: hidden;">
      <div class="flex items-start gap-2">
        <input type="checkbox" id="{checkbox_id}" data-email-id="{email['id']}" checked 
               class="mt-1 trash-email-checkbox" 
               onchange="updateTrashCount()">
        <div class="flex-1 cursor-pointer" onclick="viewEmailFromPreview('{email['id']}')">
          <div class="text-sm font-medium text-gray-900 truncate">{email['subject'] or 'No Subject'}</div>
          <div class="text-xs text-gray-500 truncate">From: {email['sender']}</div>
          <div class="text-xs text-gray-400 truncate">Date: {str(email['date'])[:10] if email.get('date') else 'Unknown'}</div>
        </div>
      </div>
    </div>"""
            
            confirm_msg = f"""<div class="p-4 border border-amber-300 rounded-lg bg-amber-50" style="width: 100%; box-sizing: border-box;">
  <div class="text-base font-semibold text-gray-900 mb-3">🗑️ Move Emails to Trash?</div>
  <div class="text-sm text-gray-600 mb-2">
    <span id="trash-count-display">{len(emails_to_delete)} of {len(emails_to_delete)}</span> emails selected
  </div>
  <div class="mb-3 flex gap-2">
    <button onclick="selectAllTrashEmails(true)" class="text-xs px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50">Select All</button>
    <button onclick="selectAllTrashEmails(false)" class="text-xs px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50">Deselect All</button>
  </div>
  <div class="bg-gray-50 p-2 rounded border border-gray-200" style="max-height: 250px; overflow-y: auto; overflow-x: hidden; position: relative;">
    <div style="position: sticky; top: 0; background: linear-gradient(to bottom, #f9fafb 0%, #f9fafb 90%, transparent 100%); z-index: 1; height: 10px; margin-bottom: -10px;"></div>
{email_items_html}
    <div style="position: sticky; bottom: 0; background: linear-gradient(to top, #f9fafb 0%, #f9fafb 90%, transparent 100%); z-index: 1; height: 10px; margin-top: -10px;"></div>
  </div>
  <div class="text-sm text-amber-700 mb-4 mt-3">
    <div>📧 Only selected emails will be moved to trash</div>
    <div>↩️ You can restore them within 30 days</div>
    <div class="text-xs text-gray-500 mt-1">💡 Click on an email to view it</div>
  </div>
  <div class="flex gap-3 justify-end">
    <button data-action="send-message" data-message="Cancel" onclick="sendMessage('Cancel')" class="px-4 py-2 text-sm border border-gray-300 rounded bg-white hover:bg-gray-50">Cancel</button>
    <button id="move-selected-btn" data-action="send-message" data-message="Move selected to trash" onclick="moveSelectedToTrash()" class="px-4 py-2 text-sm rounded text-white bg-red-500 hover:bg-red-600">Move Selected to Trash</button>
  </div>
</div>
<script>
// Track original email list
window.trashEmailList = {json.dumps(emails_to_delete, default=str)};

window.updateTrashCount = function() {{
  const checkboxes = document.querySelectorAll('.trash-email-checkbox');
  const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
  const totalCount = checkboxes.length;
  
  document.getElementById('trash-count-display').textContent = `${{checkedCount}} of ${{totalCount}}`;
  
  const btn = document.getElementById('move-selected-btn');
  if (checkedCount === 0) {{
    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
    btn.textContent = 'No Emails Selected';
  }} else {{
    btn.disabled = false;
    btn.classList.remove('opacity-50', 'cursor-not-allowed');
    btn.textContent = `Move ${{checkedCount}} Email${{checkedCount > 1 ? 's' : ''}} to Trash`;
  }}
}}

window.selectAllTrashEmails = function(select) {{
  const checkboxes = document.querySelectorAll('.trash-email-checkbox');
  checkboxes.forEach(cb => cb.checked = select);
  updateTrashCount();
}}

window.viewEmailFromPreview = function(emailId) {{
  // Find the email in the trash list
  const email = window.trashEmailList.find(e => e.id === emailId);
  if (email) {{
    // Create a modal to show the email
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50';
    modal.innerHTML = `
      <div class="bg-white rounded-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6">
        <div class="flex justify-between items-start mb-4">
          <h3 class="text-lg font-semibold text-gray-900">${{email.subject || 'No Subject'}}</h3>
          <button onclick="this.closest('.fixed').remove()" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>
        <div class="text-sm text-gray-600 mb-4">
          <div>From: ${{email.sender}}</div>
          <div>Date: ${{email.date || 'Unknown'}}</div>
        </div>
        <div class="text-sm text-gray-700">
          <p>Loading email content...</p>
        </div>
        <div class="mt-6 flex justify-end">
          <button onclick="this.closest('.fixed').remove()" class="px-4 py-2 text-sm border border-gray-300 rounded bg-white hover:bg-gray-50">Close</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    
    // Try to load full email content if available
    if (window.loadEmailContent) {{
      window.loadEmailContent(emailId).then(content => {{
        const contentDiv = modal.querySelector('.text-gray-700');
        if (content) {{
          contentDiv.innerHTML = content;
        }} else {{
          contentDiv.innerHTML = '<p class="text-gray-500">Email content not available in preview</p>';
        }}
      }});
    }}
  }}
}}

window.moveSelectedToTrash = function() {{
  // Get all selected email IDs
  const checkboxes = document.querySelectorAll('.trash-email-checkbox:checked');
  const selectedEmails = Array.from(checkboxes).map(cb => {{
    const emailId = cb.getAttribute('data-email-id');
    return window.trashEmailList.find(e => e.id === emailId);
  }}).filter(e => e);
  
  if (selectedEmails.length === 0) {{
    alert('Please select at least one email to move to trash');
    return;
  }}
  
  // CRITICAL FIX: Store selected emails globally for sendMessage to use
  window.selectedTrashEmails = selectedEmails;
  
  console.log('Selected', selectedEmails.length, 'emails for trash');
  console.log('Email IDs:', selectedEmails.map(e => e.id));
  console.log('Email subjects:', selectedEmails.map(e => e.subject));
  
  // Call a special handler that will properly update the context
  if (window.sendTrashConfirmation) {{
    window.sendTrashConfirmation(selectedEmails);
  }} else {{
    // Fallback: just send the message
    sendMessage('Move all to trash');
  }}
}}
</script>"""
        
        # Store pending delete in context for confirmation
        # CRITICAL: These are the EXACT emails that will be deleted
        context['pending_delete'] = {
            'emails': emails_to_delete,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        logger.info(f"=== Setting pending_delete in context ===")
        logger.info(f"Number of emails to delete: {len(emails_to_delete)}")
        logger.info(f"Email IDs to be deleted: {[e['id'] for e in emails_to_delete][:10]}...")
        logger.info(f"Email subjects to be deleted: {[e['subject'] for e in emails_to_delete][:5]}...")
        logger.info("Context after setting pending_delete: %s...", json.dumps(context, default=str)[:500])
        
        return confirm_msg, ["confirmation_required"]
    
    async def _move_to_folder(self, db: Session, user: User, message: str, 
                             context: Dict[str, Any]) -> tuple:
        """Move emails to a specific folder/label with natural language support"""
        
        # Extract folder name and email description from message
        prompt = f"""Extract information from this message about moving emails: {message!r}
        
Return as JSON with:
- folder_name: the target folder/label name
- email_description: description of which emails to move (if specified)

If no specific emails are mentioned, set email_description to null."""
        
        try:
            info_json = await self._call_anthropic(prompt, max_tokens=200, temperature=0.3)
            info = json.loads(info_json.strip())
            
            folder_name = info.get('folder_name', '').strip()
            if not folder_name or folder_name.lower() in ['none', 'null', '']:
                return "Please specify which folder you'd like to move emails to.", []
            
            # Find emails to move
            emails_to_move = []
            
            if info.get('email_description'):
                # Find emails by description
                emails_to_move = await self._find_emails_by_description(db, user, info['email_description'])
            elif context.get('selected_email'):
                # Use selected email
                selected_email = context['selected_email']
                email = db.query(Email).filter(
                    Email.id == selected_email['id'],
                    Email.user_id == user.id
                ).first()
                if email:
                    emails_to_move = [{
                        'id': email.id,
                        'gmail_id': email.gmail_id,
                        'subject': email.subject,
                        'sender': email.sender_name or email.sender
                    }]
            
            if not emails_to_move:
                return "I couldn't find any emails to move. Please be more specific or select an email first.", []
            
            # Move emails to folder
            success_count = 0
            failed_count = 0
            
            for email_data in emails_to_move:
                email = db.query(Email).filter(
                    Email.id == email_data['id'],
                    Email.user_id == user.id
                ).first()
                
                if email and self.gmail_service.move_to_label(user, email.gmail_id, folder_name):
                    success_count += 1
                else:
                    failed_count += 1
            
            if success_count > 0:
                if success_count == 1:
                    return f"Moved 1 email to '{folder_name}' folder.", ["emails_moved"]
                else:
                    result = f"Successfully moved {success_count} email(s) to '{folder_name}' folder."
                    if failed_count > 0:
                        result += f" {failed_count} email(s) failed."
                    return result, ["emails_moved"]
            else:
                return f"Failed to move emails to '{folder_name}'. Please try again.", []
                
        except Exception as e:
            logger.error(f"Error moving emails to folder: {e}")
            return "I had trouble moving the emails. Please try again.", []
    
    async def _create_folder(self, db: Session, user: User, message: str) -> tuple:
        """Create a new folder/label"""
        # Extract folder name from message
        prompt = f"""Extract the folder/label name to create from this message: {message!r}
Return only the folder name, nothing else."""
        
        try:
            folder_name = await self._call_anthropic(prompt, max_tokens=50, temperature=0.3)
            folder_name = folder_name.strip()
            
            if not folder_name or folder_name.lower() in ['none', 'null', '']:
                return "Please specify a name for the new folder.", []
            
            # Create folder in Gmail
            label_id = self.gmail_service.create_label(user, folder_name)
            if label_id:
                return f"Created new folder '{folder_name}'. You can now move emails to this folder.", ["folder_created"]
            else:
                return f"Failed to create folder '{folder_name}'. It may already exist.", []
                
        except Exception as e:
            logger.error(f"Error creating folder: {e}")
            return "I had trouble creating the folder. Please try again.", []
    
    async def _list_folders(self, user: User) -> str:
        """List all available folders/labels"""
        try:
            labels = self.gmail_service.list_labels(user)
            
            if not labels:
                return "You don't have any custom folders yet. You can ask me to create one!"
            
            response = f"You have {len(labels)} custom folder(s):\n\n"
            for label in labels:
                response += f"• {label['name']}\n"
            
            response += "\nYou can move emails to any of these folders or create new ones."
            return response
            
        except Exception as e:
            logger.error(f"Error listing folders: {e}")
            return "I had trouble fetching your folders. Please try again."
    
    async def _generate_response(self, message: str, context: Dict[str, Any]) -> str:
        prompt = f"""You are SAIG, a helpful email assistant. Respond to this message naturally and helpfully.

User message: {message}

Context:
- User has {context['total_emails']} total emails
- {context['total_unread']} unread emails

Keep your response concise and helpful."""

        try:
            response_text = await self._call_anthropic(prompt, max_tokens=300, temperature=0.7)
            return response_text.strip()
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm here to help with your emails. What would you like to do?"
    
    async def _compose_email(self, db: Session, user: User, message: str, 
                            context: Dict[str, Any]) -> tuple:
        prompt = f"""Extract email composition details from this message: {message!r}

Extract the following information as JSON:
- recipient: email address (required)
- recipient_name: the recipient's actual name if mentioned (optional, e.g., "John Smith" from "send an email to John Smith at john@example.com")
- subject: email subject line (required) 
- message: ONLY the main body content WITHOUT greeting or closing (required). Do NOT include "Dear X", "Hi X", "Sincerely", "Best regards", etc. Just the core message content.
- tone: formal, casual, or professional (default: professional)
- reply_to_email_id: if this is a reply to a specific email, extract the email ID from context

IMPORTANT: The 'message' field should contain ONLY the main content. Greetings and signatures will be added automatically.

If the message doesn't contain enough information, return an error indicating what's missing.

Context: {json.dumps(context, indent=2) if context else "No context"}
"""
        
        try:
            email_json = await self._call_anthropic(prompt, max_tokens=400, temperature=0.3)
            email_data = json.loads(email_json.strip())
            
            # Check for required fields
            if not email_data.get('recipient') or not email_data.get('subject') or not email_data.get('message'):
                missing = []
                if not email_data.get('recipient'): missing.append('recipient email address')
                if not email_data.get('subject'): missing.append('subject line') 
                if not email_data.get('message'): missing.append('message content')
                
                return f"I need more information to compose the email. Please provide: {', '.join(missing)}", []
            
            # Generate formatted email with greeting and signature
            # If recipient_name is provided, create a context with it
            compose_context = None
            if email_data.get('recipient_name'):
                compose_context = {'sender_name': email_data['recipient_name']}
            elif email_data.get('reply_to_email_id') and context.get('selected_email'):
                compose_context = context.get('selected_email')
            
            formatted_email = await self._format_email(
                user=user,
                recipient=email_data['recipient'],
                subject=email_data['subject'],
                message=email_data['message'],
                tone=email_data.get('tone', 'professional'),
                reply_context=compose_context
            )
            
            # Escape the email body for JavaScript
            escaped_body = formatted_email['body'].replace('\\', '\\\\').replace('`', '\\`').replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n')
            
            # Return email draft with preview
            response = f"""<div class="text-sm">
<p><strong>Here's your email draft:</strong></p>

<div class="bg-gray-50 border-l-4 border-blue-400 p-3 my-3 font-mono text-sm">
<div class="font-semibold mb-2">Email Preview:</div>
<div class="mb-1"><strong>To:</strong> {email_data['recipient']}</div>
<div class="mb-3"><strong>Subject:</strong> {email_data['subject']}</div>
<div class="whitespace-pre-wrap">{formatted_email['body']}</div>
</div>

<p>Would you like me to send this email, or would you like to edit it first?</p>

<div class="mt-4 flex space-x-2">
    <button onclick="editDraft('{email_data['recipient']}', '{email_data['subject']}', '{escaped_body}')" 
            class="bg-blue-500 text-white px-3 py-1 rounded text-sm hover:bg-blue-600">
        ✏️ Edit
    </button>
    <button onclick="sendDraftEmail('{email_data['recipient']}', '{email_data['subject']}', '{escaped_body}')" 
            class="bg-green-500 text-white px-3 py-1 rounded text-sm hover:bg-green-600">
        📧 Send
    </button>
</div>
</div>"""
            
            return response, ["email_draft_created"]
            
        except Exception as e:
            logger.error(f"Error composing email: {e}")
            return "I had trouble understanding your email request. Please provide the recipient, subject, and message content.", []
    
    async def _reply_email(self, db: Session, user: User, message: str, 
                          context: Dict[str, Any]) -> tuple:
        # Check if we have a selected email to reply to
        logger.info(f"Reply email context: {context.get('selected_email', 'None')}")
        if not context or not context.get('selected_email'):
            logger.error(f"No selected email in context. Context keys: {context.keys() if context else 'None'}")
            logger.error(f"Context selected_email value: {context.get('selected_email') if context else 'No context'}")
            return "Please select an email first, then ask me to reply to it.", []
        
        selected_email = context['selected_email']
        
        # Check if this is a direct analysis request or has additional instructions
        is_direct_analysis = "Please read this email and generate" in message
        
        if is_direct_analysis:
            # Generate intelligent reply based on email content
            prompt = f"""Analyze this email and generate an intelligent, contextually appropriate reply.

Original Email:
From: {selected_email['sender']}
Subject: {selected_email['subject']}
Body: {selected_email['body'][:2000]}

Based on the email content:
1. Identify the main purpose of the email (question, request, update, etc.)
2. Determine what response is needed
3. Generate an appropriate reply that:
   - Acknowledges their message
   - Addresses all questions or requests
   - Provides helpful information or next steps
   - Maintains a professional tone

IMPORTANT: Generate ONLY the main body of the reply. Do NOT include:
- Greeting (like "Hi John" or "Dear Sarah")
- Closing (like "Best regards" or "Sincerely")
- Signature/name
These will be added automatically.
   
{message.split('Additional instructions:')[1] if 'Additional instructions:' in message else ''}

Generate the reply as JSON with:
- reply_message: just the core message body without greeting or closing
- tone: detected appropriate tone (formal, casual, or professional)
- summary: brief explanation of what the reply addresses
"""
        else:
            # Use the user's specific instructions
            prompt = f"""Generate a reply to this email based on the user's request.

Original Email:
From: {selected_email['sender']}
Subject: {selected_email['subject']}
Body: {selected_email['body'][:1000]}

User's reply request: "{message}"

IMPORTANT: Generate ONLY the main body of the reply. Do NOT include:
- Greeting (like "Hi John" or "Dear Sarah")
- Closing (like "Best regards" or "Sincerely")
- Signature/name
These will be added automatically.

Extract the following information as JSON:
- reply_message: just the core message body without greeting or closing (required)
- tone: formal, casual, or professional (default: professional)
- include_original: true/false - whether to include original email text

Generate an appropriate reply based on the user's request and the original email context.
"""
        
        try:
            reply_text = await self._call_anthropic(prompt, max_tokens=700, temperature=0.5)
            
            # Extract JSON from the response (in case there's extra text)
            import re
            json_match = re.search(r'\{.*\}', reply_text, re.DOTALL)
            if json_match:
                reply_text = json_match.group()
            
            # Try to parse the JSON response
            try:
                # First attempt - direct parse
                reply_data = json.loads(reply_text)
            except json.JSONDecodeError:
                # Second attempt - fix common JSON issues
                # Replace actual newlines within strings with escaped newlines
                fixed_json = re.sub(r'("(?:[^"\\]|\\.)*?")', lambda m: m.group(0).replace('\n', '\\n').replace('\r', '\\r'), reply_text)
                try:
                    reply_data = json.loads(fixed_json)
                except json.JSONDecodeError:
                    # Third attempt - extract fields manually
                    logger.warning("Failed to parse JSON, extracting reply manually")
                    reply_data = {}
                    
                    # Extract reply_message
                    reply_match = re.search(r'"reply_message"\s*:\s*"((?:[^"\\]|\\.)*)"', reply_text, re.DOTALL)
                    if reply_match:
                        reply_data["reply_message"] = reply_match.group(1).replace('\\n', '\n').replace('\\"', '"')
                    
                    # Extract tone
                    tone_match = re.search(r'"tone"\s*:\s*"([^"]+)"', reply_text)
                    if tone_match:
                        reply_data["tone"] = tone_match.group(1)
                    else:
                        reply_data["tone"] = "professional"
                    
                    # Extract summary if present
                    summary_match = re.search(r'"summary"\s*:\s*"([^"]+)"', reply_text)
                    if summary_match:
                        reply_data["summary"] = summary_match.group(1)
                    
                    if not reply_data.get("reply_message"):
                        raise ValueError("Could not extract reply message")
            
            if not reply_data.get('reply_message'):
                return "I couldn't generate a reply. Please provide more specific instructions about what you'd like to say.", []
            
            # Create reply subject
            original_subject = selected_email['subject']
            reply_subject = original_subject if original_subject.startswith('Re:') else f"Re: {original_subject}"
            
            # Generate formatted reply email
            formatted_email = await self._format_email(
                user=user,
                recipient=selected_email['sender'],
                subject=reply_subject,
                message=reply_data['reply_message'],
                tone=reply_data.get('tone', 'professional'),
                reply_context=selected_email
            )
            
            # Escape the email body for JavaScript
            escaped_body = formatted_email['body'].replace('\\', '\\\\').replace('`', '\\`').replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n')
            
            # For SAIG Reply modal, just return the formatted body
            # The frontend will handle the display
            return formatted_email['body'], ["email_reply_created"]
            
        except Exception as e:
            logger.error(f"Error generating reply: {str(e)}")
            logger.error(f"Reply context: has selected_email={context.get('selected_email') is not None}")
            logger.error(f"Full exception: {e.__class__.__name__}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return "I had trouble generating a reply. Please try again with more specific instructions.", []
    
    async def _format_email(self, user: User, recipient: str, subject: str, message: str, 
                           tone: str = 'professional', reply_context: Dict = None) -> Dict[str, str]:
        # Get recipient's name - use sender_name from reply context if available
        if reply_context and reply_context.get('sender_name'):
            # Use the actual sender name from the email we're replying to
            recipient_full_name = reply_context['sender_name']
            # Extract first name from full name
            recipient_first_name = recipient_full_name.split()[0] if recipient_full_name else None
        else:
            # Fallback to extracting from email address
            recipient_name = recipient.split('@')[0].replace('.', ' ').replace('_', ' ').title()
            recipient_first_name = recipient_name.split()[0] if recipient_name else recipient.split('@')[0]
        
        # Get sender's actual name from user object
        sender_name = user.name if user.name else user.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
        
        # Choose appropriate greeting based on tone
        if tone == 'formal':
            greeting = f"Dear {recipient_first_name},"
            closing = f"Sincerely,\n{sender_name}"
        elif tone == 'casual':
            greeting = f"Hi {recipient_first_name}!"
            closing = f"Best,\n{sender_name}"
        else:  # professional
            greeting = f"Hello {recipient_first_name},"
            closing = f"Best regards,\n{sender_name}"
        
        # Add reply context if this is a reply
        context_text = ""
        if reply_context:
            context_text = f"\nThank you for your email regarding {reply_context.get('subject', 'your message')}.\n\n"
        
        # SAIG tagline
        saig_tagline = "\n\n---\nThis email was composed with SAIG in SAIGBOX"
        
        # Format the complete email body (plain text only)
        body = f"""{greeting}

{context_text}{message}

{closing}{saig_tagline}"""
        
        return {
            'body': body,
            'subject': subject,
            'recipient': recipient
        }
    
    async def analyze_urgent_email(self, email: Email, db: Session, user: User) -> Dict[str, Any]:
        """
        Deep AI analysis for emails marked as urgent.
        Extracts action items with high precision.
        
        Returns comprehensive analysis with action items and urgency confirmation.
        """
        try:
            # Prepare email content for analysis
            email_content = email.body_text or email.body_html or email.snippet or ""
            
            prompt = f"""Analyze this email marked as potentially urgent and extract any action items.

Email Details:
From: {email.sender_name or email.sender}
Subject: {email.subject}
Date: {email.received_at}
Body: {email_content[:2000]}

Please analyze and provide the following in JSON format:

1. is_truly_urgent: boolean - Is this email genuinely urgent requiring immediate attention?
2. urgency_confirmation_reason: string - Brief explanation of why it is/isn't urgent
3. summary: string - 1-2 sentence summary of the email
4. action_items: array of objects, each containing:
   - title: string - Concise, actionable task title (e.g., "Review Q4 budget proposal")
   - description: string - Detailed description with context
   - due_date: ISO date string or null - Extract any mentioned deadline
   - priority: "high" | "medium" | "low" - Based on urgency and importance
   - confidence: number 0-100 - How confident you are this is a real action item
   - source_quote: string - The exact text that indicates this action item

IMPORTANT INSTRUCTIONS:
- Be CONSERVATIVE with action items - only extract clear, actionable tasks
- Each action item must be something the recipient needs to DO, not just information
- Confidence score should be 70+ for clear action items, lower for implied tasks
- For due dates, parse relative dates (tomorrow, next week) into actual dates
- Priority should reflect both urgency and importance
- Include WHO needs to do WHAT by WHEN in the description when possible

Return ONLY valid JSON, no additional text."""

            # Call Claude API
            response_text = await self._call_anthropic(prompt, max_tokens=1000, temperature=0.3)
            
            # Parse JSON response
            try:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse SAIG response for urgent email: {e}")
                logger.error(f"Response was: {response_text}")
                
                # Return default structure on parse error
                return {
                    "is_truly_urgent": True,  # Err on side of caution
                    "urgency_confirmation_reason": "Unable to fully analyze, treating as urgent",
                    "action_items": [],
                    "summary": "Analysis failed - please review email manually"
                }
            
            # Validate and clean action items
            cleaned_action_items = []
            for item in result.get('action_items', []):
                if item.get('confidence', 0) >= 70:  # Only high-confidence items
                    # Parse due date if it's a string
                    due_date = item.get('due_date')
                    if due_date and isinstance(due_date, str):
                        try:
                            # Try to parse ISO format
                            due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                        except:
                            due_date = None
                    
                    cleaned_item = {
                        'title': item.get('title', 'Untitled Task'),
                        'description': item.get('description', ''),
                        'due_date': due_date,
                        'priority': item.get('priority', 'medium'),
                        'confidence': item.get('confidence', 70),
                        'source_quote': item.get('source_quote', '')
                    }
                    cleaned_action_items.append(cleaned_item)
            
            result['action_items'] = cleaned_action_items
            
            # Log analysis result
            logger.info(f"Analyzed urgent email {email.id}: {len(cleaned_action_items)} action items found")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing urgent email: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            return {
                "is_truly_urgent": True,  # Err on side of caution
                "urgency_confirmation_reason": f"Analysis error: {str(e)}",
                "action_items": [],
                "summary": "Unable to analyze email - please review manually"
            }
    
    def _get_help_message(self) -> str:
        return """I'm SAIG, your email assistant. Here's what I can help you with:

📧 **Email Management:**
• Search for emails by keyword
• Mark emails as read/unread
• Star or unstar emails
• Move emails to trash (recoverable for 30 days)
• Move emails to folders
• Create new folders/labels
• List available folders
• Compose and send new emails
• Reply to emails intelligently

📁 **Folder Organization:**
• "Create a folder called Work"
• "Move this email to Personal folder"
• "Show me my folders"
• "Move this email to trash" or "Delete this email"

📝 **Action Items:**
• Create action items from emails
• List your pending tasks
• Set priorities and due dates

💬 **Smart Features:**
• Summarize long emails
• Get email insights
• Natural language commands
• Analyze email patterns
• Extract action items from emails
• Categorize emails automatically
• Show personalized insights

Just tell me what you need help with!"""
    
    async def _analyze_patterns(self, db: Session, user: User) -> str:
        """Analyze user's email patterns using intelligence module"""
        try:
            patterns = await self.intelligence.analyze_email_patterns(db, user)
            
            response = "📊 **Email Pattern Analysis**\n\n"
            
            # Frequent senders
            if patterns['frequent_senders']:
                response += "**Most frequent contacts:**\n"
                for sender in patterns['frequent_senders'][:5]:
                    response += f"• {sender['name'] or sender['email']} ({sender['count']} emails)\n"
                response += "\n"
            
            # Email categories
            if patterns['email_categories']:
                response += "**Email breakdown:**\n"
                for category, count in patterns['email_categories'].items():
                    response += f"• {category.capitalize()}: {count} emails\n"
                response += "\n"
            
            # Peak hours
            if patterns['peak_hours']:
                response += f"**Peak email times:** {', '.join([f'{h}:00' for h in patterns['peak_hours']])}\n\n"
            
            # Unread buildup
            if patterns['unread_buildup'] > 0:
                response += f"⚠️ **Unread emails:** {patterns['unread_buildup']}\n\n"
            
            # Proactive suggestions
            if patterns['suggested_actions']:
                response += "**Recommendations:**\n"
                for suggestion in patterns['suggested_actions']:
                    priority_emoji = "🔴" if suggestion['priority'] == 'high' else "🟡" if suggestion['priority'] == 'medium' else "🟢"
                    response += f"{priority_emoji} {suggestion['message']}\n"
            
            return response
        except Exception as e:
            logger.error(f"Error analyzing patterns: {e}")
            return "I encountered an error analyzing your email patterns. Please try again."
    
    async def _extract_actions_from_emails(self, db: Session, user: User, message: str, context: Dict[str, Any]) -> tuple:
        """Extract action items from emails using intelligence module"""
        try:
            actions = []
            
            # Check if specific email is selected
            if context.get('selected_email'):
                email = db.query(Email).filter(
                    Email.id == context['selected_email']['id'],
                    Email.user_id == user.id
                ).first()
                
                if email:
                    content = email.body_text or email.snippet or ""
                    action_items = await self.intelligence.extract_action_items(content, email.subject or "")
                    
                    if action_items:
                        response = f"📝 **Action items extracted from email:**\n\n"
                        for item in action_items:
                            priority_emoji = "🔴" if item['priority'] == 'high' else "🟡" if item['priority'] == 'medium' else "🟢"
                            response += f"{priority_emoji} **{item['text']}**\n"
                            if item.get('deadline'):
                                response += f"   📅 Due: {item['deadline'].strftime('%B %d, %Y')}\n"
                            response += f"   Confidence: {item['confidence']*100:.0f}%\n\n"
                        
                        actions.append(f"Extracted {len(action_items)} action items")
                        
                        # Ask if user wants to save them
                        response += "\n💡 Would you like me to save these as action items in your task list?"
                    else:
                        response = "No clear action items found in this email."
                else:
                    response = "Could not find the selected email."
            else:
                # Extract from recent emails
                recent_emails = context.get('recent_emails', [])[:5]
                all_actions = []
                
                for email_data in recent_emails:
                    email = db.query(Email).filter(
                        Email.id == email_data['id'],
                        Email.user_id == user.id
                    ).first()
                    
                    if email:
                        content = email.body_text or email.snippet or ""
                        items = await self.intelligence.extract_action_items(content, email.subject or "")
                        for item in items:
                            item['email_subject'] = email.subject
                            all_actions.append(item)
                
                if all_actions:
                    response = f"📝 **Action items found in recent emails:**\n\n"
                    for item in all_actions[:10]:  # Limit to 10
                        priority_emoji = "🔴" if item['priority'] == 'high' else "🟡" if item['priority'] == 'medium' else "🟢"
                        response += f"{priority_emoji} **{item['text']}**\n"
                        response += f"   📧 From: {item['email_subject']}\n"
                        if item.get('deadline'):
                            response += f"   📅 Due: {item['deadline'].strftime('%B %d, %Y')}\n"
                        response += "\n"
                    
                    actions.append(f"Found {len(all_actions)} action items")
                else:
                    response = "No action items found in recent emails."
            
            return response, actions
            
        except Exception as e:
            logger.error(f"Error extracting actions: {e}")
            return "I encountered an error extracting action items.", []
    
    async def _categorize_emails(self, db: Session, user: User) -> tuple:
        """Categorize uncategorized emails"""
        try:
            # Get uncategorized emails
            emails = db.query(Email).filter(
                Email.user_id == user.id,
                Email.deleted_at.is_(None)
            ).limit(50).all()
            
            categorized_count = 0
            categories_applied = {}
            
            for email in emails:
                # Check if already categorized
                if email.labels and any(label.startswith("CATEGORY/") for label in email.labels):
                    continue
                
                # Detect category
                category = await self.intelligence.detect_email_category(email)
                
                # Update email
                if not email.labels:
                    email.labels = []
                email.labels.append(f"CATEGORY/{category.upper()}")
                
                categorized_count += 1
                categories_applied[category] = categories_applied.get(category, 0) + 1
                
                if categorized_count >= 20:  # Limit per request
                    break
            
            db.commit()
            
            if categorized_count > 0:
                response = f"✅ **Categorized {categorized_count} emails:**\n\n"
                for category, count in categories_applied.items():
                    response += f"• {category.capitalize()}: {count} emails\n"
                
                actions = [f"Categorized {categorized_count} emails"]
            else:
                response = "All emails are already categorized!"
                actions = []
            
            return response, actions
            
        except Exception as e:
            logger.error(f"Error categorizing emails: {e}")
            return "I encountered an error categorizing emails.", []
    
    async def _show_insights(self, db: Session, user: User) -> str:
        """Show email insights and analytics"""
        try:
            from sqlalchemy import func
            
            # Get patterns
            patterns = await self.intelligence.analyze_email_patterns(db, user)
            
            # Get statistics
            total_emails = db.query(Email).filter(
                Email.user_id == user.id,
                Email.deleted_at.is_(None)
            ).count()
            
            unread_emails = db.query(Email).filter(
                Email.user_id == user.id,
                Email.is_read == False,
                Email.deleted_at.is_(None)
            ).count()
            
            starred_emails = db.query(Email).filter(
                Email.user_id == user.id,
                Email.is_starred == True,
                Email.deleted_at.is_(None)
            ).count()
            
            # Recent activity
            recent_date = datetime.utcnow() - timedelta(days=7)
            recent_received = db.query(Email).filter(
                Email.user_id == user.id,
                Email.received_at >= recent_date,
                Email.deleted_at.is_(None)
            ).count()
            
            response = "📊 **Email Insights Dashboard**\n\n"
            
            # Statistics
            response += "**📈 Statistics:**\n"
            response += f"• Total emails: {total_emails}\n"
            unread_percentage = (unread_emails/total_emails*100) if total_emails > 0 else 0
            response += f"• Unread: {unread_emails} ({unread_percentage:.1f}%)\n"
            response += f"• Starred: {starred_emails}\n"
            response += f"• Last 7 days: {recent_received} emails\n\n"
            
            # Top contacts
            if patterns['frequent_senders']:
                response += "**👥 Top Contacts:**\n"
                for sender in patterns['frequent_senders'][:3]:
                    response += f"• {sender['name'] or sender['email']} ({sender['count']} emails)\n"
                response += "\n"
            
            # Email types
            if patterns['email_categories']:
                response += "**📧 Email Types:**\n"
                total_categorized = sum(patterns['email_categories'].values())
                for category, count in sorted(patterns['email_categories'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    percentage = (count/total_categorized*100) if total_categorized > 0 else 0
                    response += f"• {category.capitalize()}: {count} ({percentage:.1f}%)\n"
                response += "\n"
            
            # Recommendations
            if patterns['suggested_actions']:
                response += "**💡 Recommendations:**\n"
                for suggestion in patterns['suggested_actions'][:3]:
                    response += f"• {suggestion['message']}\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing insights: {e}")
            return "I encountered an error generating insights. Please try again."