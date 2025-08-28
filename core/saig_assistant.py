import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
from sqlalchemy.orm import Session

from core.database import Email, User, ChatHistory, ActionItem
from core.gmail_service import GmailService
from core.urgency_detector import UrgencyDetector

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
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.http_client = httpx.AsyncClient(timeout=30.0)
        # Use Claude 3.5 Haiku for faster responses
        self.model = "claude-3-5-haiku-20241022"
    
    async def process_message(self, db: Session, user: User, message: str, 
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            # Save user message to history
            user_msg = ChatHistory(user_id=user.id, role="user", message=message)
            db.add(user_msg)
            
            # Get email context if needed
            email_context = await self._get_email_context(db, user, message, context)
            
            # Determine intent
            intent = await self._analyze_intent(message, email_context)
            
            # Execute action based on intent
            response, actions = await self._execute_intent(db, user, intent, message, email_context)
            
            # Save assistant response to history
            assistant_msg = ChatHistory(user_id=user.id, role="assistant", message=response)
            db.add(assistant_msg)
            db.commit()
            
            return {
                "response": response,
                "actions_taken": actions,
                "intent": intent
            }
            
        except Exception as e:
            logger.error(f"Error processing SAIG message: {e}")
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
                           'star_email', 'general_question', 'help']
            
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
        elif intent == 'help':
            response = self._get_help_message()
        else:
            response = await self._generate_response(message, context)
        
        return response, actions
    
    async def _search_emails(self, db: Session, user: User, message: str) -> tuple:
        # Extract search query
        prompt = f"""Extract the search query from this message: "{message}"
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
        prompt = f"""Extract action item details from this message: "{message}"
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
    
    async def _delete_email(self, db: Session, user: User, message: str, 
                           context: Dict[str, Any]) -> tuple:
        """Move email to trash"""
        if not context.get('selected_email'):
            return "Please select an email first, then ask me to delete it.", []
        
        selected_email = context['selected_email']
        
        # Get the email from database
        email = db.query(Email).filter(
            Email.id == selected_email['id'],
            Email.user_id == user.id
        ).first()
        
        if not email:
            return "Could not find the selected email.", []
        
        # Move to trash in Gmail
        if self.gmail_service.move_to_trash(user, email.gmail_id):
            # Mark as deleted in database
            email.deleted_at = datetime.utcnow()
            db.commit()
            return f"Moved '{email.subject}' to trash.", ["email_deleted"]
        else:
            return "Failed to move email to trash. Please try again.", []
    
    async def _move_to_folder(self, db: Session, user: User, message: str, 
                             context: Dict[str, Any]) -> tuple:
        """Move email to a specific folder/label"""
        if not context.get('selected_email'):
            return "Please select an email first, then ask me to move it to a folder.", []
        
        # Extract folder name from message
        prompt = f"""Extract the folder/label name from this message: "{message}"
Return only the folder name, nothing else. Common folders are: Work, Personal, Important, Follow-up, Archive, Projects, etc."""
        
        try:
            folder_name = await self._call_anthropic(prompt, max_tokens=50, temperature=0.3)
            folder_name = folder_name.strip()
            
            if not folder_name or folder_name.lower() in ['none', 'null', '']:
                return "Please specify which folder you'd like to move the email to.", []
            
            selected_email = context['selected_email']
            
            # Get the email from database
            email = db.query(Email).filter(
                Email.id == selected_email['id'],
                Email.user_id == user.id
            ).first()
            
            if not email:
                return "Could not find the selected email.", []
            
            # Move to folder in Gmail
            if self.gmail_service.move_to_label(user, email.gmail_id, folder_name):
                return f"Moved '{email.subject}' to '{folder_name}' folder.", ["email_moved"]
            else:
                return f"Failed to move email to '{folder_name}'. Please try again.", []
                
        except Exception as e:
            logger.error(f"Error moving email to folder: {e}")
            return "I had trouble moving the email. Please try again.", []
    
    async def _create_folder(self, db: Session, user: User, message: str) -> tuple:
        """Create a new folder/label"""
        # Extract folder name from message
        prompt = f"""Extract the folder/label name to create from this message: "{message}"
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
        prompt = f"""Extract email composition details from this message: "{message}"

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
• Move emails to trash
• Move emails to folders
• Create new folders/labels
• List available folders
• Compose and send new emails
• Reply to emails intelligently

📁 **Folder Organization:**
• "Create a folder called Work"
• "Move this email to Personal folder"
• "Show me my folders"
• "Delete this email" (moves to trash)

📝 **Action Items:**
• Create action items from emails
• List your pending tasks
• Set priorities and due dates

💬 **Smart Features:**
• Summarize long emails
• Get email insights
• Natural language commands

Just tell me what you need help with!"""