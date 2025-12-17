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
from core.saig_assistant_simple import SimpleEmailHandler
from core.urgency_detector import UrgencyDetector
from core.saig_intelligence import SAIGIntelligence

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SAIGAssistant:
    def __init__(self):
        # Check if using Bedrock or direct Anthropic API
        self.use_bedrock = os.getenv('USE_BEDROCK', 'true').lower() == 'true'

        if self.use_bedrock:
            # Initialize AWS Bedrock client
            try:
                import boto3
                self.bedrock_client = boto3.client(
                    service_name='bedrock-runtime',
                    region_name=os.getenv('AWS_REGION', 'us-east-1'),
                    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
                )
                # Bedrock model ID format (using cross-region inference profile)
                self.model = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
                logger.info("SAIG Assistant initialized with AWS Bedrock")
            except Exception as e:
                logger.error(f"Failed to initialize Bedrock: {e}")
                logger.warning("Falling back to direct Anthropic API")
                self.use_bedrock = False

        if not self.use_bedrock:
            # Load Anthropic API key from environment
            self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')

            if not self.anthropic_api_key:
                logger.warning("ANTHROPIC_API_KEY not set. SAIG functionality will be limited.")
            else:
                logger.info("SAIG Assistant initialized with Anthropic API")

            self.api_url = "https://api.anthropic.com/v1/messages"
            self.http_client = httpx.AsyncClient(timeout=30.0)
            # Use Claude 3.5 Haiku for faster responses
            self.model = "claude-3-5-haiku-20241022"

        self.gmail_service = GmailService()
        self.intelligence = SAIGIntelligence()  # Initialize intelligence module
        self.simple_handler = SimpleEmailHandler()  # Simple email deletion handler
    
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
            if email_context.get('pending_delete') or message.startswith('confirm delete with ids:'):
                logger.info("=== PENDING DELETE DETECTED - CHECKING FOR CONFIRMATION ===")
                # Check if this is a confirmation or cancellation
                message_lower = message.lower().strip()
                confirmation_keywords = ['yes', 'confirm', 'proceed', 'go ahead', 'sure', 'ok', 'move', 'trash', 'delete']
                cancellation_keywords = ['no', 'cancel', 'stop', 'wait', 'never', "don't", 'abort']
                
                # Check for specific ID confirmation
                if message.startswith('confirm delete with ids:'):
                    logger.debug("Delete with specific IDs detected")
                    intent = 'delete_email'
                # Check for confirmation
                elif any(keyword in message_lower for keyword in confirmation_keywords):
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
        """Helper method to call Anthropic API (via Bedrock or direct)"""

        if self.use_bedrock:
            # AWS Bedrock call
            try:
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}]
                }

                response = self.bedrock_client.invoke_model(
                    modelId=self.model,
                    body=json.dumps(request_body)
                )

                response_body = json.loads(response['body'].read())
                return response_body['content'][0]['text']

            except Exception as e:
                logger.error(f"Bedrock API error: {e}")
                return f"Error calling Bedrock API: {str(e)}"

        else:
            # Direct Anthropic API call
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
            response, actions = await self._delete_email_simplified(db, user, message, context)
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
                response = f"""<div class="mb-3">I found {len(emails)} email(s) matching '{search_query}':</div>
<div class="space-y-2">"""
                for email in emails:
                    # Create clickable email cards
                    response += f"""
<div class="bg-white p-3 rounded border hover:shadow-sm cursor-pointer transition-shadow" 
     onclick="window.selectEmail('{email.id}')" 
     style="cursor: pointer;">
    <div class="flex justify-between items-start mb-1">
        <span class="font-medium text-sm text-blue-600 hover:text-blue-800">{email.sender_name or email.sender}</span>
        <span class="text-xs text-gray-500">{email.received_at.strftime('%Y-%m-%d %H:%M') if email.received_at else ''}</span>
    </div>
    <div class="text-sm font-medium text-gray-800">{email.subject or '(No subject)'}</div>
    <div class="text-xs text-gray-600 mt-1">{(email.snippet or '')[:100]}...</div>
</div>"""
                response += "</div>"
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
                except (ValueError, TypeError):
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
    
    # REMOVED: _find_emails_by_description - replaced by SimpleEmailHandler
    # The complex AI-based email search has been replaced with simple pattern matching
    
    async def _delete_email_simplified(self, db: Session, user: User, message: str, 
                                      context: Dict[str, Any]) -> tuple:
        """
        SIMPLIFIED email deletion handler
        Clear, simple logic with proper preview and confirmation
        """
        logger.info(f"=== SIMPLIFIED DELETE EMAIL ===")
        logger.info(f"Message: {message}")
        logger.info(f"Has context: {bool(context)}")
        
        # Check if this is a confirmation with specific IDs
        if message.startswith('confirm delete with ids:'):
            try:
                # Extract the JSON array of IDs
                import json
                ids_json = message.replace('confirm delete with ids:', '').strip()
                email_ids = json.loads(ids_json)
                
                logger.info(f"Confirming deletion of specific IDs: {email_ids}")
                
                # Get original params if available
                params = context.get('pending_delete', {}).get('params')
                
                # Execute deletion using simple handler with params verification
                result = self.simple_handler.execute_deletion(
                    db, user, email_ids, self.gmail_service, params
                )
                
                # Clear pending delete
                context.pop('pending_delete', None)
                
                if result['success']:
                    msg = f"✅ Successfully moved {result['success_count']} emails to trash."
                    if result.get('skipped_count', 0) > 0:
                        msg += f" (Skipped {result['skipped_count']} emails that didn't match criteria)"
                    return msg, ["emails_moved_to_trash"]
                else:
                    return f"⚠️ {result.get('message', 'Some emails could not be moved to trash.')}", []
            except Exception as e:
                logger.error(f"Error parsing email IDs: {e}")
                return "Error processing selected emails. Please try again.", []
        
        # Check if this is a confirmation of a previous delete request
        if context.get('pending_delete'):
            # User is confirming deletion
            confirmation_words = ['yes', 'confirm', 'proceed', 'move', 'trash', 'delete', 'ok', 'sure']
            message_lower = message.lower().strip()
            
            # Check for cancellation
            if any(word in message_lower for word in ['cancel', 'no', 'stop', 'abort']):
                context.pop('pending_delete', None)
                return "Cancelled. No emails were moved to trash.", []
            
            # Check for confirmation
            is_confirmed = any(word in message_lower for word in confirmation_words)
            
            if is_confirmed:
                pending = context['pending_delete']
                email_ids = pending.get('email_ids', [])
                params = pending.get('params')  # Get original search params
                
                if not email_ids:
                    return "No emails selected. Please try again.", []
                
                logger.info(f"Confirming deletion of {len(email_ids)} emails with params: {params}")
                
                # Execute deletion using simple handler with params verification
                result = self.simple_handler.execute_deletion(
                    db, user, email_ids, self.gmail_service, params
                )
                
                # Clear pending delete
                context.pop('pending_delete', None)
                
                if result['success']:
                    msg = f"✅ Successfully moved {result['success_count']} emails to trash."
                    if result.get('skipped_count', 0) > 0:
                        msg += f" (Skipped {result['skipped_count']} emails that didn't match criteria)"
                    return msg, ["emails_moved_to_trash"]
                else:
                    return f"⚠️ {result.get('message', 'Some emails could not be moved to trash.')}", []
            else:
                return "Please confirm by saying 'yes' or 'confirm', or 'cancel' to abort.", []
        
        # This is a new delete request - parse and find emails
        params = self.simple_handler.parse_email_request(message)
        
        if not params:
            return "I couldn't understand what emails you want to delete. Please specify the sender, time period, or count.", []
        
        # Find emails based on parameters - search directly from Gmail/Outlook
        # This ensures we get ALL emails, not just those synced to local database
        try:
            emails = self.simple_handler.find_emails_to_delete_from_provider(db, user, params, self.gmail_service)
            logger.info(f"Found {len(emails)} emails from Gmail provider")
        except Exception as e:
            logger.warning(f"Failed to search Gmail directly: {e}, falling back to local database")
            emails = self.simple_handler.find_emails_to_delete(db, user, params)
        
        if not emails:
            sender = params.get('sender', 'specified criteria')
            return f"I couldn't find any emails from {sender}. Please check and try again.", []
        
        # Create preview HTML
        preview_html = self.simple_handler.create_preview_html(emails)
        
        # Store email IDs AND original search params in context for confirmation
        context['pending_delete'] = {
            'email_ids': [str(email.id) for email in emails],
            'count': len(emails),
            'params': params,  # Store the original search parameters
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Enhanced logging to verify correct emails
        logger.info(f"Showing preview for {len(emails)} emails matching: {params}")
        if emails:
            logger.info(f"First 3 emails in preview:")
            for i, email in enumerate(emails[:3]):
                logger.info(f"  {i+1}. ID={email.id}, From={email.sender_name or email.sender}, Subject={email.subject[:50]}")
        logger.info(f"Stored {len(context['pending_delete']['email_ids'])} email IDs for potential deletion with params: {params}")
        
        return preview_html, ["confirmation_required"]
    
    # REMOVED: Old complex _delete_email method
    # The new simplified version is _delete_email_simplified above
    # Keeping stub for reference only
    async def _delete_email_old_REMOVED(self, db: Session, user: User, message: str, 
                           context: Dict[str, Any]) -> tuple:
        """REMOVED - DO NOT USE
        This old method has been replaced by _delete_email_simplified
        """
        raise NotImplementedError("This method has been removed. Use _delete_email_simplified instead")
        
    # Original complex implementation removed for clarity
    # See git history if needed
    
    async def _old_delete_implementation_stub(self):
        """Stub - old implementation removed"""
        pass
    
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
        prompt = f"""Based on this user request: {message!r}

Compose a professional email and return it as JSON with the following fields:
- recipient: email address (required)
- recipient_name: the recipient's actual name if mentioned (optional, e.g., "John Smith" from "send an email to John Smith at john@example.com")
- subject: a clear, professional email subject line (required)
- message: the FULL email body content WITHOUT greeting or closing (required). This should be a complete, well-written email body with proper paragraphs, NOT just a rewording of the user's request. Write it as if you're the sender composing a professional email.
- tone: formal, casual, or professional (default: professional)
- reply_to_email_id: if this is a reply to a specific email, extract the email ID from context

CRITICAL INSTRUCTIONS FOR THE 'message' FIELD:
- DO NOT just reword the user's request - COMPOSE an actual professional email body
- Include relevant context, explanations, and complete sentences
- Structure it with proper paragraphs if needed
- Make it sound natural and professional
- Do NOT include greetings like "Dear X" or closings like "Best regards" - those are added automatically
- The message should be what goes between the greeting and the signature

EXAMPLES:
User request: "Write an email to john@acme.com asking him to review the Q4 budget"
BAD message: "asking him to review the Q4 budget"
GOOD message: "I hope this email finds you well. I wanted to reach out regarding the Q4 budget review. Would you be able to take a look at the attached budget proposal and provide your feedback by end of week? Please let me know if you have any questions or need any additional information."

User request: "Email sarah@tech.com about rescheduling our meeting"
BAD message: "about rescheduling our meeting"
GOOD message: "I need to reschedule our meeting that was planned for this Thursday. Something unexpected has come up and I won't be able to make it. Would you be available to meet next Tuesday or Wednesday instead? I apologize for any inconvenience this may cause."

Context: {json.dumps(context, indent=2) if context else "No context"}

If the request doesn't contain enough information to compose the email, return an error indicating what's missing.

Return ONLY valid JSON, no additional text."""
        
        try:
            email_json = await self._call_anthropic(prompt, max_tokens=800, temperature=0.5)

            # Clean up the response - remove markdown code blocks if present
            email_json = email_json.strip()
            if email_json.startswith('```'):
                # Remove ```json or ``` at start and ``` at end
                lines = email_json.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].strip() == '```':
                    lines = lines[:-1]
                email_json = '\n'.join(lines)

            # Try to extract JSON if it's embedded in text
            import re
            json_match = re.search(r'\{.*\}', email_json, re.DOTALL)
            if json_match:
                email_json = json_match.group()

            # Parse JSON with strict=False to allow control characters
            email_data = json.loads(email_json, strict=False)
            
            # Check for required fields
            if not email_data.get('recipient') or not email_data.get('subject') or not email_data.get('message'):
                missing = []
                if not email_data.get('recipient'): missing.append('recipient email address')
                if not email_data.get('subject'): missing.append('subject line') 
                if not email_data.get('message'): missing.append('message content')
                
                return f"I need more information to compose the email. Please provide: {', '.join(missing)}", []
            
            # Generate formatted email with greeting and signature
            # Pass recipient_name directly to the format function
            formatted_email = await self._format_email(
                user=user,
                recipient=email_data['recipient'],
                subject=email_data['subject'],
                message=email_data['message'],
                tone=email_data.get('tone', 'professional'),
                recipient_name=email_data.get('recipient_name')
            )
            
            # Escape the email body for JavaScript
            escaped_body = formatted_email['body'].replace('\\', '\\\\').replace('`', '\\`').replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n')
            
            # Return email draft with preview (with unique ID for removal)
            import uuid
            preview_id = str(uuid.uuid4())

            response = f"""<div id="email-preview-{preview_id}" class="rounded-lg bg-white border shadow-sm overflow-hidden my-3">
    <!-- Header -->
    <div class="px-4 py-3 border-b flex items-center justify-between" style="background: linear-gradient(135deg, #7fc97f 0%, #6db56d 100%);">
        <div class="flex items-center">
            <i class="fas fa-envelope text-white mr-2"></i>
            <span class="text-white font-semibold">Email Draft Ready</span>
        </div>
        <button onclick="document.getElementById('email-preview-{preview_id}').remove()"
                class="text-white hover:bg-white hover:bg-opacity-20 rounded-full p-1 transition-colors">
            <i class="fas fa-times"></i>
        </button>
    </div>

    <!-- Email Preview Content -->
    <div class="p-4">
        <!-- Metadata -->
        <div class="space-y-2 mb-4 pb-4 border-b">
            <div class="flex items-start">
                <span class="text-gray-500 text-xs font-medium w-16">To:</span>
                <span class="text-gray-900 text-sm font-medium">{email_data['recipient']}</span>
            </div>
            <div class="flex items-start">
                <span class="text-gray-500 text-xs font-medium w-16">Subject:</span>
                <span class="text-gray-900 text-sm font-medium">{email_data['subject']}</span>
            </div>
        </div>

        <!-- Email Body -->
        <div class="bg-gray-50 rounded-lg p-4 border-l-4 mb-4" style="border-left-color: #7fc97f;">
            <div class="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{formatted_email['body']}</div>
        </div>

        <!-- Action Prompt -->
        <p class="text-sm text-gray-600 mb-4">
            <i class="fas fa-question-circle mr-1" style="color: #7fc97f;"></i>
            Would you like to send this email or edit it first?
        </p>

        <!-- Action Buttons -->
        <div class="flex space-x-3">
            <button onclick="sendDraftEmail('{email_data['recipient']}', '{email_data['subject']}', '{escaped_body}', 'email-preview-{preview_id}')"
                    class="flex-1 text-white px-4 py-2.5 rounded-lg font-medium text-sm transition-all hover:opacity-90 shadow-sm"
                    style="background: linear-gradient(135deg, #7fc97f 0%, #6db56d 100%);">
                <i class="fas fa-paper-plane mr-2"></i>Send Now
            </button>
            <button onclick="editDraft('{email_data['recipient']}', '{email_data['subject']}', '{escaped_body}', 'email-preview-{preview_id}')"
                    class="flex-1 bg-white border text-gray-700 px-4 py-2.5 rounded-lg font-medium text-sm transition-colors hover:bg-gray-50 shadow-sm"
                    style="border-color: #e5e7eb;">
                <i class="fas fa-edit mr-2"></i>Edit Draft
            </button>
        </div>
    </div>
</div>"""
            
            return response, ["email_draft_created"]
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in compose_email: {e}")
            logger.error(f"Raw response was: {email_json[:500] if 'email_json' in locals() else 'Not available'}")
            return "I had trouble formatting the email. Could you please rephrase your request with the recipient email, subject, and message details?", []
        except Exception as e:
            logger.error(f"Error composing email: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            return "I had trouble understanding your email request. Please provide the recipient email address, subject line, and message content.", []
    
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
                           tone: str = 'professional', reply_context: Dict = None, recipient_name: str = None) -> Dict[str, str]:
        # Get recipient's name
        recipient_first_name = None

        # Priority 1: Explicit recipient_name parameter (from compose prompt)
        if recipient_name:
            recipient_first_name = recipient_name.split()[0] if recipient_name else None
        # Priority 2: sender_name from reply context (when replying to an email)
        elif reply_context and reply_context.get('sender_name'):
            recipient_full_name = reply_context['sender_name']
            recipient_first_name = recipient_full_name.split()[0] if recipient_full_name else None
        # Priority 3: Try to extract from email address, but only if it looks like a real name
        else:
            email_local = recipient.split('@')[0]
            # Check if email looks like a name (contains dots or underscores suggesting name parts)
            if '.' in email_local or '_' in email_local:
                extracted_name = email_local.replace('.', ' ').replace('_', ' ').title()
                # Only use if it doesn't contain numbers (which suggests a username rather than name)
                if not any(char.isdigit() for char in extracted_name):
                    recipient_first_name = extracted_name.split()[0] if extracted_name else None

        # Get sender's actual name from user object
        sender_name = user.name if user.name else user.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()

        # Choose appropriate greeting based on tone and whether we have a name
        if recipient_first_name:
            if tone == 'formal':
                greeting = f"Dear {recipient_first_name},"
                closing = f"Sincerely,\n{sender_name}"
            elif tone == 'casual':
                greeting = f"Hi {recipient_first_name}!"
                closing = f"Best,\n{sender_name}"
            else:  # professional
                greeting = f"Hello {recipient_first_name},"
                closing = f"Best regards,\n{sender_name}"
        else:
            # Use generic greetings when we don't have a good name
            if tone == 'formal':
                greeting = "Dear Sir/Madam,"
                closing = f"Sincerely,\n{sender_name}"
            elif tone == 'casual':
                greeting = "Hi there!"
                closing = f"Best,\n{sender_name}"
            else:  # professional
                greeting = "Hello,"
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
                        except (ValueError, TypeError):
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