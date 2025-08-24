import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from sqlalchemy.orm import Session
from core.database import Email, User, UrgencyPattern

logger = logging.getLogger(__name__)

class UrgencyDetector:
    """
    Multi-layer urgency detection system that runs on all incoming emails.
    Uses keyword matching, sender analysis, and pattern recognition.
    Liberal detection (cast wide net) with 40/100 threshold.
    """
    
    # High-priority keywords (30 points each)
    HIGH_PRIORITY_KEYWORDS = [
        'urgent', 'asap', 'critical', 'emergency', 'immediate', 
        'crisis', 'escalation', 'blocker', 'showstopper'
    ]
    
    # Time-sensitive keywords (20 points each)
    TIME_SENSITIVE_KEYWORDS = [
        'today', 'tomorrow', 'eod', 'cob', 'deadline', 'due date',
        'by end of', 'within', 'expires', 'expiring', 'overdue'
    ]
    
    # Action required keywords (15 points each)
    ACTION_KEYWORDS = [
        'please review', 'need approval', 'waiting for', 'action required',
        'please confirm', 'please respond', 'need your', 'require your',
        'can you', 'could you', 'would you', 'will you'
    ]
    
    # Follow-up indicators (15 points)
    FOLLOWUP_KEYWORDS = [
        'follow up', 'following up', 'reminder', 'second request',
        'haven\'t heard', 'checking in', 'any update', 'status update'
    ]
    
    # C-level and important titles
    IMPORTANT_TITLES = [
        'ceo', 'cto', 'cfo', 'coo', 'president', 'vice president', 'vp',
        'director', 'manager', 'supervisor', 'head of', 'chief', 'executive'
    ]
    
    def __init__(self, db: Session = None):
        self.db = db
        self.urgency_threshold = int(os.getenv('URGENCY_THRESHOLD', '40'))
    
    def calculate_urgency_score(self, email: Email, user_patterns: List[UrgencyPattern] = None) -> Tuple[int, str]:
        """
        Calculate urgency score from 0-100.
        
        Returns: (score, reason_string)
        """
        score = 0
        reasons = []
        
        # Combine subject and body for analysis
        content = f"{email.subject or ''} {email.body_text or email.snippet or ''}".lower()
        
        # 1. Check high-priority keywords (30 points each)
        for keyword in self.HIGH_PRIORITY_KEYWORDS:
            if keyword in content:
                score += 30
                reasons.append(f"High-priority keyword: {keyword}")
                break  # Only count once
        
        # 2. Check time-sensitive keywords (20 points each)
        for keyword in self.TIME_SENSITIVE_KEYWORDS:
            if keyword in content:
                score += 20
                reasons.append(f"Time-sensitive: {keyword}")
                break  # Only count once
        
        # 3. Check action keywords (15 points each)
        action_count = 0
        for keyword in self.ACTION_KEYWORDS:
            if keyword in content and action_count < 2:  # Max 2 action keywords
                score += 15
                reasons.append(f"Action required: {keyword}")
                action_count += 1
        
        # 4. Check follow-up indicators (15 points)
        for keyword in self.FOLLOWUP_KEYWORDS:
            if keyword in content:
                score += 15
                reasons.append(f"Follow-up detected: {keyword}")
                break
        
        # 5. Check sender importance (40 points)
        sender_score, sender_reason = self.check_sender_importance(
            email.sender, email.sender_name, user_patterns
        )
        if sender_score > 0:
            score += sender_score
            reasons.append(sender_reason)
        
        # 6. Check subject line indicators (10-20 points)
        subject_lower = (email.subject or '').lower()
        
        # All caps words in subject
        if email.subject and any(word.isupper() and len(word) > 2 for word in email.subject.split()):
            score += 10
            reasons.append("All-caps words in subject")
        
        # Multiple exclamation marks
        if '!!' in (email.subject or ''):
            score += 10
            reasons.append("Multiple exclamation marks")
        
        # [URGENT] or similar tags
        if re.search(r'\[(urgent|important|action|priority)\]', subject_lower):
            score += 20
            reasons.append("Priority tag in subject")
        
        # 7. Check for deadlines in content
        deadline_dates = self.extract_deadlines(content)
        if deadline_dates:
            # Check if any deadline is within 48 hours
            now = datetime.now()
            for deadline, context in deadline_dates:
                if deadline and (deadline - now).days <= 2:
                    score += 25
                    reasons.append(f"Deadline within 48 hours: {context}")
                    break
        
        # 8. Check if it's a reply to a thread (might be escalation)
        if email.subject and email.subject.lower().startswith('re:'):
            # Check if there are multiple Re: (indicating back and forth)
            re_count = email.subject.lower().count('re:')
            if re_count >= 2:
                score += 15
                reasons.append(f"Multiple replies in thread ({re_count})")
        
        # Cap score at 100
        score = min(score, 100)
        
        # Join reasons
        reason_string = '; '.join(reasons) if reasons else 'No specific urgency indicators'
        
        return score, reason_string
    
    def check_sender_importance(self, sender_email: str, sender_name: str, 
                               user_patterns: List[UrgencyPattern] = None) -> Tuple[int, str]:
        """
        Check if sender is VIP or has urgency history.
        Check for C-level titles, manager, director, VP, etc.
        
        Returns: (score, reason)
        """
        if not sender_email:
            return 0, ""
        
        sender_lower = sender_email.lower()
        sender_name_lower = (sender_name or '').lower()
        
        # Check user-defined VIP patterns
        if user_patterns:
            for pattern in user_patterns:
                if pattern.is_vip and pattern.pattern_type == 'sender':
                    if pattern.pattern_value.lower() in sender_lower:
                        return 50, f"VIP sender: {sender_name or sender_email}"
                
                if pattern.is_ignored and pattern.pattern_type == 'sender':
                    if pattern.pattern_value.lower() in sender_lower:
                        return -100, f"Ignored sender"  # Negative score to prevent urgency
        
        # Check for important titles in sender name or email
        for title in self.IMPORTANT_TITLES:
            if title in sender_name_lower or title in sender_lower:
                return 40, f"Important sender title: {title}"
        
        # Check for important domains
        important_domains = ['legal', 'compliance', 'finance', 'hr', 'security']
        for domain in important_domains:
            if domain in sender_lower:
                return 30, f"Important domain: {domain}"
        
        # Check historical patterns (if database available)
        if self.db and user_patterns:
            for pattern in user_patterns:
                if pattern.pattern_type == 'sender' and pattern.pattern_value.lower() in sender_lower:
                    if pattern.times_marked_urgent > pattern.times_marked_not_urgent * 2:
                        return 35, f"Frequently urgent sender"
        
        return 0, ""
    
    def extract_deadlines(self, text: str) -> List[Tuple[Optional[datetime], str]]:
        """
        Extract any mentioned dates/deadlines from email text.
        Return list of (date, context) tuples.
        """
        deadlines = []
        text_lower = text.lower()
        
        # Common deadline patterns
        patterns = [
            (r'by (\w+day)', 'relative_day'),  # by Monday, by Friday
            (r'by (\d{1,2}/\d{1,2})', 'date'),  # by 12/25
            (r'due (\w+day)', 'relative_day'),  # due Monday
            (r'due (\d{1,2}/\d{1,2})', 'date'),  # due 12/25
            (r'before (\w+day)', 'relative_day'),  # before Friday
            (r'by end of (\w+)', 'end_of'),  # by end of week/month/day
            (r'within (\d+) (hours?|days?)', 'within'),  # within 24 hours
        ]
        
        for pattern, pattern_type in patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                context = match.group(0)
                
                if pattern_type == 'relative_day':
                    # Parse weekday names
                    day_name = match.group(1)
                    deadline_date = self._parse_weekday(day_name)
                    if deadline_date:
                        deadlines.append((deadline_date, context))
                
                elif pattern_type == 'date':
                    # Parse MM/DD format
                    date_str = match.group(1)
                    deadline_date = self._parse_date(date_str)
                    if deadline_date:
                        deadlines.append((deadline_date, context))
                
                elif pattern_type == 'within':
                    # Parse "within X hours/days"
                    amount = int(match.group(1))
                    unit = match.group(2)
                    
                    if 'hour' in unit:
                        deadline_date = datetime.now() + timedelta(hours=amount)
                    else:  # days
                        deadline_date = datetime.now() + timedelta(days=amount)
                    
                    deadlines.append((deadline_date, context))
                
                elif pattern_type == 'end_of':
                    # Parse "end of day/week/month"
                    period = match.group(1)
                    deadline_date = self._parse_end_of(period)
                    if deadline_date:
                        deadlines.append((deadline_date, context))
        
        return deadlines
    
    def _parse_weekday(self, day_name: str) -> Optional[datetime]:
        """Parse weekday name to datetime."""
        weekdays = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        day_name = day_name.lower()
        if day_name in weekdays:
            today = datetime.now()
            target_weekday = weekdays[day_name]
            days_ahead = target_weekday - today.weekday()
            
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            
            return today + timedelta(days=days_ahead)
        
        # Handle "today" and "tomorrow"
        if day_name == 'today':
            return datetime.now()
        elif day_name == 'tomorrow':
            return datetime.now() + timedelta(days=1)
        
        return None
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse MM/DD format to datetime."""
        try:
            # Assume current year
            current_year = datetime.now().year
            month, day = map(int, date_str.split('/'))
            
            # Create date
            date = datetime(current_year, month, day)
            
            # If date is in the past, assume next year
            if date < datetime.now():
                date = datetime(current_year + 1, month, day)
            
            return date
        except:
            return None
    
    def _parse_end_of(self, period: str) -> Optional[datetime]:
        """Parse 'end of day/week/month' to datetime."""
        now = datetime.now()
        
        if period == 'day' or period == 'today':
            return now.replace(hour=23, minute=59, second=59)
        elif period == 'week':
            # End of current week (Friday)
            days_until_friday = 4 - now.weekday()
            if days_until_friday < 0:
                days_until_friday += 7
            return (now + timedelta(days=days_until_friday)).replace(hour=23, minute=59, second=59)
        elif period == 'month':
            # Last day of current month
            if now.month == 12:
                last_day = datetime(now.year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(now.year, now.month + 1, 1) - timedelta(days=1)
            return last_day.replace(hour=23, minute=59, second=59)
        
        return None
    
    def should_mark_urgent(self, email: Email, user: User) -> Tuple[bool, int, str]:
        """
        Determine if an email should be marked as urgent.
        
        Returns: (is_urgent, score, reason)
        """
        # Get user patterns from database
        user_patterns = []
        if self.db:
            user_patterns = self.db.query(UrgencyPattern).filter(
                UrgencyPattern.user_id == user.id
            ).all()
        
        # Calculate urgency score
        score, reason = self.calculate_urgency_score(email, user_patterns)
        
        # Check threshold
        is_urgent = score >= self.urgency_threshold
        
        return is_urgent, score, reason
    
    def learn_from_correction(self, email: Email, user: User, corrected_to_urgent: bool):
        """
        Learn from user corrections to improve future detection.
        """
        if not self.db:
            return
        
        # Extract patterns from the email
        sender_domain = email.sender.split('@')[1] if '@' in email.sender else email.sender
        
        # Update or create sender pattern
        sender_pattern = self.db.query(UrgencyPattern).filter(
            UrgencyPattern.user_id == user.id,
            UrgencyPattern.pattern_type == 'sender',
            UrgencyPattern.pattern_value == sender_domain
        ).first()
        
        if not sender_pattern:
            sender_pattern = UrgencyPattern(
                user_id=user.id,
                pattern_type='sender',
                pattern_value=sender_domain
            )
            self.db.add(sender_pattern)
        
        # Update counts
        if corrected_to_urgent:
            sender_pattern.times_marked_urgent += 1
        else:
            sender_pattern.times_marked_not_urgent += 1
        
        self.db.commit()
        
        logger.info(f"Learned from correction: {sender_domain} -> urgent={corrected_to_urgent}")

import os