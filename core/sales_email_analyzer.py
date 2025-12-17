"""
Sales Email Analyzer - AI-powered sales intelligence for emails
Detects lead quality, objections, communication friction, and conversation stages
"""
import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ObjectionType(str, Enum):
    PRICE = "price"
    TIMING = "timing"
    AUTHORITY = "authority"
    NEED = "need"
    TRUST = "trust"
    COMPETITION = "competition"


class ConversationStage(str, Enum):
    COLD_OUTREACH = "cold_outreach"
    ENGAGED = "engaged"
    DISCOVERY = "discovery"
    EVALUATION = "evaluation"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSING = "closing"
    STALLED = "stalled"
    WON = "won"
    LOST = "lost"


class FrictionType(str, Enum):
    INFORMATION_OVERLOAD = "information_overload"
    EXPECTATION_MISMATCH = "expectation_mismatch"
    EMOTIONAL_DISCONNECT = "emotional_disconnect"
    FEAR_CONCERN = "fear_concern"
    UNANSWERED_QUESTIONS = "unanswered_questions"
    NO_LISTENING = "no_listening"


@dataclass
class BANTScore:
    """BANT qualification framework scores"""
    budget: int = 0  # 0-100
    authority: int = 0
    need: int = 0
    timeline: int = 0

    @property
    def total(self) -> int:
        """Weighted total score (0-100)"""
        # Weight: Budget 30%, Authority 25%, Need 30%, Timeline 15%
        return int(
            self.budget * 0.30 +
            self.authority * 0.25 +
            self.need * 0.30 +
            self.timeline * 0.15
        )

    @property
    def qualification_level(self) -> str:
        total = self.total
        if total >= 70:
            return "highly_qualified"
        elif total >= 50:
            return "qualified"
        elif total >= 30:
            return "needs_nurturing"
        else:
            return "cold"


@dataclass
class LeadQualityResult:
    """Complete lead quality analysis result"""
    bant_score: BANTScore
    overall_score: int
    qualification_level: str
    signals: List[Dict[str, Any]]
    recommendations: List[str]
    confidence: int


@dataclass
class Objection:
    """Detected sales objection"""
    type: ObjectionType
    exact_quote: str
    confidence: int  # 0-100
    suggested_responses: List[str]
    severity: str  # low, medium, high


@dataclass
class FrictionPoint:
    """Communication friction point"""
    type: FrictionType
    description: str
    evidence: str
    severity: str  # low, medium, high
    resolution_tips: List[str]


@dataclass
class ConversationAnalysis:
    """Full conversation stage analysis"""
    stage: ConversationStage
    confidence: int
    days_in_stage: int
    next_actions: List[str]
    risk_level: str  # low, medium, high


class SalesEmailAnalyzer:
    """
    Analyzes emails for sales intelligence signals.
    Uses pattern matching for speed, AI for complex analysis.
    """

    # Objection patterns by category
    OBJECTION_PATTERNS = {
        ObjectionType.PRICE: [
            r"too expensive", r"over budget", r"can't afford",
            r"cheaper option", r"lower price", r"cost is (too )?high",
            r"out of our budget", r"price point", r"more competitive pricing",
            r"budget constraints?", r"not in the budget", r"price is a concern"
        ],
        ObjectionType.TIMING: [
            r"not (the right )?time", r"let me think", r"get back to you",
            r"circle back", r"maybe later", r"not ready",
            r"need more time", r"too soon", r"revisit this",
            r"touch base later", r"not a priority right now", r"bad timing"
        ],
        ObjectionType.AUTHORITY: [
            r"need to (check|talk) with", r"my (boss|manager|team|committee)",
            r"run this by", r"not my decision", r"decision maker",
            r"board approval", r"stakeholder", r"get buy-?in",
            r"internal discussion", r"leadership team"
        ],
        ObjectionType.NEED: [
            r"not a priority", r"already have", r"works fine",
            r"don't need", r"no need", r"satisfied with",
            r"happy with (our )?(current|existing)", r"not looking",
            r"don't see the value", r"no pain point"
        ],
        ObjectionType.TRUST: [
            r"not sure about", r"references?", r"case studies",
            r"testimonials?", r"proof", r"guarantee",
            r"risk(y)?", r"concerned about", r"worried about",
            r"track record", r"how do we know"
        ],
        ObjectionType.COMPETITION: [
            r"competitor", r"alternative", r"compared to",
            r"vs\.?", r"shopping around", r"other options?",
            r"looking at others?", r"evaluating", r"comparing"
        ]
    }

    # BANT signal patterns
    BUDGET_SIGNALS = {
        "positive": [
            (r"\$[\d,]+[kKmM]?\b", 40),  # Specific dollar amounts
            (r"budget (is |of )?(around |about )?\$", 35),
            (r"we('ve| have) allocated", 30),
            (r"approved budget", 40),
            (r"can (spend|invest|allocate)", 25),
            (r"price (is )?(not|no) (a |an )?issue", 35),
        ],
        "negative": [
            (r"no budget", -30),
            (r"budget (is )?(tight|limited)", -15),
            (r"can't afford", -25),
            (r"free (only|tier)", -20),
        ]
    }

    AUTHORITY_SIGNALS = {
        "positive": [
            (r"I (can|will) (approve|sign|decide)", 45),
            (r"(CEO|CTO|CFO|COO|VP|Director|Head of|President|Owner|Founder)", 35),
            (r"final decision", 30),
            (r"my team", 25),
            (r"I('m| am) (in charge|responsible)", 35),
            (r"authorized to", 40),
        ],
        "negative": [
            (r"need (to )?(check|ask|run) (this )?(by|with)", -20),
            (r"not my decision", -30),
            (r"my (boss|manager) (will|needs)", -15),
        ]
    }

    NEED_SIGNALS = {
        "positive": [
            (r"we need", 30),
            (r"looking for", 25),
            (r"struggling with", 35),
            (r"pain point", 40),
            (r"problem (is|with)", 30),
            (r"challenge(s)? (we face|is)", 30),
            (r"frustrated (with|by)", 35),
            (r"must have", 40),
            (r"critical", 35),
            (r"urgent need", 45),
        ],
        "negative": [
            (r"just browsing", -20),
            (r"no (real |specific )?need", -30),
            (r"works fine", -25),
            (r"happy with (current|existing)", -25),
        ]
    }

    TIMELINE_SIGNALS = {
        "positive": [
            (r"by (end of )?(Q[1-4]|this (week|month|quarter))", 40),
            (r"deadline", 35),
            (r"asap|immediately|urgent(ly)?", 45),
            (r"within (\d+) (days?|weeks?|months?)", 35),
            (r"this (month|quarter|year)", 25),
            (r"need (it|this) (by|before)", 35),
            (r"starting (in|next)", 30),
        ],
        "negative": [
            (r"no (rush|hurry|timeline)", -20),
            (r"eventually", -15),
            (r"sometime (next year|later)", -10),
            (r"no deadline", -15),
        ]
    }

    # Communication friction patterns
    FRICTION_PATTERNS = {
        FrictionType.INFORMATION_OVERLOAD: [
            r"too much (info|information)",
            r"overwhelm(ed|ing)",
            r"confus(ed|ing)",
            r"lot to (digest|process)",
            r"tl;?dr",
        ],
        FrictionType.EXPECTATION_MISMATCH: [
            r"(thought|expected|assumed) (it|this|you) would",
            r"(not|wasn't) what (I|we) (expected|thought)",
            r"misunderst(ood|anding)",
            r"(different|not the same) (than|from) what",
            r"clarify",
        ],
        FrictionType.EMOTIONAL_DISCONNECT: [
            r"feel(s)? (like )?you (don't|do not) understand",
            r"not listening",
            r"(don't|doesn't) get (it|us|me)",
            r"just (want to|trying to) sell",
            r"pushy",
        ],
        FrictionType.FEAR_CONCERN: [
            r"worried (about|that)",
            r"concerned (about|that)",
            r"what if",
            r"afraid (of|that)",
            r"risk(y|s)?",
            r"scared",
            r"hesitant",
        ],
        FrictionType.UNANSWERED_QUESTIONS: [
            r"still (have|need) (a )?question",
            r"didn't (answer|address)",
            r"what about",
            r"you never (said|mentioned|answered)",
        ],
    }

    # Stage detection signals
    STAGE_SIGNALS = {
        ConversationStage.DISCOVERY: [
            r"tell me (more )?about",
            r"how does (it|this|your)",
            r"what (is|are|does)",
            r"can you explain",
            r"curious about",
        ],
        ConversationStage.EVALUATION: [
            r"compar(e|ing)",
            r"vs\.?|versus",
            r"alternative",
            r"other (options?|solutions?)",
            r"(pros|cons|benefits)",
            r"demo|trial",
        ],
        ConversationStage.PROPOSAL: [
            r"(send|share) (a |the )?(proposal|quote|pricing)",
            r"what (would|does) (it|this) cost",
            r"pricing (details|information)",
            r"formal (proposal|offer)",
            r"SOW|statement of work",
        ],
        ConversationStage.NEGOTIATION: [
            r"(can you|could we) (do|offer)",
            r"discount",
            r"terms",
            r"contract",
            r"(negotiate|negotiation)",
            r"what if we",
            r"flexibility",
        ],
        ConversationStage.CLOSING: [
            r"ready (to|for)",
            r"let('s| us) (start|begin|proceed|move forward)",
            r"sign (the |this )?",
            r"when can we start",
            r"next steps",
            r"onboard(ing)?",
        ],
    }

    # Objection response templates
    OBJECTION_RESPONSES = {
        ObjectionType.PRICE: [
            "Focus on ROI: 'Many clients see a {X}x return within {timeframe}. Would you like me to walk through the value breakdown?'",
            "Reframe the conversation: 'I understand budget is important. What if we looked at the cost of NOT solving this problem?'",
            "Offer flexibility: 'We have different tiers. Let me show you options that might better fit your budget while still addressing your core needs.'",
        ],
        ObjectionType.TIMING: [
            "Create urgency gently: 'I understand timing is tricky. Quick question - what would need to change for this to become a priority?'",
            "Stay top of mind: 'No problem at all. Would it be helpful if I checked back in {timeframe}? In the meantime, I can share some resources.'",
            "Find the trigger: 'What events or milestones would make this the right time? I'd love to be ready when that happens.'",
        ],
        ObjectionType.AUTHORITY: [
            "Offer to help: 'I'd be happy to join a call with your team to answer any questions they might have.'",
            "Provide materials: 'Would it help if I put together a brief summary you could share with [decision maker]?'",
            "Understand the process: 'What does the approval process typically look like at [company]? I want to make sure I'm supporting you effectively.'",
        ],
        ObjectionType.NEED: [
            "Dig deeper: 'I appreciate you sharing that. Just curious - what would need to change in your current setup to consider alternatives?'",
            "Plant seeds: 'That makes sense. Many of our clients felt the same way before they experienced [specific benefit]. Would a case study be helpful?'",
            "Validate and pivot: 'I respect that. Out of curiosity, what are your biggest priorities this quarter?'",
        ],
        ObjectionType.TRUST: [
            "Provide social proof: 'Totally understandable. We work with companies like [similar company]. Would you like to speak with a reference?'",
            "Offer a trial: 'How about we start with a small pilot project? That way you can see results before making a bigger commitment.'",
            "Share case studies: 'I have a case study from a company in your industry that faced similar concerns. Would that be helpful?'",
        ],
        ObjectionType.COMPETITION: [
            "Differentiate: 'Great question. The key difference with us is [unique value prop]. Would you like me to show you a side-by-side comparison?'",
            "Be confident: 'I'm glad you're doing your research. Here's what our clients say sets us apart: [1, 2, 3].'",
            "Find the gap: 'What specifically are you hoping to find that you haven't seen yet? I want to make sure I'm addressing your actual needs.'",
        ],
    }

    def __init__(self, ai_client=None):
        """Initialize with optional AI client for advanced analysis"""
        self.ai_client = ai_client

    def analyze_lead_quality(self, email_content: str, sender_info: Dict = None) -> LeadQualityResult:
        """
        Analyze email for lead quality using BANT framework.
        Returns overall qualification score and detailed breakdown.
        """
        content_lower = email_content.lower()
        signals = []

        # Calculate BANT scores
        budget_score = self._calculate_signal_score(content_lower, self.BUDGET_SIGNALS, signals, "budget")
        authority_score = self._calculate_signal_score(content_lower, self.AUTHORITY_SIGNALS, signals, "authority")
        need_score = self._calculate_signal_score(content_lower, self.NEED_SIGNALS, signals, "need")
        timeline_score = self._calculate_signal_score(content_lower, self.TIMELINE_SIGNALS, signals, "timeline")

        # Bonus for sender info
        if sender_info:
            # Handle both dict and string sender_info
            if isinstance(sender_info, dict):
                title = sender_info.get("title", "").lower()
                if any(t in title for t in ["ceo", "cto", "cfo", "vp", "director", "head", "owner", "founder"]):
                    authority_score = min(100, authority_score + 20)
                    signals.append({
                        "category": "authority",
                        "type": "positive",
                        "match": f"Decision-maker title: {sender_info.get('title')}"
                    })
            elif isinstance(sender_info, str):
                # Extract potential title info from email/name string
                sender_lower = sender_info.lower()
                if any(t in sender_lower for t in ["ceo", "cto", "cfo", "vp", "director", "head", "owner", "founder"]):
                    authority_score = min(100, authority_score + 20)
                    signals.append({
                        "category": "authority",
                        "type": "positive",
                        "match": f"Potential decision-maker: {sender_info}"
                    })

        bant = BANTScore(
            budget=max(0, min(100, budget_score)),
            authority=max(0, min(100, authority_score)),
            need=max(0, min(100, need_score)),
            timeline=max(0, min(100, timeline_score))
        )

        # Generate recommendations
        recommendations = self._generate_qualification_recommendations(bant, signals)

        return LeadQualityResult(
            bant_score=bant,
            overall_score=bant.total,
            qualification_level=bant.qualification_level,
            signals=signals,
            recommendations=recommendations,
            confidence=self._calculate_signal_confidence(signals)
        )

    def _calculate_signal_score(
        self,
        content: str,
        patterns: Dict,
        signals: List,
        category: str
    ) -> int:
        """Calculate score based on pattern matches"""
        score = 0

        for polarity in ["positive", "negative"]:
            for pattern, value in patterns.get(polarity, []):
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    score += value
                    for match in matches[:2]:  # Limit to 2 examples
                        signals.append({
                            "category": category,
                            "type": polarity,
                            "match": match if isinstance(match, str) else match[0],
                            "score_impact": value
                        })

        return score

    def _calculate_signal_confidence(self, signals: List) -> int:
        """Calculate confidence based on number of signals detected"""
        if len(signals) >= 8:
            return 90
        elif len(signals) >= 5:
            return 75
        elif len(signals) >= 3:
            return 60
        elif len(signals) >= 1:
            return 40
        return 20

    def _generate_qualification_recommendations(self, bant: BANTScore, signals: List) -> List[str]:
        """Generate actionable recommendations based on BANT gaps"""
        recommendations = []

        if bant.budget < 40:
            recommendations.append("Probe for budget: Ask about their typical investment range for solutions like this")

        if bant.authority < 40:
            recommendations.append("Identify decision-makers: Ask who else should be involved in evaluating this")

        if bant.need < 40:
            recommendations.append("Uncover pain points: Ask about their biggest challenges in this area")

        if bant.timeline < 40:
            recommendations.append("Establish timeline: Ask about their ideal implementation timeframe")

        if bant.total >= 70:
            recommendations.append("High-quality lead: Consider fast-tracking to proposal stage")

        return recommendations

    def detect_objections(self, email_content: str) -> List[Objection]:
        """
        Detect sales objections in email content.
        Returns list of objections with suggested responses.
        """
        content_lower = email_content.lower()
        objections = []

        for obj_type, patterns in self.OBJECTION_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, content_lower, re.IGNORECASE)
                for match in matches:
                    # Get surrounding context
                    start = max(0, match.start() - 30)
                    end = min(len(email_content), match.end() + 50)
                    context = email_content[start:end].strip()

                    objections.append(Objection(
                        type=obj_type,
                        exact_quote=context,
                        confidence=self._calculate_objection_confidence(pattern, context),
                        suggested_responses=self.OBJECTION_RESPONSES.get(obj_type, []),
                        severity=self._assess_objection_severity(obj_type, context)
                    ))
                    break  # One objection per type per email

        return objections

    def _calculate_objection_confidence(self, pattern: str, context: str) -> int:
        """Calculate confidence score for objection detection"""
        # Stronger patterns get higher confidence
        strong_patterns = ["too expensive", "can't afford", "not now", "not my decision"]
        if any(p in context.lower() for p in strong_patterns):
            return 90
        return 70

    def _assess_objection_severity(self, obj_type: ObjectionType, context: str) -> str:
        """Assess how severe the objection is"""
        context_lower = context.lower()

        # Strong negative indicators
        if any(word in context_lower for word in ["definitely", "absolutely", "never", "no way"]):
            return "high"

        # Soft objections
        if any(word in context_lower for word in ["maybe", "might", "could", "possibly"]):
            return "low"

        return "medium"

    def analyze_friction(self, email_thread: List[Dict]) -> List[FrictionPoint]:
        """
        Analyze email thread for communication friction points.
        """
        friction_points = []

        if not email_thread:
            return friction_points

        # Analyze each email for friction patterns
        for email in email_thread:
            content = email.get("body_text", "") or email.get("body_html", "")
            content_lower = content.lower()

            for friction_type, patterns in self.FRICTION_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, content_lower, re.IGNORECASE):
                        friction_points.append(FrictionPoint(
                            type=friction_type,
                            description=self._get_friction_description(friction_type),
                            evidence=self._extract_evidence(content, pattern),
                            severity=self._assess_friction_severity(friction_type, content),
                            resolution_tips=self._get_friction_tips(friction_type)
                        ))
                        break

        # Check for meta-friction (thread-level issues)
        friction_points.extend(self._detect_thread_friction(email_thread))

        return friction_points

    def _get_friction_description(self, friction_type: FrictionType) -> str:
        """Get human-readable description of friction type"""
        descriptions = {
            FrictionType.INFORMATION_OVERLOAD: "Prospect feels overwhelmed by too much information",
            FrictionType.EXPECTATION_MISMATCH: "There's a gap between what was expected and what was delivered",
            FrictionType.EMOTIONAL_DISCONNECT: "Prospect doesn't feel heard or understood",
            FrictionType.FEAR_CONCERN: "Prospect has unaddressed fears or concerns",
            FrictionType.UNANSWERED_QUESTIONS: "Previous questions weren't adequately addressed",
            FrictionType.NO_LISTENING: "Communication feels one-sided",
        }
        return descriptions.get(friction_type, "Communication issue detected")

    def _extract_evidence(self, content: str, pattern: str) -> str:
        """Extract the matching text as evidence"""
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 20)
            end = min(len(content), match.end() + 30)
            return content[start:end].strip()
        return ""

    def _assess_friction_severity(self, friction_type: FrictionType, content: str) -> str:
        """Assess severity of friction point"""
        # Emotional disconnect and fear are typically more severe
        high_severity_types = [FrictionType.EMOTIONAL_DISCONNECT, FrictionType.FEAR_CONCERN]
        if friction_type in high_severity_types:
            return "high"
        return "medium"

    def _get_friction_tips(self, friction_type: FrictionType) -> List[str]:
        """Get resolution tips for friction type"""
        tips = {
            FrictionType.INFORMATION_OVERLOAD: [
                "Simplify your next message - focus on ONE key point",
                "Use bullet points instead of paragraphs",
                "Ask what specific information they need",
            ],
            FrictionType.EXPECTATION_MISMATCH: [
                "Acknowledge the misunderstanding directly",
                "Clarify what you can actually deliver",
                "Reset expectations with specific examples",
            ],
            FrictionType.EMOTIONAL_DISCONNECT: [
                "Lead with empathy in your response",
                "Ask more questions before making statements",
                "Summarize their concerns to show you listened",
            ],
            FrictionType.FEAR_CONCERN: [
                "Address the fear directly and honestly",
                "Provide specific reassurance with evidence",
                "Offer a risk-free way to proceed (trial, pilot)",
            ],
            FrictionType.UNANSWERED_QUESTIONS: [
                "Go back and explicitly answer each question",
                "Apologize for the oversight",
                "Ask if they have additional questions",
            ],
            FrictionType.NO_LISTENING: [
                "Start your next email with a summary of their points",
                "Ask clarifying questions before presenting solutions",
                "Reduce the ratio of talking vs asking",
            ],
        }
        return tips.get(friction_type, ["Review the conversation for clarity"])

    def _detect_thread_friction(self, email_thread: List[Dict]) -> List[FrictionPoint]:
        """Detect thread-level friction patterns"""
        friction_points = []

        if len(email_thread) < 2:
            return friction_points

        # Check for unanswered questions
        for i, email in enumerate(email_thread[:-1]):
            content = email.get("body_text", "") or ""
            questions = content.count("?")

            # If previous email had questions, check if next email addresses them
            if questions >= 2:
                next_email = email_thread[i + 1]
                next_content = next_email.get("body_text", "") or ""

                # Simple heuristic: if response is very short, questions might be unanswered
                if len(next_content) < 100 and questions >= 3:
                    friction_points.append(FrictionPoint(
                        type=FrictionType.UNANSWERED_QUESTIONS,
                        description="Multiple questions in previous email may not have been fully addressed",
                        evidence=f"{questions} questions asked, but response was brief",
                        severity="medium",
                        resolution_tips=self._get_friction_tips(FrictionType.UNANSWERED_QUESTIONS)
                    ))

        return friction_points

    def detect_conversation_stage(
        self,
        email_thread: List[Dict],
        last_activity_date: datetime = None
    ) -> ConversationAnalysis:
        """
        Detect the current stage of the sales conversation.
        """
        if not email_thread:
            return ConversationAnalysis(
                stage=ConversationStage.COLD_OUTREACH,
                confidence=100,
                days_in_stage=0,
                next_actions=["Send initial outreach email"],
                risk_level="low"
            )

        # Check for stalled conversation first
        if last_activity_date:
            days_since = (datetime.utcnow() - last_activity_date).days
            if days_since > 7:
                return ConversationAnalysis(
                    stage=ConversationStage.STALLED,
                    confidence=90,
                    days_in_stage=days_since,
                    next_actions=[
                        "Send a re-engagement email",
                        "Try a different channel (phone, LinkedIn)",
                        "Offer new value (case study, insight)",
                    ],
                    risk_level="high"
                )

        # Combine all email content for analysis
        all_content = " ".join([
            (e.get("body_text", "") or e.get("body_html", ""))
            for e in email_thread
        ]).lower()

        # Score each stage
        stage_scores = {}
        for stage, patterns in self.STAGE_SIGNALS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, all_content, re.IGNORECASE):
                    score += 1
            stage_scores[stage] = score

        # Determine stage based on scores and email count
        email_count = len(email_thread)

        # Only first email, no response
        if email_count == 1:
            return ConversationAnalysis(
                stage=ConversationStage.COLD_OUTREACH,
                confidence=90,
                days_in_stage=0,
                next_actions=["Follow up in 2-3 days if no response"],
                risk_level="medium"
            )

        # Has response - determine specific stage
        best_stage = max(stage_scores.items(), key=lambda x: x[1], default=(ConversationStage.ENGAGED, 0))

        if best_stage[1] > 0:
            stage = best_stage[0]
        else:
            # Default progression based on email count
            if email_count <= 3:
                stage = ConversationStage.ENGAGED
            elif email_count <= 6:
                stage = ConversationStage.DISCOVERY
            else:
                stage = ConversationStage.EVALUATION

        return ConversationAnalysis(
            stage=stage,
            confidence=min(95, 50 + (best_stage[1] * 15)),
            days_in_stage=self._estimate_days_in_stage(email_thread, stage),
            next_actions=self._get_stage_actions(stage),
            risk_level=self._assess_stage_risk(stage, email_thread)
        )

    def _estimate_days_in_stage(self, email_thread: List[Dict], stage: ConversationStage) -> int:
        """Estimate how many days the conversation has been in this stage"""
        if not email_thread:
            return 0

        # Use the date of the most recent email
        try:
            latest = email_thread[-1]
            received = latest.get("received_at")
            if received:
                if isinstance(received, str):
                    received = datetime.fromisoformat(received.replace("Z", "+00:00"))
                return (datetime.utcnow() - received.replace(tzinfo=None)).days
        except:
            pass
        return 0

    def _get_stage_actions(self, stage: ConversationStage) -> List[str]:
        """Get recommended next actions for each stage"""
        actions = {
            ConversationStage.COLD_OUTREACH: [
                "Follow up in 2-3 days",
                "Try a different value proposition",
                "Test a new subject line",
            ],
            ConversationStage.ENGAGED: [
                "Schedule a discovery call",
                "Ask qualifying questions (BANT)",
                "Share relevant content",
            ],
            ConversationStage.DISCOVERY: [
                "Dive deeper into pain points",
                "Identify all stakeholders",
                "Confirm timeline and budget",
            ],
            ConversationStage.EVALUATION: [
                "Provide comparison materials",
                "Offer a demo or trial",
                "Address competitive concerns",
            ],
            ConversationStage.PROPOSAL: [
                "Send detailed proposal",
                "Include ROI calculations",
                "Propose next steps clearly",
            ],
            ConversationStage.NEGOTIATION: [
                "Address specific concerns",
                "Explore creative solutions",
                "Prepare for close",
            ],
            ConversationStage.CLOSING: [
                "Remove final barriers",
                "Prepare contract",
                "Plan implementation kickoff",
            ],
            ConversationStage.STALLED: [
                "Re-engage with new value",
                "Try different channel",
                "Consider timing-based follow-up",
            ],
        }
        return actions.get(stage, ["Continue the conversation"])

    def _assess_stage_risk(self, stage: ConversationStage, email_thread: List[Dict]) -> str:
        """Assess risk level based on stage and thread characteristics"""
        # Later stages with no recent activity are higher risk
        if stage in [ConversationStage.PROPOSAL, ConversationStage.NEGOTIATION]:
            return "high"

        if stage == ConversationStage.STALLED:
            return "high"

        if stage in [ConversationStage.COLD_OUTREACH, ConversationStage.ENGAGED]:
            return "low"

        return "medium"

    def get_comprehensive_analysis(
        self,
        email_content: str,
        email_thread: List[Dict] = None,
        sender_info: Dict = None,
        last_activity_date: datetime = None
    ) -> Dict[str, Any]:
        """
        Run all analyses and return comprehensive sales intelligence.
        """
        lead_quality = self.analyze_lead_quality(email_content, sender_info)
        objections = self.detect_objections(email_content)
        friction = self.analyze_friction(email_thread or [])
        stage = self.detect_conversation_stage(email_thread or [], last_activity_date)

        return {
            "lead_quality": asdict(lead_quality),
            "objections": [asdict(o) for o in objections],
            "friction_points": [asdict(f) for f in friction],
            "conversation_stage": asdict(stage),
            "summary": {
                "qualification_level": lead_quality.qualification_level,
                "overall_score": lead_quality.overall_score,
                "active_objections": len(objections),
                "friction_detected": len(friction) > 0,
                "current_stage": stage.stage.value,
                "risk_level": stage.risk_level,
                "top_recommendations": (
                    lead_quality.recommendations[:2] +
                    stage.next_actions[:2]
                )[:3]
            }
        }


# Global instance
sales_analyzer = SalesEmailAnalyzer()
