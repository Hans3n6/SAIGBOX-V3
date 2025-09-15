"""
Automatic Action Item Creator
Creates action items from urgent emails automatically
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from core.database import Email, User, ActionItem

logger = logging.getLogger(__name__)

class ActionItemCreator:
    """Creates action items from urgent emails automatically"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_from_urgent_email(self, email: Email, user: User) -> Optional[ActionItem]:
        """
        Create an action item from an urgent email.
        Returns the created action item or None if skipped.
        """
        # Skip if action items already created for this email
        if email.auto_actions_created:
            logger.debug(f"Action items already created for email {email.id}")
            return None
        
        # Only create for emails with high urgency score
        if email.urgency_score < 70:
            logger.debug(f"Email urgency score {email.urgency_score} below threshold (70)")
            return None
        
        # Extract action item details
        title = self._extract_title(email)
        description = self._extract_description(email)
        due_date = self._extract_due_date(email)
        priority = self._calculate_priority(email.urgency_score)
        
        # Create the action item
        action_item = ActionItem(
            user_id=user.id,
            email_id=email.id,
            title=title,
            description=description,
            due_date=due_date,
            priority=priority,
            status="pending",
            auto_created=True,
            confidence_score=email.urgency_score,
            source_quote=email.urgency_reason
        )
        
        self.db.add(action_item)
        
        # Mark email as having auto-created actions
        email.auto_actions_created = True
        email.action_count = (email.action_count or 0) + 1
        
        # Commit the changes
        self.db.commit()
        
        logger.info(f"Created action item '{title}' from urgent email {email.id}")
        return action_item
    
    def _extract_title(self, email: Email) -> str:
        """Extract a concise title for the action item"""
        subject = email.subject or "Urgent Email"
        
        # Remove common prefixes
        prefixes_to_remove = ['Re:', 'Fwd:', 'RE:', 'FW:', 'Fw:']
        for prefix in prefixes_to_remove:
            if subject.startswith(prefix):
                subject = subject[len(prefix):].strip()
        
        # Truncate if too long
        if len(subject) > 100:
            subject = subject[:97] + "..."
        
        # Add urgency indicator if not already present
        if 'urgent' not in subject.lower() and email.urgency_score >= 90:
            subject = "🔴 " + subject
        elif email.urgency_score >= 80:
            subject = "🟡 " + subject
        
        return subject
    
    def _extract_description(self, email: Email) -> str:
        """Extract description from email content"""
        description_parts = []
        
        # Add sender info
        description_parts.append(f"From: {email.sender_name or email.sender}")
        
        # Add urgency reason
        if email.urgency_reason:
            description_parts.append(f"Urgency: {email.urgency_reason}")
        
        # Add email snippet
        if email.snippet:
            snippet = email.snippet[:500]  # Limit length
            description_parts.append(f"\nEmail preview:\n{snippet}")
        
        return "\n".join(description_parts)
    
    def _extract_due_date(self, email: Email) -> Optional[datetime]:
        """
        Extract due date from email content or urgency reason.
        Returns a datetime or None.
        """
        # Default due dates based on urgency score
        now = datetime.now()
        
        if email.urgency_score >= 90:
            # Very urgent: due today EOD
            return now.replace(hour=17, minute=0, second=0, microsecond=0)
        elif email.urgency_score >= 80:
            # Urgent: due tomorrow EOD
            return (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
        elif email.urgency_score >= 70:
            # Moderately urgent: due in 2 days
            return (now + timedelta(days=2)).replace(hour=17, minute=0, second=0, microsecond=0)
        
        # Check urgency reason for specific deadlines
        if email.urgency_reason:
            reason_lower = email.urgency_reason.lower()
            
            # Today
            if any(word in reason_lower for word in ['today', 'eod', 'end of day', 'cob']):
                return now.replace(hour=17, minute=0, second=0, microsecond=0)
            
            # Tomorrow
            if 'tomorrow' in reason_lower:
                return (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
            
            # Within 24/48 hours
            if 'within 24 hours' in reason_lower:
                return now + timedelta(hours=24)
            if 'within 48 hours' in reason_lower:
                return now + timedelta(hours=48)
            
            # This week
            if 'this week' in reason_lower or 'end of week' in reason_lower:
                # Friday EOD
                days_until_friday = (4 - now.weekday()) % 7
                if days_until_friday == 0 and now.hour >= 17:
                    days_until_friday = 7  # Next Friday
                return (now + timedelta(days=days_until_friday)).replace(
                    hour=17, minute=0, second=0, microsecond=0
                )
        
        # Default: 3 days from now
        return (now + timedelta(days=3)).replace(hour=17, minute=0, second=0, microsecond=0)
    
    def _calculate_priority(self, urgency_score: int) -> int:
        """
        Calculate priority based on urgency score.
        Returns 1 (High), 2 (Medium), or 3 (Low).
        """
        if urgency_score >= 85:
            return 1  # High priority
        elif urgency_score >= 70:
            return 2  # Medium priority
        else:
            return 3  # Low priority
    
    def process_urgent_emails(self, user: User) -> int:
        """
        Process all urgent emails for a user that don't have action items yet.
        Returns the number of action items created.
        """
        # Find urgent emails without action items
        urgent_emails = self.db.query(Email).filter(
            Email.user_id == user.id,
            Email.is_urgent == True,
            Email.auto_actions_created == False,
            Email.urgency_score >= 70,
            Email.deleted_at.is_(None)
        ).all()
        
        created_count = 0
        for email in urgent_emails:
            action_item = self.create_from_urgent_email(email, user)
            if action_item:
                created_count += 1
        
        if created_count > 0:
            logger.info(f"Created {created_count} action items for user {user.email}")
        
        return created_count