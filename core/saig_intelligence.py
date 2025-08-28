"""
SAIG Intelligence Module - Advanced AI capabilities for email management
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc

from core.database import Email, User, ActionItem, ChatHistory

logger = logging.getLogger(__name__)

class SAIGIntelligence:
    """Advanced intelligence capabilities for SAIG"""
    
    def __init__(self):
        self.pattern_cache = {}
        self.user_patterns = defaultdict(dict)
    
    async def analyze_email_patterns(self, db: Session, user: User) -> Dict[str, Any]:
        """Analyze user's email patterns for proactive suggestions"""
        
        patterns = {
            'frequent_senders': [],
            'usual_actions': {},
            'response_times': {},
            'email_categories': {},
            'peak_hours': [],
            'unread_buildup': 0,
            'suggested_actions': []
        }
        
        # Get last 30 days of email activity
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        # Analyze frequent senders
        frequent_senders = db.query(
            Email.sender,
            Email.sender_name,
            func.count(Email.id).label('count')
        ).filter(
            Email.user_id == user.id,
            Email.received_at >= cutoff_date,
            Email.deleted_at.is_(None)
        ).group_by(Email.sender, Email.sender_name).order_by(desc('count')).limit(10).all()
        
        patterns['frequent_senders'] = [
            {'email': s.sender, 'name': s.sender_name, 'count': s.count}
            for s in frequent_senders
        ]
        
        # Analyze usual actions per sender
        for sender in frequent_senders[:5]:  # Top 5 senders
            sender_emails = db.query(Email).filter(
                Email.user_id == user.id,
                Email.sender == sender.sender,
                Email.deleted_at.is_(None)
            ).all()
            
            # Track what user usually does with emails from this sender
            actions = {
                'read_rate': sum(1 for e in sender_emails if e.is_read) / len(sender_emails) if sender_emails else 0,
                'star_rate': sum(1 for e in sender_emails if e.is_starred) / len(sender_emails) if sender_emails else 0,
                'has_labels': any(e.labels for e in sender_emails if e.labels),
                'avg_response_time': None  # Would need to track replies
            }
            patterns['usual_actions'][sender.sender] = actions
        
        # Analyze email categories
        categories = defaultdict(int)
        keywords = {
            'receipts': ['receipt', 'order', 'invoice', 'payment', 'purchase'],
            'meetings': ['meeting', 'calendar', 'invite', 'schedule', 'call'],
            'newsletters': ['newsletter', 'update', 'weekly', 'monthly', 'digest'],
            'social': ['linkedin', 'facebook', 'twitter', 'instagram'],
            'promotions': ['sale', 'discount', 'offer', 'deal', 'save'],
            'work': ['project', 'deadline', 'report', 'task', 'assigned']
        }
        
        recent_emails = db.query(Email).filter(
            Email.user_id == user.id,
            Email.received_at >= cutoff_date,
            Email.deleted_at.is_(None)
        ).all()
        
        for email in recent_emails:
            subject_lower = (email.subject or '').lower()
            body_snippet = (email.snippet or '').lower()
            
            for category, words in keywords.items():
                if any(word in subject_lower or word in body_snippet for word in words):
                    categories[category] += 1
        
        patterns['email_categories'] = dict(categories)
        
        # Analyze peak email hours
        hour_counts = defaultdict(int)
        for email in recent_emails:
            if email.received_at:
                hour = email.received_at.hour
                hour_counts[hour] += 1
        
        # Find top 3 peak hours
        peak_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        patterns['peak_hours'] = [hour for hour, count in peak_hours]
        
        # Check unread buildup
        patterns['unread_buildup'] = db.query(Email).filter(
            Email.user_id == user.id,
            Email.is_read == False,
            Email.deleted_at.is_(None)
        ).count()
        
        # Generate proactive suggestions
        patterns['suggested_actions'] = self._generate_suggestions(patterns)
        
        return patterns
    
    def _generate_suggestions(self, patterns: Dict) -> List[Dict]:
        """Generate proactive suggestions based on patterns"""
        suggestions = []
        
        # Suggest archiving old newsletters
        if patterns['email_categories'].get('newsletters', 0) > 20:
            suggestions.append({
                'type': 'bulk_action',
                'priority': 'medium',
                'message': f"You have {patterns['email_categories']['newsletters']} newsletters. Want me to archive the older ones?",
                'action': 'archive_old_newsletters'
            })
        
        # Suggest managing unread emails
        if patterns['unread_buildup'] > 50:
            suggestions.append({
                'type': 'inbox_management',
                'priority': 'high',
                'message': f"You have {patterns['unread_buildup']} unread emails. Let me help you quickly sort through them.",
                'action': 'triage_unread'
            })
        
        # Suggest creating filters for frequent senders
        for sender in patterns['frequent_senders'][:3]:
            if sender['count'] > 10:
                action_data = patterns['usual_actions'].get(sender['email'], {})
                if action_data.get('read_rate', 1) < 0.3:  # Rarely read
                    suggestions.append({
                        'type': 'create_filter',
                        'priority': 'low',
                        'message': f"You rarely read emails from {sender['name'] or sender['email']}. Create a filter to auto-archive?",
                        'action': 'create_filter',
                        'sender': sender['email']
                    })
        
        # Suggest email time management
        if patterns['peak_hours']:
            peak_hour = patterns['peak_hours'][0]
            suggestions.append({
                'type': 'time_management',
                'priority': 'low',
                'message': f"You receive most emails around {peak_hour}:00. Want to set up a focus time before then?",
                'action': 'schedule_focus_time'
            })
        
        return suggestions
    
    async def extract_action_items(self, email_content: str, subject: str = "") -> List[Dict]:
        """Extract action items from email content using pattern matching and NLP"""
        
        action_items = []
        
        # Combine subject and content for analysis
        full_text = f"{subject}\n{email_content}"
        
        # Patterns that indicate action items
        action_patterns = [
            # Direct requests
            r"(?:please|could you|can you|would you|will you)\s+([^.?!]{5,50})",
            # Deadlines
            r"(?:by|before|until|due|deadline)\s+([^.?!]{5,50})",
            # Tasks
            r"(?:need to|needs to|must|should|have to)\s+([^.?!]{5,50})",
            # Action verbs at sentence start
            r"^(?:Review|Complete|Send|Submit|Prepare|Schedule|Call|Email|Contact|Finish)\s+([^.?!]{5,50})",
            # Numbered lists
            r"^\d+[\.\)]\s*([^.?!]{5,100})",
            # Bullet points
            r"^[\•\-\*]\s*([^.?!]{5,100})"
        ]
        
        # Extract potential action items
        for pattern in action_patterns:
            matches = re.finditer(pattern, full_text, re.MULTILINE | re.IGNORECASE)
            for match in matches:
                action_text = match.group(1) if match.groups() else match.group(0)
                action_text = action_text.strip()
                
                # Skip if too short or too long
                if len(action_text) < 10 or len(action_text) > 200:
                    continue
                
                # Skip common false positives
                skip_phrases = ['thank you', 'thanks', 'regards', 'sincerely', 'best']
                if any(phrase in action_text.lower() for phrase in skip_phrases):
                    continue
                
                # Try to extract deadline
                deadline = self._extract_deadline(action_text)
                
                # Determine priority based on keywords
                priority = self._determine_priority(action_text)
                
                action_items.append({
                    'text': action_text,
                    'deadline': deadline,
                    'priority': priority,
                    'confidence': 0.7  # Base confidence
                })
        
        # Deduplicate similar action items
        unique_actions = []
        for item in action_items:
            is_duplicate = False
            for unique in unique_actions:
                if self._similarity(item['text'], unique['text']) > 0.8:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_actions.append(item)
        
        return unique_actions
    
    def _extract_deadline(self, text: str) -> Optional[datetime]:
        """Extract deadline from text"""
        
        # Tomorrow
        if 'tomorrow' in text.lower():
            return datetime.utcnow() + timedelta(days=1)
        
        # Next week
        if 'next week' in text.lower():
            return datetime.utcnow() + timedelta(weeks=1)
        
        # End of week
        if 'end of week' in text.lower() or 'eow' in text.lower():
            days_until_friday = (4 - datetime.utcnow().weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            return datetime.utcnow() + timedelta(days=days_until_friday)
        
        # Specific dates (basic patterns)
        date_patterns = [
            r'(\d{1,2})[/-](\d{1,2})',  # MM/DD or MM-DD
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})',  # Month DD
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text.lower())
            if match:
                # Simple date parsing (would need more robust handling in production)
                try:
                    # This is simplified - would need proper date parsing
                    return datetime.utcnow() + timedelta(days=7)  # Default to a week from now
                except:
                    pass
        
        return None
    
    def _determine_priority(self, text: str) -> str:
        """Determine priority based on keywords"""
        
        text_lower = text.lower()
        
        high_priority_keywords = ['urgent', 'asap', 'immediately', 'critical', 'important', 'priority']
        medium_priority_keywords = ['soon', 'when you can', 'this week']
        low_priority_keywords = ['eventually', 'when you get time', 'no rush']
        
        if any(keyword in text_lower for keyword in high_priority_keywords):
            return 'high'
        elif any(keyword in text_lower for keyword in low_priority_keywords):
            return 'low'
        else:
            return 'medium'
    
    def _similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity"""
        
        # Convert to lowercase and split into words
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        # Calculate Jaccard similarity
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    async def summarize_thread(self, db: Session, thread_id: str, user: User) -> Dict[str, Any]:
        """Summarize an email thread"""
        
        # Get all emails in thread
        thread_emails = db.query(Email).filter(
            Email.user_id == user.id,
            Email.thread_id == thread_id,
            Email.deleted_at.is_(None)
        ).order_by(Email.received_at).all()
        
        if not thread_emails:
            return {'error': 'No emails found in thread'}
        
        # Extract key information
        participants = set()
        key_points = []
        decisions = []
        questions = []
        action_items = []
        
        for email in thread_emails:
            # Collect participants
            if email.sender:
                participants.add(email.sender_name or email.sender)
            
            # Extract content
            content = email.body_text or email.snippet or ""
            
            # Look for questions
            question_matches = re.findall(r'[^.?!]*\?', content)
            questions.extend([q.strip() for q in question_matches if len(q.strip()) > 20])
            
            # Look for decisions (simplified)
            decision_patterns = ['decided', 'agreed', 'will proceed', 'confirmed', 'approved']
            for pattern in decision_patterns:
                if pattern in content.lower():
                    # Extract sentence containing decision
                    sentences = content.split('.')
                    for sentence in sentences:
                        if pattern in sentence.lower():
                            decisions.append(sentence.strip())
                            break
            
            # Extract action items
            email_actions = await self.extract_action_items(content, email.subject or "")
            action_items.extend(email_actions)
        
        # Create summary
        summary = {
            'thread_subject': thread_emails[0].subject if thread_emails else 'Unknown',
            'num_emails': len(thread_emails),
            'participants': list(participants),
            'date_range': {
                'start': thread_emails[0].received_at.isoformat() if thread_emails[0].received_at else None,
                'end': thread_emails[-1].received_at.isoformat() if thread_emails[-1].received_at else None
            },
            'key_points': key_points[:5],  # Top 5 key points
            'decisions': decisions[:3],     # Top 3 decisions
            'open_questions': questions[:3], # Top 3 unanswered questions
            'action_items': action_items[:5] # Top 5 action items
        }
        
        return summary
    
    async def predict_email_importance(self, email: Email, user: User, db: Session) -> Dict[str, Any]:
        """Predict the importance of an email based on various factors"""
        
        importance_score = 50  # Base score
        factors = []
        
        # Check sender importance
        sender_email_count = db.query(func.count(Email.id)).filter(
            Email.user_id == user.id,
            Email.sender == email.sender
        ).scalar()
        
        if sender_email_count > 20:
            importance_score += 10
            factors.append("Frequent sender")
        
        # Check for urgency keywords
        urgent_keywords = ['urgent', 'asap', 'immediately', 'deadline', 'critical', 'important']
        content = (email.subject or "") + " " + (email.snippet or "")
        content_lower = content.lower()
        
        for keyword in urgent_keywords:
            if keyword in content_lower:
                importance_score += 15
                factors.append(f"Contains '{keyword}'")
                break
        
        # Check if sender is in frequent senders
        if email.sender_name and any(
            name in email.sender_name.lower() 
            for name in ['boss', 'manager', 'director', 'ceo', 'president']
        ):
            importance_score += 20
            factors.append("Likely from management")
        
        # Check for question marks (needs response)
        if '?' in content:
            importance_score += 10
            factors.append("Contains questions")
        
        # Check for attachments
        if email.has_attachments:
            importance_score += 5
            factors.append("Has attachments")
        
        # Check time sensitivity
        if any(day in content_lower for day in ['today', 'tomorrow', 'tonight']):
            importance_score += 15
            factors.append("Time sensitive")
        
        # Normalize score
        importance_score = min(100, max(0, importance_score))
        
        # Determine category
        if importance_score >= 80:
            category = 'high'
        elif importance_score >= 50:
            category = 'medium'
        else:
            category = 'low'
        
        return {
            'score': importance_score,
            'category': category,
            'factors': factors,
            'suggested_action': self._suggest_action_for_importance(category)
        }
    
    def _suggest_action_for_importance(self, category: str) -> str:
        """Suggest action based on importance category"""
        
        suggestions = {
            'high': "Read and respond immediately",
            'medium': "Review within the next few hours",
            'low': "Can be reviewed later or archived"
        }
        
        return suggestions.get(category, "Review when convenient")
    
    async def learn_user_preferences(self, db: Session, user: User, action: str, email: Email) -> None:
        """Learn from user actions to improve future predictions"""
        
        # Store user action patterns
        pattern_key = f"{user.id}_{email.sender}_{action}"
        
        if pattern_key not in self.pattern_cache:
            self.pattern_cache[pattern_key] = {
                'count': 0,
                'last_action': None,
                'email_characteristics': []
            }
        
        self.pattern_cache[pattern_key]['count'] += 1
        self.pattern_cache[pattern_key]['last_action'] = datetime.utcnow()
        
        # Store email characteristics for pattern learning
        characteristics = {
            'subject_keywords': email.subject.lower().split() if email.subject else [],
            'has_attachments': email.has_attachments,
            'is_thread': bool(email.thread_id),
            'time_of_day': email.received_at.hour if email.received_at else None
        }
        
        self.pattern_cache[pattern_key]['email_characteristics'].append(characteristics)
        
        # TODO: Implement more sophisticated learning algorithm
        # This could include ML models for better predictions
    
    async def smart_compose_suggestions(self, db: Session, user: User, context: Dict) -> List[str]:
        """Generate smart compose suggestions based on context"""
        
        suggestions = []
        
        if context.get('reply_to'):
            # Analyze the email being replied to
            original_email = context['reply_to']
            
            # Check if it's a question
            if '?' in original_email.get('content', ''):
                suggestions.extend([
                    "Yes, that works for me.",
                    "Let me check and get back to you.",
                    "Thanks for asking. Here's my thoughts:"
                ])
            
            # Check for meeting requests
            if any(word in original_email.get('subject', '').lower() 
                   for word in ['meeting', 'call', 'schedule']):
                suggestions.extend([
                    "I'm available at the following times:",
                    "That time works for me.",
                    "Could we reschedule to:"
                ])
        
        else:
            # New email suggestions based on common patterns
            suggestions.extend([
                "I hope this email finds you well.",
                "Following up on our previous conversation,",
                "I wanted to reach out regarding"
            ])
        
        return suggestions[:5]  # Return top 5 suggestions
    
    async def detect_email_category(self, email: Email) -> str:
        """Detect the category of an email"""
        
        content = (email.subject or "") + " " + (email.snippet or "")
        content_lower = content.lower()
        
        categories = {
            'receipt': ['receipt', 'order', 'invoice', 'payment', 'purchase', 'transaction'],
            'newsletter': ['newsletter', 'unsubscribe', 'update', 'weekly', 'monthly'],
            'meeting': ['meeting', 'calendar', 'invite', 'schedule', 'appointment'],
            'social': ['linkedin', 'facebook', 'twitter', 'instagram', 'social'],
            'promotion': ['sale', 'discount', 'offer', 'deal', 'limited time', 'save'],
            'work': ['project', 'deadline', 'report', 'task', 'assigned', 'review'],
            'personal': ['family', 'friend', 'birthday', 'wedding', 'vacation'],
            'support': ['ticket', 'support', 'help', 'issue', 'problem', 'resolved'],
            'notification': ['notification', 'alert', 'reminder', 'automated', 'no-reply']
        }
        
        # Score each category
        category_scores = {}
        for category, keywords in categories.items():
            score = sum(1 for keyword in keywords if keyword in content_lower)
            if score > 0:
                category_scores[category] = score
        
        # Return category with highest score
        if category_scores:
            return max(category_scores, key=category_scores.get)
        
        return 'other'