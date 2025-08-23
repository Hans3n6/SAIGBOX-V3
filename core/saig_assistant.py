import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import boto3
from sqlalchemy.orm import Session

from core.database import Email, User, ChatHistory, ActionItem
from core.gmail_service import GmailService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SAIGAssistant:
    def __init__(self):
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        self.gmail_service = GmailService()
        self.model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    
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
                    "subject": email.subject,
                    "sender": email.sender,
                    "body": email.body_text or email.snippet,
                    "received_at": email.received_at.isoformat() if email.received_at else None
                }
        
        return email_context
    
    async def _analyze_intent(self, message: str, context: Dict[str, Any]) -> str:
        prompt = f"""Analyze the user's message and determine their intent.
        
User message: {message}

Available intents:
- search_emails: User wants to find specific emails
- compose_email: User wants to write/send a new email
- mark_read: User wants to mark emails as read
- mark_unread: User wants to mark emails as unread
- summarize: User wants a summary of emails or a specific email
- create_action: User wants to create an action item
- list_actions: User wants to see action items
- delete_email: User wants to delete/trash emails
- star_email: User wants to star/favorite emails
- general_question: General question about emails or the system
- help: User needs help or instructions

Context:
- Total emails: {context['total_emails']}
- Unread emails: {context['total_unread']}
- Has selected email: {context['selected_email'] is not None}

Return only the intent name, nothing else."""

        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 50,
                    "temperature": 0.3
                })
            )
            
            result = json.loads(response['body'].read())
            intent = result['content'][0]['text'].strip().lower()
            
            # Validate intent
            valid_intents = ['search_emails', 'compose_email', 'mark_read', 'mark_unread', 
                           'summarize', 'create_action', 'list_actions', 'delete_email', 
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
        
        if intent == 'search_emails':
            response, actions = await self._search_emails(db, user, message)
        elif intent == 'compose_email':
            response = "I can help you compose an email. Please provide the recipient's email address, subject, and message body."
        elif intent == 'mark_read':
            response, actions = await self._mark_emails_read(db, user, message, context)
        elif intent == 'summarize':
            response = await self._summarize_emails(context)
        elif intent == 'create_action':
            response, actions = await self._create_action_item(db, user, message, context)
        elif intent == 'list_actions':
            response = await self._list_action_items(db, user)
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
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                    "temperature": 0.3
                })
            )
            
            result = json.loads(response['body'].read())
            search_query = result['content'][0]['text'].strip()
            
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
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.5
                })
            )
            
            result = json.loads(response['body'].read())
            return result['content'][0]['text'].strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "I couldn't generate a summary at this time."
    
    async def _create_action_item(self, db: Session, user: User, message: str, 
                                 context: Dict[str, Any]) -> tuple:
        # Extract action item details from message
        prompt = f"""Extract action item details from this message: "{message}"
Return as JSON with keys: title, description, priority (high/medium/low), due_date (ISO format or null)"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.3
                })
            )
            
            result = json.loads(response['body'].read())
            action_data = json.loads(result['content'][0]['text'].strip())
            
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
    
    async def _generate_response(self, message: str, context: Dict[str, Any]) -> str:
        prompt = f"""You are SAIG, a helpful email assistant. Respond to this message naturally and helpfully.

User message: {message}

Context:
- User has {context['total_emails']} total emails
- {context['total_unread']} unread emails

Keep your response concise and helpful."""

        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.7
                })
            )
            
            result = json.loads(response['body'].read())
            return result['content'][0]['text'].strip()
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm here to help with your emails. What would you like to do?"
    
    def _get_help_message(self) -> str:
        return """I'm SAIG, your email assistant. Here's what I can help you with:

📧 **Email Management:**
• Search for emails by keyword
• Mark emails as read/unread
• Star or unstar emails
• Move emails to trash
• Compose and send new emails

📝 **Action Items:**
• Create action items from emails
• List your pending tasks
• Set priorities and due dates

💬 **Smart Features:**
• Summarize long emails
• Get email insights
• Natural language commands

Just tell me what you need help with!"""