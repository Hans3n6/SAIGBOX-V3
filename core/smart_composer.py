"""
Smart Email Composer - AI-powered sales email generation
Generates optimized subject lines, CTAs, and personalized content
"""
import re
import json
import logging
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class SubjectLineCategory(str, Enum):
    CURIOSITY = "curiosity"
    VALUE = "value"
    SOCIAL_PROOF = "social_proof"
    PERSONALIZED = "personalized"
    URGENCY = "urgency"


class CTAStrength(str, Enum):
    SOFT = "soft"  # Low commitment
    MEDIUM = "medium"
    STRONG = "strong"  # High commitment


class PersonalizationLevel(str, Enum):
    BASIC = "basic"  # Name, company
    MEDIUM = "medium"  # Industry, role
    ADVANCED = "advanced"  # Recent activity, mutual connections


@dataclass
class SubjectLineSuggestion:
    """Subject line with metadata"""
    text: str
    category: SubjectLineCategory
    estimated_open_rate: str  # "low", "medium", "high"
    word_count: int
    personalized: bool


@dataclass
class CTASuggestion:
    """Call-to-action suggestion"""
    text: str
    strength: CTAStrength
    action_type: str  # "meeting", "demo", "reply", "download", etc.
    estimated_click_rate: str


@dataclass
class EmailDraft:
    """Complete email draft"""
    subject: str
    body: str
    cta_text: str
    personalization_level: PersonalizationLevel
    sequence_stage: Optional[str] = None
    estimated_metrics: Optional[Dict] = None


class SmartComposer:
    """
    AI-powered email composition with sales optimization.
    Generates subject lines, CTAs, and personalized content.
    """

    # Subject line templates by category
    SUBJECT_TEMPLATES = {
        SubjectLineCategory.CURIOSITY: [
            "Quick question about {topic}",
            "Quick question for you",
            "Thought about {company}",
            "Have you considered this?",
            "Is this still a priority?",
            "Something I noticed about {company}",
        ],
        SubjectLineCategory.VALUE: [
            "This might help with {pain_point}",
            "Idea for {company}'s {goal}",
            "{benefit} for {company}",
            "How {similar_company} solved {problem}",
            "Save {time_or_money} on {task}",
        ],
        SubjectLineCategory.SOCIAL_PROOF: [
            "How {similar_company} achieved {result}",
            "{industry} companies are seeing {result}",
            "What {role}s are doing differently",
            "Trend: {industry} teams are {action}",
        ],
        SubjectLineCategory.PERSONALIZED: [
            "{first_name}, saw your post about {topic}",
            "Following up on {event_or_topic}",
            "Re: our conversation about {topic}",
            "{first_name} - {mutual_connection} mentioned you",
        ],
        SubjectLineCategory.URGENCY: [
            "Before {deadline}",
            "Last chance: {offer}",
            "Ending {timeframe}",
            "Time-sensitive: {topic}",
        ],
    }

    # CTA templates by stage
    CTA_TEMPLATES = {
        "cold_outreach": [
            ("Worth a quick chat?", CTAStrength.SOFT, "reply"),
            ("Open to learning more?", CTAStrength.SOFT, "reply"),
            ("Quick question - does this resonate?", CTAStrength.SOFT, "reply"),
        ],
        "engaged": [
            ("Can we schedule 15 minutes this week?", CTAStrength.MEDIUM, "meeting"),
            ("Would a brief call help?", CTAStrength.MEDIUM, "meeting"),
            ("Want me to walk you through it?", CTAStrength.MEDIUM, "demo"),
        ],
        "discovery": [
            ("Let's schedule a proper demo", CTAStrength.MEDIUM, "demo"),
            ("Would a case study be helpful?", CTAStrength.SOFT, "content"),
            ("Can I loop in our specialist?", CTAStrength.MEDIUM, "meeting"),
        ],
        "evaluation": [
            ("Ready for a personalized proposal?", CTAStrength.STRONG, "proposal"),
            ("Want to see pricing options?", CTAStrength.STRONG, "proposal"),
            ("Shall I set up a trial?", CTAStrength.MEDIUM, "trial"),
        ],
        "proposal": [
            ("Any questions on the proposal?", CTAStrength.MEDIUM, "reply"),
            ("Ready to move forward?", CTAStrength.STRONG, "close"),
            ("Let's hop on a call to discuss", CTAStrength.MEDIUM, "meeting"),
        ],
        "negotiation": [
            ("I can do {offer} - deal?", CTAStrength.STRONG, "close"),
            ("Let's finalize this", CTAStrength.STRONG, "close"),
            ("What would make this a yes?", CTAStrength.MEDIUM, "reply"),
        ],
        "closing": [
            ("Ready to get started?", CTAStrength.STRONG, "close"),
            ("Let's kick this off", CTAStrength.STRONG, "close"),
            ("Sign here to begin", CTAStrength.STRONG, "close"),
        ],
    }

    # Personalization templates
    PERSONALIZATION_OPENERS = {
        PersonalizationLevel.BASIC: [
            "Hi {first_name},",
            "Hello {first_name},",
        ],
        PersonalizationLevel.MEDIUM: [
            "Hi {first_name}, I noticed {company} is in the {industry} space.",
            "Hi {first_name}, as a {role} at {company}, you might appreciate this.",
            "{first_name}, given your focus on {focus_area}, I thought of you.",
        ],
        PersonalizationLevel.ADVANCED: [
            "Hi {first_name}, I saw your recent post about {topic} - really insightful.",
            "{first_name}, {mutual_connection} suggested I reach out regarding {topic}.",
            "Hi {first_name}, congrats on {recent_news}! Quick thought for you.",
            "{first_name}, noticed {company} just {recent_action}. Perfect timing to discuss...",
        ],
    }

    # Email body templates by sequence stage
    SEQUENCE_BODY_TEMPLATES = {
        "value_email": """
{opener}

I wanted to share something that might be valuable for {company}.

{value_insight}

{social_proof_snippet}

{cta}

{closing}
""",
        "problem_agitation": """
{opener}

Many {role}s I talk to mention {pain_point} as a major challenge.

The cost of not addressing this can be significant:
{pain_consequences}

If this resonates, {cta}

{closing}
""",
        "solution_email": """
{opener}

Based on what you shared about {their_challenge}, I think we can help.

Here's how:
{solution_points}

{case_study_snippet}

{cta}

{closing}
""",
        "social_proof": """
{opener}

Wanted to share a quick win from a company similar to {company}.

{case_study}

The results:
{results}

Would love to explore if we can do the same for you. {cta}

{closing}
""",
        "direct_offer": """
{opener}

I'll get straight to the point.

{offer}

{terms}

{scarcity_element}

{cta}

{closing}
""",
        "final_reminder": """
{opener}

I've reached out a few times, so I'll keep this brief.

{value_reminder}

If the timing isn't right, just let me know and I'll close out your file.

Either way, {cta}

{closing}
""",
    }

    # Spam trigger words to avoid
    SPAM_TRIGGERS = [
        "free", "urgent", "act now", "limited time", "click here",
        "buy now", "order now", "special offer", "congratulations",
        "winner", "you've been selected", "100% free", "no obligation",
    ]

    def __init__(self, ai_client=None):
        """Initialize with optional AI client for advanced generation"""
        self.ai_client = ai_client

    def generate_subject_lines(
        self,
        context: Dict[str, Any],
        count: int = 5
    ) -> List[SubjectLineSuggestion]:
        """
        Generate multiple subject line suggestions.

        Context should include:
        - first_name, company, role, industry
        - topic, pain_point, goal
        - previous_interaction (optional)
        - similar_company, result (for social proof)
        """
        suggestions = []

        # Determine which categories to use based on context
        categories = self._select_categories(context)

        for category in categories[:count]:
            templates = self.SUBJECT_TEMPLATES.get(category, [])
            if not templates:
                continue

            # Get best template for this category
            template = self._select_best_template(templates, context)

            # Fill in template
            subject = self._fill_template(template, context)

            # Validate
            if self._validate_subject_line(subject):
                suggestions.append(SubjectLineSuggestion(
                    text=subject,
                    category=category,
                    estimated_open_rate=self._estimate_open_rate(subject, category),
                    word_count=len(subject.split()),
                    personalized=self._is_personalized(subject, context)
                ))

        # If we need more suggestions, generate variations (with max attempts to prevent infinite loop)
        max_attempts = count * 3
        attempts = 0
        while len(suggestions) < count and attempts < max_attempts:
            attempts += 1
            # Add variations of existing suggestions
            if suggestions:
                base = suggestions[attempts % len(suggestions)]  # Cycle through bases
                variation = self._create_variation(base.text, context)
                if variation and variation not in [s.text for s in suggestions]:
                    suggestions.append(SubjectLineSuggestion(
                        text=variation,
                        category=base.category,
                        estimated_open_rate="medium",
                        word_count=len(variation.split()),
                        personalized=self._is_personalized(variation, context)
                    ))
            else:
                # Fallback to generic
                suggestions.append(SubjectLineSuggestion(
                    text="Quick question",
                    category=SubjectLineCategory.CURIOSITY,
                    estimated_open_rate="medium",
                    word_count=2,
                    personalized=False
                ))

        return suggestions[:count]

    def _select_categories(self, context: Dict) -> List[SubjectLineCategory]:
        """Select best categories based on context"""
        categories = []

        # Always include curiosity - highest performing
        categories.append(SubjectLineCategory.CURIOSITY)

        # Value if we have pain points
        if context.get("pain_point") or context.get("goal"):
            categories.append(SubjectLineCategory.VALUE)

        # Social proof if we have success stories
        if context.get("similar_company") or context.get("result"):
            categories.append(SubjectLineCategory.SOCIAL_PROOF)

        # Personalized if we have specific info
        if context.get("topic") or context.get("mutual_connection"):
            categories.append(SubjectLineCategory.PERSONALIZED)

        # Urgency sparingly
        if context.get("deadline") or context.get("scarcity"):
            categories.append(SubjectLineCategory.URGENCY)

        return categories

    def _select_best_template(self, templates: List[str], context: Dict) -> str:
        """Select best template based on available context"""
        for template in templates:
            # Check if we have all required placeholders
            placeholders = re.findall(r'\{(\w+)\}', template)
            if all(context.get(p) for p in placeholders):
                return template

        # Return first template that requires minimal placeholders
        return min(templates, key=lambda t: len(re.findall(r'\{(\w+)\}', t)))

    def _fill_template(self, template: str, context: Dict) -> str:
        """Fill in template with context values"""
        result = template

        for key, value in context.items():
            if value:
                result = result.replace(f"{{{key}}}", str(value))

        # Remove any unfilled placeholders
        result = re.sub(r'\{[^}]+\}', '', result).strip()

        # Clean up extra spaces
        result = re.sub(r'\s+', ' ', result)

        return result

    def _validate_subject_line(self, subject: str) -> bool:
        """Validate subject line against best practices"""
        if not subject:
            return False

        # Check length (max 7 words, 50 chars)
        if len(subject.split()) > 10 or len(subject) > 60:
            return False

        # Check for spam triggers
        subject_lower = subject.lower()
        if any(trigger in subject_lower for trigger in self.SPAM_TRIGGERS):
            return False

        # No all caps
        if subject.isupper():
            return False

        # No excessive punctuation
        if subject.count("!") > 1 or subject.count("?") > 1:
            return False

        return True

    def _estimate_open_rate(self, subject: str, category: SubjectLineCategory) -> str:
        """Estimate open rate based on subject characteristics"""
        score = 50  # Base score

        # Category bonuses
        category_bonuses = {
            SubjectLineCategory.CURIOSITY: 15,
            SubjectLineCategory.PERSONALIZED: 20,
            SubjectLineCategory.VALUE: 10,
            SubjectLineCategory.SOCIAL_PROOF: 5,
            SubjectLineCategory.URGENCY: -5,  # Can trigger spam filters
        }
        score += category_bonuses.get(category, 0)

        # Length bonus (shorter is better)
        words = len(subject.split())
        if words <= 4:
            score += 15
        elif words <= 6:
            score += 10
        elif words <= 8:
            score += 5

        # Question bonus
        if "?" in subject:
            score += 5

        # Personalization bonus (has a name)
        if any(word[0].isupper() and len(word) > 2 for word in subject.split()):
            score += 10

        if score >= 70:
            return "high"
        elif score >= 50:
            return "medium"
        return "low"

    def _is_personalized(self, subject: str, context: Dict) -> bool:
        """Check if subject line contains personalization"""
        first_name = context.get("first_name", "")
        company = context.get("company", "")

        return (
            (first_name and first_name in subject) or
            (company and company in subject)
        )

    def _create_variation(self, base: str, context: Dict) -> Optional[str]:
        """Create a variation of a subject line"""
        variations = [
            lambda s: f"Re: {s}",
            lambda s: s.replace("Quick question", "Thought"),
            lambda s: f"{context.get('first_name', 'Hi')}, {s.lower()}" if context.get('first_name') else None,
        ]

        for variation in variations:
            result = variation(base)
            if result and self._validate_subject_line(result):
                return result

        return None

    def suggest_cta(
        self,
        stage: str,
        context: Dict[str, Any] = None
    ) -> List[CTASuggestion]:
        """
        Suggest CTAs appropriate for the conversation stage.
        """
        templates = self.CTA_TEMPLATES.get(stage, self.CTA_TEMPLATES["cold_outreach"])
        suggestions = []

        for text, strength, action_type in templates:
            # Fill in any context
            if context:
                text = self._fill_template(text, context)

            suggestions.append(CTASuggestion(
                text=text,
                strength=strength,
                action_type=action_type,
                estimated_click_rate=self._estimate_cta_performance(strength, stage)
            ))

        return suggestions

    def _estimate_cta_performance(self, strength: CTAStrength, stage: str) -> str:
        """Estimate CTA click rate based on strength and stage alignment"""
        # Soft CTAs work better early, strong CTAs work better late
        stage_strength_alignment = {
            "cold_outreach": CTAStrength.SOFT,
            "engaged": CTAStrength.SOFT,
            "discovery": CTAStrength.MEDIUM,
            "evaluation": CTAStrength.MEDIUM,
            "proposal": CTAStrength.STRONG,
            "negotiation": CTAStrength.STRONG,
            "closing": CTAStrength.STRONG,
        }

        ideal = stage_strength_alignment.get(stage, CTAStrength.MEDIUM)

        if strength == ideal:
            return "high"
        elif abs(list(CTAStrength).index(strength) - list(CTAStrength).index(ideal)) == 1:
            return "medium"
        return "low"

    def personalize_email(
        self,
        body_template: str,
        prospect_data: Dict[str, Any],
        level: PersonalizationLevel = PersonalizationLevel.MEDIUM
    ) -> str:
        """
        Add personalization to email body.
        """
        # Select opener based on level
        openers = self.PERSONALIZATION_OPENERS.get(level, [])
        opener = ""

        for template in openers:
            placeholders = re.findall(r'\{(\w+)\}', template)
            if all(prospect_data.get(p) for p in placeholders):
                opener = self._fill_template(template, prospect_data)
                break

        if not opener:
            opener = f"Hi {prospect_data.get('first_name', 'there')},"

        # Replace opener placeholder in body
        body = body_template.replace("{opener}", opener)

        # Fill in other placeholders
        body = self._fill_template(body, prospect_data)

        return body

    def compose_sequence_email(
        self,
        stage: str,
        context: Dict[str, Any],
        personalization_level: PersonalizationLevel = PersonalizationLevel.MEDIUM
    ) -> EmailDraft:
        """
        Compose a complete email for a specific sequence stage.
        """
        # Get body template
        body_template = self.SEQUENCE_BODY_TEMPLATES.get(stage, self.SEQUENCE_BODY_TEMPLATES["value_email"])

        # Generate subject lines
        subject_suggestions = self.generate_subject_lines(context, count=1)
        subject = subject_suggestions[0].text if subject_suggestions else "Quick note"

        # Get CTA
        cta_suggestions = self.suggest_cta(stage, context)
        cta = cta_suggestions[0].text if cta_suggestions else "Let me know your thoughts."

        # Add CTA to context
        context["cta"] = cta
        context["closing"] = context.get("closing", "Best,\n" + context.get("sender_name", ""))

        # Personalize body
        body = self.personalize_email(body_template, context, personalization_level)

        # Clean up any remaining placeholders
        body = re.sub(r'\{[^}]+\}', '', body)
        body = re.sub(r'\n{3,}', '\n\n', body).strip()

        return EmailDraft(
            subject=subject,
            body=body,
            cta_text=cta,
            personalization_level=personalization_level,
            sequence_stage=stage,
            estimated_metrics={
                "open_rate": subject_suggestions[0].estimated_open_rate if subject_suggestions else "medium",
                "click_rate": cta_suggestions[0].estimated_click_rate if cta_suggestions else "medium",
            }
        )

    def add_ethical_urgency(
        self,
        email_body: str,
        urgency_type: str,
        details: Dict[str, Any]
    ) -> str:
        """
        Add ethical urgency/scarcity to email. Only use with real constraints.
        """
        urgency_templates = {
            "limited_time": "This offer is available until {deadline}.",
            "limited_spots": "We only have {spots} spots left this {period}.",
            "price_increase": "Our rates are increasing on {date}. Lock in current pricing now.",
            "seasonal": "Before the {season} rush, I wanted to reach out.",
            "capacity": "Our team's calendar is filling up for {period}.",
        }

        template = urgency_templates.get(urgency_type)
        if not template:
            return email_body

        urgency_text = self._fill_template(template, details)

        # Add before the CTA
        if "\n\n" in email_body:
            parts = email_body.rsplit("\n\n", 1)
            return f"{parts[0]}\n\n{urgency_text}\n\n{parts[1]}"

        return f"{email_body}\n\n{urgency_text}"

    def get_role_specific_talking_points(
        self,
        recipient_role: str,
        business_profile: Dict[str, Any],
        recipient_industry: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get talking points, objections, and personalization suggestions based on recipient role.

        Uses industry templates + business profile to provide role-specific sales intelligence.

        Args:
            recipient_role: The recipient's job title/role (e.g., "CEO", "VP of Operations")
            business_profile: The user's business profile data
            recipient_industry: Optional industry of the recipient's company

        Returns:
            Dict with relevant_objections, talking_points, pain_points, and suggested_angle
        """
        from core.industry_templates import get_industry_template, get_all_industries

        result = {
            "relevant_objections": [],
            "talking_points": [],
            "pain_points": [],
            "suggested_angle": "",
            "cta_suggestion": "",
            "personalization_tips": []
        }

        role_lower = recipient_role.lower() if recipient_role else ""

        # Determine which industry template to use
        industry = recipient_industry or business_profile.get("industry", "")
        template = get_industry_template(industry) if industry else {}

        # Get objections from business profile first, then supplement from template
        profile_objections = business_profile.get("common_objections", [])
        template_objections = template.get("common_objections", [])

        # Combine unique objections
        all_objections = list(profile_objections)
        for obj in template_objections:
            exists = any(o.get("objection") == obj.get("objection") for o in all_objections)
            if not exists:
                all_objections.append(obj)

        # Role-based filtering - what concerns does each role typically have?
        role_priorities = {
            "ceo": ["roi", "growth", "competitive", "strategic", "risk", "revenue"],
            "cfo": ["cost", "roi", "budget", "margin", "expensive", "investment", "price"],
            "cto": ["integration", "security", "technical", "scale", "build", "technology"],
            "coo": ["efficiency", "operations", "process", "implementation", "time"],
            "vp": ["team", "productivity", "results", "performance", "capacity"],
            "director": ["implementation", "resources", "team", "process", "results"],
            "manager": ["time", "team", "easy", "training", "workflow", "adoption"],
            "owner": ["cost", "roi", "risk", "growth", "compete"]
        }

        # Find matching role category
        matched_priorities = []
        for role_key, priorities in role_priorities.items():
            if role_key in role_lower:
                matched_priorities = priorities
                break

        # If no match, use general priorities
        if not matched_priorities:
            matched_priorities = ["roi", "results", "implementation", "cost"]

        # Filter objections by role relevance
        for obj in all_objections:
            objection_text = obj.get("objection", "").lower()
            if any(priority in objection_text for priority in matched_priorities):
                result["relevant_objections"].append(obj)

        # If we didn't find role-specific objections, include top general ones
        if len(result["relevant_objections"]) < 2 and all_objections:
            result["relevant_objections"] = all_objections[:3]

        # Get pain points from business profile
        pain_points = business_profile.get("customer_pain_points", [])
        if not pain_points and template:
            pain_points = template.get("customer_pain_points", [])

        # Filter pain points by role relevance
        for pp in pain_points:
            pp_lower = pp.lower() if isinstance(pp, str) else ""
            if any(priority in pp_lower for priority in matched_priorities):
                result["pain_points"].append(pp)

        if len(result["pain_points"]) < 2:
            result["pain_points"] = pain_points[:3]

        # Generate talking points based on products/services and differentiators
        products = business_profile.get("products_services", [])
        differentiators = business_profile.get("key_differentiators", [])
        usps = business_profile.get("unique_selling_points", [])

        # Build talking points
        if products:
            for product in products[:2]:
                if isinstance(product, dict):
                    benefit = product.get("key_benefit") or product.get("description", "")
                    if benefit:
                        result["talking_points"].append(f"Our {product.get('name', 'solution')} helps with {benefit}")

        for diff in differentiators[:2]:
            result["talking_points"].append(f"We differentiate by: {diff}")

        for usp in usps[:2]:
            result["talking_points"].append(f"Key advantage: {usp}")

        # Suggested approach based on role
        role_angles = {
            "ceo": "Focus on strategic value, competitive advantage, and high-level ROI. Keep it brief and business-focused.",
            "cfo": "Lead with cost savings, ROI numbers, and financial impact. Be specific about pricing and value.",
            "cto": "Emphasize technical capabilities, security, and integration ease. Offer technical deep-dives.",
            "coo": "Focus on operational efficiency, implementation timeline, and process improvements.",
            "vp": "Highlight team productivity gains and how it helps them hit their goals.",
            "director": "Show how it makes their team more effective and reduces their workload.",
            "manager": "Emphasize ease of use, quick onboarding, and day-to-day time savings.",
            "owner": "Balance cost concerns with growth potential. Speak their language."
        }

        for role_key, angle in role_angles.items():
            if role_key in role_lower:
                result["suggested_angle"] = angle
                break

        if not result["suggested_angle"]:
            result["suggested_angle"] = "Focus on specific value and keep the message concise and relevant."

        # CTA suggestion based on role
        role_ctas = {
            "ceo": "Would a 15-minute strategic overview be valuable?",
            "cfo": "Can I send over an ROI analysis for your review?",
            "cto": "Would you like to see the technical architecture?",
            "coo": "Open to a quick walkthrough of the implementation process?",
            "vp": "Worth a conversation about how this could help your team?",
            "director": "Can I show you how this works in practice?",
            "manager": "Would a quick demo be helpful?",
        }

        for role_key, cta in role_ctas.items():
            if role_key in role_lower:
                result["cta_suggestion"] = cta
                break

        if not result["cta_suggestion"]:
            result["cta_suggestion"] = "Would a brief conversation be helpful?"

        # Personalization tips
        result["personalization_tips"] = [
            f"As a {recipient_role}, they likely care about: {', '.join(matched_priorities[:3])}",
            "Reference their company's specific situation if known",
            "Keep initial outreach under 100 words for executives",
        ]

        return result

    def compose_with_intelligence(
        self,
        recipient_email: str,
        recipient_name: str,
        recipient_role: str,
        recipient_company: str,
        business_profile: Dict[str, Any],
        email_type: str = "cold_outreach",
        additional_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Compose an email using full sales intelligence from business profile and industry templates.

        Returns the email draft plus the intelligence used to generate it.
        """
        # Get role-specific talking points
        intelligence = self.get_role_specific_talking_points(
            recipient_role,
            business_profile,
            recipient_industry=additional_context.get("recipient_industry") if additional_context else None
        )

        # Build context for email composition
        context = {
            "first_name": recipient_name.split()[0] if recipient_name else "there",
            "company": recipient_company,
            "role": recipient_role,
            "industry": additional_context.get("recipient_industry", "") if additional_context else "",
            "sender_name": business_profile.get("company_name", ""),
            "value_proposition": business_profile.get("value_proposition", ""),
            "elevator_pitch": business_profile.get("elevator_pitch", ""),
        }

        # Add pain point if available
        if intelligence["pain_points"]:
            context["pain_point"] = intelligence["pain_points"][0]

        # Add talking points to context
        if intelligence["talking_points"]:
            context["value_insight"] = intelligence["talking_points"][0]

        # Add additional context
        if additional_context:
            context.update(additional_context)

        # Compose the email
        email_draft = self.compose_sequence_email(
            stage=email_type,
            context=context,
            personalization_level=PersonalizationLevel.MEDIUM
        )

        return {
            "draft": asdict(email_draft),
            "intelligence": intelligence,
            "context_used": context
        }

    def analyze_email_quality(self, email: EmailDraft) -> Dict[str, Any]:
        """
        Analyze email quality and provide improvement suggestions.
        """
        analysis = {
            "score": 0,
            "max_score": 100,
            "checks": [],
            "suggestions": []
        }

        # Subject line checks (25 points)
        subject_words = len(email.subject.split())
        if subject_words <= 7:
            analysis["score"] += 15
            analysis["checks"].append(("Subject length optimal", True))
        else:
            analysis["checks"].append(("Subject too long", False))
            analysis["suggestions"].append("Shorten subject line to 7 words or less")

        if not email.subject.isupper():
            analysis["score"] += 5
            analysis["checks"].append(("No all caps", True))
        else:
            analysis["checks"].append(("Avoid all caps", False))
            analysis["suggestions"].append("Don't use all caps in subject")

        if "?" in email.subject or email.subject[0].islower():
            analysis["score"] += 5
            analysis["checks"].append(("Conversational subject", True))

        # Body checks (50 points)
        body_words = len(email.body.split())

        if 50 <= body_words <= 150:
            analysis["score"] += 20
            analysis["checks"].append(("Optimal length (50-150 words)", True))
        elif body_words < 50:
            analysis["score"] += 10
            analysis["checks"].append(("Email might be too short", False))
            analysis["suggestions"].append("Add more value or context")
        else:
            analysis["score"] += 10
            analysis["checks"].append(("Email might be too long", False))
            analysis["suggestions"].append("Shorten to 150 words or less")

        # Personalization check
        if email.personalization_level in [PersonalizationLevel.MEDIUM, PersonalizationLevel.ADVANCED]:
            analysis["score"] += 15
            analysis["checks"].append(("Good personalization", True))
        else:
            analysis["checks"].append(("Basic personalization", False))
            analysis["suggestions"].append("Add industry or role-specific personalization")

        # CTA check (15 points)
        if email.cta_text and "?" in email.cta_text:
            analysis["score"] += 15
            analysis["checks"].append(("Clear call to action", True))
        elif email.cta_text:
            analysis["score"] += 10
            analysis["checks"].append(("CTA present but could be stronger", False))
            analysis["suggestions"].append("Frame CTA as a question")
        else:
            analysis["checks"].append(("Missing clear CTA", False))
            analysis["suggestions"].append("Add a clear call to action")

        # Spam check (10 points)
        spam_found = [word for word in self.SPAM_TRIGGERS if word in email.body.lower()]
        if not spam_found:
            analysis["score"] += 10
            analysis["checks"].append(("No spam triggers", True))
        else:
            analysis["checks"].append(("Contains spam triggers", False))
            analysis["suggestions"].append(f"Remove spam triggers: {', '.join(spam_found)}")

        # Calculate grade
        score = analysis["score"]
        if score >= 80:
            analysis["grade"] = "A"
        elif score >= 65:
            analysis["grade"] = "B"
        elif score >= 50:
            analysis["grade"] = "C"
        else:
            analysis["grade"] = "D"

        return analysis


# Global instance
smart_composer = SmartComposer()
