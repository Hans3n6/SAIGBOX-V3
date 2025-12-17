"""
Email Sequences - Strategic follow-up sequence management
Tracks prospect conversations and suggests next emails in sequence
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SequenceStage(str, Enum):
    """Email sequence stages following profit-maximizing pattern"""
    VALUE_EMAIL = "value_email"           # 1. Education or insight
    PROBLEM_AGITATION = "problem_agitation"  # 2. Highlight pain points
    SOLUTION_EMAIL = "solution_email"       # 3. Present your solution
    SOCIAL_PROOF = "social_proof"           # 4. Case studies, testimonials
    DIRECT_OFFER = "direct_offer"           # 5. Clear CTA
    FINAL_REMINDER = "final_reminder"       # 6. Last chance, scarcity

    @classmethod
    def next_stage(cls, current: 'SequenceStage') -> Optional['SequenceStage']:
        """Get the next stage in the sequence"""
        stages = list(cls)
        try:
            idx = stages.index(current)
            if idx < len(stages) - 1:
                return stages[idx + 1]
        except ValueError:
            pass
        return None

    @classmethod
    def stage_number(cls, stage: 'SequenceStage') -> int:
        """Get the 1-based stage number"""
        stages = list(cls)
        try:
            return stages.index(stage) + 1
        except ValueError:
            return 0


@dataclass
class SequenceEmail:
    """Email in a sequence with timing and content guidance"""
    stage: SequenceStage
    days_after_previous: int
    subject_template: str
    body_guidance: str
    cta_type: str
    purpose: str


@dataclass
class ProspectSequence:
    """Tracking a prospect through a sequence"""
    prospect_email: str
    prospect_name: Optional[str]
    company: Optional[str]
    current_stage: SequenceStage
    stage_number: int
    emails_sent: int
    emails_opened: int
    emails_replied: int
    last_email_date: Optional[datetime]
    days_since_last: int
    next_action: str
    next_email_due: Optional[datetime]
    is_stalled: bool
    risk_level: str


@dataclass
class SequencePerformance:
    """Performance metrics for a sequence"""
    total_prospects: int
    active_prospects: int
    completed_sequences: int
    avg_open_rate: float
    avg_reply_rate: float
    avg_meeting_rate: float
    stage_conversion: Dict[str, float]


class EmailSequenceManager:
    """
    Manages email sequences for sales outreach.
    Tracks prospects through sequence stages and suggests next actions.
    """

    # Standard sequence timing (days after previous email)
    SEQUENCE_TIMING = {
        SequenceStage.VALUE_EMAIL: 0,          # Initial email
        SequenceStage.PROBLEM_AGITATION: 3,    # 3 days later
        SequenceStage.SOLUTION_EMAIL: 4,       # 4 days after that
        SequenceStage.SOCIAL_PROOF: 5,         # 5 days after that
        SequenceStage.DIRECT_OFFER: 4,         # 4 days after that
        SequenceStage.FINAL_REMINDER: 7,       # 7 days after that (final push)
    }

    # Stage-specific guidance
    SEQUENCE_TEMPLATES = {
        SequenceStage.VALUE_EMAIL: SequenceEmail(
            stage=SequenceStage.VALUE_EMAIL,
            days_after_previous=0,
            subject_template="Quick insight about {topic}",
            body_guidance="""
PURPOSE: Provide genuine value without asking for anything.

STRUCTURE:
1. Personal opener (reference something specific about them)
2. Share an insight, trend, or useful information
3. Optional: Brief mention of how you help with this
4. Soft CTA: "Thought this might be useful" or "Happy to share more"

DO:
- Lead with value, not your pitch
- Be brief (under 100 words)
- Reference something specific about their company

DON'T:
- Ask for a meeting
- Talk about your product features
- Use generic templates
""",
            cta_type="soft",
            purpose="Establish credibility and provide value"
        ),

        SequenceStage.PROBLEM_AGITATION: SequenceEmail(
            stage=SequenceStage.PROBLEM_AGITATION,
            days_after_previous=3,
            subject_template="The hidden cost of {problem}",
            body_guidance="""
PURPOSE: Help them feel the pain of their current situation.

STRUCTURE:
1. Acknowledge a common challenge in their industry/role
2. Quantify the impact (time, money, opportunity cost)
3. Share what happens if left unaddressed
4. Soft CTA: "Does this resonate?"

DO:
- Use specific numbers and data
- Reference real consequences
- Show you understand their world

DON'T:
- Be fear-mongering or negative
- Make it about you yet
- Exaggerate or make up statistics
""",
            cta_type="soft",
            purpose="Create awareness of the problem's impact"
        ),

        SequenceStage.SOLUTION_EMAIL: SequenceEmail(
            stage=SequenceStage.SOLUTION_EMAIL,
            days_after_previous=4,
            subject_template="How {similar_company} solved this",
            body_guidance="""
PURPOSE: Show how the problem can be solved.

STRUCTURE:
1. Transition from the problem to solution
2. Briefly explain your approach (not features)
3. Mention results you've achieved
4. Medium CTA: "Would a quick call help?"

DO:
- Focus on outcomes, not features
- Keep it high-level
- Include a specific result/metric

DON'T:
- Overwhelm with details
- Use jargon
- Make the email too long
""",
            cta_type="medium",
            purpose="Position your solution as the answer"
        ),

        SequenceStage.SOCIAL_PROOF: SequenceEmail(
            stage=SequenceStage.SOCIAL_PROOF,
            days_after_previous=5,
            subject_template="{customer} saw {result} - here's how",
            body_guidance="""
PURPOSE: Build trust through third-party validation.

STRUCTURE:
1. Share a specific customer success story
2. Include before/after metrics
3. Show it's someone similar to them
4. Medium CTA: "Want to see if we can do the same for you?"

DO:
- Use specific, verifiable results
- Choose a customer similar to the prospect
- Include a quote if possible

DON'T:
- Use vague claims ("great results")
- Reference companies they can't relate to
- Make it feel like a testimonial page
""",
            cta_type="medium",
            purpose="Build trust through proven results"
        ),

        SequenceStage.DIRECT_OFFER: SequenceEmail(
            stage=SequenceStage.DIRECT_OFFER,
            days_after_previous=4,
            subject_template="Quick question",
            body_guidance="""
PURPOSE: Make a clear, direct ask.

STRUCTURE:
1. Brief recap of value/relevance
2. Clear, specific offer
3. Remove friction (free trial, no commitment, etc.)
4. Strong CTA: Calendar link or specific next step

DO:
- Be direct and clear
- Make the next step easy
- Create some urgency if authentic

DON'T:
- Be pushy or aggressive
- Add new information
- Make the CTA confusing
""",
            cta_type="strong",
            purpose="Drive a specific action"
        ),

        SequenceStage.FINAL_REMINDER: SequenceEmail(
            stage=SequenceStage.FINAL_REMINDER,
            days_after_previous=7,
            subject_template="Closing the loop",
            body_guidance="""
PURPOSE: Give one final chance and gracefully close.

STRUCTURE:
1. Acknowledge you've reached out several times
2. Quick value reminder (one sentence)
3. Either/or close: proceed or close the file
4. Make it easy to say "not now" or "not interested"

DO:
- Be respectful and brief
- Give them an out
- Leave the door open for future

DON'T:
- Be guilt-tripping
- Be desperate
- Burn the bridge
""",
            cta_type="soft",
            purpose="Final attempt with graceful exit"
        ),
    }

    # Non-opener resend subject variations
    RESEND_SUBJECTS = [
        "Re: {original_subject}",
        "Bumping this up",
        "Following up on my note",
        "Did this get buried?",
        "{first_name}, quick follow-up",
    ]

    def __init__(self):
        pass

    def get_sequence_template(self, stage: SequenceStage) -> SequenceEmail:
        """Get the template for a specific sequence stage"""
        return self.SEQUENCE_TEMPLATES.get(stage)

    def get_all_templates(self) -> List[SequenceEmail]:
        """Get all sequence templates in order"""
        return [self.SEQUENCE_TEMPLATES[stage] for stage in SequenceStage]

    def analyze_prospect_sequence(
        self,
        emails: List[Dict[str, Any]],
        prospect_email: str
    ) -> ProspectSequence:
        """
        Analyze where a prospect is in the sequence based on email history.
        """
        if not emails:
            return ProspectSequence(
                prospect_email=prospect_email,
                prospect_name=None,
                company=None,
                current_stage=SequenceStage.VALUE_EMAIL,
                stage_number=1,
                emails_sent=0,
                emails_opened=0,
                emails_replied=0,
                last_email_date=None,
                days_since_last=0,
                next_action="Send initial value email",
                next_email_due=datetime.utcnow(),
                is_stalled=False,
                risk_level="low"
            )

        # Analyze email history
        sent_emails = [e for e in emails if e.get('is_sent')]
        received_emails = [e for e in emails if not e.get('is_sent')]

        emails_sent = len(sent_emails)
        emails_replied = len(received_emails)
        emails_opened = sum(1 for e in sent_emails if e.get('is_opened', False))

        # Get most recent email
        all_sorted = sorted(emails, key=lambda e: e.get('received_at', ''), reverse=True)
        last_email = all_sorted[0] if all_sorted else None
        last_email_date = None
        days_since_last = 0

        if last_email:
            received_at = last_email.get('received_at')
            if received_at:
                if isinstance(received_at, str):
                    try:
                        last_email_date = datetime.fromisoformat(received_at.replace('Z', '+00:00'))
                    except:
                        last_email_date = datetime.utcnow()
                else:
                    last_email_date = received_at

                days_since_last = (datetime.utcnow() - last_email_date.replace(tzinfo=None)).days

        # Determine current stage based on sent emails
        current_stage = self._determine_stage(emails_sent, emails_replied)
        stage_number = SequenceStage.stage_number(current_stage)

        # Check if stalled
        is_stalled = days_since_last > 14 and emails_replied == 0

        # Determine next action
        next_action, next_email_due = self._get_next_action(
            current_stage, days_since_last, emails_replied
        )

        # Assess risk level
        risk_level = self._assess_risk(
            days_since_last, emails_sent, emails_replied, current_stage
        )

        # Extract prospect info from emails
        prospect_name = None
        company = None
        for email in emails:
            if email.get('sender') == prospect_email:
                prospect_name = email.get('sender_name')
                # Try to extract company from email domain
                if '@' in prospect_email:
                    domain = prospect_email.split('@')[1]
                    if domain not in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']:
                        company = domain.split('.')[0].title()
                break

        return ProspectSequence(
            prospect_email=prospect_email,
            prospect_name=prospect_name,
            company=company,
            current_stage=current_stage,
            stage_number=stage_number,
            emails_sent=emails_sent,
            emails_opened=emails_opened,
            emails_replied=emails_replied,
            last_email_date=last_email_date,
            days_since_last=days_since_last,
            next_action=next_action,
            next_email_due=next_email_due,
            is_stalled=is_stalled,
            risk_level=risk_level
        )

    def _determine_stage(self, emails_sent: int, emails_replied: int) -> SequenceStage:
        """Determine sequence stage based on email count"""
        stages = list(SequenceStage)

        # If they've replied, we're likely past the cold sequence
        if emails_replied > 0:
            if emails_sent >= 5:
                return SequenceStage.DIRECT_OFFER
            elif emails_sent >= 3:
                return SequenceStage.SOLUTION_EMAIL
            else:
                return SequenceStage.PROBLEM_AGITATION

        # No reply - progress through stages
        if emails_sent == 0:
            return SequenceStage.VALUE_EMAIL
        elif emails_sent == 1:
            return SequenceStage.PROBLEM_AGITATION
        elif emails_sent == 2:
            return SequenceStage.SOLUTION_EMAIL
        elif emails_sent == 3:
            return SequenceStage.SOCIAL_PROOF
        elif emails_sent == 4:
            return SequenceStage.DIRECT_OFFER
        else:
            return SequenceStage.FINAL_REMINDER

    def _get_next_action(
        self,
        current_stage: SequenceStage,
        days_since_last: int,
        emails_replied: int
    ) -> tuple:
        """Get the recommended next action and due date"""
        next_stage = SequenceStage.next_stage(current_stage)

        if emails_replied > 0:
            return "Reply to their response - personalize based on their message", datetime.utcnow()

        if current_stage == SequenceStage.FINAL_REMINDER:
            if days_since_last > 30:
                return "Consider re-engaging in 30+ days with new angle", None
            return "Sequence complete - wait for response or close", None

        # Check if it's time for next email
        timing = self.SEQUENCE_TIMING.get(next_stage, 4) if next_stage else 7
        if days_since_last >= timing:
            template = self.SEQUENCE_TEMPLATES.get(next_stage)
            if template:
                return f"Send {next_stage.value.replace('_', ' ')} - {template.purpose}", datetime.utcnow()

        # Not time yet
        days_to_wait = timing - days_since_last
        next_due = datetime.utcnow() + timedelta(days=days_to_wait)
        return f"Wait {days_to_wait} more day(s), then send {next_stage.value.replace('_', ' ') if next_stage else 'follow-up'}", next_due

    def _assess_risk(
        self,
        days_since_last: int,
        emails_sent: int,
        emails_replied: int,
        current_stage: SequenceStage
    ) -> str:
        """Assess risk level for this sequence"""
        if emails_replied > 0:
            return "low"  # Engaged prospect

        if days_since_last > 21:
            return "high"

        if days_since_last > 14:
            return "medium"

        if current_stage == SequenceStage.FINAL_REMINDER:
            return "medium"

        return "low"

    def suggest_resend_for_non_opener(
        self,
        original_email: Dict[str, Any],
        prospect: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Suggest a resend for non-openers (10-25% revenue boost).
        Change subject line, resend 48-72 hours later.
        """
        original_subject = original_email.get('subject', '')
        first_name = prospect.get('first_name', '')

        # Generate new subject options
        new_subjects = []
        for template in self.RESEND_SUBJECTS:
            subject = template.format(
                original_subject=original_subject,
                first_name=first_name
            )
            new_subjects.append(subject)

        return {
            "original_subject": original_subject,
            "suggested_subjects": new_subjects[:3],
            "timing": "48-72 hours after original",
            "body": "Keep the same body - only change subject line",
            "expected_boost": "10-25% additional opens"
        }

    def get_sequence_performance(
        self,
        prospect_sequences: List[ProspectSequence]
    ) -> SequencePerformance:
        """Calculate overall sequence performance metrics"""
        if not prospect_sequences:
            return SequencePerformance(
                total_prospects=0,
                active_prospects=0,
                completed_sequences=0,
                avg_open_rate=0.0,
                avg_reply_rate=0.0,
                avg_meeting_rate=0.0,
                stage_conversion={}
            )

        total = len(prospect_sequences)
        active = sum(1 for p in prospect_sequences if not p.is_stalled and p.current_stage != SequenceStage.FINAL_REMINDER)
        completed = sum(1 for p in prospect_sequences if p.current_stage == SequenceStage.FINAL_REMINDER)

        total_sent = sum(p.emails_sent for p in prospect_sequences)
        total_opened = sum(p.emails_opened for p in prospect_sequences)
        total_replied = sum(p.emails_replied for p in prospect_sequences)

        avg_open = (total_opened / total_sent) if total_sent > 0 else 0.0
        avg_reply = (total_replied / total_sent) if total_sent > 0 else 0.0

        # Stage conversion (how many made it to each stage)
        stage_counts = {}
        for stage in SequenceStage:
            count = sum(1 for p in prospect_sequences if SequenceStage.stage_number(p.current_stage) >= SequenceStage.stage_number(stage))
            stage_counts[stage.value] = count / total if total > 0 else 0.0

        return SequencePerformance(
            total_prospects=total,
            active_prospects=active,
            completed_sequences=completed,
            avg_open_rate=round(avg_open, 3),
            avg_reply_rate=round(avg_reply, 3),
            avg_meeting_rate=0.0,  # Would need meeting tracking
            stage_conversion=stage_counts
        )

    def get_stage_guidance(self, stage: SequenceStage) -> Dict[str, Any]:
        """Get detailed guidance for a specific stage"""
        template = self.SEQUENCE_TEMPLATES.get(stage)
        if not template:
            return {}

        return {
            "stage": stage.value,
            "stage_number": SequenceStage.stage_number(stage),
            "purpose": template.purpose,
            "subject_template": template.subject_template,
            "body_guidance": template.body_guidance.strip(),
            "cta_type": template.cta_type,
            "days_after_previous": template.days_after_previous,
            "next_stage": SequenceStage.next_stage(stage).value if SequenceStage.next_stage(stage) else None
        }


# Global instance
sequence_manager = EmailSequenceManager()
