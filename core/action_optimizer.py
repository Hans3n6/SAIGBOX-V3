"""
Enhanced Action Item Creation System with Optimizations
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from core.database import Email, User, ActionItem, UrgencyPattern

logger = logging.getLogger(__name__)

class ActionOptimizer:
    """
    Optimized action item creation system with ML, caching, and parallel processing
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.pattern_cache = {}
        self.sender_history = {}
        
    @lru_cache(maxsize=1000)
    def get_cached_urgency_score(self, email_hash: str) -> Optional[int]:
        """Cache urgency scores for similar emails"""
        # Check if we've seen similar email recently
        return self.pattern_cache.get(email_hash)
    
    def hash_email_content(self, email: Email) -> str:
        """Create hash of email characteristics for caching"""
        content = f"{email.sender}:{email.subject}:{(email.snippet or '')[:100]}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def parallel_process_urgent_emails(self, emails: List[Email], user: User) -> List[ActionItem]:
        """Process multiple emails in parallel for efficiency"""
        tasks = []
        for email in emails:
            task = asyncio.create_task(self.extract_and_create_action(email, user))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out errors and None results
        actions = [r for r in results if isinstance(r, ActionItem)]
        return actions
    
    async def extract_and_create_action(self, email: Email, user: User) -> Optional[ActionItem]:
        """Extract action items with enhanced context awareness"""
        try:
            # Check cache first
            email_hash = self.hash_email_content(email)
            cached_score = self.get_cached_urgency_score(email_hash)
            
            if cached_score and cached_score < 40:
                return None  # Skip low-priority cached emails
            
            # Get sender history for context
            sender_context = await self.get_sender_context(email.sender, user.id)
            
            # Extract action with context
            action_data = await self.smart_extract_action(email, sender_context, user)
            
            if action_data and action_data['confidence'] >= 65:
                # Create action item
                action = ActionItem(
                    user_id=user.id,
                    email_id=email.id,
                    title=action_data['title'],
                    description=action_data['description'],
                    due_date=action_data.get('due_date'),
                    priority=action_data.get('priority', 2),
                    auto_created=True,
                    confidence_score=action_data['confidence'],
                    source_quote=action_data.get('source_quote')
                )
                self.db.add(action)
                self.db.commit()
                
                # Update cache
                self.pattern_cache[email_hash] = action_data['confidence']
                
                return action
                
        except Exception as e:
            logger.error(f"Error creating action from email {email.id}: {e}")
            return None
    
    async def get_sender_context(self, sender: str, user_id: str) -> Dict[str, Any]:
        """Get historical context about sender"""
        if sender in self.sender_history:
            return self.sender_history[sender]
        
        # Query sender statistics
        stats = self.db.query(
            func.count(Email.id).label('total_emails'),
            func.sum(Email.is_urgent).label('urgent_count'),
            func.avg(Email.urgency_score).label('avg_urgency')
        ).filter(
            Email.sender == sender,
            Email.user_id == user_id
        ).first()
        
        context = {
            'total_emails': stats.total_emails or 0,
            'urgent_count': stats.urgent_count or 0,
            'avg_urgency': float(stats.avg_urgency or 0),
            'is_frequent': stats.total_emails > 10,
            'usually_urgent': (stats.urgent_count / max(stats.total_emails, 1)) > 0.5
        }
        
        # Cache for future use
        self.sender_history[sender] = context
        return context
    
    async def smart_extract_action(self, email: Email, sender_context: Dict, user: User) -> Optional[Dict]:
        """
        Smart action extraction with ML-like pattern recognition
        """
        content = email.body_text or email.snippet or ""
        subject = email.subject or ""
        
        # Pattern matching for different action types
        patterns = {
            'meeting_request': {
                'keywords': ['schedule', 'meeting', 'call', 'discuss', 'availability'],
                'template': 'Schedule meeting regarding {subject}',
                'priority': 2
            },
            'approval_needed': {
                'keywords': ['approval', 'approve', 'sign off', 'authorize'],
                'template': 'Review and approve: {subject}',
                'priority': 1
            },
            'document_review': {
                'keywords': ['review', 'feedback', 'comments', 'draft', 'document'],
                'template': 'Review document: {subject}',
                'priority': 2
            },
            'payment_action': {
                'keywords': ['invoice', 'payment', 'bill', 'due', 'remittance'],
                'template': 'Process payment for {subject}',
                'priority': 1
            },
            'response_required': {
                'keywords': ['respond', 'reply', 'answer', 'confirm', 'let me know'],
                'template': 'Respond to: {subject}',
                'priority': 2
            }
        }
        
        # Find matching patterns
        matched_pattern = None
        confidence = 0
        
        for pattern_name, pattern_data in patterns.items():
            matches = sum(1 for kw in pattern_data['keywords'] if kw in content.lower() or kw in subject.lower())
            pattern_confidence = min(matches * 25, 90)  # Max 90% from pattern matching
            
            # Boost confidence based on sender context
            if sender_context['usually_urgent']:
                pattern_confidence += 10
            
            if pattern_confidence > confidence:
                confidence = pattern_confidence
                matched_pattern = pattern_data
        
        if matched_pattern and confidence >= 50:
            # Extract deadline if mentioned
            due_date = self.extract_deadline(content)
            
            # Find source quote (most relevant sentence)
            source_quote = self.extract_relevant_sentence(content, matched_pattern['keywords'])
            
            return {
                'title': matched_pattern['template'].format(subject=subject[:50]),
                'description': f"From {email.sender_name or email.sender}: {source_quote}",
                'priority': matched_pattern['priority'],
                'due_date': due_date,
                'confidence': confidence,
                'source_quote': source_quote[:200]
            }
        
        return None
    
    def extract_deadline(self, text: str) -> Optional[datetime]:
        """Extract deadline from text using patterns"""
        import re
        from dateutil import parser
        
        # Common deadline patterns
        patterns = [
            r'by\s+(\w+\s+\d{1,2})',  # by January 15
            r'before\s+(\w+\s+\d{1,2})',  # before March 1
            r'due\s+(\w+\s+\d{1,2})',  # due February 28
            r'deadline[:\s]+(\w+\s+\d{1,2})',  # deadline: April 10
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1)
                    deadline = parser.parse(date_str, fuzzy=True)
                    # Ensure it's in the future
                    if deadline > datetime.now():
                        return deadline
                except:
                    continue
        
        # Check for relative dates
        if 'today' in text.lower():
            return datetime.now().replace(hour=23, minute=59)
        elif 'tomorrow' in text.lower():
            return datetime.now() + timedelta(days=1)
        elif 'this week' in text.lower():
            return datetime.now() + timedelta(days=7)
        
        return None
    
    def extract_relevant_sentence(self, text: str, keywords: List[str]) -> str:
        """Extract the most relevant sentence containing action keywords"""
        sentences = text.split('.')
        best_sentence = ""
        best_score = 0
        
        for sentence in sentences:
            score = sum(1 for kw in keywords if kw in sentence.lower())
            if score > best_score:
                best_score = score
                best_sentence = sentence.strip()
        
        return best_sentence or text[:200]
    
    async def learn_from_feedback(self, action_id: str, user_confirmed: bool):
        """Learn from user feedback to improve future predictions"""
        action = self.db.query(ActionItem).filter(ActionItem.id == action_id).first()
        if not action or not action.email_id:
            return
        
        email = self.db.query(Email).filter(Email.id == action.email_id).first()
        if not email:
            return
        
        # Update pattern confidence based on feedback
        email_hash = self.hash_email_content(email)
        
        if user_confirmed:
            # Increase confidence for similar patterns
            self.pattern_cache[email_hash] = min(100, self.pattern_cache.get(email_hash, 70) + 10)
        else:
            # Decrease confidence for similar patterns
            self.pattern_cache[email_hash] = max(0, self.pattern_cache.get(email_hash, 70) - 20)
        
        # Store feedback in database for future ML training
        # This could be expanded to train a proper ML model
        logger.info(f"Learned from feedback: action_id={action_id}, confirmed={user_confirmed}")


class RealTimeActionProcessor:
    """
    Real-time action processing with WebSocket support
    """
    
    def __init__(self, optimizer: ActionOptimizer):
        self.optimizer = optimizer
        self.active_connections = []
    
    async def process_email_stream(self, email: Email, user: User):
        """Process email in real-time and notify connected clients"""
        # Quick urgency check
        if email.urgency_score < 30:
            return
        
        # Extract action immediately
        action = await self.optimizer.extract_and_create_action(email, user)
        
        if action:
            # Notify all connected WebSocket clients
            notification = {
                "type": "new_action_item",
                "action": {
                    "id": action.id,
                    "title": action.title,
                    "priority": action.priority,
                    "due_date": action.due_date.isoformat() if action.due_date else None,
                    "email_subject": email.subject
                }
            }
            
            for connection in self.active_connections:
                await connection.send_json(notification)
    
    def add_connection(self, websocket):
        """Add WebSocket connection for real-time updates"""
        self.active_connections.append(websocket)
    
    def remove_connection(self, websocket):
        """Remove WebSocket connection"""
        self.active_connections.remove(websocket)