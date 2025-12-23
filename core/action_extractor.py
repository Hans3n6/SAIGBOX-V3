"""
AI-powered action item extraction from emails
Uses Bedrock/Anthropic to analyze email content and extract actionable tasks
"""
import os
import json
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from core.database import Email, User, ActionItem
from core.saig_assistant import SAIGAssistant

logger = logging.getLogger(__name__)


class ActionableContentChecker:
    """
    Fast, regex-based checker to identify emails likely to contain action items.
    No AI required - uses keyword patterns to pre-filter before expensive AI extraction.
    """

    # Patterns that suggest actionable content
    PATTERNS = {
        # Direct requests
        'request_phrases': [
            r'\b(please|kindly|could you|can you|would you|will you)\b',
            r'\b(need you to|asking you to|want you to|require you to)\b',
            r'\b(let me know|get back to me|respond|reply)\b',
        ],
        # Deadline indicators
        'deadline_phrases': [
            r'\b(by|before|deadline|due|due date)\b',
            r'\b(asap|urgent|urgently|immediately|right away)\b',
            r'\b(eod|eow|end of day|end of week|end of month)\b',
            r'\b(by (monday|tuesday|wednesday|thursday|friday|tomorrow|today))\b',
            r'\b(this week|next week|by \d{1,2}[\/\-]\d{1,2})\b',
        ],
        # Action verbs (imperative or request form)
        'action_verbs': [
            r'\b(send|submit|review|approve|confirm|update|provide|complete)\b',
            r'\b(schedule|call|meet|discuss|prepare|finalize|sign)\b',
            r'\b(forward|share|attach|upload|download|check)\b',
            r'\b(follow up|follow-up|followup|reach out)\b',
        ],
        # Questions that need response
        'questions': [
            r'\?',  # Any question mark
            r'\b(what|when|where|who|how|which|why)\b.*\?',
        ],
        # Meeting/call requests
        'meeting_requests': [
            r'\b(meeting|call|zoom|teams|google meet|webex)\b',
            r'\b(availability|available|schedule a|set up a)\b',
            r'\b(calendar invite|book a time|find a time)\b',
        ],
    }

    # Compile patterns for efficiency
    _compiled_patterns = None

    @classmethod
    def _get_compiled_patterns(cls) -> Dict[str, List[re.Pattern]]:
        """Compile patterns once and cache them"""
        if cls._compiled_patterns is None:
            cls._compiled_patterns = {}
            for category, patterns in cls.PATTERNS.items():
                cls._compiled_patterns[category] = [
                    re.compile(p, re.IGNORECASE) for p in patterns
                ]
        return cls._compiled_patterns

    @classmethod
    def has_actionable_content(cls, email: Email, min_score: int = 2) -> tuple[bool, int, List[str]]:
        """
        Check if email likely contains actionable content.

        Args:
            email: Email object to check
            min_score: Minimum score to consider actionable (default: 2)

        Returns:
            Tuple of (is_actionable, score, matched_categories)
        """
        content = (email.body_text or email.body_html or email.snippet or "").lower()
        subject = (email.subject or "").lower()
        full_text = f"{subject} {content}"

        if not full_text.strip():
            return False, 0, []

        patterns = cls._get_compiled_patterns()
        score = 0
        matched_categories = []

        for category, compiled_list in patterns.items():
            for pattern in compiled_list:
                if pattern.search(full_text):
                    score += 1
                    if category not in matched_categories:
                        matched_categories.append(category)
                    break  # Only count each category once

        # Bonus: subject line matches are stronger signals
        for category, compiled_list in patterns.items():
            for pattern in compiled_list:
                if pattern.search(subject):
                    score += 1  # Extra point for subject match
                    break

        is_actionable = score >= min_score

        logger.debug(
            f"Email {email.id[:8]}... actionable check: score={score}, "
            f"min={min_score}, result={is_actionable}, categories={matched_categories}"
        )

        return is_actionable, score, matched_categories

    @classmethod
    def get_actionable_emails(cls, emails: List[Email], min_score: int = 2) -> List[Email]:
        """Filter a list of emails to only those with actionable content"""
        actionable = []
        for email in emails:
            is_actionable, score, _ = cls.has_actionable_content(email, min_score)
            if is_actionable:
                actionable.append(email)
        return actionable


class ActionItemExtractor:
    """AI-powered action item extraction from emails"""

    def __init__(self):
        self.saig = SAIGAssistant()
        self.confidence_threshold = int(os.getenv('ACTION_CONFIDENCE_THRESHOLD', '70'))

    async def extract_from_email(
        self,
        email: Email,
        user: User
    ) -> List[Dict[str, Any]]:
        """
        Extract action items from a single email using AI

        Returns list of action item dictionaries ready for database insertion
        """
        # Get email content - prefer plain text, fallback to HTML/snippet
        email_content = email.body_text or email.body_html or email.snippet or ""

        if not email_content.strip():
            logger.info(f"Email {email.id} has no content to analyze")
            return []

        # Truncate to avoid token limits
        email_content = email_content[:4000]

        prompt = f"""Analyze this email and extract specific action items that require follow-up.

Email Details:
From: {email.sender_name or email.sender or 'Unknown'}
Subject: {email.subject or '(No subject)'}
Date: {email.received_at.strftime('%Y-%m-%d %H:%M') if email.received_at else 'Unknown'}

Body:
{email_content}

INSTRUCTIONS:
1. Identify concrete tasks, requests, or commitments that require action from the recipient
2. Each action item should be something specific that needs to be DONE
3. Include deadlines, people involved, and deliverables when mentioned
4. Only extract clear, actionable items - not general information or FYI content
5. Skip greetings, signatures, and pleasantries

Return a JSON array of action items. Each item should have:
{{
    "title": "Brief, actionable title starting with a verb (e.g., 'Send Q4 report to Sarah', 'Schedule meeting with client')",
    "description": "Detailed description with context and specifics from the email",
    "due_date": "ISO date string (YYYY-MM-DD) or relative like 'tomorrow', 'end of week', or null if no deadline",
    "priority": "high|medium|low based on urgency keywords and importance",
    "confidence": 0-100 (how confident you are this is a real action item),
    "source_quote": "The exact sentence or phrase from the email that indicates this task"
}}

Confidence scoring guide:
- 90-100: Explicit request with clear deadline ("Please submit by Friday")
- 80-89: Direct request without specific deadline ("Could you review this document?")
- 70-79: Implied action needed ("Let me know your thoughts on...")
- 60-69: Suggested task ("It would be helpful if...")
- Below 60: Vague or uncertain - skip these

If no actionable items are found, return an empty array: []

Return ONLY valid JSON, no explanation text."""

        try:
            response = await self.saig._call_anthropic(
                prompt, max_tokens=1000, temperature=0.2
            )

            # Parse JSON response
            action_items = self._parse_action_items(response)

            # Filter by confidence threshold
            filtered_items = [
                item for item in action_items
                if item.get('confidence', 0) >= self.confidence_threshold
            ]

            logger.info(
                f"Extracted {len(action_items)} action items from email {email.id}, "
                f"{len(filtered_items)} above confidence threshold ({self.confidence_threshold})"
            )

            return filtered_items

        except Exception as e:
            logger.error(f"Action extraction error for email {email.id}: {e}")
            return []

    def _parse_action_items(self, response: str) -> List[Dict]:
        """Parse AI response into action items list"""
        try:
            # Try to find JSON array in response
            # Handle case where AI adds explanation text
            array_match = re.search(r'\[[\s\S]*\]', response)
            if array_match:
                json_str = array_match.group()
                items = json.loads(json_str)
                return items if isinstance(items, list) else []

            # Try parsing entire response as JSON
            items = json.loads(response)
            return items if isinstance(items, list) else []

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in action extraction: {e}")
            logger.debug(f"Response was: {response[:500]}")
            return []

    async def create_action_items(
        self,
        db: Session,
        email: Email,
        user: User
    ) -> List[ActionItem]:
        """
        Extract and create action items in database

        Returns list of created ActionItem objects
        """
        # Check if action items already exist for this email (avoid duplicates)
        existing_count = db.query(ActionItem).filter(
            ActionItem.email_id == email.id,
            ActionItem.user_id == user.id,
            ActionItem.auto_created == True
        ).count()

        if existing_count > 0:
            logger.info(
                f"Action items already exist for email {email.id}, skipping extraction"
            )
            return []

        # Extract action items using AI
        extracted_items = await self.extract_from_email(email, user)

        if not extracted_items:
            logger.info(f"No action items extracted from email {email.id}")
            return []

        created_items = []
        for item_data in extracted_items:
            try:
                # Parse due date
                due_date = self._parse_due_date(item_data.get('due_date'))

                # Map priority string to integer
                priority_map = {'high': 1, 'medium': 2, 'low': 3}
                priority = priority_map.get(
                    str(item_data.get('priority', 'medium')).lower(), 2
                )

                # Create action item
                action_item = ActionItem(
                    user_id=user.id,
                    email_id=email.id,
                    title=str(item_data.get('title', 'Untitled Task'))[:200],
                    description=str(item_data.get('description', '')),
                    due_date=due_date,
                    priority=priority,
                    status='pending',
                    auto_created=True,
                    confidence_score=int(item_data.get('confidence', 70)),
                    source_quote=str(item_data.get('source_quote', ''))[:500]
                )

                db.add(action_item)
                created_items.append(action_item)

            except Exception as e:
                logger.error(f"Error creating action item: {e}")
                continue

        if created_items:
            db.commit()

            # Refresh to get generated IDs
            for item in created_items:
                db.refresh(item)

            logger.info(
                f"Created {len(created_items)} action items for email {email.id}"
            )

        return created_items

    def _parse_due_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse various date formats into datetime"""
        if not date_str:
            return None

        date_str_lower = str(date_str).lower().strip()
        now = datetime.utcnow()

        # Handle null/none strings
        if date_str_lower in ('null', 'none', 'n/a', ''):
            return None

        # Handle relative dates
        if 'today' in date_str_lower:
            return now.replace(hour=17, minute=0, second=0, microsecond=0)

        if 'tomorrow' in date_str_lower:
            return (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)

        if 'next week' in date_str_lower:
            return now + timedelta(weeks=1)

        if 'end of week' in date_str_lower or 'eow' in date_str_lower:
            # Find next Friday
            days_until_friday = (4 - now.weekday()) % 7
            if days_until_friday == 0 and now.hour >= 17:
                days_until_friday = 7
            return (now + timedelta(days=days_until_friday)).replace(hour=17, minute=0, second=0, microsecond=0)

        if 'friday' in date_str_lower:
            days_until_friday = (4 - now.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            return (now + timedelta(days=days_until_friday)).replace(hour=17, minute=0, second=0, microsecond=0)

        if 'monday' in date_str_lower:
            days_until_monday = (0 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            return (now + timedelta(days=days_until_monday)).replace(hour=9, minute=0, second=0, microsecond=0)

        if 'end of month' in date_str_lower or 'eom' in date_str_lower:
            if now.month == 12:
                return datetime(now.year + 1, 1, 1) - timedelta(days=1)
            return datetime(now.year, now.month + 1, 1) - timedelta(days=1)

        if 'asap' in date_str_lower or 'urgent' in date_str_lower:
            return now + timedelta(days=1)  # Tomorrow for urgent

        # Try ISO format (YYYY-MM-DD)
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00').split('T')[0])
        except (ValueError, AttributeError):
            pass

        # Try common date formats
        formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%B %d, %Y',
            '%B %d',
            '%b %d, %Y',
            '%b %d',
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If no year in format, use current year
                if parsed.year == 1900:
                    parsed = parsed.replace(year=now.year)
                return parsed
            except ValueError:
                continue

        logger.debug(f"Could not parse date: {date_str}")
        return None


# Global instance
action_extractor = ActionItemExtractor()
