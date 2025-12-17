"""
AI-powered semantic email search
Uses Bedrock/Anthropic to understand query intent and find relevant emails
"""
import os
import json
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.database import Email, User
from core.saig_assistant import SAIGAssistant

logger = logging.getLogger(__name__)


class SemanticEmailSearch:
    """AI-powered semantic email search"""

    def __init__(self):
        self.saig = SAIGAssistant()
        self.max_candidates = int(os.getenv('SEMANTIC_SEARCH_CANDIDATES', '200'))
        self.use_ai_ranking = os.getenv('USE_AI_RANKING', 'true').lower() == 'true'

    async def search(
        self,
        db: Session,
        user_id: str,
        query: str,
        limit: int = 50,
        page: int = 1
    ) -> List[Email]:
        """
        Perform semantic search on emails using AI understanding

        Process:
        1. Analyze query intent with AI to extract concepts and filters
        2. Get candidate emails from database using expanded terms
        3. Rank candidates using AI relevance scoring
        4. Return paginated results
        """
        try:
            # Step 1: Analyze query intent
            query_analysis = await self._analyze_query(query)
            logger.info(f"Query analysis: {query_analysis}")

            # Step 2: Get candidate emails from database
            candidates = self._get_candidates(db, user_id, query, query_analysis)

            if not candidates:
                logger.info(f"No candidates found for query: {query}")
                return []

            logger.info(f"Found {len(candidates)} candidates for query: {query}")

            # Step 3: Rank candidates
            if self.use_ai_ranking and len(candidates) > 10:
                ranked_emails = await self._rank_with_ai(query, query_analysis, candidates)
            else:
                # Use keyword scoring for small result sets
                ranked_emails = self._keyword_rank(query, candidates)

            # Step 4: Apply pagination
            start = (page - 1) * limit
            end = start + limit

            return ranked_emails[start:end]

        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            # Fall back to basic search
            return await self._fallback_search(db, user_id, query, limit, page)

    async def _analyze_query(self, query: str) -> Dict[str, Any]:
        """Use AI to understand the search query intent"""

        prompt = f"""Analyze this email search query and extract search criteria.

Query: "{query}"

Return a JSON object with:
{{
    "intent": "Brief description of what the user is looking for",
    "key_concepts": ["list", "of", "main", "search", "terms"],
    "related_terms": ["synonyms", "and", "related", "words"],
    "filters": {{
        "sender_hints": ["names or domains to look for in sender"],
        "date_range": "today|this_week|this_month|any",
        "has_attachments": true|false|null,
        "is_urgent": true|false|null
    }},
    "email_type": "meeting|invoice|newsletter|personal|work|any"
}}

Examples:
- "emails from john about the project" -> key_concepts: ["john", "project"], sender_hints: ["john"]
- "urgent messages this week" -> key_concepts: ["urgent"], filters: {{ date_range: "this_week", is_urgent: true }}
- "invoices with attachments" -> key_concepts: ["invoice"], email_type: "invoice", has_attachments: true

Return ONLY valid JSON, no explanation."""

        try:
            response = await self.saig._call_anthropic(
                prompt, max_tokens=400, temperature=0.1
            )

            # Parse JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                analysis = json.loads(json_match.group())
                return analysis

        except Exception as e:
            logger.error(f"Query analysis error: {e}")

        # Default analysis if AI fails
        return {
            'intent': query,
            'key_concepts': query.lower().split(),
            'related_terms': [],
            'filters': {'date_range': 'any'},
            'email_type': 'any'
        }

    def _get_candidates(
        self,
        db: Session,
        user_id: str,
        original_query: str,
        query_analysis: Dict
    ) -> List[Email]:
        """Get candidate emails from database based on query analysis"""

        # Build base query
        base_query = db.query(Email).filter(
            Email.user_id == user_id,
            Email.deleted_at.is_(None)
        )

        # Apply filters from analysis
        filters = query_analysis.get('filters', {})

        # Date filter
        date_range = filters.get('date_range', 'any')
        if date_range and date_range != 'any':
            now = datetime.utcnow()
            cutoff = None
            if date_range == 'today':
                cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif date_range == 'this_week':
                cutoff = now - timedelta(days=7)
            elif date_range == 'this_month':
                cutoff = now - timedelta(days=30)

            if cutoff:
                base_query = base_query.filter(Email.received_at >= cutoff)

        # Attachment filter
        if filters.get('has_attachments') is True:
            base_query = base_query.filter(Email.has_attachments == True)

        # Urgency filter
        if filters.get('is_urgent') is True:
            base_query = base_query.filter(Email.is_urgent == True)

        # Build search conditions from key concepts and related terms
        search_terms = list(set(
            query_analysis.get('key_concepts', []) +
            query_analysis.get('related_terms', []) +
            original_query.lower().split()
        ))

        # Also check sender hints
        sender_hints = filters.get('sender_hints', [])

        if search_terms or sender_hints:
            conditions = []

            # Search in email fields
            for term in search_terms[:15]:  # Limit terms to avoid query complexity
                if len(term) < 2:  # Skip very short terms
                    continue
                term_pattern = f"%{term}%"
                conditions.append(Email.subject.ilike(term_pattern))
                conditions.append(Email.body_text.ilike(term_pattern))
                conditions.append(Email.snippet.ilike(term_pattern))
                conditions.append(Email.sender.ilike(term_pattern))
                conditions.append(Email.sender_name.ilike(term_pattern))

            # Add sender-specific conditions
            for sender in sender_hints:
                if len(sender) >= 2:
                    sender_pattern = f"%{sender}%"
                    conditions.append(Email.sender.ilike(sender_pattern))
                    conditions.append(Email.sender_name.ilike(sender_pattern))

            if conditions:
                base_query = base_query.filter(or_(*conditions))

        # Get candidates ordered by recency
        candidates = base_query.order_by(
            Email.received_at.desc()
        ).limit(self.max_candidates).all()

        return candidates

    async def _rank_with_ai(
        self,
        query: str,
        query_analysis: Dict,
        candidates: List[Email]
    ) -> List[Email]:
        """Use AI to rank email relevance to the query"""

        # Prepare email summaries for ranking (limit to 40 to manage token usage)
        email_summaries = []
        for i, email in enumerate(candidates[:40]):
            email_summaries.append({
                'idx': i,
                'subject': (email.subject or '(no subject)')[:80],
                'from': (email.sender_name or email.sender or 'Unknown')[:40],
                'preview': (email.snippet or email.body_text or '')[:100],
                'date': email.received_at.strftime('%m/%d') if email.received_at else '?'
            })

        prompt = f"""Rank these emails by relevance to the search query.

Search Query: "{query}"
Intent: {query_analysis.get('intent', 'find matching emails')}

Emails:
{json.dumps(email_summaries, indent=1)}

Return a JSON array of indices ordered by relevance (most relevant first).
Only include emails that are actually relevant to the query.
Omit emails that don't match the search intent.

Example output: [5, 2, 8, 0, 12]

Return ONLY the JSON array of indices, nothing else."""

        try:
            response = await self.saig._call_anthropic(
                prompt, max_tokens=200, temperature=0.1
            )

            # Parse ranking array
            array_match = re.search(r'\[[\d\s,]*\]', response)
            if array_match:
                ranked_indices = json.loads(array_match.group())

                # Build ranked result
                ranked_emails = []
                seen_indices = set()

                for idx in ranked_indices:
                    if isinstance(idx, int) and idx < len(candidates) and idx not in seen_indices:
                        ranked_emails.append(candidates[idx])
                        seen_indices.add(idx)

                # Add remaining candidates not in ranking (may still be relevant)
                for i, email in enumerate(candidates):
                    if i not in seen_indices:
                        ranked_emails.append(email)

                logger.info(f"AI ranked {len(ranked_indices)} emails as relevant")
                return ranked_emails

        except Exception as e:
            logger.error(f"AI ranking error: {e}")

        # Fall back to keyword ranking
        return self._keyword_rank(query, candidates)

    def _keyword_rank(self, query: str, candidates: List[Email]) -> List[Email]:
        """Keyword-based ranking fallback"""

        query_words = set(query.lower().split())

        def score_email(email: Email) -> int:
            score = 0
            text = f"{email.subject or ''} {email.sender_name or ''} {email.sender or ''} {email.snippet or ''}".lower()

            # Exact phrase match - highest score
            if query.lower() in text:
                score += 50

            # Individual word matches
            for word in query_words:
                if len(word) < 2:
                    continue
                if word in text:
                    score += 10
                    # Bonus for subject match
                    if email.subject and word in email.subject.lower():
                        score += 5
                    # Bonus for sender match
                    if email.sender and word in email.sender.lower():
                        score += 5

            return score

        scored = [(email, score_email(email)) for email in candidates]
        scored.sort(key=lambda x: (-x[1], x[0].received_at or datetime.min), reverse=False)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Return emails with score > 0, or all if none match
        relevant = [email for email, score in scored if score > 0]
        return relevant if relevant else candidates

    async def _fallback_search(
        self,
        db: Session,
        user_id: str,
        query: str,
        limit: int,
        page: int
    ) -> List[Email]:
        """Basic fallback search when AI fails"""

        search_pattern = f"%{query}%"
        offset = (page - 1) * limit

        return db.query(Email).filter(
            Email.user_id == user_id,
            Email.deleted_at.is_(None),
            or_(
                Email.subject.ilike(search_pattern),
                Email.sender.ilike(search_pattern),
                Email.sender_name.ilike(search_pattern),
                Email.body_text.ilike(search_pattern),
                Email.snippet.ilike(search_pattern)
            )
        ).order_by(Email.received_at.desc()).offset(offset).limit(limit).all()


# Global instance
semantic_search = SemanticEmailSearch()
