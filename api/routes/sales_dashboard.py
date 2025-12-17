from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, case
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import re
import json
import logging
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from core.database import get_db, User, Email, ActionItem, BusinessProfile, ColdEmailCampaign, ColdEmailProspect
from core.outlook_service import OutlookService
from core.sales_email_analyzer import sales_analyzer, ObjectionType, ConversationStage
from core.smart_composer import smart_composer, SubjectLineCategory, PersonalizationLevel
from core.email_sequences import sequence_manager, SequenceStage
from api.auth import get_current_user

router = APIRouter(prefix="/api/sales-dashboard", tags=["sales-dashboard"])
logger = logging.getLogger(__name__)

# Helper functions
def _format_pricing_html(pricing: Dict) -> str:
    """Format pricing options as HTML"""
    html = "<div style='margin: 20px 0;'>"
    for option in pricing.get("options", []):
        recommended = " (Recommended)" if option.get("recommended") else ""
        html += f"""
        <div style='border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px;'>
            <h4 style='margin-top: 0;'>{option['name']}{recommended}</h4>
            <p style='font-size: 24px; color: #2563eb; font-weight: bold;'>${option['price']:,.2f}</p>
            <ul>
                {''.join([f"<li>{feature}</li>" for feature in option.get('features', [])])}
            </ul>
        </div>
        """
    html += "</div>"
    return html

class SalesDashboard:
    """Main dashboard class for sales intelligence features"""

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def get_dashboard_overview(self) -> Dict:
        """Get high-level dashboard metrics"""
        # Get opportunities (open leads)
        opportunities = self.get_opportunity_scores()

        # Count by temperature
        hot_leads = len([opp for opp in opportunities if opp.get("temperature") == "hot"])
        warm_leads = len([opp for opp in opportunities if opp.get("temperature") == "warm"])
        cold_leads = len([opp for opp in opportunities if opp.get("temperature") == "cold"])

        # Count by type
        new_inquiries = len([opp for opp in opportunities if opp.get("type") == "new"])
        existing_customers = len([opp for opp in opportunities if opp.get("type") == "existing"])

        # Get unread emails count
        unread_count = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.is_read == False,
            Email.deleted_at.is_(None)
        ).count()

        # Get total recent emails (last 30 days)
        recent_cutoff = datetime.utcnow() - timedelta(days=30)
        total_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.received_at >= recent_cutoff,
            Email.deleted_at.is_(None)
        ).count()

        return {
            "total_emails": len(opportunities),  # All scored opportunities = open leads
            "unread_count": unread_count,
            "opportunities": {
                "total": len(opportunities),
                "hot": hot_leads,
                "warm": warm_leads,
                "cold": cold_leads,
                "new_inquiries": new_inquiries,
                "existing_customers": existing_customers
            },
            "emails": {
                "recent_total": total_emails,
                "unread": unread_count
            }
        }

    def get_revenue_pipeline(self) -> Dict:
        """Get revenue pipeline overview"""
        # Get all emails from last 90 days
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.received_at >= cutoff_date,
            Email.deleted_at.is_(None)
        ).all()
        
        pipeline = {
            "active_deals": [],
            "stalled_opportunities": [],
            "hot_leads": [],
            "total_pipeline_value": 0,
            "conversion_funnel": {
                "prospect": 0,
                "qualified": 0,
                "proposal": 0,
                "negotiation": 0,
                "closed": 0
            }
        }
        
        # Group emails by thread/conversation
        threads = self._group_by_thread(emails)
        
        for thread_id, thread_emails in threads.items():
            deal_info = self._analyze_deal_thread(thread_emails)
            
            if deal_info["value"] > 0:
                pipeline["total_pipeline_value"] += deal_info["value"]
                
                # Check if stalled (no activity in 7 days)
                last_email = max(thread_emails, key=lambda e: e.received_at)
                days_silent = (datetime.utcnow() - last_email.received_at).days
                
                if days_silent > 7:
                    pipeline["stalled_opportunities"].append({
                        **deal_info,
                        "days_stalled": days_silent
                    })
                elif deal_info["urgency_score"] > 0.7:
                    pipeline["hot_leads"].append(deal_info)
                else:
                    pipeline["active_deals"].append(deal_info)
                
                # Update funnel
                stage = deal_info.get("stage", "prospect")
                pipeline["conversion_funnel"][stage] += 1
        
        return pipeline
    
    def get_opportunity_scores(self) -> List[Dict]:
        """Score and rank opportunities"""
        opportunities = []
        
        # Get unique senders from recent emails
        recent_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.received_at >= datetime.utcnow() - timedelta(days=30),
            Email.deleted_at.is_(None)
        ).all()
        
        sender_groups = defaultdict(list)
        for email in recent_emails:
            sender_groups[email.sender].append(email)
        
        for sender, emails in sender_groups.items():
            opportunity = self._score_opportunity(sender, emails)
            if opportunity["score"] > 0.25:  # Lower threshold to catch early-stage inquiries
                opportunities.append(opportunity)
        
        # Sort by score
        opportunities.sort(key=lambda x: x["score"], reverse=True)
        return opportunities[:20]  # Top 20 opportunities
    
    def get_engagement_analytics(self) -> Dict:
        """Get engagement analytics"""
        analytics = {
            "response_rates": {},
            "best_times": {},
            "engagement_heatmap": [],
            "deal_velocity": []
        }

        # Analyze sent emails and their responses
        sent_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.is_sent == True,  # Only analyze emails sent by user
            Email.deleted_at.is_(None),
            Email.received_at >= datetime.utcnow() - timedelta(days=90)  # Last 90 days
        ).limit(200).all()
        
        # Calculate response rates by day of week
        day_stats = defaultdict(lambda: {"sent": 0, "responded": 0})
        hour_stats = defaultdict(lambda: {"sent": 0, "responded": 0})
        
        for email in sent_emails:
            day = email.received_at.strftime("%A")
            hour = email.received_at.hour
            
            day_stats[day]["sent"] += 1
            hour_stats[hour]["sent"] += 1
            
            # Check if got response (simplified - looks for reply within 7 days)
            if self._has_response(email):
                day_stats[day]["responded"] += 1
                hour_stats[hour]["responded"] += 1
        
        # Calculate rates
        for day, stats in day_stats.items():
            if stats["sent"] > 0:
                analytics["response_rates"][day] = stats["responded"] / stats["sent"]
        
        # Find best times
        best_hours = sorted(
            [(h, s["responded"]/s["sent"]) for h, s in hour_stats.items() if s["sent"] > 0],
            key=lambda x: x[1],
            reverse=True
        )[:3]
        analytics["best_times"]["hours"] = [{"hour": h, "rate": r} for h, r in best_hours]
        
        # Generate heatmap data
        for hour in range(24):
            for day in range(7):
                analytics["engagement_heatmap"].append({
                    "hour": hour,
                    "day": day,
                    "value": hour_stats[hour]["responded"] / max(hour_stats[hour]["sent"], 1)
                })
        
        return analytics
    
    def get_action_priority_queue(self) -> List[Dict]:
        """Get prioritized action items"""
        actions = []
        
        # Get emails requiring follow-up (recent emails that may need response)
        unanswered_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.is_read == True,  # Focus on read emails that might need follow-up
            Email.deleted_at.is_(None),
            Email.received_at >= datetime.utcnow() - timedelta(days=7)
        ).all()
        
        for email in unanswered_emails:
            # Check if email contains questions or requests
            if self._requires_response(email):
                priority = self._calculate_priority(email)
                actions.append({
                    "id": str(email.id),
                    "type": "follow_up",
                    "subject": email.subject,
                    "sender": email.sender_name or email.sender,
                    "received": email.received_at.isoformat(),
                    "priority_score": priority,
                    "suggested_action": self._suggest_action(email),
                    "potential_value": self._estimate_value(email)
                })
        
        # Add contract renewals, quote expirations, etc.
        actions.extend(self._get_time_sensitive_actions())
        
        # Sort by priority
        actions.sort(key=lambda x: x["priority_score"], reverse=True)
        return actions[:10]  # Top 10 actions
    
    def get_revenue_leakage_alerts(self) -> List[Dict]:
        """Get revenue leakage alerts"""
        alerts = []
        
        # Check for competitor mentions
        competitor_keywords = ["competitor", "alternative", "switching", "cancel", "termination"]
        risk_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.deleted_at.is_(None),
            or_(*[Email.body_text.ilike(f"%{kw}%") for kw in competitor_keywords])
        ).limit(20).all()
        
        for email in risk_emails:
            risk_level = self._assess_risk_level(email)
            if risk_level > 0.5:
                alerts.append({
                    "id": str(email.id),
                    "type": "competitor_threat",
                    "risk_level": risk_level,
                    "subject": email.subject,
                    "sender": email.sender_name or email.sender,
                    "detected_issue": self._identify_issue(email),
                    "recommended_action": self._recommend_retention_action(email)
                })
        
        # Check for VIP emails left unread
        vip_domains = self._get_vip_domains()
        unread_vip = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.is_read == False,
            Email.deleted_at.is_(None),
            or_(*[Email.sender.ilike(f"%{domain}%") for domain in vip_domains])
        ).all()
        
        for email in unread_vip:
            alerts.append({
                "id": str(email.id),
                "type": "vip_neglect",
                "risk_level": 0.8,
                "subject": email.subject,
                "sender": email.sender_name or email.sender,
                "days_unread": (datetime.utcnow() - email.received_at).days,
                "recommended_action": "Immediate response required"
            })
        
        return alerts
    
    def get_quick_actions(self) -> Dict:
        """Get quick action templates and suggestions"""
        return {
            "templates": self._get_response_templates(),
            "bulk_actions": self._get_bulk_action_suggestions(),
            "optimal_send_times": self._get_optimal_send_times(),
            "saved_responses": self._get_saved_responses()
        }
    
    def get_profit_insights(self) -> Dict:
        """Get profit insights and trends"""
        insights = {
            "average_deal_size": 0,
            "deal_size_trend": [],
            "lost_revenue_potential": 0,
            "customer_lifetime_values": [],
            "product_interest_signals": [],
            "conversion_metrics": {}
        }
        
        # Calculate average deal size from emails
        deal_values = []
        emails_with_values = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.deleted_at.is_(None),
            or_(
                Email.body_text.ilike("%$%"),
                Email.body_text.ilike("%USD%"),
                Email.body_text.ilike("%price%"),
                Email.body_text.ilike("%cost%")
            )
        ).all()
        
        for email in emails_with_values:
            value = self._extract_monetary_value(email.body_text)
            if value > 0:
                deal_values.append(value)
        
        if deal_values:
            insights["average_deal_size"] = sum(deal_values) / len(deal_values)
        
        # Calculate lost revenue from stalled deals
        stalled_deals = self._get_stalled_deals()
        insights["lost_revenue_potential"] = sum(d["value"] for d in stalled_deals)
        
        # Track product mentions
        products = self._extract_product_mentions(emails_with_values)
        insights["product_interest_signals"] = products
        
        return insights
    
    def get_ai_recommendations(self) -> List[Dict]:
        """Get AI-powered recommendations"""
        recommendations = []
        
        # Get recent emails for context
        recent_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.received_at >= datetime.utcnow() - timedelta(days=7),
            Email.deleted_at.is_(None)
        ).limit(50).all()
        
        for email in recent_emails:
            if self._requires_response(email):
                rec = {
                    "email_id": str(email.id),
                    "subject": email.subject,
                    "sender": email.sender_name or email.sender,
                    "next_actions": self._generate_next_actions(email),
                    "response_draft": self._generate_response_draft(email),
                    "risk_score": self._calculate_risk_score(email),
                    "optimal_timing": self._suggest_timing(email)
                }
                recommendations.append(rec)
        
        # Sort by importance
        recommendations.sort(key=lambda x: x["risk_score"], reverse=True)
        return recommendations[:10]
    
    # Helper methods
    def _group_by_thread(self, emails: List[Email]) -> Dict:
        """Group emails by conversation thread"""
        threads = defaultdict(list)
        for email in emails:
            # Simple threading by subject (remove Re: Fw: etc)
            clean_subject = re.sub(r'^(Re:|Fw:|Fwd:)\s*', '', email.subject, flags=re.IGNORECASE).strip()
            threads[clean_subject].append(email)
        return threads
    
    def _analyze_deal_thread(self, emails: List[Email]) -> Dict:
        """Analyze a thread of emails for deal information"""
        deal_info = {
            "thread_subject": emails[0].subject if emails else "",
            "participants": list(set(e.sender for e in emails)),
            "value": 0,
            "stage": "prospect",
            "urgency_score": 0,
            "last_activity": max(e.received_at for e in emails).isoformat() if emails else None
        }
        
        # Extract deal value
        for email in emails:
            value = self._extract_monetary_value(email.body_text or "")
            if value > deal_info["value"]:
                deal_info["value"] = value
        
        # Determine stage based on keywords
        all_text = " ".join(e.body_text or "" for e in emails if e.body_text)
        if "contract" in all_text.lower() or "agreement" in all_text.lower():
            deal_info["stage"] = "negotiation"
        elif "proposal" in all_text.lower() or "quote" in all_text.lower():
            deal_info["stage"] = "proposal"
        elif "interested" in all_text.lower() or "pricing" in all_text.lower():
            deal_info["stage"] = "qualified"
        
        # Calculate urgency
        urgency_keywords = ["urgent", "asap", "immediately", "deadline", "expires"]
        urgency_count = sum(1 for kw in urgency_keywords if kw in all_text.lower())
        deal_info["urgency_score"] = min(urgency_count / 3, 1.0)
        
        return deal_info
    
    def _score_opportunity(self, sender: str, emails: List[Email]) -> Dict:
        """Score an opportunity based on comprehensive context analysis"""
        opportunity = {
            "sender": sender,
            "sender_name": emails[0].sender_name if emails and emails[0].sender_name else sender,
            "score": 0,
            "type": "new",  # Will be set to "existing" if appropriate
            "temperature": "cold",  # Will be set to hot/warm/cold based on score
            "potential_value": 0,
            "last_interaction": max(e.received_at for e in emails).isoformat(),
            "email_count": len(emails),
            "signals": [],
            "context_factors": {},
            "sentiment": "neutral",
            "domain_type": "unknown"
        }

        # Determine if existing customer
        if len(emails) > 5:
            opportunity["type"] = "existing"
            opportunity["signals"].append("Frequent communication")

        # Collect all buying signals and monetary values
        all_text = ""
        for email in emails:
            body = email.body_text if email.body_text else ""
            all_text += body + " "

            signals = self._detect_buying_signals(body)
            opportunity["signals"].extend(signals)

            value = self._extract_monetary_value(body)
            if value > opportunity["potential_value"]:
                opportunity["potential_value"] = value

        # Calculate comprehensive context-heavy scoring
        days_since_last = (datetime.utcnow() - emails[-1].received_at).days

        # 1. Relationship Context (20%)
        relationship_score = self._calculate_relationship_context(emails, sender)

        # 2. Conversation Context (25%)
        conversation_score = self._calculate_conversation_context(emails, all_text, opportunity["signals"])

        # 3. Business Context (20%)
        business_score = self._calculate_business_context(emails, all_text, opportunity["potential_value"])

        # 4. Behavioral Context (15%)
        behavioral_score = self._calculate_behavioral_context(emails, sender)

        # 5. Buying Signals (15% - reduced from 40%)
        buying_signals_score = min(len(opportunity["signals"]) / 8, 1.0) * 0.15

        # 6. Recency (5% - reduced from 30%)
        recency_score = (1.0 - min(days_since_last / 30, 1.0)) * 0.05

        # Additional context factors
        opportunity["sentiment"] = self._analyze_sentiment(all_text)
        opportunity["has_competitive_mentions"] = self._detect_competitive_mentions(all_text)
        opportunity["referral_source"] = self._detect_referral_source(all_text)
        opportunity["domain_type"] = self._assess_domain_reputation(sender)

        # Compile score factors
        score_factors = {
            "relationship_context": relationship_score,
            "conversation_context": conversation_score,
            "business_context": business_score,
            "behavioral_context": behavioral_score,
            "buying_signals": buying_signals_score,
            "recency": recency_score
        }

        opportunity["context_factors"] = score_factors
        opportunity["score"] = sum(score_factors.values())

        # Classify temperature (Hot/Warm/Cold)
        if opportunity["score"] >= 0.65:
            opportunity["temperature"] = "hot"
        elif opportunity["score"] >= 0.40:
            opportunity["temperature"] = "warm"
        else:
            opportunity["temperature"] = "cold"

        # Enhanced debug logging
        logger.debug(f"Opportunity scoring for {sender} ({opportunity['type']}):")
        logger.debug(f"  Email count: {len(emails)}")
        logger.debug(f"  Signals detected ({len(opportunity['signals'])}): {opportunity['signals'][:5]}...")
        logger.debug(f"  Days since last email: {days_since_last}")
        logger.debug(f"  Sentiment: {opportunity['sentiment']}")
        logger.debug(f"  Domain type: {opportunity['domain_type']}")
        logger.debug(f"  Score breakdown:")
        logger.debug(f"    - Relationship Context (20%): {score_factors['relationship_context']:.3f}")
        logger.debug(f"    - Conversation Context (25%): {score_factors['conversation_context']:.3f}")
        logger.debug(f"    - Business Context (20%): {score_factors['business_context']:.3f}")
        logger.debug(f"    - Behavioral Context (15%): {score_factors['behavioral_context']:.3f}")
        logger.debug(f"    - Buying Signals (15%): {score_factors['buying_signals']:.3f}")
        logger.debug(f"    - Recency (5%): {score_factors['recency']:.3f}")
        logger.debug(f"  Total score: {opportunity['score']:.3f} - {opportunity['temperature'].upper()} {opportunity['type'].upper()}")
        logger.debug(f"  Status: {'INCLUDED' if opportunity['score'] > 0.25 else 'EXCLUDED - below threshold'}")

        return opportunity
    
    def _detect_buying_signals(self, text: str) -> List[str]:
        """Detect buying signals in email text"""
        signals = []
        buying_keywords = {
            # Strong buying signals
            "interested in": "Interest expressed",
            "looking for": "Active search",
            "need": "Need identified",
            "budget": "Budget discussion",
            "pricing": "Pricing inquiry",
            "proposal": "Proposal requested",
            "demo": "Demo requested",
            "trial": "Trial requested",
            "purchase": "Purchase intent",
            "contract": "Contract discussion",

            # Inquiry and research signals
            "inquiry": "Inquiry received",
            "inquire": "Inquiry received",
            "question": "Questions asked",
            "information": "Information requested",
            "details": "Details requested",
            "learn more": "Learning interest",
            "tell me more": "Learning interest",
            "find out": "Research phase",

            # Pricing and quotes
            "quote": "Quote requested",
            "quotation": "Quote requested",
            "estimate": "Estimate requested",
            "cost": "Cost inquiry",
            "price": "Price inquiry",
            "how much": "Price inquiry",

            # Service inquiries
            "services": "Service inquiry",
            "products": "Product inquiry",
            "offering": "Service inquiry",
            "solutions": "Solution search",
            "help": "Assistance needed",
            "assistance": "Assistance needed",
            "support": "Support inquiry",

            # Availability and timing
            "availability": "Availability check",
            "available": "Availability check",
            "schedule": "Scheduling interest",
            "meeting": "Meeting requested",
            "call": "Call requested",
            "discuss": "Discussion requested"
        }

        text_lower = text.lower()
        for keyword, signal in buying_keywords.items():
            if keyword in text_lower:
                signals.append(signal)

        return signals
    
    def _extract_monetary_value(self, text: str) -> float:
        """Extract monetary value from text"""
        if not text:
            return 0
            
        # Look for dollar amounts
        import re
        pattern = r'\$[\d,]+(?:\.\d{2})?|\b\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|dollars?)\b'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        if matches:
            # Extract numeric value from first match
            value_str = matches[0].replace('$', '').replace(',', '').replace('USD', '').replace('dollars', '').replace('dollar', '').strip()
            try:
                return float(value_str)
            except ValueError:
                return 0
        return 0

    def _calculate_relationship_context(self, emails: List[Email], sender: str) -> float:
        """Calculate relationship context score (20% weight)"""
        score = 0.0

        # 1. First-time vs repeat customer (0-0.05)
        if len(emails) == 1:
            score += 0.02  # New inquiry gets some base score
        elif len(emails) > 10:
            score += 0.05  # Strong relationship
        else:
            score += 0.03

        # 2. Email thread depth (0-0.08)
        # More back-and-forth = higher engagement
        thread_depth = len(emails)
        score += min(thread_depth / 20, 1.0) * 0.08

        # 3. Response pattern (0-0.07)
        # Check if they respond to our emails (indicates engagement)
        sent_count = len([e for e in emails if e.is_sent])
        received_count = len([e for e in emails if not e.is_sent])
        if sent_count > 0 and received_count > 0:
            response_ratio = min(received_count / max(sent_count, 1), 1.0)
            score += response_ratio * 0.07

        return min(score, 0.20)  # Cap at 20%

    def _calculate_conversation_context(self, emails: List[Email], all_text: str, signals: List[str]) -> float:
        """Calculate conversation context score (25% weight)"""
        score = 0.0

        # 1. Questions asked (0-0.08)
        question_marks = all_text.count('?')
        score += min(question_marks / 10, 1.0) * 0.08

        # 2. Detail level / message length (0-0.05)
        avg_length = len(all_text) / max(len(emails), 1)
        if avg_length > 500:  # Detailed messages
            score += 0.05
        elif avg_length > 200:  # Moderate detail
            score += 0.03
        else:  # Brief messages
            score += 0.01

        # 3. Multiple buying signals in one email (compound interest) (0-0.07)
        if len(signals) > 3:
            score += 0.07
        elif len(signals) > 1:
            score += 0.04

        # 4. Technical/specific product mentions (0-0.05)
        specific_keywords = ['feature', 'specification', 'integration', 'api', 'custom', 'requirement']
        specific_count = sum(1 for kw in specific_keywords if kw in all_text.lower())
        score += min(specific_count / 5, 1.0) * 0.05

        return min(score, 0.25)  # Cap at 25%

    def _calculate_business_context(self, emails: List[Email], all_text: str, potential_value: float) -> float:
        """Calculate business context score (20% weight)"""
        score = 0.0

        # 1. Company size indicators (0-0.05)
        size_keywords = {
            'enterprise': 0.05,
            'team of': 0.04,
            'employees': 0.04,
            'department': 0.03,
            'organization': 0.03,
            'company': 0.02
        }
        for keyword, points in size_keywords.items():
            if keyword in all_text.lower():
                score += points
                break

        # 2. Decision-maker signals (0-0.06)
        title_keywords = ['ceo', 'cto', 'cfo', 'director', 'vp', 'head of', 'manager', 'founder', 'owner', 'president']
        for keyword in title_keywords:
            if keyword in all_text.lower():
                score += 0.06
                break

        # 3. Budget/monetary value (0-0.05)
        if potential_value > 10000:
            score += 0.05
        elif potential_value > 5000:
            score += 0.04
        elif potential_value > 1000:
            score += 0.02

        # 4. Urgency/timeline indicators (0-0.04)
        urgency_keywords = ['urgent', 'asap', 'immediately', 'deadline', 'timeline', 'by when']
        urgency_count = sum(1 for kw in urgency_keywords if kw in all_text.lower())
        score += min(urgency_count / 3, 1.0) * 0.04

        return min(score, 0.20)  # Cap at 20%

    def _calculate_behavioral_context(self, emails: List[Email], sender: str) -> float:
        """Calculate behavioral context score (15% weight)"""
        score = 0.0

        # 1. Business hours activity (0-0.05)
        business_hours_count = 0
        for email in emails:
            hour = email.received_at.hour
            if 8 <= hour <= 18:  # 8am to 6pm
                business_hours_count += 1

        if len(emails) > 0:
            business_hours_ratio = business_hours_count / len(emails)
            score += business_hours_ratio * 0.05

        # 2. Response speed (0-0.05)
        # Check if they reply quickly (within 24 hours)
        quick_responses = 0
        for i in range(1, len(emails)):
            time_diff = (emails[i].received_at - emails[i-1].received_at).total_seconds() / 3600
            if time_diff < 24:  # Within 24 hours
                quick_responses += 1

        if len(emails) > 1:
            quick_response_ratio = quick_responses / (len(emails) - 1)
            score += quick_response_ratio * 0.05

        # 3. Consistent engagement pattern (0-0.05)
        # Regular communication over time indicates serious interest
        if len(emails) > 1:
            date_range = (emails[-1].received_at - emails[0].received_at).days
            if date_range > 7 and len(emails) > 3:  # Sustained over a week
                score += 0.05
            elif date_range > 2:
                score += 0.03

        return min(score, 0.15)  # Cap at 15%

    def _analyze_sentiment(self, text: str) -> str:
        """Analyze email sentiment (positive/neutral/negative)"""
        text_lower = text.lower()

        # Positive sentiment indicators
        positive_keywords = [
            'excited', 'great', 'excellent', 'perfect', 'love', 'impressive',
            'fantastic', 'wonderful', 'amazing', 'interested', 'look forward',
            'thank you', 'appreciate', 'glad', 'happy', 'pleased'
        ]

        # Negative sentiment indicators
        negative_keywords = [
            'concerned', 'disappointed', 'unfortunately', 'problem', 'issue',
            'difficult', 'frustrated', 'worried', 'unhappy', 'not satisfied'
        ]

        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)

        if positive_count > negative_count and positive_count > 0:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"

    def _detect_competitive_mentions(self, text: str) -> bool:
        """Detect if they're comparing to competitors"""
        text_lower = text.lower()
        competitive_keywords = [
            'competitor', 'alternative', 'compared to', 'vs', 'versus',
            'other options', 'shopping around', 'evaluating', 'comparing'
        ]
        return any(kw in text_lower for kw in competitive_keywords)

    def _detect_referral_source(self, text: str) -> str:
        """Detect if they mentioned how they found you"""
        text_lower = text.lower()

        referral_patterns = {
            'referral': ['referred by', 'recommended by', 'suggested by', 'told me about'],
            'search': ['found you on google', 'searched for', 'found online'],
            'social': ['saw on linkedin', 'facebook', 'twitter', 'social media'],
            'event': ['met you at', 'conference', 'event', 'trade show'],
            'website': ['found your website', 'visited your site', 'saw your website']
        }

        for source, patterns in referral_patterns.items():
            if any(pattern in text_lower for pattern in patterns):
                return source

        return "unknown"

    def _assess_domain_reputation(self, sender: str) -> str:
        """Assess email domain quality"""
        if '@' not in sender:
            return "unknown"

        domain = sender.split('@')[1].lower()

        # Free email providers (lower quality for B2B)
        free_providers = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com']
        if domain in free_providers:
            return "personal"

        # Known business domains
        business_indicators = ['.com', '.net', '.org', '.io', '.co']
        if any(domain.endswith(indicator) for indicator in business_indicators):
            return "business"

        return "unknown"

    def _has_response(self, email: Email) -> bool:
        """Check if an email received a response"""
        # Look for emails with similar subject that came after this one
        # Since we don't have email.recipient, we'll check for replies by subject pattern
        response = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.subject.ilike(f"%{email.subject}%"),
            Email.received_at > email.received_at,
            Email.received_at < email.received_at + timedelta(days=7)
        ).first()
        return response is not None
    
    def _requires_response(self, email: Email) -> bool:
        """Check if an email requires a response"""
        if not email.body_text:
            return False
            
        # Check for question marks
        if "?" in email.body_text:
            return True
            
        # Check for request keywords
        request_keywords = ["please", "could you", "would you", "can you", "need", "require", "request"]
        body_lower = email.body_text.lower()
        return any(kw in body_lower for kw in request_keywords)
    
    def _calculate_priority(self, email: Email) -> float:
        """Calculate priority score for an email"""
        priority = 0.5  # Base priority
        
        # Increase for questions
        if email.body_text and "?" in email.body_text:
            priority += 0.2
            
        # Increase for urgency keywords
        if email.body_text:
            urgency_keywords = ["urgent", "asap", "immediately", "critical", "important"]
            if any(kw in email.body_text.lower() for kw in urgency_keywords):
                priority += 0.3
        
        # Increase based on sender importance (simplified)
        if email.sender and any(domain in email.sender for domain in ["ceo", "president", "director"]):
            priority += 0.2
            
        # Decrease for older emails
        days_old = (datetime.utcnow() - email.received_at).days
        priority -= (days_old * 0.05)
        
        return max(0, min(1, priority))
    
    def _suggest_action(self, email: Email) -> str:
        """Suggest an action for an email"""
        if not email.body_text:
            return "Review and respond"
            
        body_lower = email.body_text.lower()
        
        if "meeting" in body_lower or "call" in body_lower:
            return "Schedule meeting"
        elif "proposal" in body_lower or "quote" in body_lower:
            return "Send proposal"
        elif "?" in email.body_text:
            return "Answer questions"
        elif "interested" in body_lower:
            return "Send product information"
        else:
            return "Send follow-up"
    
    def _estimate_value(self, email: Email) -> float:
        """Estimate potential value of an email/opportunity"""
        if not email.body_text:
            return 0
            
        # Try to extract monetary value
        value = self._extract_monetary_value(email.body_text)
        if value > 0:
            return value
            
        # Estimate based on keywords (simplified)
        high_value_keywords = ["enterprise", "corporate", "bulk", "annual", "contract"]
        if any(kw in email.body_text.lower() for kw in high_value_keywords):
            return 50000  # High value estimate
            
        return 5000  # Default estimate
    
    def _get_time_sensitive_actions(self) -> List[Dict]:
        """Get time-sensitive actions like expiring quotes"""
        actions = []
        
        # Look for emails with expiration mentions
        expiration_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.deleted_at.is_(None),
            or_(
                Email.body_text.ilike("%expire%"),
                Email.body_text.ilike("%deadline%"),
                Email.body_text.ilike("%valid until%")
            )
        ).limit(10).all()
        
        for email in expiration_emails:
            actions.append({
                "id": str(email.id),
                "type": "expiring_quote",
                "subject": email.subject,
                "sender": email.sender_name or email.sender,
                "received": email.received_at.isoformat(),
                "priority_score": 0.9,
                "suggested_action": "Review and act on expiring item",
                "potential_value": self._estimate_value(email)
            })
        
        return actions
    
    def _assess_risk_level(self, email: Email) -> float:
        """Assess risk level of losing a customer/deal"""
        if not email.body_text:
            return 0
            
        risk_score = 0
        body_lower = email.body_text.lower()
        
        # High risk keywords
        high_risk = ["cancel", "terminate", "switch", "competitor", "unhappy", "disappointed"]
        risk_score += sum(0.2 for kw in high_risk if kw in body_lower)
        
        # Medium risk keywords
        medium_risk = ["concern", "issue", "problem", "alternative", "options"]
        risk_score += sum(0.1 for kw in medium_risk if kw in body_lower)
        
        return min(risk_score, 1.0)
    
    def _identify_issue(self, email: Email) -> str:
        """Identify the main issue in a risk email"""
        if not email.body_text:
            return "Unknown issue"
            
        body_lower = email.body_text.lower()
        
        if "price" in body_lower or "cost" in body_lower or "expensive" in body_lower:
            return "Price objection"
        elif "support" in body_lower or "help" in body_lower:
            return "Support issue"
        elif "feature" in body_lower or "functionality" in body_lower:
            return "Feature gap"
        elif "competitor" in body_lower:
            return "Competitive threat"
        else:
            return "General concern"
    
    def _recommend_retention_action(self, email: Email) -> str:
        """Recommend action to retain at-risk customer"""
        issue = self._identify_issue(email)
        
        if "Price" in issue:
            return "Offer discount or payment plan"
        elif "Support" in issue:
            return "Schedule immediate support call"
        elif "Feature" in issue:
            return "Demo additional features or roadmap"
        elif "Competitive" in issue:
            return "Highlight unique value proposition"
        else:
            return "Schedule retention call with decision maker"
    
    def _get_vip_domains(self) -> List[str]:
        """Get list of VIP domains (simplified)"""
        # In production, this would come from user configuration
        return ["ceo", "president", "director", "vp", "chief", "founder"]
    
    def _get_response_templates(self) -> List[Dict]:
        """Get response templates"""
        return [
            {
                "name": "Initial Interest",
                "template": "Thank you for your interest in our products/services. I'd be happy to discuss how we can help you achieve your goals. When would be a good time for a brief call?"
            },
            {
                "name": "Follow Up",
                "template": "I wanted to follow up on my previous email regarding [topic]. Have you had a chance to review the information? I'm available to answer any questions."
            },
            {
                "name": "Proposal Follow Up",
                "template": "I'm following up on the proposal I sent on [date]. Do you have any questions about the pricing or implementation timeline? I'm here to help make this work for your team."
            }
        ]
    
    def _get_bulk_action_suggestions(self) -> List[Dict]:
        """Get bulk action suggestions"""
        return [
            {
                "action": "Follow up on all stalled deals",
                "count": 0,  # Would be calculated
                "potential_recovery": 0
            },
            {
                "action": "Send renewal reminders",
                "count": 0,
                "potential_value": 0
            }
        ]
    
    def _get_optimal_send_times(self) -> Dict:
        """Get optimal send times"""
        return {
            "best_day": "Tuesday",
            "best_hour": 10,
            "timezone": "EST",
            "confidence": 0.75
        }
    
    def _get_saved_responses(self) -> List[Dict]:
        """Get saved response templates"""
        # In production, these would be stored in database
        return []
    
    def _get_stalled_deals(self) -> List[Dict]:
        """Get stalled deals"""
        stalled = []
        
        # Look for emails with deal indicators that haven't had recent activity
        deal_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.deleted_at.is_(None),
            or_(
                Email.body_text.ilike("%proposal%"),
                Email.body_text.ilike("%quote%"),
                Email.body_text.ilike("%contract%")
            ),
            Email.received_at < datetime.utcnow() - timedelta(days=7)
        ).all()
        
        for email in deal_emails:
            value = self._estimate_value(email)
            if value > 0:
                stalled.append({
                    "email_id": str(email.id),
                    "subject": email.subject,
                    "value": value,
                    "days_stalled": (datetime.utcnow() - email.received_at).days
                })
        
        return stalled
    
    def _extract_product_mentions(self, emails: List[Email]) -> List[Dict]:
        """Extract product mentions from emails"""
        products = defaultdict(int)
        
        # Simple keyword extraction (in production, would use NLP)
        product_keywords = ["product", "service", "solution", "platform", "software", "tool"]
        
        for email in emails:
            if email.body_text:
                for keyword in product_keywords:
                    if keyword in email.body_text.lower():
                        products[keyword] += 1
        
        return [{"product": k, "mentions": v} for k, v in products.items()]
    
    def _generate_next_actions(self, email: Email) -> List[Dict]:
        """Generate next action recommendations"""
        actions = []
        
        if self._requires_response(email):
            actions.append({
                "action": "Send response",
                "priority": "high",
                "estimated_time": "5 minutes"
            })
        
        if email.body_text and "meeting" in email.body_text.lower():
            actions.append({
                "action": "Schedule meeting",
                "priority": "medium",
                "estimated_time": "2 minutes"
            })
        
        return actions
    
    def _generate_response_draft(self, email: Email) -> str:
        """Generate a response draft (simplified)"""
        if not email.body_text:
            return ""
            
        if "?" in email.body_text:
            return "Thank you for your question. [Answer their specific question here]. Please let me know if you need any additional information."
        elif "meeting" in email.body_text.lower():
            return "I'd be happy to meet. Here are a few times that work for me: [Insert availability]. Please let me know what works best for you."
        else:
            return "Thank you for your email. I've reviewed your message and [insert response]. Please feel free to reach out if you have any questions."
    
    def _calculate_risk_score(self, email: Email) -> float:
        """Calculate risk score for a deal/opportunity"""
        risk = 0.3  # Base risk
        
        # Increase risk for older emails
        days_old = (datetime.utcnow() - email.received_at).days
        risk += min(days_old * 0.05, 0.4)
        
        # Check for risk keywords
        if email.body_text:
            risk_keywords = ["concern", "issue", "problem", "competitor", "alternative"]
            if any(kw in email.body_text.lower() for kw in risk_keywords):
                risk += 0.3
        
        return min(risk, 1.0)
    
    def _suggest_timing(self, email: Email) -> Dict:
        """Suggest optimal timing for response"""
        # Simplified - in production would analyze recipient's response patterns
        return {
            "send_within": "24 hours",
            "best_time": "10:00 AM",
            "day": "Tomorrow",
            "reasoning": "Based on typical response patterns"
        }
    
    def get_client_followup_sequences(self) -> List[Dict]:
        """Get client follow-up sequences with AI-powered nudges"""
        sequences = []
        
        # Get all unique client conversations
        client_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.deleted_at.is_(None),
            Email.received_at >= datetime.utcnow() - timedelta(days=30)
        ).all()
        
        # Group by sender
        client_threads = defaultdict(list)
        for email in client_emails:
            client_threads[email.sender].append(email)
        
        for sender, emails in client_threads.items():
            # Sort emails by date
            emails.sort(key=lambda x: x.received_at)
            
            # Check if client hasn't responded recently
            last_email = emails[-1]
            days_since_last = (datetime.utcnow() - last_email.received_at).days
            
            if days_since_last >= 3:  # No response for 3+ days
                # Analyze conversation tone and context
                conversation_tone = self._analyze_conversation_tone(emails)
                conversation_stage = self._identify_conversation_stage(emails)
                
                sequence = {
                    "client": sender,
                    "client_name": emails[0].sender_name or sender,
                    "last_contact": last_email.received_at.isoformat(),
                    "days_silent": days_since_last,
                    "conversation_stage": conversation_stage,
                    "tone": conversation_tone,
                    "follow_ups": self._generate_followup_sequence(
                        emails, days_since_last, conversation_tone, conversation_stage
                    ),
                    "priority": self._calculate_followup_priority(emails, days_since_last),
                    "potential_value": self._estimate_value(last_email),
                    "risk_of_loss": min(days_since_last * 0.1, 1.0)
                }
                sequences.append(sequence)
        
        # Sort by priority
        sequences.sort(key=lambda x: x["priority"], reverse=True)
        return sequences[:20]  # Return top 20
    
    def _analyze_conversation_tone(self, emails: List[Email]) -> str:
        """Analyze the tone of a conversation"""
        if not emails:
            return "neutral"
        
        # Analyze recent emails for tone indicators
        recent_text = " ".join(e.body_text or "" for e in emails[-3:])
        recent_lower = recent_text.lower()
        
        # Positive indicators
        positive_words = ["excited", "looking forward", "great", "excellent", "perfect", "thank you"]
        positive_count = sum(1 for word in positive_words if word in recent_lower)
        
        # Negative indicators
        negative_words = ["concern", "worried", "disappointed", "issue", "problem", "unfortunately"]
        negative_count = sum(1 for word in negative_words if word in recent_lower)
        
        # Formal indicators
        formal_words = ["regards", "sincerely", "respectfully", "kindly", "please advise"]
        formal_count = sum(1 for word in formal_words if word in recent_lower)
        
        if positive_count > negative_count:
            return "positive" if positive_count >= 2 else "friendly"
        elif negative_count > positive_count:
            return "concerned" if negative_count >= 2 else "cautious"
        elif formal_count >= 2:
            return "formal"
        else:
            return "neutral"
    
    def _identify_conversation_stage(self, emails: List[Email]) -> str:
        """Identify what stage the conversation is at"""
        all_text = " ".join(e.body_text or "" for e in emails).lower()
        
        if "contract" in all_text or "agreement" in all_text:
            return "negotiation"
        elif "proposal" in all_text or "quote" in all_text:
            return "proposal"
        elif "demo" in all_text or "trial" in all_text:
            return "evaluation"
        elif "interested" in all_text or "more information" in all_text:
            return "discovery"
        elif len(emails) <= 2:
            return "initial_contact"
        else:
            return "ongoing_discussion"
    
    def _generate_followup_sequence(self, emails: List[Email], days_silent: int, 
                                   tone: str, stage: str) -> List[Dict]:
        """Generate a sequence of follow-up messages"""
        sequence = []
        
        # First follow-up (3-5 days)
        if days_silent >= 3 and days_silent < 7:
            sequence.append({
                "day": 0,
                "type": "gentle_nudge",
                "subject": f"Re: {emails[-1].subject}",
                "message": self._generate_nudge_message(tone, stage, "first"),
                "send_time": "10:00 AM",
                "auto_send": False
            })
        
        # Second follow-up (7-10 days)
        if days_silent >= 7 and days_silent < 14:
            sequence.append({
                "day": 3,
                "type": "value_reminder",
                "subject": f"Quick question about {emails[-1].subject}",
                "message": self._generate_nudge_message(tone, stage, "second"),
                "send_time": "2:00 PM",
                "auto_send": False
            })
        
        # Third follow-up (14+ days)
        if days_silent >= 14:
            sequence.append({
                "day": 7,
                "type": "final_attempt",
                "subject": "Should we close this loop?",
                "message": self._generate_nudge_message(tone, stage, "final"),
                "send_time": "11:00 AM",
                "auto_send": False
            })
        
        return sequence
    
    def _generate_nudge_message(self, tone: str, stage: str, attempt: str) -> str:
        """Generate personalized nudge message based on context"""
        templates = {
            "positive": {
                "first": "Hi there! I wanted to check in on our discussion about [topic]. I know you were excited about [benefit]. Any thoughts or questions I can help with?",
                "second": "Hope you're having a great week! Just circling back on [topic]. I've prepared some additional insights that might be helpful. Should we schedule a quick call?",
                "final": "I understand priorities shift! If now isn't the right time for [solution], no worries at all. Should I check back in a few months, or is there a better timeline?"
            },
            "formal": {
                "first": "I hope this message finds you well. I wanted to follow up on our previous correspondence regarding [topic]. Please let me know if you require any additional information.",
                "second": "Following up on my previous email. I understand you have many priorities. Would it be helpful if I provided a brief summary of our discussion and next steps?",
                "final": "I wanted to ensure my previous messages reached you. If this is no longer a priority, I completely understand. Please let me know either way so I can update my records accordingly."
            },
            "concerned": {
                "first": "Hi [Name], I noticed you had some concerns about [issue]. I've been thinking about your situation and have a few ideas that might help. Would you like to discuss?",
                "second": "I've been reflecting on your concerns about [issue]. I've worked with similar situations and found [solution approach] to be effective. Worth a quick chat?",
                "final": "I understand there were some reservations about moving forward. If those concerns still exist, I'm happy to address them. Otherwise, should we revisit this in the future?"
            },
            "neutral": {
                "first": "Hi [Name], just wanted to touch base on our discussion. Are you still exploring options for [topic]? Happy to answer any questions!",
                "second": "Following up on [topic]. I have some new information that might be relevant to your decision. Should we connect this week?",
                "final": "Hi [Name], I'll keep this brief - should we continue our discussion about [topic], or would you prefer I check back at a later date?"
            }
        }
        
        # Get appropriate template
        tone_templates = templates.get(tone, templates["neutral"])
        return tone_templates.get(attempt, tone_templates["first"])
    
    def _calculate_followup_priority(self, emails: List[Email], days_silent: int) -> float:
        """Calculate priority for follow-up"""
        priority = 0.5
        
        # Increase priority based on conversation value
        for email in emails:
            value = self._extract_monetary_value(email.body_text or "")
            if value > 10000:
                priority += 0.3
            elif value > 1000:
                priority += 0.1
        
        # Increase priority based on stage
        stage = self._identify_conversation_stage(emails)
        if stage == "negotiation":
            priority += 0.4
        elif stage == "proposal":
            priority += 0.3
        elif stage == "evaluation":
            priority += 0.2
        
        # Adjust based on silence duration
        if days_silent >= 7 and days_silent < 14:
            priority += 0.2  # Sweet spot for follow-up
        elif days_silent >= 14:
            priority -= 0.1  # May be too late
        
        return min(priority, 1.0)
    
    def generate_proposals(self, template_id: Optional[str] = None) -> Dict:
        """Generate comprehensive sales proposals using sales intelligence"""
        proposals = []

        # Get business profile for company info
        profile = self.get_business_profile()

        # Handle case where profile might be a string or None
        if isinstance(profile, str) or profile is None:
            business_info = {}
        else:
            profile_data = profile.get("profile", {})
            business_info = profile_data if isinstance(profile_data, dict) else {}

        # Get active opportunities
        opportunities = self.get_opportunity_scores()[:10]  # Top 10 opportunities

        for opp in opportunities:
            # Ensure opp is a dict
            if not isinstance(opp, dict):
                continue

            if opp.get("score", 0) > 0.4:  # Include warm+ leads
                # Get all emails for this opportunity
                opp_emails = self.db.query(Email).filter(
                    Email.user_id == self.user.id,
                    Email.sender == opp["sender"],
                    Email.deleted_at.is_(None)
                ).order_by(Email.received_at.desc()).limit(20).all()

                if not opp_emails:
                    continue

                # Use sales intelligence for deeper analysis
                all_text = " ".join(e.body_text or "" for e in opp_emails)

                # Convert Email objects to dicts for sales_analyzer methods that expect List[Dict]
                email_dicts = [
                    {"body_text": e.body_text or "", "body_html": e.body_html or ""}
                    for e in opp_emails
                ]

                # BANT Analysis
                bant_result = sales_analyzer.analyze_lead_quality(all_text, opp["sender"])

                # Objection Detection
                objections = sales_analyzer.detect_objections(all_text)

                # Conversation Stage - pass email_dicts (List[Dict]), not all_text (str)
                stage_result = sales_analyzer.detect_conversation_stage(email_dicts)

                # Extract enhanced client info
                client_info = self._extract_enhanced_client_info(opp_emails, bant_result)

                # Extract requirements with AI analysis
                requirements = self._extract_enhanced_requirements(opp_emails)

                # Generate tailored solution
                solution = self._generate_tailored_solution(requirements, client_info, stage_result.stage.value)

                # Generate smart pricing based on BANT
                pricing = self._generate_smart_pricing(requirements, opp.get("potential_value", 0), bant_result)

                # Build comprehensive proposal
                proposal = {
                    "id": f"prop_{opp['sender'][:8]}_{datetime.utcnow().strftime('%Y%m%d%H%M')}",
                    "client": opp["sender_name"] or opp["sender"].split("@")[0].title(),
                    "client_email": opp["sender"],
                    "opportunity_score": opp["score"],
                    "conversation_stage": stage_result.stage.value,
                    "bant_score": bant_result.bant_score.total,
                    "bant_details": {
                        "budget": bant_result.bant_score.budget,
                        "authority": bant_result.bant_score.authority,
                        "need": bant_result.bant_score.need,
                        "timeline": bant_result.bant_score.timeline
                    },
                    "client_info": client_info,
                    "requirements": requirements,
                    "objections_detected": [
                        {"type": obj.type.value, "text": obj.exact_quote[:100] if obj.exact_quote else ""}
                        for obj in objections[:3]
                    ],
                    "proposed_solution": solution,
                    "pricing": pricing,
                    "timeline": self._generate_timeline(requirements),
                    "terms": self._generate_terms(),
                    "template_used": template_id or "default",
                    "created_at": datetime.utcnow().isoformat(),
                    "valid_until": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                    "status": "draft",
                    "pdf_url": None,
                    "html_preview": self._generate_comprehensive_proposal_html(
                        client_info, requirements, solution, pricing, opp, bant_result, business_info
                    )
                }
                proposals.append(proposal)

        return {
            "proposals": proposals,
            "templates": self._get_proposal_templates(),
            "recent_wins": self._get_recent_wins(),
            "stats": {
                "total_generated": len(proposals),
                "avg_bant_score": sum(p["bant_score"] for p in proposals) / len(proposals) if proposals else 0,
                "total_potential_value": sum(p["pricing"]["base_price"] for p in proposals)
            }
        }

    def _extract_enhanced_client_info(self, emails: List[Email], bant_result) -> Dict:
        """Extract comprehensive client information using BANT analysis"""
        info = {
            "company": "",
            "contact_name": "",
            "industry": "",
            "company_size": "",
            "pain_points": [],
            "goals": [],
            "budget_range": "",
            "decision_timeline": "",
            "decision_makers": [],
            "current_solution": "",
            "urgency_level": "medium"
        }

        all_text = " ".join(e.body_text or "" for e in emails)

        # Extract company from email domain
        if emails and "@" in emails[0].sender:
            domain = emails[0].sender.split("@")[1]
            info["company"] = domain.split(".")[0].replace("-", " ").title()

        # Extract contact name from sender
        if emails and emails[0].sender_name:
            info["contact_name"] = emails[0].sender_name

        # Industry detection
        industries = {
            "Technology": ["software", "tech", "saas", "platform", "app", "digital", "IT", "cloud"],
            "Financial Services": ["financial", "banking", "investment", "fund", "insurance", "fintech"],
            "Healthcare": ["medical", "health", "hospital", "clinic", "pharma", "patient"],
            "E-commerce/Retail": ["store", "shop", "retail", "commerce", "e-commerce", "shopping"],
            "Manufacturing": ["manufacture", "production", "factory", "supply chain", "industrial"],
            "Professional Services": ["consulting", "legal", "accounting", "agency", "marketing"],
            "Education": ["education", "school", "university", "training", "learning", "academic"],
            "Real Estate": ["property", "real estate", "construction", "building", "development"]
        }

        text_lower = all_text.lower()
        for industry, keywords in industries.items():
            if any(kw in text_lower for kw in keywords):
                info["industry"] = industry
                break

        # Extract pain points (more comprehensive)
        pain_patterns = [
            r"(?:we|our|my)\s+(?:team|company|organization)?\s*(?:is|are|have been)?\s*(?:struggling|challenged|having trouble|facing issues?)\s+(?:with|to)\s+([^.]+)",
            r"(?:the|our|my)\s+(?:problem|challenge|issue|difficulty)\s+(?:is|with)\s+([^.]+)",
            r"we\s+need\s+(?:to\s+)?(?:improve|fix|solve|address)\s+([^.]+)",
            r"(?:pain point|bottleneck|roadblock)\s*(?:is|:)?\s*([^.]+)"
        ]

        for pattern in pain_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches[:3]:
                if len(match) > 10:
                    info["pain_points"].append(match.strip().capitalize()[:150])

        # Extract goals
        goal_patterns = [
            r"(?:we|our)\s+(?:want|goal|aim|objective)\s+(?:is\s+)?(?:to\s+)?([^.]+)",
            r"(?:looking|hoping|trying)\s+to\s+([^.]+)",
            r"(?:need|require|must)\s+(?:to\s+)?(?:achieve|accomplish|reach)\s+([^.]+)"
        ]

        for pattern in goal_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches[:3]:
                if len(match) > 10:
                    info["goals"].append(match.strip().capitalize()[:150])

        # Budget from BANT
        if bant_result.bant_score.budget >= 70:
            value = self._extract_monetary_value(all_text)
            if value > 100000:
                info["budget_range"] = "$100,000+"
            elif value > 50000:
                info["budget_range"] = "$50,000 - $100,000"
            elif value > 25000:
                info["budget_range"] = "$25,000 - $50,000"
            elif value > 10000:
                info["budget_range"] = "$10,000 - $25,000"
            else:
                info["budget_range"] = "Under $10,000"
        else:
            info["budget_range"] = "To be discussed"

        # Timeline from BANT
        if bant_result.bant_score.timeline >= 70:
            timeline_patterns = [
                r"(?:by|before|within)\s+(Q[1-4]|next\s+(?:week|month|quarter)|end\s+of\s+(?:month|year))",
                r"(?:deadline|timeline)\s*(?:is|:)?\s*([^.]+)",
                r"need\s+(?:this|it)\s+(?:by|before)\s+([^.]+)"
            ]
            for pattern in timeline_patterns:
                match = re.search(pattern, all_text, re.IGNORECASE)
                if match:
                    info["decision_timeline"] = match.group(1).strip()
                    break

        # Urgency level
        if bant_result.bant_score.timeline >= 80 or "urgent" in text_lower or "asap" in text_lower:
            info["urgency_level"] = "high"
        elif bant_result.bant_score.timeline >= 50:
            info["urgency_level"] = "medium"
        else:
            info["urgency_level"] = "low"

        return info

    def _extract_enhanced_requirements(self, emails: List[Email]) -> List[Dict]:
        """Extract detailed requirements from email conversations"""
        requirements = []
        all_text = " ".join(e.body_text or "" for e in emails)

        # Requirement patterns
        req_patterns = [
            (r"(?:we|I)\s+(?:need|require|want|must have)\s+([^.]+)", "high"),
            (r"(?:looking for|searching for)\s+([^.]+)", "medium"),
            (r"(?:would be nice|would like|prefer)\s+(?:to have\s+)?([^.]+)", "low"),
            (r"(?:essential|critical|important)\s+(?:that|to have)\s+([^.]+)", "high"),
            (r"(?:feature|functionality|capability)\s+(?:for|to)\s+([^.]+)", "medium")
        ]

        seen = set()
        for pattern, priority in req_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            for match in matches:
                clean = match.strip()[:200]
                if len(clean) > 15 and clean.lower() not in seen:
                    seen.add(clean.lower())
                    requirements.append({
                        "description": clean.capitalize(),
                        "priority": priority,
                        "category": self._categorize_requirement(clean),
                        "addressed": True  # We'll address all requirements
                    })

        # If no requirements found, create generic ones from pain points
        if not requirements:
            requirements = [
                {"description": "Improve operational efficiency", "priority": "high", "category": "performance", "addressed": True},
                {"description": "Streamline current workflows", "priority": "medium", "category": "feature", "addressed": True},
                {"description": "Better reporting and analytics", "priority": "medium", "category": "feature", "addressed": True}
            ]

        return requirements[:8]  # Limit to 8 requirements

    def _generate_tailored_solution(self, requirements: List[Dict], client_info: Dict, stage: str) -> Dict:
        """Generate a tailored solution based on requirements and conversation stage"""

        # Group requirements by category
        categories = defaultdict(list)
        for req in requirements:
            categories[req["category"]].append(req)

        # Build solution components
        components = []
        for category, reqs in categories.items():
            component = {
                "name": self._get_component_name(category),
                "description": f"Addresses your {category} requirements",
                "features": [],
                "requirements_addressed": [r["description"][:80] for r in reqs[:3]]
            }

            # Add specific features based on category
            feature_map = {
                "feature": ["Custom dashboard", "Advanced analytics", "Automated workflows", "Real-time notifications"],
                "integration": ["API access", "Third-party connectors", "Data sync", "Webhook support"],
                "performance": ["High availability (99.9% uptime)", "Auto-scaling", "Performance monitoring", "Load balancing"],
                "support": ["24/7 technical support", "Dedicated account manager", "Training sessions", "Documentation portal"],
                "security": ["Enterprise-grade security", "SOC 2 compliance", "Data encryption", "Role-based access"],
                "customization": ["White-label options", "Custom branding", "Configurable workflows", "Flexible reporting"],
                "general": ["Core platform features", "User management", "Reporting tools", "Mobile access"]
            }

            component["features"] = feature_map.get(category, feature_map["general"])[:4]
            components.append(component)

        # Tailor messaging based on stage
        stage_messaging = {
            "cold_outreach": "We're excited to introduce our solution that can help transform your business.",
            "engaged": "Based on our conversations, we've identified the perfect solution for your needs.",
            "discovery": "After understanding your requirements, we've crafted a tailored solution.",
            "evaluation": "We've refined our proposal based on your evaluation criteria.",
            "proposal": "This comprehensive solution addresses all your documented requirements.",
            "negotiation": "We've optimized this solution to provide maximum value within your parameters.",
            "closing": "This final proposal reflects all our discussions and your specific needs."
        }

        return {
            "overview": stage_messaging.get(stage, stage_messaging["engaged"]),
            "value_proposition": f"Help {client_info.get('company', 'your organization')} achieve its goals through our proven solution.",
            "components": components,
            "benefits": [
                f"Address {len(requirements)} specific requirements",
                "Increase efficiency by 30-50%",
                "Reduce operational costs by 20%",
                "Improve team productivity",
                "Scalable for future growth"
            ],
            "differentiators": [
                "Proven track record with similar companies",
                "Industry-leading technology",
                "Dedicated implementation team",
                "Flexible deployment options",
                "Continuous innovation and updates"
            ],
            "success_metrics": [
                "Time to value: 4-6 weeks",
                "ROI typically seen within 6 months",
                "95%+ customer satisfaction rate",
                "99.9% platform uptime"
            ]
        }

    def _get_component_name(self, category: str) -> str:
        """Get a professional component name for a category"""
        names = {
            "feature": "Core Platform Module",
            "integration": "Integration Suite",
            "performance": "Performance & Reliability Package",
            "support": "Premium Support Services",
            "security": "Security & Compliance Module",
            "customization": "Customization Package",
            "general": "Essential Services"
        }
        return names.get(category, "Additional Services")

    def _generate_smart_pricing(self, requirements: List[Dict], estimated_value: float, bant_result) -> Dict:
        """Generate intelligent pricing based on BANT and requirements"""

        # Base price calculation
        if estimated_value > 0:
            base_price = estimated_value
        else:
            # Calculate based on requirements complexity
            base_price = 15000
            high_priority = len([r for r in requirements if r["priority"] == "high"])
            base_price += high_priority * 5000
            base_price += len(requirements) * 1500

        # Adjust based on BANT budget signals
        if bant_result.bant_score.budget >= 80:
            base_price *= 1.2  # They have budget, price accordingly
        elif bant_result.bant_score.budget < 40:
            base_price *= 0.8  # Be more competitive

        # Round to nice numbers
        base_price = round(base_price / 1000) * 1000

        return {
            "model": "subscription" if base_price < 50000 else "license + subscription",
            "base_price": base_price,
            "currency": "USD",
            "options": [
                {
                    "name": "Starter",
                    "price": round(base_price * 0.6 / 100) * 100,
                    "billing": "per month" if base_price < 50000 else "one-time",
                    "features": [
                        "Core features",
                        "Up to 5 users",
                        "Email support",
                        "Monthly updates",
                        "Basic reporting"
                    ],
                    "recommended": False,
                    "best_for": "Small teams getting started"
                },
                {
                    "name": "Professional",
                    "price": base_price,
                    "billing": "per month" if base_price < 50000 else "one-time",
                    "features": [
                        "All Starter features",
                        "Unlimited users",
                        "Priority support",
                        "API access",
                        "Advanced reporting",
                        "Custom integrations",
                        "Dedicated success manager"
                    ],
                    "recommended": True,
                    "best_for": "Growing businesses with complex needs"
                },
                {
                    "name": "Enterprise",
                    "price": round(base_price * 1.8 / 100) * 100,
                    "billing": "per month" if base_price < 50000 else "one-time + maintenance",
                    "features": [
                        "All Professional features",
                        "Custom development",
                        "White-label options",
                        "SLA guarantee (99.9%)",
                        "24/7 phone support",
                        "On-site training",
                        "Quarterly business reviews"
                    ],
                    "recommended": False,
                    "best_for": "Large organizations requiring full customization"
                }
            ],
            "discounts": [
                {"type": "Early Decision", "amount": "10%", "condition": "Sign within 14 days"},
                {"type": "Annual Commitment", "amount": "15%", "condition": "Pay annually upfront"},
                {"type": "Multi-year", "amount": "20%", "condition": "3-year commitment"}
            ],
            "payment_terms": "Net 30",
            "includes": [
                "Implementation and setup",
                "Data migration assistance",
                "Initial training (8 hours)",
                "30-day money-back guarantee"
            ]
        }
    
    def _extract_client_info(self, emails: List[Email]) -> Dict:
        """Extract client information from emails"""
        info = {
            "company": "",
            "industry": "",
            "size": "",
            "pain_points": [],
            "budget_range": "",
            "decision_timeline": ""
        }
        
        all_text = " ".join(e.body_text or "" for e in emails)
        
        # Extract company name (simplified - would use NER in production)
        if "@" in emails[0].sender:
            domain = emails[0].sender.split("@")[1]
            info["company"] = domain.split(".")[0].title()
        
        # Detect industry keywords
        industries = {
            "technology": ["software", "tech", "saas", "platform"],
            "finance": ["financial", "banking", "investment", "fund"],
            "healthcare": ["medical", "health", "hospital", "clinic"],
            "retail": ["store", "shop", "retail", "commerce"],
            "manufacturing": ["manufacture", "production", "factory", "supply chain"]
        }
        
        for industry, keywords in industries.items():
            if any(kw in all_text.lower() for kw in keywords):
                info["industry"] = industry
                break
        
        # Extract pain points
        pain_keywords = ["challenge", "problem", "issue", "struggle", "difficult", "need"]
        for keyword in pain_keywords:
            if keyword in all_text.lower():
                # Extract sentence containing keyword (simplified)
                sentences = all_text.split(".")
                for sentence in sentences:
                    if keyword in sentence.lower():
                        info["pain_points"].append(sentence.strip()[:100])
                        break
        
        # Extract budget if mentioned
        value = self._extract_monetary_value(all_text)
        if value > 0:
            if value < 10000:
                info["budget_range"] = "< $10,000"
            elif value < 50000:
                info["budget_range"] = "$10,000 - $50,000"
            elif value < 100000:
                info["budget_range"] = "$50,000 - $100,000"
            else:
                info["budget_range"] = "> $100,000"
        
        return info
    
    def _extract_requirements(self, emails: List[Email]) -> List[Dict]:
        """Extract requirements from email conversations"""
        requirements = []
        
        all_text = " ".join(e.body_text or "" for e in emails)
        
        # Look for requirement indicators
        requirement_keywords = ["need", "require", "must have", "looking for", "want", "would like"]
        
        sentences = all_text.split(".")
        for sentence in sentences:
            if any(kw in sentence.lower() for kw in requirement_keywords):
                requirements.append({
                    "description": sentence.strip()[:200],
                    "priority": "high" if "must" in sentence.lower() or "require" in sentence.lower() else "medium",
                    "category": self._categorize_requirement(sentence)
                })
        
        return requirements[:10]  # Limit to 10 requirements
    
    def _categorize_requirement(self, text: str) -> str:
        """Categorize a requirement"""
        categories = {
            "feature": ["feature", "functionality", "capability", "able to"],
            "integration": ["integrate", "connect", "api", "sync"],
            "performance": ["fast", "speed", "performance", "scalable"],
            "support": ["support", "help", "training", "onboarding"],
            "security": ["secure", "security", "compliance", "privacy"],
            "customization": ["custom", "configure", "personalize", "tailor"]
        }
        
        text_lower = text.lower()
        for category, keywords in categories.items():
            if any(kw in text_lower for kw in keywords):
                return category
        
        return "general"
    
    def _generate_solution(self, requirements: List[Dict]) -> Dict:
        """Generate solution based on requirements"""
        return {
            "overview": "Based on your requirements, we recommend our comprehensive solution that addresses all your key needs.",
            "components": [
                {
                    "name": f"Solution for {req['category']}",
                    "description": f"Addresses: {req['description'][:100]}",
                    "features": ["Feature A", "Feature B", "Feature C"]
                }
                for req in requirements[:3]
            ],
            "benefits": [
                "Increased efficiency by 40%",
                "Reduced operational costs",
                "Improved customer satisfaction",
                "Scalable for future growth"
            ],
            "differentiators": [
                "Industry-leading technology",
                "24/7 dedicated support",
                "Proven track record with similar companies",
                "Flexible implementation options"
            ]
        }
    
    def _generate_pricing(self, requirements: List[Dict], estimated_value: float) -> Dict:
        """Generate pricing structure"""
        base_price = estimated_value if estimated_value > 0 else 25000
        
        return {
            "model": "subscription" if base_price < 50000 else "license",
            "base_price": base_price,
            "options": [
                {
                    "name": "Standard",
                    "price": base_price * 0.8,
                    "features": ["Core features", "Email support", "Monthly updates"],
                    "recommended": False
                },
                {
                    "name": "Professional",
                    "price": base_price,
                    "features": ["All features", "Priority support", "Weekly updates", "Custom integrations"],
                    "recommended": True
                },
                {
                    "name": "Enterprise",
                    "price": base_price * 1.5,
                    "features": ["Everything in Professional", "Dedicated account manager", "Custom development", "SLA"],
                    "recommended": False
                }
            ],
            "discounts": [
                {"type": "early_bird", "amount": "10%", "condition": "Sign within 14 days"},
                {"type": "annual", "amount": "15%", "condition": "Annual payment upfront"}
            ],
            "payment_terms": "Net 30"
        }
    
    def _generate_timeline(self, requirements: List[Dict]) -> List[Dict]:
        """Generate implementation timeline"""
        phases = [
            {
                "phase": 1,
                "name": "Discovery & Planning",
                "duration": "1-2 weeks",
                "deliverables": ["Requirements documentation", "Project plan", "Success metrics"],
                "start_date": datetime.utcnow().isoformat()
            },
            {
                "phase": 2,
                "name": "Implementation",
                "duration": "3-4 weeks",
                "deliverables": ["System setup", "Configuration", "Integration"],
                "start_date": (datetime.utcnow() + timedelta(weeks=2)).isoformat()
            },
            {
                "phase": 3,
                "name": "Training & Testing",
                "duration": "1-2 weeks",
                "deliverables": ["User training", "Documentation", "Testing & QA"],
                "start_date": (datetime.utcnow() + timedelta(weeks=6)).isoformat()
            },
            {
                "phase": 4,
                "name": "Go-Live & Support",
                "duration": "Ongoing",
                "deliverables": ["Launch", "Support", "Optimization"],
                "start_date": (datetime.utcnow() + timedelta(weeks=8)).isoformat()
            }
        ]
        
        return phases
    
    def _generate_terms(self) -> Dict:
        """Generate standard terms and conditions"""
        return {
            "validity": "30 days",
            "payment": "Net 30",
            "warranty": "90 days",
            "support": "Included for 12 months",
            "cancellation": "30 days notice",
            "confidentiality": "Mutual NDA",
            "governing_law": "Delaware, USA"
        }
    
    def _get_proposal_templates(self) -> List[Dict]:
        """Get available proposal templates"""
        return [
            {
                "id": "default",
                "name": "Standard Proposal",
                "description": "General purpose proposal template",
                "sections": ["Executive Summary", "Solution", "Pricing", "Timeline", "Terms"]
            },
            {
                "id": "enterprise",
                "name": "Enterprise Proposal",
                "description": "Comprehensive proposal for large deals",
                "sections": ["Executive Summary", "Current State", "Proposed Solution", "ROI Analysis", "Implementation", "Pricing", "Risk Mitigation", "Terms"]
            },
            {
                "id": "quick",
                "name": "Quick Quote",
                "description": "Simple pricing quote",
                "sections": ["Summary", "Pricing", "Terms"]
            }
        ]
    
    def _get_recent_wins(self) -> List[Dict]:
        """Get recent successful proposals (mock data)"""
        return [
            {
                "client": "TechCorp Inc.",
                "value": 75000,
                "closed_date": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                "proposal_to_close": "14 days"
            },
            {
                "client": "Global Solutions LLC",
                "value": 120000,
                "closed_date": (datetime.utcnow() - timedelta(days=15)).isoformat(),
                "proposal_to_close": "21 days"
            }
        ]
    
    def _generate_proposal_html(self, client_info: Dict, requirements: List[Dict], opp: Dict) -> str:
        """Generate HTML preview of proposal (legacy method)"""
        return self._generate_comprehensive_proposal_html(
            client_info, requirements, {}, {}, opp, None, {}
        )

    def _generate_comprehensive_proposal_html(self, client_info: Dict, requirements: List[Dict],
                                               solution: Dict, pricing: Dict, opp: Dict,
                                               bant_result, business_info: Dict) -> str:
        """Generate comprehensive professional HTML proposal"""

        company_name = business_info.get("company_name", "Our Company")
        client_company = client_info.get("company", "Your Company")
        contact_name = client_info.get("contact_name", opp.get("sender_name", "Valued Client"))
        today = datetime.utcnow().strftime("%B %d, %Y")
        valid_until = (datetime.utcnow() + timedelta(days=30)).strftime("%B %d, %Y")

        # Build requirements HTML
        requirements_html = ""
        for req in requirements[:6]:
            priority_color = {"high": "#dc2626", "medium": "#f59e0b", "low": "#3b82f6"}.get(req["priority"], "#6b7280")
            requirements_html += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{req['description']}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: center;">
                    <span style="background: {priority_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{req['priority'].upper()}</span>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: center; color: #16a34a;">✓</td>
            </tr>
            """

        # Build solution components HTML
        components_html = ""
        if solution and solution.get("components"):
            for comp in solution["components"][:4]:
                features_list = "".join(f"<li style='margin: 4px 0;'>{f}</li>" for f in comp.get("features", [])[:4])
                components_html += f"""
                <div style="background: #f9fafb; border-radius: 8px; padding: 20px; margin-bottom: 16px;">
                    <h4 style="margin: 0 0 12px 0; color: #1f2937; font-size: 16px;">{comp['name']}</h4>
                    <p style="margin: 0 0 12px 0; color: #6b7280; font-size: 14px;">{comp.get('description', '')}</p>
                    <ul style="margin: 0; padding-left: 20px; color: #374151; font-size: 14px;">{features_list}</ul>
                </div>
                """

        # Build pricing HTML
        pricing_html = ""
        if pricing and pricing.get("options"):
            for opt in pricing["options"]:
                rec_badge = '<span style="background: #16a34a; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px;">RECOMMENDED</span>' if opt.get("recommended") else ""
                border_color = "#16a34a" if opt.get("recommended") else "#e5e7eb"
                features_list = "".join(f"<li style='margin: 6px 0; color: #374151;'>✓ {f}</li>" for f in opt.get("features", []))
                pricing_html += f"""
                <div style="flex: 1; border: 2px solid {border_color}; border-radius: 12px; padding: 24px; text-align: center; min-width: 200px;">
                    <h4 style="margin: 0 0 8px 0; font-size: 18px; color: #1f2937;">{opt['name']}{rec_badge}</h4>
                    <p style="margin: 0 0 16px 0; font-size: 32px; font-weight: bold; color: #1f2937;">${opt['price']:,.0f}<span style="font-size: 14px; font-weight: normal; color: #6b7280;"> {opt.get('billing', '')}</span></p>
                    <p style="margin: 0 0 16px 0; font-size: 12px; color: #6b7280;">{opt.get('best_for', '')}</p>
                    <ul style="text-align: left; list-style: none; padding: 0; margin: 0; font-size: 13px;">{features_list}</ul>
                </div>
                """

        # Build timeline HTML
        timeline_html = """
        <div style="display: flex; justify-content: space-between; margin-top: 20px;">
            <div style="text-align: center; flex: 1;">
                <div style="width: 40px; height: 40px; background: #3b82f6; color: white; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: bold;">1</div>
                <p style="margin: 8px 0 0 0; font-size: 14px; font-weight: 600;">Discovery</p>
                <p style="margin: 4px 0 0 0; font-size: 12px; color: #6b7280;">1-2 weeks</p>
            </div>
            <div style="text-align: center; flex: 1;">
                <div style="width: 40px; height: 40px; background: #3b82f6; color: white; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: bold;">2</div>
                <p style="margin: 8px 0 0 0; font-size: 14px; font-weight: 600;">Implementation</p>
                <p style="margin: 4px 0 0 0; font-size: 12px; color: #6b7280;">3-4 weeks</p>
            </div>
            <div style="text-align: center; flex: 1;">
                <div style="width: 40px; height: 40px; background: #3b82f6; color: white; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: bold;">3</div>
                <p style="margin: 8px 0 0 0; font-size: 14px; font-weight: 600;">Training</p>
                <p style="margin: 4px 0 0 0; font-size: 12px; color: #6b7280;">1-2 weeks</p>
            </div>
            <div style="text-align: center; flex: 1;">
                <div style="width: 40px; height: 40px; background: #16a34a; color: white; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: bold;">4</div>
                <p style="margin: 8px 0 0 0; font-size: 14px; font-weight: 600;">Go-Live</p>
                <p style="margin: 4px 0 0 0; font-size: 12px; color: #6b7280;">Ongoing</p>
            </div>
        </div>
        """

        # BANT indicator
        bant_html = ""
        if bant_result:
            bant_html = f"""
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                <p style="margin: 0; font-size: 14px; color: #166534;">
                    <strong>Lead Quality Score: {bant_result.bant_score.total}%</strong> -
                    Budget: {'✓' if bant_result.bant_score.budget >= 50 else '○'} |
                    Authority: {'✓' if bant_result.bant_score.authority >= 50 else '○'} |
                    Need: {'✓' if bant_result.bant_score.need >= 50 else '○'} |
                    Timeline: {'✓' if bant_result.bant_score.timeline >= 50 else '○'}
                </p>
            </div>
            """

        # Pain points section
        pain_points_html = ""
        if client_info.get("pain_points"):
            points = "".join(f"<li style='margin: 8px 0;'>{p}</li>" for p in client_info["pain_points"][:3])
            pain_points_html = f"""
            <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; margin: 20px 0;">
                <h4 style="margin: 0 0 12px 0; color: #92400e;">Challenges We'll Address</h4>
                <ul style="margin: 0; padding-left: 20px; color: #78350f;">{points}</ul>
            </div>
            """

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Business Proposal - {client_company}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1f2937; margin: 0; padding: 0; background: #f3f4f6; }}
        .proposal {{ max-width: 900px; margin: 0 auto; background: white; }}
        .header {{ background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%); color: white; padding: 48px; }}
        .section {{ padding: 32px 48px; border-bottom: 1px solid #e5e7eb; }}
        .section:last-child {{ border-bottom: none; }}
        h1 {{ margin: 0 0 8px 0; font-size: 32px; }}
        h2 {{ margin: 0 0 24px 0; font-size: 24px; color: #1f2937; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; }}
        h3 {{ margin: 0 0 16px 0; font-size: 18px; color: #374151; }}
        .meta {{ opacity: 0.9; font-size: 14px; }}
        .highlight {{ background: #eff6ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .cta {{ background: #16a34a; color: white; padding: 16px 32px; border-radius: 8px; text-decoration: none; display: inline-block; font-weight: 600; margin-top: 16px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f9fafb; padding: 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #e5e7eb; }}
        @media print {{ .proposal {{ box-shadow: none; }} }}
    </style>
</head>
<body>
    <div class="proposal">
        <!-- Header -->
        <div class="header">
            <h1>Business Proposal</h1>
            <p class="meta">Prepared for <strong>{client_company}</strong></p>
            <p class="meta">Prepared by {company_name} | {today}</p>
            <p class="meta">Valid until: {valid_until}</p>
        </div>

        <!-- Executive Summary -->
        <div class="section">
            <h2>Executive Summary</h2>
            {bant_html}
            <p>Dear {contact_name},</p>
            <p>Thank you for considering {company_name} as your partner. Based on our conversations and analysis of your requirements, we've prepared this comprehensive proposal to address your specific needs.</p>
            {pain_points_html}
            <div class="highlight">
                <h3>Why Partner With Us?</h3>
                <ul style="margin: 0; padding-left: 20px;">
                    <li>Proven track record with companies like {client_company}</li>
                    <li>Dedicated implementation and support team</li>
                    <li>Flexible solutions tailored to your requirements</li>
                    <li>95%+ customer satisfaction rate</li>
                </ul>
            </div>
        </div>

        <!-- Requirements -->
        <div class="section">
            <h2>Your Requirements</h2>
            <p>Based on our analysis, we've identified the following key requirements:</p>
            <table>
                <thead>
                    <tr>
                        <th>Requirement</th>
                        <th style="text-align: center; width: 100px;">Priority</th>
                        <th style="text-align: center; width: 80px;">Addressed</th>
                    </tr>
                </thead>
                <tbody>
                    {requirements_html}
                </tbody>
            </table>
        </div>

        <!-- Proposed Solution -->
        <div class="section">
            <h2>Proposed Solution</h2>
            <p>{solution.get('overview', 'We recommend our comprehensive solution tailored to your needs.') if solution else 'Our tailored solution addresses all your requirements.'}</p>
            {components_html}

            <h3 style="margin-top: 24px;">Key Benefits</h3>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;">
                <div style="background: #f0fdf4; padding: 16px; border-radius: 8px;">
                    <strong style="color: #166534;">✓ Efficiency</strong>
                    <p style="margin: 8px 0 0 0; font-size: 14px; color: #15803d;">Increase productivity by 30-50%</p>
                </div>
                <div style="background: #eff6ff; padding: 16px; border-radius: 8px;">
                    <strong style="color: #1e40af;">✓ Cost Savings</strong>
                    <p style="margin: 8px 0 0 0; font-size: 14px; color: #1d4ed8;">Reduce operational costs by 20%</p>
                </div>
                <div style="background: #fef3c7; padding: 16px; border-radius: 8px;">
                    <strong style="color: #92400e;">✓ Time to Value</strong>
                    <p style="margin: 8px 0 0 0; font-size: 14px; color: #a16207;">See results in 4-6 weeks</p>
                </div>
                <div style="background: #f3e8ff; padding: 16px; border-radius: 8px;">
                    <strong style="color: #7c3aed;">✓ Scalability</strong>
                    <p style="margin: 8px 0 0 0; font-size: 14px; color: #6d28d9;">Grows with your business</p>
                </div>
            </div>
        </div>

        <!-- Investment -->
        <div class="section">
            <h2>Investment Options</h2>
            <p>Choose the plan that best fits your needs:</p>
            <div style="display: flex; gap: 16px; flex-wrap: wrap; margin-top: 24px;">
                {pricing_html}
            </div>

            <div class="highlight" style="margin-top: 24px;">
                <h3>Special Offers</h3>
                <ul style="margin: 0; padding-left: 20px;">
                    <li><strong>Early Decision Discount:</strong> 10% off if you sign within 14 days</li>
                    <li><strong>Annual Commitment:</strong> 15% off with annual payment upfront</li>
                    <li><strong>Multi-year Agreement:</strong> 20% off with 3-year commitment</li>
                </ul>
            </div>

            <p style="margin-top: 16px; font-size: 14px; color: #6b7280;">
                <strong>All plans include:</strong> Implementation, data migration assistance, 8 hours of training, and 30-day money-back guarantee.
            </p>
        </div>

        <!-- Timeline -->
        <div class="section">
            <h2>Implementation Timeline</h2>
            <p>Our proven implementation process ensures a smooth transition:</p>
            {timeline_html}
        </div>

        <!-- Terms -->
        <div class="section">
            <h2>Terms & Conditions</h2>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; font-size: 14px;">
                <div><strong>Proposal Valid:</strong> 30 days</div>
                <div><strong>Payment Terms:</strong> Net 30</div>
                <div><strong>Warranty:</strong> 90 days</div>
                <div><strong>Support Included:</strong> 12 months</div>
                <div><strong>Cancellation:</strong> 30 days notice</div>
                <div><strong>Confidentiality:</strong> Mutual NDA available</div>
            </div>
        </div>

        <!-- Call to Action -->
        <div class="section" style="background: #f9fafb; text-align: center;">
            <h2 style="border: none; text-align: center;">Ready to Get Started?</h2>
            <p>We're excited to partner with {client_company} and help you achieve your goals.</p>
            <p>Contact us to discuss this proposal or schedule a demo.</p>
            <a href="mailto:{opp.get('sender', '')}" class="cta">Accept Proposal</a>
            <p style="margin-top: 24px; font-size: 14px; color: #6b7280;">
                Questions? Reply to this email or call us directly.
            </p>
        </div>

        <!-- Footer -->
        <div style="padding: 24px 48px; background: #1f2937; color: #9ca3af; font-size: 12px; text-align: center;">
            <p style="margin: 0;">© {datetime.utcnow().year} {company_name}. All rights reserved.</p>
            <p style="margin: 8px 0 0 0;">This proposal is confidential and intended solely for {client_company}.</p>
        </div>
    </div>
</body>
</html>
        """
        return html
    
    def get_business_profile(self) -> Dict:
        """Get or create business profile for the user"""
        profile = self.db.query(BusinessProfile).filter(
            BusinessProfile.user_id == self.user.id
        ).first()
        
        if not profile:
            # Create a new profile with learned patterns from existing emails
            profile = self._create_business_profile()
        
        return {
            "exists": profile is not None,
            "profile": self._serialize_profile(profile) if profile else None,
            "learned_insights": self._extract_business_insights() if not profile else None
        }
    
    def _create_business_profile(self) -> BusinessProfile:
        """Create initial business profile from email analysis"""
        insights = self._extract_business_insights()
        
        profile = BusinessProfile(
            user_id=self.user.id,
            company_name=insights.get("company_name", ""),
            industry=insights.get("industry", ""),
            successful_subject_lines=insights.get("successful_subjects", []),
            successful_email_patterns=insights.get("patterns", []),
            best_sending_times=insights.get("best_times", {})
        )
        
        self.db.add(profile)
        self.db.commit()
        return profile
    
    def _extract_business_insights(self) -> Dict:
        """Extract business insights from existing emails"""
        # Get user's sent emails (we'll approximate with emails they're involved in)
        recent_emails = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.deleted_at.is_(None)
        ).order_by(Email.received_at.desc()).limit(100).all()
        
        insights = {
            "company_name": "",
            "industry": "",
            "successful_subjects": [],
            "patterns": [],
            "best_times": {},
            "common_phrases": []
        }
        
        # Extract domain from user email
        if "@" in self.user.email:
            domain = self.user.email.split("@")[1]
            insights["company_name"] = domain.split(".")[0].title()
        
        # Analyze email patterns
        subject_responses = {}
        hour_stats = defaultdict(int)
        
        for email in recent_emails:
            # Track sending times
            hour_stats[email.received_at.hour] += 1
            
            # Look for successful patterns (emails with responses)
            if self._has_response(email):
                if email.subject not in subject_responses:
                    subject_responses[email.subject] = 0
                subject_responses[email.subject] += 1
        
        # Get top performing subjects
        insights["successful_subjects"] = [
            subj for subj, count in sorted(
                subject_responses.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10]
        ]
        
        # Best sending times
        if hour_stats:
            best_hour = max(hour_stats.items(), key=lambda x: x[1])[0]
            insights["best_times"] = {
                "hour": best_hour,
                "timezone": "UTC"  # Would detect from user settings
            }
        
        return insights
    
    def _serialize_profile(self, profile: BusinessProfile) -> Dict:
        """Serialize business profile for API response"""
        if not profile:
            return None

        return {
            "id": profile.id,
            # Company Overview
            "company_name": profile.company_name,
            "company_website": profile.company_website,
            "industry": profile.industry,
            "company_size": profile.company_size,
            "founded_year": profile.founded_year,
            # Business Details
            "value_proposition": profile.value_proposition,
            "elevator_pitch": profile.elevator_pitch,
            "key_differentiators": profile.key_differentiators,
            "target_market": profile.target_market,
            "ideal_customer_profile": profile.ideal_customer_profile,
            # Products/Services
            "products_services": profile.products_services,
            "pricing_model": profile.pricing_model,
            "average_deal_size": profile.average_deal_size,
            # Sales Context (NEW)
            "sales_cycle_length": profile.sales_cycle_length,
            "average_deal_size_min": profile.average_deal_size_min,
            "average_deal_size_max": profile.average_deal_size_max,
            "decision_makers": profile.decision_makers,
            "common_objections": profile.common_objections,
            "competitors": profile.competitors,
            "sales_methodology": profile.sales_methodology,
            # Target Market for Prospecting (NEW)
            "target_industries": profile.target_industries,
            "target_company_sizes": profile.target_company_sizes,
            "target_job_titles": profile.target_job_titles,
            "target_locations": profile.target_locations,
            "excluded_industries": profile.excluded_industries,
            # Pain Points & Solutions (NEW)
            "customer_pain_points": profile.customer_pain_points,
            "solutions_offered": profile.solutions_offered,
            "unique_selling_points": profile.unique_selling_points,
            # Success Stories
            "case_studies": profile.case_studies,
            "testimonials": profile.testimonials,
            "notable_clients": profile.notable_clients,
            # Marketing Materials
            "email_signature": profile.email_signature,
            "email_signature_html": profile.email_signature_html,
            "boilerplate": profile.boilerplate,
            "social_proof_stats": profile.social_proof_stats,
            # Communication Preferences (NEW)
            "preferred_outreach_channels": profile.preferred_outreach_channels,
            "follow_up_cadence": profile.follow_up_cadence,
            "calendar_link": profile.calendar_link,
            # Success Metrics (NEW)
            "win_rate": profile.win_rate,
            "average_response_time": profile.average_response_time,
            "nps_score": profile.nps_score,
            "customer_retention_rate": profile.customer_retention_rate,
            # Learned Patterns
            "successful_subject_lines": profile.successful_subject_lines,
            "successful_email_patterns": profile.successful_email_patterns,
            "best_sending_times": profile.best_sending_times,
            # Settings
            "cold_email_tone": profile.cold_email_tone,
            "max_emails_per_day": profile.max_emails_per_day,
            "quality_threshold": profile.quality_threshold
        }
    
    def generate_cold_emails(self, prospects: List[Dict], campaign_type: str = "lead_generation") -> Dict:
        """Generate personalized cold emails for prospects"""
        profile = self.db.query(BusinessProfile).filter(
            BusinessProfile.user_id == self.user.id
        ).first()
        
        if not profile:
            return {
                "error": "Please set up your business profile first",
                "action_needed": "complete_profile",
                "message": "Click on 'Setup Business Profile' to add your company information before generating emails"
            }
        
        # Create campaign
        campaign = ColdEmailCampaign(
            user_id=self.user.id,
            name=f"Campaign - {datetime.utcnow().strftime('%Y-%m-%d')}",
            campaign_type=campaign_type,
            total_prospects=len(prospects)
        )
        self.db.add(campaign)
        self.db.flush()
        
        generated_emails = []
        
        # Use max_emails_per_day if set, otherwise process all prospects
        max_emails = profile.max_emails_per_day if profile.max_emails_per_day else 50
        for prospect_data in prospects[:max_emails]:
            # Create prospect record
            prospect = ColdEmailProspect(
                campaign_id=campaign.id,
                email=prospect_data.get("email"),
                first_name=prospect_data.get("first_name"),
                last_name=prospect_data.get("last_name"),
                company_name=prospect_data.get("company_name"),
                job_title=prospect_data.get("job_title"),
                company_website=prospect_data.get("company_website"),
                company_industry=prospect_data.get("industry"),
                linkedin_url=prospect_data.get("linkedin_url")
            )
            
            # Enrich prospect data
            enriched = self._enrich_prospect(prospect_data)
            prospect.company_description = enriched.get("description")
            prospect.recent_news = enriched.get("news", [])
            prospect.pain_points = enriched.get("pain_points", [])
            
            # Calculate personalization score
            personalization_score = self._calculate_personalization_score(prospect, enriched)
            prospect.personalization_score = personalization_score
            
            # Generate email for all prospects (manual review will filter)
            email_content = self._generate_cold_email(
                prospect, profile, campaign_type, personalization_score
            )
            prospect.generated_subject = email_content["subject"]
            prospect.generated_body = email_content["body"]
            prospect.quality_score = email_content["quality_score"]
            prospect.review_status = "pending"  # All emails start as pending review
            
            generated_emails.append({
                "prospect": prospect_data,
                "email": email_content,
                "personalization_score": personalization_score,
                "quality_score": email_content["quality_score"],
                "review_status": "pending"
            })
            
            self.db.add(prospect)
        
        self.db.commit()
        
        return {
            "campaign_id": campaign.id,
            "total_prospects": len(prospects),
            "emails_generated": len(generated_emails),
            "emails": generated_emails,
            "requires_review": True,
            "review_instructions": "Please review each email before sending"
        }
    
    def _enrich_prospect(self, prospect_data: Dict) -> Dict:
        """Enrich prospect data with additional information"""
        enriched = {
            "description": "",
            "news": [],
            "pain_points": [],
            "technologies": []
        }
        
        # Simulate enrichment (in production, would use APIs)
        industry = prospect_data.get("industry", "").lower()
        
        # Industry-specific pain points
        pain_point_map = {
            "technology": ["scaling infrastructure", "technical debt", "security concerns", "talent retention"],
            "finance": ["regulatory compliance", "risk management", "digital transformation", "customer acquisition"],
            "healthcare": ["patient engagement", "data interoperability", "cost reduction", "compliance"],
            "retail": ["inventory management", "customer experience", "omnichannel", "supply chain"],
            "manufacturing": ["supply chain disruption", "quality control", "automation", "sustainability"]
        }
        
        for key, points in pain_point_map.items():
            if key in industry:
                enriched["pain_points"] = points[:2]
                break
        
        # Simulate recent news
        company_name = prospect_data.get("company_name", "")
        if company_name:
            enriched["news"] = [
                f"{company_name} announces expansion",
                f"{company_name} adopts new technology"
            ]
        
        return enriched
    
    def _calculate_personalization_score(self, prospect: ColdEmailProspect, enriched: Dict) -> int:
        """Calculate how well we can personalize for this prospect"""
        score = 0
        max_score = 100
        
        # Basic information (30 points)
        if prospect.first_name:
            score += 10
        if prospect.company_name:
            score += 10
        if prospect.job_title:
            score += 10
        
        # Company information (20 points)
        if prospect.company_website:
            score += 10
        if prospect.company_industry:
            score += 10
        
        # Enriched data (30 points)
        if enriched.get("pain_points"):
            score += 15
        if enriched.get("news"):
            score += 15
        
        # Contact quality (20 points)
        if prospect.linkedin_url:
            score += 10
        if prospect.email and "@" in prospect.email:
            score += 10
        
        return min(score, max_score)
    
    def _generate_cold_email(self, prospect: ColdEmailProspect, profile: BusinessProfile, 
                            campaign_type: str, personalization_score: int) -> Dict:
        """Generate personalized cold email content"""
        
        # Select approach based on campaign type and personalization level
        if personalization_score >= 80:
            approach = "highly_personalized"
        elif personalization_score >= 60:
            approach = "moderately_personalized"
        else:
            approach = "generic_value"
        
        # Generate subject line
        subject = self._generate_subject_line(prospect, profile, campaign_type, approach)
        
        # Generate email body
        body = self._generate_email_body(prospect, profile, campaign_type, approach)
        
        # Calculate quality score
        quality_score = self._calculate_email_quality(subject, body, personalization_score)
        
        return {
            "subject": subject,
            "body": body,
            "approach": approach,
            "quality_score": quality_score,
            "personalization_elements": self._get_personalization_elements(prospect)
        }
    
    def _generate_subject_line(self, prospect: ColdEmailProspect, profile: BusinessProfile,
                              campaign_type: str, approach: str) -> str:
        """Generate subject line based on approach"""
        
        import random
        
        # More natural subject line variations based on tone
        if profile.cold_email_tone == "casual":
            templates = {
                "highly_personalized": [
                    f"Quick thought on {prospect.company_name}",
                    f"Hey {prospect.first_name}, noticed something interesting",
                    f"Re: {prospect.company_name}'s {prospect.pain_points[0] if prospect.pain_points else 'recent initiatives'}",
                    f"Idea for your team at {prospect.company_name}"
                ],
                "moderately_personalized": [
                    f"Quick thought for {prospect.company_name}",
                    f"{prospect.first_name} - got 5 minutes?",
                    f"Question about {prospect.company_name}",
                    f"Something that might interest you"
                ],
                "generic_value": [
                    "Quick question",
                    "Thought you might find this interesting",
                    f"About your {campaign_type.replace('_', ' ')}",
                    "Got 5 minutes this week?"
                ]
            }
        elif profile.cold_email_tone == "technical":
            templates = {
                "highly_personalized": [
                    f"Technical solution for {prospect.company_name}'s {prospect.pain_points[0] if prospect.pain_points else 'infrastructure'}",
                    f"Re: {prospect.company_name}'s tech stack",
                    f"API integration opportunity for {prospect.company_name}",
                    f"Performance optimization for {prospect.company_industry or 'your industry'}"
                ],
                "moderately_personalized": [
                    f"Technical proposal for {prospect.company_name}",
                    f"Integration opportunity - {prospect.company_name}",
                    f"Scaling solution for {prospect.company_industry or 'your team'}"
                ],
                "generic_value": [
                    "Technical solution for your consideration",
                    "Performance improvement opportunity",
                    "Infrastructure optimization proposal"
                ]
            }
        else:  # professional
            templates = {
                "highly_personalized": [
                    f"{prospect.company_name} - partnership opportunity",
                    f"Following up on {prospect.company_name}'s {prospect.recent_news[0] if prospect.recent_news else 'recent growth'}",
                    f"Strategic initiative for {prospect.company_name}",
                    f"{prospect.first_name} - regarding {prospect.company_name}'s expansion"
                ],
                "moderately_personalized": [
                    f"Partnership opportunity - {prospect.company_name}",
                    f"Introduction: {profile.company_name} <> {prospect.company_name}",
                    f"Proposal for {prospect.company_name}"
                ],
                "generic_value": [
                    "Partnership opportunity",
                    f"Introduction from {profile.company_name}",
                    "Business development opportunity"
                ]
            }
        
        # Get appropriate templates
        subject_templates = templates.get(approach, templates["generic_value"])
        
        # Select based on successful patterns if available
        if profile.successful_subject_lines:
            # Try to match pattern
            for pattern in profile.successful_subject_lines[:3]:
                if pattern and len(pattern) < 100:
                    return self._adapt_subject_pattern(pattern, prospect, profile)
        
        # Return random template for variety
        return random.choice(subject_templates)
    
    def _adapt_subject_pattern(self, pattern: str, prospect: ColdEmailProspect, 
                              profile: BusinessProfile) -> str:
        """Adapt a successful subject pattern to new prospect"""
        # Simple token replacement
        adapted = pattern
        adapted = adapted.replace("[company]", prospect.company_name or "your company")
        adapted = adapted.replace("[name]", prospect.first_name or "there")
        adapted = adapted.replace("[industry]", prospect.company_industry or "your industry")
        return adapted
    
    def _generate_email_body(self, prospect: ColdEmailProspect, profile: BusinessProfile,
                            campaign_type: str, approach: str) -> str:
        """Generate email body based on approach and tone"""
        
        import random
        
        # More natural greetings based on tone
        if profile.cold_email_tone == "casual":
            if prospect.first_name:
                greetings = [
                    f"Hey {prospect.first_name},",
                    f"Hi {prospect.first_name},",
                    f"{prospect.first_name},"
                ]
            else:
                greetings = ["Hey there,", "Hi,", "Hello,"]
            greeting = random.choice(greetings)
        elif profile.cold_email_tone == "technical":
            greeting = f"Hi {prospect.first_name}," if prospect.first_name else "Hello,"
        else:  # professional
            if prospect.first_name:
                greeting = f"Dear {prospect.first_name}," if random.random() < 0.3 else f"Hi {prospect.first_name},"
            else:
                greeting = "Hello,"
        
        # Opening line based on approach
        if approach == "highly_personalized":
            opening = self._generate_personalized_opening(prospect, profile)
        elif approach == "moderately_personalized":
            opening = self._generate_moderate_opening(prospect, profile)
        else:
            opening = self._generate_generic_opening(prospect, profile)
        
        # Build email based on tone
        if profile.cold_email_tone == "casual":
            # Casual tone - conversational, brief
            value_prop = self._generate_casual_value_prop(prospect, profile)
            social_proof = self._generate_casual_social_proof(profile)
            cta = self._generate_casual_cta(campaign_type)
            
            # Compose in a more conversational way
            body_parts = [greeting, opening]
            if value_prop:
                body_parts.append(value_prop)
            if social_proof and random.random() < 0.7:  # Sometimes skip social proof for brevity
                body_parts.append(social_proof)
            body_parts.append(cta)
            
        elif profile.cold_email_tone == "technical":
            # Technical tone - specific, detailed
            value_prop = self._generate_technical_value_prop(prospect, profile)
            social_proof = self._generate_technical_social_proof(profile)
            cta = self._generate_technical_cta(campaign_type)
            
            body_parts = [greeting, opening, value_prop]
            if social_proof:
                body_parts.append(social_proof)
            body_parts.append(cta)
            
        else:  # professional
            # Professional tone - polished, structured
            value_prop = self._generate_professional_value_prop(prospect, profile)
            social_proof = self._generate_professional_social_proof(profile)
            cta = self._generate_professional_cta(campaign_type)
            
            body_parts = [greeting, opening, value_prop]
            if social_proof:
                body_parts.append(social_proof)
            body_parts.append(cta)
        
        # Signature
        signature = profile.email_signature or self._generate_signature(profile.cold_email_tone, self.user.name)
        body_parts.append(signature)
        
        # Join with appropriate spacing (single line break for casual, double for others)
        separator = "\n" if profile.cold_email_tone == "casual" else "\n\n"
        body = separator.join(body_parts)
        
        return body
    
    def _generate_personalized_opening(self, prospect: ColdEmailProspect, profile: BusinessProfile) -> str:
        """Generate highly personalized opening"""
        import random
        
        if prospect.recent_news and len(prospect.recent_news) > 0:
            openings = [
                f"Just saw the news about {prospect.recent_news[0]} - exciting stuff!",
                f"Congrats on {prospect.recent_news[0]}. I imagine {prospect.pain_points[0] if prospect.pain_points else 'scaling'} is top of mind now.",
                f"I was reading about {prospect.recent_news[0]} and had a thought about how we might be able to help.",
                f"Impressive what you're doing with {prospect.recent_news[0]}."
            ]
        elif prospect.pain_points and len(prospect.pain_points) > 0:
            openings = [
                f"I've been helping {prospect.company_industry or 'companies'} with {prospect.pain_points[0]} lately and thought of you.",
                f"Quick question - is {prospect.pain_points[0]} still a priority for your team?",
                f"I noticed {prospect.company_name} might be dealing with {prospect.pain_points[0]}.",
                f"Been seeing a lot of {prospect.company_industry or 'companies'} struggle with {prospect.pain_points[0]} recently."
            ]
        else:
            openings = [
                f"I've been following {prospect.company_name} for a while now.",
                f"Your work at {prospect.company_name} caught my attention.",
                f"I came across {prospect.company_name} and was impressed by what you're building.",
                f"Been meaning to reach out after learning about {prospect.company_name}."
            ]
        return random.choice(openings)
    
    def _generate_moderate_opening(self, prospect: ColdEmailProspect, profile: BusinessProfile) -> str:
        """Generate moderately personalized opening"""
        import random
        
        openings = [
            f"I work with {prospect.company_industry or 'companies'} like {prospect.company_name}.",
            f"Reaching out because I think we can help {prospect.company_name}.",
            f"I noticed {prospect.company_name} and wanted to connect.",
            f"We specialize in helping {prospect.company_industry or 'companies'} like yours.",
            f"I help {prospect.company_industry or 'businesses'} with similar challenges to what {prospect.company_name} might be facing."
        ]
        return random.choice(openings)
    
    def _generate_generic_opening(self, prospect: ColdEmailProspect, profile: BusinessProfile) -> str:
        """Generate generic opening"""
        import random
        
        openings = [
            f"I'm reaching out because {profile.value_proposition or 'we help companies improve efficiency'}.",
            "Hope this message finds you well.",
            f"I wanted to introduce {profile.company_name} and what we do.",
            "I help companies solve similar challenges to what you might be experiencing.",
            "Reaching out with something that might be valuable for your team."
        ]
        return random.choice(openings)
    
    def _generate_value_proposition(self, prospect: ColdEmailProspect, profile: BusinessProfile) -> str:
        """Generate value proposition paragraph"""
        if profile.elevator_pitch:
            return profile.elevator_pitch
        
        # Generic value prop
        value = f"We help companies like {prospect.company_name or 'yours'} "
        
        if prospect.pain_points and len(prospect.pain_points) > 0:
            value += f"solve {prospect.pain_points[0]} "
        else:
            value += "increase efficiency "
        
        if profile.social_proof_stats:
            stats = profile.social_proof_stats
            if "roi" in stats:
                value += f"with an average ROI of {stats['roi']}."
            elif "customers" in stats:
                value += f"(trusted by {stats['customers']} customers)."
        else:
            value += "with measurable results."
        
        return value
    
    def _generate_social_proof(self, profile: BusinessProfile) -> str:
        """Generate social proof section"""
        if profile.notable_clients and len(profile.notable_clients) > 0:
            clients = ", ".join(profile.notable_clients[:3])
            return f"We've helped companies like {clients} achieve similar results."
        elif profile.testimonials and len(profile.testimonials) > 0:
            return f"One client said: '{profile.testimonials[0][:100]}...'"
        else:
            return "We've helped dozens of companies in your industry."
    
    # Casual tone methods
    def _generate_casual_value_prop(self, prospect: ColdEmailProspect, profile: BusinessProfile) -> str:
        """Generate casual value proposition"""
        import random
        
        if profile.elevator_pitch:
            # Make the elevator pitch more casual
            pitch = profile.elevator_pitch.replace("We ", "We basically ").replace("Our ", "Our ")
            return pitch[:150] if len(pitch) > 150 else pitch
        
        props = [
            f"We basically help {prospect.company_industry or 'teams'} {prospect.pain_points[0] if prospect.pain_points else 'work more efficiently'}. Nothing fancy, just stuff that works.",
            f"Long story short - we make {prospect.pain_points[0] if prospect.pain_points else 'things'} a lot easier.",
            f"We've got a pretty straightforward way to help with {prospect.pain_points[0] if prospect.pain_points else 'what you are working on'}.",
            f"The gist is we help teams like yours save time and headaches."
        ]
        return random.choice(props)
    
    def _generate_casual_social_proof(self, profile: BusinessProfile) -> str:
        """Generate casual social proof"""
        import random
        
        if profile.notable_clients and len(profile.notable_clients) > 0:
            client = random.choice(profile.notable_clients[:3])
            return f"(We're working with {client} on something similar, actually.)"
        elif profile.social_proof_stats and "customers" in profile.social_proof_stats:
            return f"Already helping {profile.social_proof_stats['customers']} teams with this."
        else:
            return random.choice([
                "Already helping a bunch of teams with this.",
                "Got some cool success stories I can share.",
                ""  # Sometimes skip social proof in casual emails
            ])
    
    def _generate_casual_cta(self, campaign_type: str) -> str:
        """Generate casual call to action"""
        import random
        
        ctas = [
            "Worth a quick chat?",
            "Want to hop on a quick call this week?",
            "Free for 15 minutes sometime?",
            "Interested? Happy to chat more.",
            "Let me know if this sounds useful - happy to explain more.",
            "Thoughts?",
            "Make sense to connect?"
        ]
        return random.choice(ctas)
    
    # Technical tone methods
    def _generate_technical_value_prop(self, prospect: ColdEmailProspect, profile: BusinessProfile) -> str:
        """Generate technical value proposition"""
        import random
        
        if profile.elevator_pitch:
            return profile.elevator_pitch
        
        tech_features = [
            "API-first architecture",
            "sub-millisecond latency",
            "99.99% uptime SLA",
            "enterprise-grade security",
            "horizontal scaling",
            "real-time synchronization"
        ]
        
        feature = random.choice(tech_features)
        return f"Our solution provides {feature} for {prospect.pain_points[0] if prospect.pain_points else 'your use case'}. Built specifically for {prospect.company_industry or 'technical teams'} that need reliability and performance at scale."
    
    def _generate_technical_social_proof(self, profile: BusinessProfile) -> str:
        """Generate technical social proof"""
        if profile.social_proof_stats:
            stats = []
            if "uptime" in profile.social_proof_stats:
                stats.append(f"{profile.social_proof_stats['uptime']} uptime")
            if "performance" in profile.social_proof_stats:
                stats.append(f"{profile.social_proof_stats['performance']} performance improvement")
            if stats:
                return f"Current metrics from production deployments: {', '.join(stats)}."
        
        if profile.notable_clients:
            return f"Currently deployed at scale with {', '.join(profile.notable_clients[:2])}."
        
        return "Full technical documentation and benchmarks available upon request."
    
    def _generate_technical_cta(self, campaign_type: str) -> str:
        """Generate technical call to action"""
        import random
        
        ctas = [
            "Would you be interested in a technical deep-dive? I can walk through the architecture and integration points.",
            "Happy to schedule a technical demo where we can discuss your specific requirements and implementation details.",
            "I can share our API documentation and discuss integration options if you're interested.",
            "Would a proof-of-concept be valuable? We can set up a sandbox environment for your team.",
            "Interested in seeing performance benchmarks for your specific use case?"
        ]
        return random.choice(ctas)
    
    # Professional tone methods
    def _generate_professional_value_prop(self, prospect: ColdEmailProspect, profile: BusinessProfile) -> str:
        """Generate professional value proposition"""
        if profile.elevator_pitch:
            return profile.elevator_pitch
        
        value = f"{profile.company_name} specializes in helping {prospect.company_industry or 'organizations'} "
        
        if prospect.pain_points and len(prospect.pain_points) > 0:
            value += f"address {prospect.pain_points[0]} through our proven methodology"
        else:
            value += "achieve operational excellence and drive measurable business outcomes"
        
        if profile.social_proof_stats and "roi" in profile.social_proof_stats:
            value += f", delivering an average ROI of {profile.social_proof_stats['roi']}."
        else:
            value += "."
        
        return value
    
    def _generate_professional_social_proof(self, profile: BusinessProfile) -> str:
        """Generate professional social proof"""
        if profile.notable_clients and len(profile.notable_clients) > 0:
            clients = ", ".join(profile.notable_clients[:3])
            return f"We've had the privilege of partnering with industry leaders including {clients}."
        elif profile.testimonials and len(profile.testimonials) > 0:
            return f"As one of our clients recently noted: \"{profile.testimonials[0][:100]}...\""
        elif profile.social_proof_stats and "customers" in profile.social_proof_stats:
            return f"We currently serve {profile.social_proof_stats['customers']} organizations across various industries."
        else:
            return ""
    
    def _generate_professional_cta(self, campaign_type: str) -> str:
        """Generate professional call to action"""
        import random
        
        ctas = [
            "Would you be open to a brief introductory call to explore potential synergies? I have availability this Thursday or Friday afternoon.",
            "I would welcome the opportunity to discuss how we might support your initiatives. Could we schedule a 20-minute call next week?",
            "If this aligns with your current priorities, I'd be happy to share more details. When might be a convenient time for a brief discussion?",
            "I believe there could be significant value in exploring a partnership. Would you be available for a short call to discuss further?",
            "If you're interested in learning more, I'd be happy to arrange a brief call at your convenience."
        ]
        return random.choice(ctas)
    
    def _generate_signature(self, tone: str, name: str) -> str:
        """Generate email signature based on tone"""
        import random
        
        if tone == "casual":
            signatures = [
                f"Cheers,\n{name or 'Your Name'}",
                f"Best,\n{name or 'Your Name'}",
                f"-{name or 'Your Name'}",
                f"Thanks,\n{name or 'Your Name'}"
            ]
        elif tone == "technical":
            signatures = [
                f"Best regards,\n{name or 'Your Name'}",
                f"Regards,\n{name or 'Your Name'}",
                f"Thanks,\n{name or 'Your Name'}\nTechnical Sales"
            ]
        else:  # professional
            signatures = [
                f"Best regards,\n{name or 'Your Name'}",
                f"Sincerely,\n{name or 'Your Name'}",
                f"Kind regards,\n{name or 'Your Name'}",
                f"Warm regards,\n{name or 'Your Name'}"
            ]
        return random.choice(signatures)
    
    def _generate_cta(self, campaign_type: str, tone: str) -> str:
        """Generate call to action - legacy method for backward compatibility"""
        if tone == "casual":
            return self._generate_casual_cta(campaign_type)
        elif tone == "technical":
            return self._generate_technical_cta(campaign_type)
        else:  # professional
            return self._generate_professional_cta(campaign_type)
    
    def _calculate_email_quality(self, subject: str, body: str, personalization_score: int) -> int:
        """Calculate overall email quality score"""
        score = personalization_score
        
        # Length checks
        if 30 <= len(subject) <= 60:
            score += 5
        if 100 <= len(body) <= 300:
            score += 5
        
        # Spam indicators (reduce score)
        spam_words = ["free", "guarantee", "urgent", "act now", "limited time", "$$$"]
        for word in spam_words:
            if word.lower() in body.lower() or word.lower() in subject.lower():
                score -= 5
        
        # Professional indicators
        if "?" in subject:  # Questions perform well
            score += 3
        if body.count("\n\n") >= 3:  # Well-formatted
            score += 2
        
        return max(0, min(100, score))
    
    def _get_personalization_elements(self, prospect: ColdEmailProspect) -> List[str]:
        """Get list of personalization elements used"""
        elements = []
        
        if prospect.first_name:
            elements.append("first_name")
        if prospect.company_name:
            elements.append("company_name")
        if prospect.recent_news:
            elements.append("recent_news")
        if prospect.pain_points:
            elements.append("pain_points")
        if prospect.company_industry:
            elements.append("industry")
        
        return elements
    
    def parse_prospects_from_text(self, text: str) -> List[Dict]:
        """Parse various text formats to extract prospect information"""
        import re
        
        prospects = []
        email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        
        # Try different parsing strategies
        lines = text.strip().split('\n')
        
        for line in lines:
            # Find email addresses
            emails = re.findall(email_regex, line)
            if not emails:
                continue
                
            email = emails[0]
            
            # Try to extract information around the email
            parts = re.split(r'[,\t|;]', line)
            
            prospect = {
                'email': email,
                'first_name': '',
                'last_name': '',
                'company_name': '',
                'job_title': '',
                'company_industry': '',
                'linkedin_url': ''
            }
            
            # Look for names (capitalized words)
            name_pattern = r'\b[A-Z][a-z]+\b'
            names = re.findall(name_pattern, line)
            
            # Filter out common titles
            titles = ['CEO', 'CTO', 'CFO', 'VP', 'Director', 'Manager', 'Engineer']
            names = [n for n in names if n not in titles]
            
            if len(names) >= 2:
                prospect['first_name'] = names[0]
                prospect['last_name'] = names[1]
            elif len(names) == 1:
                prospect['first_name'] = names[0]
            
            # Look for LinkedIn URLs
            linkedin_pattern = r'linkedin\.com/in/[\w-]+'
            linkedin_matches = re.findall(linkedin_pattern, line)
            if linkedin_matches:
                prospect['linkedin_url'] = f"https://{linkedin_matches[0]}"
            
            # Try to find company name and title
            for part in parts:
                part = part.strip()
                if part and part != email and part not in [prospect['first_name'], prospect['last_name']]:
                    # Check if it's a job title
                    if any(title_word in part.upper() for title_word in ['CEO', 'CTO', 'CFO', 'MANAGER', 'DIRECTOR', 'VP', 'PRESIDENT']):
                        prospect['job_title'] = part
                    elif len(part) > 2 and not prospect['company_name']:
                        prospect['company_name'] = part
                    elif len(part) > 2 and not prospect['company_industry']:
                        prospect['company_industry'] = part
            
            prospects.append(prospect)
        
        return prospects
    
    def extract_contacts_from_emails(self, include_sent: bool, include_received: bool, days_back: int) -> List[Dict]:
        """Extract contacts from user's email history"""
        from datetime import datetime, timedelta
        import re
        
        prospects = []
        seen_emails = set()
        
        # Calculate date range
        since_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Query emails
        query = self.db.query(Email).filter(
            Email.user_id == self.user.id,
            Email.received_at >= since_date,
            Email.deleted_at.is_(None)
        )
        
        emails = query.all()
        
        for email in emails:
            # Process sender if including received
            if include_received and email.sender and email.sender not in seen_emails:
                # Parse sender field
                email_addr = email.sender
                name = email.sender_name or ''
                
                # Extract email from format "Name <email@domain.com>"
                email_match = re.search(r'<(.+?)>', email.sender)
                if email_match:
                    email_addr = email_match.group(1)
                    name = email.sender.replace(f'<{email_addr}>', '').strip()
                
                # Parse name
                name_parts = name.split()
                first_name = name_parts[0] if name_parts else ''
                last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                
                # Try to extract company from domain
                domain = email_addr.split('@')[1] if '@' in email_addr else ''
                company = domain.split('.')[0].title() if domain else ''
                
                if email_addr not in seen_emails:
                    seen_emails.add(email_addr)
                    prospects.append({
                        'email': email_addr,
                        'first_name': first_name,
                        'last_name': last_name,
                        'company_name': company,
                        'job_title': '',
                        'company_industry': '',
                        'linkedin_url': ''
                    })
            
            # Process recipients if including sent
            if include_sent and email.recipients:
                for recipient in email.recipients:
                    if isinstance(recipient, dict):
                        email_addr = recipient.get('email', '')
                        name = recipient.get('name', '')
                    else:
                        email_addr = str(recipient)
                        name = ''
                    
                    if email_addr and email_addr not in seen_emails:
                        # Parse name
                        name_parts = name.split() if name else []
                        first_name = name_parts[0] if name_parts else ''
                        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                        
                        # Extract company from domain
                        domain = email_addr.split('@')[1] if '@' in email_addr else ''
                        company = domain.split('.')[0].title() if domain else ''
                        
                        seen_emails.add(email_addr)
                        prospects.append({
                            'email': email_addr,
                            'first_name': first_name,
                            'last_name': last_name,
                            'company_name': company,
                            'job_title': '',
                            'company_industry': '',
                            'linkedin_url': ''
                        })
        
        # Filter out common email providers
        common_providers = ['gmail', 'yahoo', 'hotmail', 'outlook', 'icloud', 'aol']
        prospects = [p for p in prospects if not any(provider in p['email'].lower() for provider in common_providers)]
        
        return prospects[:100]  # Limit to 100 contacts
    
    def scrape_website_content(self, url: str) -> Dict:
        """Scrape website content for business information"""
        try:
            # Validate and clean URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Request website
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract text content
            content = {
                'url': url,
                'title': soup.title.string if soup.title else '',
                'meta_description': '',
                'headings': [],
                'main_text': '',
                'about_text': '',
                'features': [],
                'services': []
            }
            
            # Get meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                content['meta_description'] = meta_desc.get('content', '')
            
            # Get all headings
            for heading in soup.find_all(['h1', 'h2', 'h3']):
                text = heading.get_text(strip=True)
                if text:
                    content['headings'].append(text)
            
            # Get main content paragraphs
            paragraphs = []
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 50:  # Only substantial paragraphs
                    paragraphs.append(text)
            content['main_text'] = ' '.join(paragraphs[:10])  # First 10 paragraphs
            
            # Try to find About section
            about_sections = soup.find_all(['div', 'section'], class_=re.compile('about', re.I))
            if not about_sections:
                about_sections = soup.find_all(['div', 'section'], id=re.compile('about', re.I))
            
            for section in about_sections:
                about_text = section.get_text(strip=True)
                if len(about_text) > 100:
                    content['about_text'] = about_text[:1000]
                    break
            
            # Look for features/benefits
            feature_keywords = ['feature', 'benefit', 'solution', 'service', 'product', 'offer']
            for keyword in feature_keywords:
                feature_sections = soup.find_all(['div', 'section', 'ul'], class_=re.compile(keyword, re.I))
                for section in feature_sections:
                    items = section.find_all(['li', 'div', 'p'])
                    for item in items[:10]:  # Limit to 10 items
                        text = item.get_text(strip=True)
                        if 20 < len(text) < 200:
                            content['features'].append(text)
            
            # Look for navigation links to find key pages
            nav_links = []
            nav = soup.find(['nav', 'header'])
            if nav:
                links = nav.find_all('a')
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    if text and not href.startswith('#'):
                        full_url = urljoin(url, href)
                        nav_links.append({'text': text, 'url': full_url})
            
            # Try to identify industry from content
            content['detected_industry'] = self._detect_industry_from_content(
                content['title'] + ' ' + content['meta_description'] + ' ' + content['main_text']
            )
            
            # Extract company name from domain
            parsed_url = urlparse(url)
            domain_parts = parsed_url.netloc.split('.')
            content['company_name'] = domain_parts[0].replace('-', ' ').title()
            
            return content
            
        except Exception as e:
            return {
                'error': str(e),
                'url': url
            }
    
    def _detect_industry_from_content(self, text: str) -> str:
        """Detect industry from website content"""
        text_lower = text.lower()
        
        industry_keywords = {
            'technology': ['software', 'saas', 'platform', 'api', 'cloud', 'data', 'analytics', 'ai', 'machine learning'],
            'finance': ['financial', 'banking', 'investment', 'trading', 'fintech', 'payment', 'accounting'],
            'healthcare': ['health', 'medical', 'patient', 'clinic', 'hospital', 'therapy', 'wellness', 'pharmaceutical'],
            'retail': ['shop', 'store', 'ecommerce', 'retail', 'product', 'merchandise', 'fashion'],
            'manufacturing': ['manufacture', 'production', 'factory', 'industrial', 'supply chain', 'logistics'],
            'education': ['education', 'learning', 'training', 'course', 'student', 'teacher', 'university'],
            'marketing': ['marketing', 'advertising', 'brand', 'campaign', 'seo', 'content', 'social media'],
            'consulting': ['consulting', 'advisory', 'strategy', 'management', 'business transformation'],
            'real_estate': ['real estate', 'property', 'realty', 'housing', 'commercial space', 'residential']
        }
        
        industry_scores = {}
        for industry, keywords in industry_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                industry_scores[industry] = score
        
        if industry_scores:
            return max(industry_scores.items(), key=lambda x: x[1])[0]
        return 'general'
    
    def generate_value_prop_from_website(self, website_content: Dict) -> Dict:
        """Generate value proposition and elevator pitch from website content"""
        
        if 'error' in website_content:
            return {
                'error': website_content['error'],
                'value_proposition': '',
                'elevator_pitch': ''
            }
        
        # Combine relevant content
        combined_text = f"""
        Title: {website_content.get('title', '')}
        Description: {website_content.get('meta_description', '')}
        Main Content: {website_content.get('main_text', '')[:500]}
        About: {website_content.get('about_text', '')[:300]}
        Features: {', '.join(website_content.get('features', [])[:5])}
        """
        
        # Analyze content for key value elements
        value_elements = self._extract_value_elements(website_content)
        
        # Generate value proposition
        value_proposition = self._generate_value_proposition_from_elements(value_elements, website_content)
        
        # Generate elevator pitch
        elevator_pitch = self._generate_elevator_pitch_from_elements(value_elements, website_content)
        
        # Extract key differentiators
        differentiators = self._extract_differentiators(website_content)
        
        # Identify target market
        target_market = self._identify_target_market(website_content)
        
        # Extract product/service list
        products_services = self._extract_products_services(website_content)
        
        return {
            'company_name': website_content.get('company_name', ''),
            'industry': website_content.get('detected_industry', ''),
            'value_proposition': value_proposition,
            'elevator_pitch': elevator_pitch,
            'key_differentiators': differentiators,
            'target_market': target_market,
            'products_services': products_services,
            'website_analyzed': True
        }
    
    def _extract_value_elements(self, content: Dict) -> Dict:
        """Extract key value elements from website content"""
        elements = {
            'problems_solved': [],
            'benefits': [],
            'features': [],
            'unique_aspects': []
        }
        
        # Combine all text
        all_text = f"{content.get('meta_description', '')} {content.get('main_text', '')} {' '.join(content.get('features', []))}"
        all_text_lower = all_text.lower()
        
        # Problem indicators
        problem_keywords = ['solve', 'problem', 'challenge', 'issue', 'pain point', 'struggle', 'difficult', 'frustrated']
        benefit_keywords = ['increase', 'improve', 'enhance', 'boost', 'optimize', 'save', 'reduce', 'eliminate', 'streamline']
        unique_keywords = ['only', 'first', 'unique', 'exclusive', 'proprietary', 'patented', 'revolutionary', 'innovative']
        
        # Extract sentences containing value indicators
        sentences = all_text.split('.')
        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            if any(keyword in sentence_lower for keyword in problem_keywords):
                elements['problems_solved'].append(sentence.strip())
            
            if any(keyword in sentence_lower for keyword in benefit_keywords):
                elements['benefits'].append(sentence.strip())
            
            if any(keyword in sentence_lower for keyword in unique_keywords):
                elements['unique_aspects'].append(sentence.strip())
        
        # Use provided features
        elements['features'] = content.get('features', [])[:5]
        
        return elements
    
    def _generate_value_proposition_from_elements(self, elements: Dict, content: Dict) -> str:
        """Generate a value proposition from extracted elements"""
        
        # Start with company name and what they do
        company = content.get('company_name', 'We')
        industry = content.get('detected_industry', '')
        
        # Identify main action verb
        if elements['benefits']:
            # Extract action from first benefit
            first_benefit = elements['benefits'][0] if elements['benefits'] else ''
            action_verbs = ['helps', 'enables', 'empowers', 'provides', 'delivers', 'offers']
            main_verb = 'helps'  # default
            
            for verb in ['increase', 'improve', 'enhance', 'boost', 'optimize', 'save', 'reduce']:
                if verb in first_benefit.lower():
                    main_verb = f"helps businesses {verb}"
                    break
        else:
            main_verb = 'provides'
        
        # Construct value prop
        if elements['problems_solved']:
            # Problem-focused value prop
            problem = elements['problems_solved'][0].lower()
            if 'solve' in problem:
                problem_phrase = problem.split('solve')[-1].strip()
            else:
                problem_phrase = 'business challenges'
            
            value_prop = f"{company} {main_verb} {problem_phrase}"
        
        elif elements['benefits']:
            # Benefit-focused value prop
            top_benefits = elements['benefits'][:2]
            benefit_phrase = ' and '.join([b.split('.')[-1].strip() for b in top_benefits])
            value_prop = f"{company} {main_verb} {benefit_phrase}"
        
        elif content.get('meta_description'):
            # Use meta description as base
            value_prop = content['meta_description']
        
        else:
            # Generic based on industry
            industry_value = {
                'technology': 'innovative software solutions that drive digital transformation',
                'finance': 'financial solutions that maximize returns and minimize risk',
                'healthcare': 'healthcare solutions that improve patient outcomes',
                'retail': 'retail solutions that enhance customer experience',
                'marketing': 'marketing solutions that drive growth and engagement',
                'default': 'solutions that drive business success'
            }
            value_prop = f"{company} provides {industry_value.get(industry, industry_value['default'])}"
        
        # Clean up and limit length
        value_prop = re.sub(r'\s+', ' ', value_prop).strip()
        if len(value_prop) > 150:
            value_prop = value_prop[:147] + '...'
        
        return value_prop
    
    def _generate_elevator_pitch_from_elements(self, elements: Dict, content: Dict) -> str:
        """Generate an elevator pitch from extracted elements"""
        
        company = content.get('company_name', 'We')
        industry = content.get('detected_industry', '')
        
        # Build pitch components
        intro = f"{company} is a {industry} company that "
        
        # What we do
        if content.get('meta_description'):
            what_we_do = content['meta_description'].split('.')[0]
        else:
            what_we_do = f"provides innovative {industry} solutions"
        
        # Who we serve
        target = self._identify_target_market(content)
        if target:
            who_we_serve = f" We serve {target}"
        else:
            who_we_serve = " We serve businesses looking to grow"
        
        # Key differentiator
        if elements['unique_aspects']:
            differentiator = f" What sets us apart is {elements['unique_aspects'][0].lower()}"
        elif elements['benefits']:
            differentiator = f" Our clients typically see {elements['benefits'][0].lower()}"
        else:
            differentiator = " We focus on delivering measurable results"
        
        # Combine into pitch
        elevator_pitch = f"{intro}{what_we_do}.{who_we_serve}.{differentiator}."
        
        # Clean up
        elevator_pitch = re.sub(r'\s+', ' ', elevator_pitch).strip()
        elevator_pitch = elevator_pitch.replace('..', '.')
        
        # Limit to ~30 seconds of speech (~75-100 words)
        words = elevator_pitch.split()
        if len(words) > 75:
            elevator_pitch = ' '.join(words[:75]) + '...'
        
        return elevator_pitch
    
    def _extract_differentiators(self, content: Dict) -> List[str]:
        """Extract key differentiators from website content"""
        differentiators = []
        
        # Look in features for unique aspects
        for feature in content.get('features', []):
            feature_lower = feature.lower()
            if any(word in feature_lower for word in ['unique', 'only', 'first', 'exclusive', 'proprietary']):
                differentiators.append(feature)
        
        # Look in headings for differentiators
        for heading in content.get('headings', []):
            heading_lower = heading.lower()
            if any(word in heading_lower for word in ['why choose', 'why us', 'different', 'advantage']):
                differentiators.append(heading)
        
        # If no explicit differentiators, extract from benefits
        if not differentiators and content.get('features'):
            differentiators = content['features'][:3]
        
        return differentiators[:5]  # Limit to 5
    
    def _identify_target_market(self, content: Dict) -> str:
        """Identify target market from website content"""
        
        all_text = f"{content.get('main_text', '')} {content.get('about_text', '')}"
        all_text_lower = all_text.lower()
        
        # Look for target market indicators
        market_patterns = [
            (r'for (small|medium|large|enterprise) businesses', 'businesses'),
            (r'for (startups|entrepreneurs)', 'startups and entrepreneurs'),
            (r'for (agencies|consultants)', 'agencies and consultants'),
            (r'for (developers|engineers)', 'developers and technical teams'),
            (r'for (marketers|marketing teams)', 'marketing professionals'),
            (r'for (sales teams|sales professionals)', 'sales teams'),
            (r'for (healthcare|medical) professionals', 'healthcare professionals'),
            (r'for (educators|teachers)', 'educators'),
            (r'for (ecommerce|online) (stores|retailers)', 'ecommerce businesses')
        ]
        
        for pattern, market in market_patterns:
            if re.search(pattern, all_text_lower):
                return market
        
        # Industry-based default
        industry_markets = {
            'technology': 'innovative companies',
            'finance': 'financial institutions and investors',
            'healthcare': 'healthcare providers',
            'retail': 'retail businesses',
            'marketing': 'growth-focused companies',
            'education': 'educational institutions'
        }
        
        industry = content.get('detected_industry', '')
        return industry_markets.get(industry, 'forward-thinking organizations')
    
    def _extract_products_services(self, content: Dict) -> List[Dict]:
        """Extract products and services from website content"""
        products = []
        
        # Look for product/service mentions in headings
        for heading in content.get('headings', []):
            heading_lower = heading.lower()
            if any(word in heading_lower for word in ['product', 'service', 'solution', 'platform', 'tool']):
                products.append({
                    'name': heading,
                    'description': ''
                })
        
        # Extract from features
        for feature in content.get('features', [])[:10]:
            # Simple heuristic: if it's a noun phrase, might be a product/service
            if len(feature.split()) < 10:  # Short enough to be a product name
                products.append({
                    'name': feature.split('-')[0].strip() if '-' in feature else feature,
                    'description': feature
                })
        
        # Deduplicate and limit
        seen = set()
        unique_products = []
        for product in products:
            if product['name'] not in seen:
                seen.add(product['name'])
                unique_products.append(product)
        
        return unique_products[:5]


@router.get("/")
async def get_sales_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get sales dashboard summary for UI"""
    dashboard = SalesDashboard(db, current_user)
    
    # Get basic metrics
    overview = dashboard.get_dashboard_overview()
    pipeline = dashboard.get_revenue_pipeline()
    analytics = dashboard.get_engagement_analytics()
    
    # Format for UI
    return {
        "open_leads": overview.get("total_emails", 0),
        "active_deals": len(pipeline.get("active_deals", [])),
        "followups_today": overview.get("unread_count", 0),
        "pipeline": [
            {
                "name": stage,
                "count": count,
                "percentage": (count / max(sum(pipeline["conversion_funnel"].values()), 1)) * 100,
                "value": count * 5000  # Example value
            }
            for stage, count in pipeline["conversion_funnel"].items()
        ],
        "recent_activity": [
            {
                "description": f"New email from {email.get('sender_name', 'Unknown')}",
                "time": email.get('received_at', 'Recently'),
                "icon": "fa-envelope",
                "color": "blue"
            }
            for email in analytics.get("emails", [])[:5]
        ]
    }


@router.get("/overview")
async def get_dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get complete dashboard overview"""
    dashboard = SalesDashboard(db, current_user)
    
    return {
        "revenue_pipeline": dashboard.get_revenue_pipeline(),
        "opportunity_scores": dashboard.get_opportunity_scores()[:5],  # Top 5
        "action_queue": dashboard.get_action_priority_queue()[:5],  # Top 5
        "revenue_alerts": dashboard.get_revenue_leakage_alerts()[:3],  # Top 3
        "ai_recommendations": dashboard.get_ai_recommendations()[:3]  # Top 3
    }


@router.get("/pipeline")
async def get_revenue_pipeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get revenue pipeline details"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_revenue_pipeline()


@router.get("/opportunities")
async def get_opportunities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get scored opportunities"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_opportunity_scores()


@router.get("/analytics")
async def get_engagement_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get engagement analytics"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_engagement_analytics()


@router.get("/actions")
async def get_action_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get prioritized action queue"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_action_priority_queue()


@router.get("/alerts")
async def get_revenue_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get revenue leakage alerts"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_revenue_leakage_alerts()


@router.get("/quick-actions")
async def get_quick_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get quick action templates"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_quick_actions()


@router.get("/insights")
async def get_profit_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get profit insights"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_profit_insights()


@router.get("/recommendations")
async def get_ai_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get AI recommendations"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_ai_recommendations()


@router.get("/followup-sequences")
async def get_followup_sequences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get client follow-up sequences with AI-powered nudges"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_client_followup_sequences()


@router.post("/followup-sequences/send")
async def send_followup(
    request_data: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send a follow-up email to a client"""
    try:
        client_email = request_data.get("client_email")
        message = request_data.get("message")
        subject = request_data.get("subject")

        if not all([client_email, message, subject]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Initialize email service
        outlook_service = OutlookService()

        # Send email
        success = outlook_service.send_email(
            user=current_user,
            to=[client_email],
            subject=subject,
            body=message,
            db=db
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to send email")

        # Store sent email in database
        sent_email = Email(
            user_id=current_user.id,
            subject=subject,
            sender=current_user.email,
            sender_name=current_user.name,
            recipients=[{"email": client_email}],
            body_text=message,
            body_html=message if '<' in message else None,
            is_sent=True,
            is_read=True,
            received_at=datetime.utcnow()
        )
        db.add(sent_email)
        db.commit()

        return {
            "status": "success",
            "message": f"Follow-up sent to {client_email}",
            "scheduled": False,
            "sent_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error sending follow-up: {e}")
        raise HTTPException(status_code=500, detail=f"Error sending follow-up: {str(e)}")


@router.get("/proposals")
async def get_proposals(
    template_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate sales proposals from CRM data"""
    try:
        dashboard = SalesDashboard(db, current_user)
        return dashboard.generate_proposals(template_id)
    except Exception as e:
        logger.error(f"Error generating proposals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating proposals: {str(e)}")


@router.post("/proposals/{proposal_id}/send")
async def send_proposal(
    proposal_id: str,
    request_data: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send a proposal to a client"""
    try:
        recipient_email = request_data.get("recipient_email")
        if not recipient_email:
            raise HTTPException(status_code=400, detail="Recipient email is required")

        # Get the proposal (in this case, we'll generate it fresh - in production you'd store these)
        dashboard = SalesDashboard(db, current_user)
        proposals_data = dashboard.generate_proposals()

        # Find the proposal by ID
        proposal = None
        for p in proposals_data.get("proposals", []):
            if p["id"] == proposal_id:
                proposal = p
                break

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        # Generate email body with proposal details
        email_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2>Proposal for {proposal['client']}</h2>

    <p>Dear {proposal['client']},</p>

    <p>Thank you for your interest. Please find our proposal below:</p>

    <h3>Proposed Solution</h3>
    <p>{proposal['proposed_solution']['overview']}</p>

    <h3>Key Benefits</h3>
    <ul>
        {''.join([f"<li>{benefit}</li>" for benefit in proposal['proposed_solution']['benefits']])}
    </ul>

    <h3>Pricing Options</h3>
    {_format_pricing_html(proposal['pricing'])}

    <h3>Timeline</h3>
    <p>{proposal['timeline'].get('overview', 'We can discuss timeline details during our next conversation.')}</p>

    <p>Please review this proposal at your convenience. I'm available to discuss any questions you may have.</p>

    <p>Best regards,<br>
    {current_user.name or current_user.email}</p>
</body>
</html>
"""

        # Initialize email service
        outlook_service = OutlookService()

        # Send email
        success = outlook_service.send_email(
            user=current_user,
            to=[recipient_email],
            subject=f"Proposal: {proposal['client_info'].get('company', 'Your Business')}",
            body=email_body,
            db=db
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to send proposal email")

        # Store sent email in database
        sent_email = Email(
            user_id=current_user.id,
            subject=f"Proposal: {proposal['client_info'].get('company', 'Your Business')}",
            sender=current_user.email,
            sender_name=current_user.name,
            recipients=[{"email": recipient_email}],
            body_text="Proposal sent",
            body_html=email_body,
            is_sent=True,
            is_read=True,
            received_at=datetime.utcnow()
        )
        db.add(sent_email)
        db.commit()

        return {
            "status": "success",
            "proposal_id": proposal_id,
            "sent_to": recipient_email,
            "sent_at": datetime.utcnow().isoformat(),
            "tracking_enabled": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error sending proposal: {e}")
        raise HTTPException(status_code=500, detail=f"Error sending proposal: {str(e)}")


@router.post("/proposals/{proposal_id}/export")
async def export_proposal(
    proposal_id: str,
    request_data: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export a proposal in various formats"""
    try:
        format = request_data.get("format", "pdf")

        # Get the proposal
        dashboard = SalesDashboard(db, current_user)
        proposals_data = dashboard.generate_proposals()

        # Find the proposal by ID
        proposal = None
        for p in proposals_data.get("proposals", []):
            if p["id"] == proposal_id:
                proposal = p
                break

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        # Build HTML parts separately to avoid nested f-string issues
        def format_requirements(reqs):
            items = []
            for req in reqs[:5]:
                cat = req.get('category', 'General')
                desc = req.get('description', '')[:150]
                items.append(f"<li><strong>{cat}:</strong> {desc}</li>")
            return ''.join(items)

        def format_list_items(items):
            return ''.join(f"<li>{item}</li>" for item in items)

        def format_pricing_options(options):
            html_parts = []
            for opt in options:
                rec_class = 'recommended' if opt.get('recommended') else ''
                rec_label = '  (Recommended)' if opt.get('recommended') else ''
                price = f"${opt['price']:,}"
                features = ''.join(f"<li>{f}</li>" for f in opt.get('features', []))
                html_parts.append(f'''
        <div class="pricing-option {rec_class}">
            <h3>{opt['name']}{rec_label}</h3>
            <div class="price">{price}</div>
            <ul>{features}</ul>
        </div>''')
            return ''.join(html_parts)

        def format_timeline_phases(phases):
            return ''.join(
                f"<p><strong>{p['name']}:</strong> {p.get('duration', 'TBD')}</p>"
                for p in phases[:4]
            )

        # Build the HTML content
        requirements_html = format_requirements(proposal.get('requirements', []))
        benefits_html = format_list_items(proposal['proposed_solution']['benefits'])
        differentiators_html = format_list_items(proposal['proposed_solution']['differentiators'])
        pricing_html = format_pricing_options(proposal['pricing'].get('options', []))
        timeline_overview = proposal['timeline'].get('overview', 'We will work with you to establish a timeline that meets your needs.')
        timeline_phases_html = format_timeline_phases(proposal['timeline'].get('phases', []))
        user_name = current_user.name or current_user.email
        date_str = datetime.utcnow().strftime('%B %d, %Y')

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 40px; }}
        h1 {{ color: #2563eb; border-bottom: 3px solid #2563eb; padding-bottom: 10px; }}
        h2 {{ color: #1e40af; margin-top: 30px; }}
        h3 {{ color: #1e3a8a; }}
        .header {{ background: #eff6ff; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
        .section {{ margin: 30px 0; }}
        .pricing-option {{ border: 2px solid #ddd; padding: 20px; margin: 15px 0; border-radius: 8px; }}
        .pricing-option.recommended {{ border-color: #2563eb; background: #eff6ff; }}
        .price {{ font-size: 32px; color: #2563eb; font-weight: bold; margin: 10px 0; }}
        ul {{ line-height: 1.8; }}
        .footer {{ margin-top: 50px; padding-top: 20px; border-top: 2px solid #ddd; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Business Proposal</h1>
        <p><strong>For:</strong> {proposal['client']}</p>
        <p><strong>From:</strong> {user_name}</p>
        <p><strong>Date:</strong> {date_str}</p>
    </div>

    <div class="section">
        <h2>Executive Summary</h2>
        <p>{proposal['proposed_solution']['overview']}</p>
    </div>

    <div class="section">
        <h2>Client Requirements</h2>
        <ul>{requirements_html}</ul>
    </div>

    <div class="section">
        <h2>Proposed Solution</h2>
        <h3>Key Benefits</h3>
        <ul>{benefits_html}</ul>
        <h3>Differentiators</h3>
        <ul>{differentiators_html}</ul>
    </div>

    <div class="section">
        <h2>Pricing Options</h2>
        {pricing_html}
    </div>

    <div class="section">
        <h2>Timeline</h2>
        <p>{timeline_overview}</p>
        {timeline_phases_html}
    </div>

    <div class="section">
        <h2>Next Steps</h2>
        <ol>
            <li>Review this proposal and select your preferred option</li>
            <li>Schedule a call to discuss any questions</li>
            <li>Sign the agreement and begin implementation</li>
        </ol>
    </div>

    <div class="footer">
        <p>This proposal is valid for 30 days from the date above.</p>
        <p>For questions, please contact {user_name} at {current_user.email}</p>
    </div>
</body>
</html>
"""

        if format == "pdf":
            # Generate PDF using weasyprint
            try:
                from weasyprint import HTML, CSS
                import tempfile
                import os

                # Create temporary directory for PDFs
                pdf_dir = "static/downloads/proposals"
                os.makedirs(pdf_dir, exist_ok=True)

                # Generate PDF
                pdf_filename = f"{proposal_id}.pdf"
                pdf_path = os.path.join(pdf_dir, pdf_filename)

                HTML(string=html_content).write_pdf(pdf_path)

                return {
                    "status": "success",
                    "proposal_id": proposal_id,
                    "format": format,
                    "download_url": f"/downloads/proposals/{pdf_filename}",
                    "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat()
                }

            except ImportError:
                # Fallback if weasyprint is not available
                logger = logging.getLogger(__name__)
                logger.warning("WeasyPrint not available, returning HTML")
                return {
                    "status": "success",
                    "proposal_id": proposal_id,
                    "format": "html",
                    "content": html_content,
                    "message": "PDF generation not available, returning HTML"
                }

        elif format == "html":
            return {
                "status": "success",
                "proposal_id": proposal_id,
                "format": "html",
                "content": html_content
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    except HTTPException:
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error exporting proposal: {e}")
        raise HTTPException(status_code=500, detail=f"Error exporting proposal: {str(e)}")


@router.get("/business-profile")
async def get_business_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get or create business profile"""
    dashboard = SalesDashboard(db, current_user)
    return dashboard.get_business_profile()


@router.post("/business-profile")
async def update_business_profile(
    profile_data: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update business profile"""
    try:
        profile = db.query(BusinessProfile).filter(
            BusinessProfile.user_id == current_user.id
        ).first()

        if not profile:
            profile = BusinessProfile(user_id=current_user.id)
            db.add(profile)

        # Update fields
        for key, value in profile_data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        profile.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(profile)

        return {"status": "success", "profile_id": profile.id, "message": "Profile saved successfully"}

    except Exception as e:
        logger.error(f"Error saving business profile: {e}")
        db.rollback()
        return {"status": "error", "message": str(e)}


@router.post("/scrape-profile")
async def scrape_profile_from_website(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Scrape company website and use AI to extract business profile data.
    This is the enhanced Quick Setup feature.
    """
    from core.profile_scraper import scrape_and_analyze_profile

    website_url = request.get("website_url", "")
    if not website_url:
        raise HTTPException(status_code=400, detail="Website URL is required")

    try:
        # Initialize Bedrock client if available
        bedrock_client = None
        try:
            import boto3
            bedrock_client = boto3.client(
                'bedrock-runtime',
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
        except Exception as e:
            logger.warning(f"Bedrock client not available: {e}")

        # Scrape and analyze the website
        result = await scrape_and_analyze_profile(website_url, bedrock_client)

        if result.get("success"):
            return {
                "success": True,
                "profile_data": result.get("profile_data", {}),
                "scraped_pages": result.get("scraped_pages", []),
                "errors": result.get("errors", [])
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to analyze website")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scraping profile: {e}")
        raise HTTPException(status_code=500, detail=f"Error analyzing website: {str(e)}")


@router.post("/analyze-website")
async def analyze_website(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Analyze website to generate business profile content"""
    dashboard = SalesDashboard(db, current_user)
    
    website_url = request.get("url", "")
    if not website_url:
        raise HTTPException(status_code=400, detail="Website URL is required")
    
    # Scrape website content
    website_content = dashboard.scrape_website_content(website_url)
    
    if 'error' in website_content:
        return {
            "success": False,
            "error": website_content['error'],
            "message": "Failed to access website. Please check the URL and try again."
        }
    
    # Generate value proposition and other content
    generated_content = dashboard.generate_value_prop_from_website(website_content)
    
    return {
        "success": True,
        "generated_content": generated_content,
        "website_info": {
            "title": website_content.get('title', ''),
            "meta_description": website_content.get('meta_description', ''),
            "detected_industry": website_content.get('detected_industry', '')
        }
    }


@router.post("/cold-emails/generate")
async def generate_cold_emails(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate cold emails for prospects"""
    dashboard = SalesDashboard(db, current_user)
    
    prospects = request.get("prospects", [])
    campaign_type = request.get("campaign_type", "lead_generation")
    
    return dashboard.generate_cold_emails(prospects, campaign_type)


@router.post("/cold-emails/send")
async def send_reviewed_emails(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send manually reviewed and approved cold emails"""
    try:
        emails = request.get("emails", [])
        sent_count = 0
        failed_count = 0

        # Initialize email service
        outlook_service = OutlookService()

        for email_data in emails:
            try:
                # Extract prospect and email info
                prospect_info = email_data.get("prospect", {})
                email_content = email_data.get("email", {})
                review_status = email_data.get("review_status", "")

                # Only send approved or edited emails
                if review_status not in ["approved", "edited"]:
                    continue

                recipient_email = prospect_info.get("email")
                subject = email_content.get("subject")
                body = email_content.get("body")

                if not all([recipient_email, subject, body]):
                    failed_count += 1
                    continue

                # Send email via Outlook service
                success = outlook_service.send_email(
                    user=current_user,
                    to=[recipient_email],
                    subject=subject,
                    body=body,
                    db=db
                )

                if success:
                    # Store sent email in database
                    sent_email = Email(
                        user_id=current_user.id,
                        subject=subject,
                        sender=current_user.email,
                        sender_name=current_user.name,
                        recipients=[{"email": recipient_email}],
                        body_text=body,
                        body_html=body if '<' in body else None,
                        is_sent=True,
                        is_read=True,
                        received_at=datetime.utcnow()
                    )
                    db.add(sent_email)
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send email to {prospect_info.get('email', 'unknown')}: {str(e)}")
                failed_count += 1

        # Commit all sent emails
        db.commit()

        return {
            "status": "success",
            "emails_sent": sent_count,
            "emails_failed": failed_count,
            "message": f"Successfully sent {sent_count} emails, {failed_count} failed"
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in cold email sending: {e}")
        raise HTTPException(status_code=500, detail=f"Error sending cold emails: {str(e)}")


@router.post("/cold-emails/send/{campaign_id}")
async def send_cold_emails(
    campaign_id: str,
    request_data: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send cold emails from a campaign"""
    try:
        email_ids = request_data.get("email_ids", [])
        sent_count = 0
        failed_count = 0

        # Initialize email service
        outlook_service = OutlookService()

        for email_id in email_ids:
            try:
                prospect = db.query(ColdEmailProspect).filter(
                    ColdEmailProspect.id == email_id,
                    ColdEmailProspect.campaign_id == campaign_id
                ).first()

                if not prospect or not prospect.generated_body:
                    failed_count += 1
                    continue

                # Send email
                success = outlook_service.send_email(
                    user=current_user,
                    to=[prospect.email],
                    subject=prospect.generated_subject or "Business Inquiry",
                    body=prospect.generated_body,
                    db=db
                )

                if success:
                    # Update prospect status
                    prospect.email_status = "sent"
                    prospect.email_sent_at = datetime.utcnow()

                    # Store sent email in database
                    sent_email = Email(
                        user_id=current_user.id,
                        subject=prospect.generated_subject or "Business Inquiry",
                        sender=current_user.email,
                        sender_name=current_user.name,
                        recipients=[{"email": prospect.email}],
                        body_text=prospect.generated_body,
                        body_html=prospect.generated_body if '<' in prospect.generated_body else None,
                        is_sent=True,
                        is_read=True,
                        received_at=datetime.utcnow()
                    )
                    db.add(sent_email)
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send email to prospect {email_id}: {str(e)}")
                failed_count += 1

        # Update campaign metrics
        campaign = db.query(ColdEmailCampaign).filter(ColdEmailCampaign.id == campaign_id).first()
        if campaign:
            campaign.emails_sent = (campaign.emails_sent or 0) + sent_count

        db.commit()

        return {
            "status": "success",
            "emails_sent": sent_count,
            "emails_failed": failed_count,
            "campaign_id": campaign_id
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error sending campaign emails: {e}")
        raise HTTPException(status_code=500, detail=f"Error sending campaign emails: {str(e)}")


@router.post("/parse-prospects")
async def parse_prospects_text(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Smart parse text to extract prospect information"""
    text = request.get("text", "")
    
    dashboard = SalesDashboard(db, current_user)
    prospects = dashboard.parse_prospects_from_text(text)
    
    return {"prospects": prospects}


@router.post("/extract-contacts")
async def extract_contacts_from_inbox(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Extract contacts from user's inbox"""
    include_sent = request.get("include_sent", True)
    include_received = request.get("include_received", True)
    days_back = request.get("days_back", 30)
    
    dashboard = SalesDashboard(db, current_user)
    prospects = dashboard.extract_contacts_from_emails(
        include_sent, include_received, days_back
    )
    
    return {"prospects": prospects}


@router.get("/cold-emails/campaigns")
async def get_campaigns(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all cold email campaigns"""
    campaigns = db.query(ColdEmailCampaign).filter(
        ColdEmailCampaign.user_id == current_user.id
    ).order_by(ColdEmailCampaign.created_at.desc()).all()
    
    return [{
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "total_prospects": c.total_prospects,
        "emails_sent": c.emails_sent,
        "emails_opened": c.emails_opened,
        "emails_responded": c.emails_responded,
        "created_at": c.created_at.isoformat()
    } for c in campaigns]


@router.post("/execute-action/{action_id}")
async def execute_action(
    action_id: str,
    action_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute a suggested action"""
    # This would handle executing quick actions, sending emails, etc.
    return {"status": "success", "message": f"Action {action_id} executed"}


# =============================================================================
# Sales Intelligence Endpoints
# =============================================================================

@router.get("/lead-scores")
async def get_lead_scores(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get lead qualification scores using BANT framework.
    Analyzes emails to determine lead quality.
    """
    # Get recent incoming emails (potential leads)
    emails = db.query(Email).filter(
        Email.user_id == current_user.id,
        Email.deleted_at.is_(None),
        Email.is_sent != True,
        Email.received_at >= datetime.utcnow() - timedelta(days=30)
    ).order_by(desc(Email.received_at)).limit(100).all()

    qualified_leads = []
    needs_nurturing = []
    cold_leads = []

    budget_confirmed = 0
    authority_confirmed = 0
    need_identified = 0
    timeline_set = 0

    for email in emails:
        content = email.body_text or email.body_html or ""
        if not content:
            continue

        # Analyze lead quality
        sender_info = {
            "title": "",  # Would need to extract from signature
            "email": email.sender
        }
        result = sales_analyzer.analyze_lead_quality(content, sender_info)

        lead_data = {
            "email_id": str(email.id),
            "sender": email.sender,
            "sender_name": email.sender_name or email.sender,
            "subject": email.subject,
            "received_at": email.received_at.isoformat(),
            "overall_score": result.overall_score,
            "qualification_level": result.qualification_level,
            "bant_scores": {
                "budget": result.bant_score.budget,
                "authority": result.bant_score.authority,
                "need": result.bant_score.need,
                "timeline": result.bant_score.timeline
            },
            "signals": result.signals[:5],  # Top 5 signals
            "recommendations": result.recommendations,
            "confidence": result.confidence
        }

        # Categorize and count
        if result.bant_score.budget >= 40:
            budget_confirmed += 1
        if result.bant_score.authority >= 40:
            authority_confirmed += 1
        if result.bant_score.need >= 40:
            need_identified += 1
        if result.bant_score.timeline >= 40:
            timeline_set += 1

        if result.overall_score >= 60:
            qualified_leads.append(lead_data)
        elif result.overall_score >= 30:
            needs_nurturing.append(lead_data)
        else:
            cold_leads.append(lead_data)

    return {
        "qualified_leads": qualified_leads[:20],
        "needs_nurturing": needs_nurturing[:20],
        "cold_leads": cold_leads[:10],
        "qualification_breakdown": {
            "budget_confirmed": budget_confirmed,
            "authority_confirmed": authority_confirmed,
            "need_identified": need_identified,
            "timeline_set": timeline_set
        },
        "total_analyzed": len(emails)
    }


@router.get("/objections")
async def get_objections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detected objections from emails with suggested responses.
    """
    # Get recent incoming emails
    emails = db.query(Email).filter(
        Email.user_id == current_user.id,
        Email.deleted_at.is_(None),
        Email.is_sent != True,
        Email.received_at >= datetime.utcnow() - timedelta(days=30)
    ).order_by(desc(Email.received_at)).limit(100).all()

    objection_counts = defaultdict(int)
    active_objections = []
    all_objections_by_type = defaultdict(list)

    for email in emails:
        content = email.body_text or email.body_html or ""
        if not content:
            continue

        # Detect objections
        objections = sales_analyzer.detect_objections(content)

        for obj in objections:
            objection_counts[obj.type.value] += 1
            all_objections_by_type[obj.type.value].append(obj)

            active_objections.append({
                "email_id": str(email.id),
                "sender": email.sender,
                "sender_name": email.sender_name or email.sender,
                "subject": email.subject,
                "received_at": email.received_at.isoformat(),
                "objection_type": obj.type.value,
                "exact_quote": obj.exact_quote[:200],
                "confidence": obj.confidence,
                "severity": obj.severity,
                "suggested_responses": obj.suggested_responses[:2]
            })

    # Build common objections summary
    common_objections = []
    for obj_type, count in sorted(objection_counts.items(), key=lambda x: -x[1]):
        common_objections.append({
            "type": obj_type,
            "count": count,
            "win_rate": 0.3 if obj_type == "price" else 0.5  # Would calculate from historical data
        })

    # Get suggested responses by type
    suggested_responses = {}
    for obj_type in ObjectionType:
        if obj_type.value in all_objections_by_type:
            suggested_responses[obj_type.value] = sales_analyzer.OBJECTION_RESPONSES.get(obj_type, [])[:2]

    return {
        "common_objections": common_objections,
        "active_objections": active_objections[:20],
        "suggested_responses": suggested_responses,
        "total_objections": sum(objection_counts.values())
    }


@router.get("/sequences")
async def get_sequences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get email sequence tracking for prospects.
    Shows where each prospect is in the follow-up sequence.
    """
    # Get all emails grouped by sender (as prospects)
    emails = db.query(Email).filter(
        Email.user_id == current_user.id,
        Email.deleted_at.is_(None),
        Email.received_at >= datetime.utcnow() - timedelta(days=60)
    ).order_by(Email.sender, Email.received_at).all()

    # Group by sender
    prospect_emails = defaultdict(list)
    for email in emails:
        prospect_emails[email.sender].append({
            "id": str(email.id),
            "subject": email.subject,
            "received_at": email.received_at,
            "is_sent": email.is_sent or False,
            "is_opened": False,  # Would need tracking
            "sender_name": email.sender_name
        })

    active_sequences = []
    for prospect_email, emails_list in prospect_emails.items():
        # Skip if only one email or it's a newsletter
        if len(emails_list) < 1:
            continue

        # Analyze sequence
        sequence = sequence_manager.analyze_prospect_sequence(emails_list, prospect_email)

        # Skip stalled or completed sequences for active list
        if sequence.current_stage != SequenceStage.FINAL_REMINDER:
            active_sequences.append({
                "prospect": prospect_email,
                "prospect_name": sequence.prospect_name or prospect_email.split("@")[0],
                "company": sequence.company,
                "current_stage": sequence.stage_number,
                "stage_name": sequence.current_stage.value,
                "emails_sent": sequence.emails_sent,
                "emails_replied": sequence.emails_replied,
                "days_since_last": sequence.days_since_last,
                "next_action": sequence.next_action,
                "next_email_due": sequence.next_email_due.isoformat() if sequence.next_email_due else None,
                "is_stalled": sequence.is_stalled,
                "risk_level": sequence.risk_level,
                "open_rate": sequence.emails_opened / max(sequence.emails_sent, 1),
                "reply_rate": sequence.emails_replied / max(sequence.emails_sent, 1)
            })

    # Sort by next action urgency
    active_sequences.sort(key=lambda x: (x["is_stalled"], -x["days_since_last"]), reverse=True)

    # Calculate performance metrics
    all_sequences = [
        sequence_manager.analyze_prospect_sequence(emails_list, email)
        for email, emails_list in prospect_emails.items()
    ]
    performance = sequence_manager.get_sequence_performance(all_sequences)

    return {
        "active_sequences": active_sequences[:30],
        "sequence_performance": {
            "total_prospects": performance.total_prospects,
            "active_prospects": performance.active_prospects,
            "completed_sequences": performance.completed_sequences,
            "avg_open_rate": performance.avg_open_rate,
            "avg_reply_rate": performance.avg_reply_rate,
            "avg_meeting_rate": performance.avg_meeting_rate
        },
        "stage_templates": [
            sequence_manager.get_stage_guidance(stage)
            for stage in SequenceStage
        ]
    }


@router.post("/analyze-email/{email_id}")
async def analyze_email_sales_intelligence(
    email_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive sales intelligence analysis for a specific email.
    """
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    content = email.body_text or email.body_html or ""

    # Get thread emails for context
    thread_emails = []
    if email.thread_id:
        thread_emails = db.query(Email).filter(
            Email.user_id == current_user.id,
            Email.thread_id == email.thread_id
        ).order_by(Email.received_at).all()

    thread_data = [
        {
            "body_text": e.body_text,
            "body_html": e.body_html,
            "received_at": e.received_at.isoformat(),
            "sender": e.sender,
            "is_sent": e.is_sent or False
        }
        for e in thread_emails
    ]

    # Run comprehensive analysis
    analysis = sales_analyzer.get_comprehensive_analysis(
        email_content=content,
        email_thread=thread_data,
        sender_info={"email": email.sender, "name": email.sender_name},
        last_activity_date=email.received_at
    )

    return {
        "email_id": email_id,
        "subject": email.subject,
        "sender": email.sender,
        "analysis": analysis
    }


@router.post("/generate-subject-lines")
async def generate_subject_lines(
    context: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate optimized subject line suggestions for an email.

    Context can include:
    - first_name, company, role, industry
    - topic, pain_point, goal
    - previous_interaction
    - similar_company, result (for social proof)
    """
    count = context.pop("count", 5)
    suggestions = smart_composer.generate_subject_lines(context, count=count)

    return {
        "suggestions": [
            {
                "text": s.text,
                "category": s.category.value,
                "estimated_open_rate": s.estimated_open_rate,
                "word_count": s.word_count,
                "personalized": s.personalized
            }
            for s in suggestions
        ]
    }


@router.post("/suggest-cta")
async def suggest_cta(
    stage: str,
    context: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get CTA suggestions appropriate for the conversation stage.

    Stages: cold_outreach, engaged, discovery, evaluation, proposal, negotiation, closing
    """
    suggestions = smart_composer.suggest_cta(stage, context or {})

    return {
        "stage": stage,
        "suggestions": [
            {
                "text": s.text,
                "strength": s.strength.value,
                "action_type": s.action_type,
                "estimated_click_rate": s.estimated_click_rate
            }
            for s in suggestions
        ]
    }


@router.post("/compose-sequence-email")
async def compose_sequence_email(
    stage: str,
    context: Dict[str, Any],
    personalization_level: str = "medium",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compose a complete email for a specific sequence stage.

    Stages: value_email, problem_agitation, solution_email, social_proof, direct_offer, final_reminder
    """
    # Map string to enum
    level_map = {
        "basic": PersonalizationLevel.BASIC,
        "medium": PersonalizationLevel.MEDIUM,
        "advanced": PersonalizationLevel.ADVANCED
    }
    level = level_map.get(personalization_level, PersonalizationLevel.MEDIUM)

    # Add sender name from user
    context["sender_name"] = current_user.name or current_user.email.split("@")[0]

    draft = smart_composer.compose_sequence_email(stage, context, level)

    # Analyze the draft quality
    quality = smart_composer.analyze_email_quality(draft)

    return {
        "draft": {
            "subject": draft.subject,
            "body": draft.body,
            "cta_text": draft.cta_text,
            "personalization_level": draft.personalization_level.value,
            "sequence_stage": draft.sequence_stage
        },
        "quality_analysis": quality,
        "stage_guidance": sequence_manager.get_stage_guidance(
            SequenceStage(stage) if stage in [s.value for s in SequenceStage] else SequenceStage.VALUE_EMAIL
        )
    }


@router.get("/sequence-templates")
async def get_sequence_templates(
    current_user: User = Depends(get_current_user)
):
    """
    Get all email sequence stage templates with guidance.
    """
    templates = []
    for stage in SequenceStage:
        guidance = sequence_manager.get_stage_guidance(stage)
        templates.append(guidance)

    return {
        "templates": templates,
        "sequence_timing": {
            stage.value: sequence_manager.SEQUENCE_TIMING[stage]
            for stage in SequenceStage
        }
    }


@router.post("/suggest-resend")
async def suggest_resend(
    email_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Suggest a resend strategy for non-openers (10-25% revenue boost).
    Changes subject line, resends 48-72 hours later.
    """
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    # Get recipient info
    recipient_email = email.recipients[0] if email.recipients else ""
    first_name = ""
    if recipient_email:
        name_part = recipient_email.split("@")[0]
        if "." in name_part:
            first_name = name_part.split(".")[0].title()

    suggestion = sequence_manager.suggest_resend_for_non_opener(
        {
            "subject": email.subject,
            "body": email.body_text
        },
        {
            "first_name": first_name,
            "email": recipient_email
        }
    )

    return suggestion


@router.post("/smart-templates")
async def generate_smart_templates(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate context-aware email templates based on conversation history with a recipient.
    Returns AI-generated suggestions tailored to the relationship and recent discussions.
    """
    recipient_email = request.get("recipient_email", "").strip().lower()
    tone = request.get("tone", "professional")  # professional, friendly, formal

    if not recipient_email:
        return {
            "templates": [],
            "context": None,
            "message": "No recipient specified"
        }

    # Get conversation history with this recipient
    conversations = db.query(Email).filter(
        Email.user_id == current_user.id,
        Email.deleted_at.is_(None),
        or_(
            func.lower(Email.sender) == recipient_email,
            func.lower(Email.recipients).contains(recipient_email)
        )
    ).order_by(desc(Email.received_at)).limit(20).all()

    if not conversations:
        # No history - return generic templates with helpful context
        return {
            "templates": _get_first_contact_templates(recipient_email, tone),
            "context": {
                "relationship": "new",
                "last_topic": None,
                "days_since_contact": None,
                "email_count": 0
            }
        }

    # Analyze conversation history
    context = _analyze_conversation_context(conversations, recipient_email)

    # Generate templates based on context
    templates = _generate_contextual_templates(context, tone, conversations)

    return {
        "templates": templates,
        "context": context
    }


def _analyze_conversation_context(conversations: List[Email], recipient_email: str) -> Dict:
    """Analyze conversation history to extract context for template generation."""

    # Get most recent email
    most_recent = conversations[0]
    days_since_contact = (datetime.utcnow() - most_recent.received_at).days

    # Determine who sent the last email
    last_was_them = most_recent.sender.lower() == recipient_email.lower()

    # Extract key topics from recent emails
    topics = []
    pending_items = []
    mentions_pricing = False
    mentions_meeting = False
    mentions_deadline = False
    has_questions = False

    for email in conversations[:5]:  # Look at last 5 emails
        text = (email.body_text or email.snippet or "").lower()
        subject = (email.subject or "").lower()

        # Check for key patterns
        if any(word in text for word in ["price", "pricing", "cost", "quote", "proposal"]):
            mentions_pricing = True
            if "proposal" in text or "quote" in text:
                topics.append("proposal/pricing discussion")

        if any(word in text for word in ["meeting", "call", "schedule", "calendar"]):
            mentions_meeting = True
            topics.append("meeting scheduling")

        if any(word in text for word in ["deadline", "urgent", "asap", "by friday", "by monday"]):
            mentions_deadline = True

        if "?" in text:
            has_questions = True
            # Extract question context
            if "when" in text.lower():
                pending_items.append("timeline question")
            if "how" in text.lower():
                pending_items.append("process question")

        # Extract subject-based topics
        if "re:" not in subject.lower():
            topics.append(subject[:50])

    # Determine relationship stage
    email_count = len(conversations)
    if email_count <= 2:
        relationship = "early"
    elif email_count <= 5:
        relationship = "developing"
    else:
        relationship = "established"

    # Get sender name
    sender_name = None
    for email in conversations:
        if email.sender.lower() == recipient_email.lower() and email.sender_name:
            sender_name = email.sender_name.split()[0]  # First name
            break

    return {
        "relationship": relationship,
        "email_count": email_count,
        "days_since_contact": days_since_contact,
        "last_was_them": last_was_them,
        "last_topic": topics[0] if topics else most_recent.subject,
        "mentions_pricing": mentions_pricing,
        "mentions_meeting": mentions_meeting,
        "mentions_deadline": mentions_deadline,
        "has_unanswered_questions": has_questions and last_was_them,
        "pending_items": list(set(pending_items))[:3],
        "sender_name": sender_name,
        "last_subject": most_recent.subject
    }


def _generate_contextual_templates(context: Dict, tone: str, conversations: List[Email]) -> List[Dict]:
    """Generate email templates based on conversation context."""

    templates = []
    name = context.get("sender_name") or "there"
    days = context.get("days_since_contact", 0)
    last_topic = context.get("last_topic", "our conversation")

    # Tone-based greetings
    greetings = {
        "professional": f"Hi {name},",
        "friendly": f"Hey {name}!",
        "formal": f"Dear {name},"
    }
    greeting = greetings.get(tone, greetings["professional"])

    # Template 1: Follow-up based on last conversation
    if context.get("last_was_them"):
        # They sent the last email - we need to respond
        if context.get("has_unanswered_questions"):
            templates.append({
                "name": "Answer & Follow Up",
                "icon": "fa-reply",
                "preview": f"Respond to their questions about {last_topic[:30]}...",
                "subject": f"Re: {context.get('last_subject', last_topic)}",
                "body": f"""{greeting}

Thank you for your message. To address your questions:

[Your answers here]

Please let me know if you need any additional information or clarification.

Best regards"""
            })
        else:
            templates.append({
                "name": "Quick Acknowledgment",
                "icon": "fa-check",
                "preview": "Acknowledge their message and next steps...",
                "subject": f"Re: {context.get('last_subject', last_topic)}",
                "body": f"""{greeting}

Thank you for getting back to me. I've noted your points and will [next action].

I'll follow up with [deliverable/update] by [timeframe].

Best regards"""
            })
    else:
        # We sent the last email - following up
        if days <= 2:
            templates.append({
                "name": "Quick Check-In",
                "icon": "fa-hand-wave",
                "preview": "Brief follow-up on recent message...",
                "subject": f"Re: {context.get('last_subject', last_topic)}",
                "body": f"""{greeting}

Just wanted to make sure my previous message came through. Did you have a chance to review it?

Happy to clarify anything or hop on a quick call if that would be helpful.

Best"""
            })
        elif days <= 7:
            templates.append({
                "name": "Gentle Follow-Up",
                "icon": "fa-clock",
                "preview": f"Following up on {last_topic[:25]}...",
                "subject": f"Following up: {context.get('last_subject', last_topic)[:40]}",
                "body": f"""{greeting}

I wanted to follow up on my previous message regarding {last_topic}.

I understand you're busy, but I'd love to keep the momentum going on this. Would [specific next step] work for you?

Let me know what works best.

Best regards"""
            })
        else:
            templates.append({
                "name": "Re-Engagement",
                "icon": "fa-redo",
                "preview": f"Reconnecting after {days} days...",
                "subject": f"Checking in - {last_topic[:35]}",
                "body": f"""{greeting}

It's been a little while since we last connected about {last_topic}. I wanted to reach out and see if this is still on your radar.

If circumstances have changed or you have questions, I'm happy to discuss.

Looking forward to hearing from you.

Best regards"""
            })

    # Template 2: Context-specific templates
    if context.get("mentions_pricing"):
        templates.append({
            "name": "Pricing Discussion",
            "icon": "fa-dollar-sign",
            "preview": "Address pricing questions or send proposal...",
            "subject": f"Re: Pricing details - {last_topic[:30]}",
            "body": f"""{greeting}

Following up on our pricing discussion. I've put together some options that I think will work well for your needs:

[Option 1]: $X - includes [features]
[Option 2]: $X - includes [features]

I'd recommend [Option X] based on what you've shared about your requirements.

Would you like to schedule a quick call to walk through these in detail?

Best regards"""
        })

    if context.get("mentions_meeting"):
        templates.append({
            "name": "Schedule Meeting",
            "icon": "fa-calendar",
            "preview": "Propose meeting times...",
            "subject": f"Re: Let's schedule time to connect",
            "body": f"""{greeting}

I'd love to find time to connect. Here are a few options that work on my end:

- [Day, Time]
- [Day, Time]
- [Day, Time]

Let me know what works best for you, or feel free to grab time on my calendar: [calendar link]

Looking forward to it!

Best"""
        })

    # Template 3: Value-add template
    if context.get("relationship") in ["developing", "established"]:
        templates.append({
            "name": "Add Value",
            "icon": "fa-gift",
            "preview": "Share helpful resource or insight...",
            "subject": f"Thought of you - {last_topic[:30]}",
            "body": f"""{greeting}

I came across [article/resource/case study] that reminded me of our conversation about {last_topic}.

[Brief insight or key takeaway]

Thought it might be helpful given what you mentioned about [their situation/challenge].

Let me know if you'd like to discuss further!

Best"""
        })

    # Template 4: Close/Decision template
    if context.get("mentions_pricing") or context.get("email_count", 0) > 5:
        templates.append({
            "name": "Move to Decision",
            "icon": "fa-handshake",
            "preview": "Guide toward a decision...",
            "subject": f"Next steps - {last_topic[:35]}",
            "body": f"""{greeting}

I wanted to check in on where things stand with {last_topic}.

Based on our discussions, I believe we have a strong foundation to move forward. What would help you feel confident in taking the next step?

Happy to:
- Address any remaining questions
- Provide additional references or case studies
- Set up a call with our team

What would be most helpful?

Best regards"""
        })

    return templates[:4]  # Return max 4 templates


def _get_first_contact_templates(recipient_email: str, tone: str) -> List[Dict]:
    """Get templates for first-time contact with someone."""

    # Try to extract name from email
    name_part = recipient_email.split("@")[0]
    if "." in name_part:
        name = name_part.split(".")[0].title()
    else:
        name = "there"

    greetings = {
        "professional": f"Hi {name},",
        "friendly": f"Hey {name}!",
        "formal": f"Dear {name},"
    }
    greeting = greetings.get(tone, greetings["professional"])

    return [
        {
            "name": "Introduction",
            "icon": "fa-hand-wave",
            "preview": "Introduce yourself and your value...",
            "subject": "Quick introduction",
            "body": f"""{greeting}

I hope this message finds you well. My name is [Your Name] from [Company].

I'm reaching out because [reason/value proposition].

I'd love to learn more about [their challenge/goal] and see if there's an opportunity to help.

Would you be open to a brief conversation?

Best regards"""
        },
        {
            "name": "Referral-Based",
            "icon": "fa-user-friends",
            "preview": "Mention mutual connection...",
            "subject": "[Mutual Contact] suggested I reach out",
            "body": f"""{greeting}

[Mutual Contact] suggested I get in touch with you regarding [topic].

They mentioned you might be interested in [value proposition/solution].

I'd love to learn more about your current approach and share some ideas that have worked well for similar organizations.

Would you have 15 minutes for a quick call this week?

Best regards"""
        },
        {
            "name": "Value-First",
            "icon": "fa-gift",
            "preview": "Lead with valuable insight...",
            "subject": "Quick thought on [their challenge]",
            "body": f"""{greeting}

I noticed [observation about their company/industry] and thought you might find this helpful:

[Valuable insight, tip, or resource]

We've helped companies like [similar company] achieve [specific result] by [approach].

If you're open to it, I'd enjoy sharing more details on how this could apply to [their company].

Best regards"""
        },
        {
            "name": "Direct Ask",
            "icon": "fa-bullseye",
            "preview": "Get straight to the point...",
            "subject": "Quick question about [topic]",
            "body": f"""{greeting}

I'll keep this brief - I'm researching companies in [industry/space] and [Company Name] stood out.

Are you currently looking to improve [specific area]?

If so, I have a few ideas that might help. If not, no worries at all.

Thanks for your time.

Best regards"""
        }
    ]