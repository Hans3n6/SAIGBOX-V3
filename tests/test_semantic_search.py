"""
Tests for AI-powered semantic email search
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.semantic_search import SemanticEmailSearch


class TestSemanticEmailSearch:
    """Tests for SemanticEmailSearch class"""

    def test_init_defaults(self):
        """Test default initialization values"""
        search = SemanticEmailSearch()

        assert search.max_candidates == 200
        assert search.use_ai_ranking == True

    @patch.dict(os.environ, {'SEMANTIC_SEARCH_CANDIDATES': '100', 'USE_AI_RANKING': 'false'})
    def test_init_custom_env_values(self):
        """Test initialization with custom env values"""
        search = SemanticEmailSearch()

        assert search.max_candidates == 100
        assert search.use_ai_ranking == False


class TestQueryAnalysis:
    """Tests for query analysis functionality"""

    @pytest.mark.asyncio
    async def test_analyze_query_returns_structure(self, mock_saig_assistant):
        """Test that query analysis returns expected structure"""
        mock_saig_assistant._call_anthropic.return_value = json.dumps({
            "intent": "find meeting emails",
            "key_concepts": ["meeting", "schedule"],
            "related_terms": ["calendar", "appointment"],
            "filters": {"date_range": "this_week", "is_urgent": True},
            "email_type": "meeting"
        })

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant

        result = await search._analyze_query("meetings this week")

        assert "intent" in result
        assert "key_concepts" in result
        assert "related_terms" in result
        assert "filters" in result

    @pytest.mark.asyncio
    async def test_analyze_query_handles_ai_failure(self, mock_saig_assistant):
        """Test fallback when AI analysis fails"""
        mock_saig_assistant._call_anthropic.side_effect = Exception("API Error")

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant

        result = await search._analyze_query("find my emails")

        # Should return default analysis
        assert result['intent'] == "find my emails"
        assert "find" in result['key_concepts']
        assert result['filters']['date_range'] == 'any'

    @pytest.mark.asyncio
    async def test_analyze_query_extracts_sender_hints(self, mock_saig_assistant):
        """Test that sender hints are extracted from query"""
        mock_saig_assistant._call_anthropic.return_value = json.dumps({
            "intent": "find emails from John",
            "key_concepts": ["john"],
            "related_terms": [],
            "filters": {"sender_hints": ["john"], "date_range": "any"},
            "email_type": "any"
        })

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant

        result = await search._analyze_query("emails from John")

        assert "john" in result['filters'].get('sender_hints', [])


class TestGetCandidates:
    """Tests for candidate retrieval from database"""

    def test_get_candidates_basic_search(self, db_session, test_user, sample_emails):
        """Test basic candidate retrieval"""
        search = SemanticEmailSearch()

        query_analysis = {
            'key_concepts': ['meeting', 'planning'],
            'related_terms': ['schedule'],
            'filters': {'date_range': 'any'}
        }

        candidates = search._get_candidates(
            db_session, test_user.id, "meeting planning", query_analysis
        )

        # Should find the Q4 Planning Meeting email
        assert len(candidates) > 0
        subjects = [c.subject for c in candidates]
        assert any('Planning' in s for s in subjects)

    def test_get_candidates_filters_by_urgency(self, db_session, test_user, sample_emails):
        """Test that urgency filter is applied"""
        search = SemanticEmailSearch()

        query_analysis = {
            'key_concepts': [],
            'related_terms': [],
            'filters': {'date_range': 'any', 'is_urgent': True}
        }

        candidates = search._get_candidates(
            db_session, test_user.id, "urgent", query_analysis
        )

        # All returned emails should be urgent
        assert all(c.is_urgent for c in candidates)

    def test_get_candidates_filters_by_date(self, db_session, test_user, sample_emails):
        """Test that date filter is applied"""
        search = SemanticEmailSearch()

        query_analysis = {
            'key_concepts': [],
            'related_terms': [],
            'filters': {'date_range': 'today'}
        }

        candidates = search._get_candidates(
            db_session, test_user.id, "today", query_analysis
        )

        # All emails should be from today
        today = datetime.utcnow().date()
        for c in candidates:
            if c.received_at:
                assert c.received_at.date() == today

    def test_get_candidates_filters_by_attachments(self, db_session, test_user, sample_emails):
        """Test attachment filter"""
        search = SemanticEmailSearch()

        query_analysis = {
            'key_concepts': ['invoice'],
            'related_terms': [],
            'filters': {'date_range': 'any', 'has_attachments': True}
        }

        candidates = search._get_candidates(
            db_session, test_user.id, "invoices with attachments", query_analysis
        )

        # Should find the invoice email
        assert len(candidates) > 0
        assert any('Invoice' in (c.subject or '') for c in candidates)

    def test_get_candidates_searches_multiple_fields(self, db_session, test_user, sample_emails):
        """Test that search covers subject, body, sender"""
        search = SemanticEmailSearch()

        # Search by sender name
        query_analysis = {
            'key_concepts': ['sarah', 'client'],
            'related_terms': [],
            'filters': {'sender_hints': ['sarah'], 'date_range': 'any'}
        }

        candidates = search._get_candidates(
            db_session, test_user.id, "from sarah", query_analysis
        )

        assert len(candidates) > 0
        assert any('Sarah' in (c.sender_name or '') for c in candidates)

    def test_get_candidates_limits_results(self, db_session, test_user, sample_emails):
        """Test that max_candidates limit is respected"""
        search = SemanticEmailSearch()
        search.max_candidates = 2

        query_analysis = {
            'key_concepts': [],
            'related_terms': [],
            'filters': {'date_range': 'any'}
        }

        candidates = search._get_candidates(
            db_session, test_user.id, "", query_analysis
        )

        assert len(candidates) <= 2


class TestKeywordRanking:
    """Tests for keyword-based ranking fallback"""

    def test_keyword_rank_exact_match_scores_highest(self, sample_emails):
        """Test exact phrase match gets highest score"""
        search = SemanticEmailSearch()

        query = "Q4 Planning Meeting"
        ranked = search._keyword_rank(query, sample_emails)

        # Q4 Planning Meeting email should be first
        assert "Q4 Planning" in ranked[0].subject

    def test_keyword_rank_partial_matches(self, sample_emails):
        """Test partial keyword matches are ranked"""
        search = SemanticEmailSearch()

        query = "proposal pricing"
        ranked = search._keyword_rank(query, sample_emails)

        # Proposal email should be ranked higher
        assert len(ranked) > 0
        assert any("Proposal" in (e.subject or '') for e in ranked[:2])

    def test_keyword_rank_no_matches_returns_all(self, sample_emails):
        """Test that unmatched queries return all candidates"""
        search = SemanticEmailSearch()

        query = "xyznonexistent"
        ranked = search._keyword_rank(query, sample_emails)

        # Should return all emails since none match
        assert len(ranked) == len(sample_emails)


class TestAIRanking:
    """Tests for AI-powered ranking"""

    @pytest.mark.asyncio
    async def test_rank_with_ai_success(self, sample_emails, mock_saig_assistant):
        """Test AI ranking returns ordered results"""
        # AI returns indices [0, 3] (first and fourth email as most relevant)
        mock_saig_assistant._call_anthropic.return_value = "[0, 3]"

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant

        query_analysis = {"intent": "test"}
        ranked = await search._rank_with_ai("test", query_analysis, sample_emails)

        # First email should be at index 0 of original list
        assert ranked[0] == sample_emails[0]
        # Second should be index 3
        assert ranked[1] == sample_emails[3]

    @pytest.mark.asyncio
    async def test_rank_with_ai_handles_invalid_indices(self, sample_emails, mock_saig_assistant):
        """Test AI ranking handles out of bounds indices"""
        # AI returns some invalid indices
        mock_saig_assistant._call_anthropic.return_value = "[0, 100, -1, 1]"

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant

        query_analysis = {"intent": "test"}
        ranked = await search._rank_with_ai("test", query_analysis, sample_emails)

        # Should include valid indices (0, 1) and remaining emails
        assert len(ranked) == len(sample_emails)

    @pytest.mark.asyncio
    async def test_rank_with_ai_falls_back_on_error(self, sample_emails, mock_saig_assistant):
        """Test fallback to keyword ranking on AI error"""
        mock_saig_assistant._call_anthropic.side_effect = Exception("API Error")

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant

        query_analysis = {"intent": "test"}
        ranked = await search._rank_with_ai("meeting", query_analysis, sample_emails)

        # Should fall back to keyword ranking - still return results
        assert len(ranked) > 0


class TestFullSearch:
    """Integration tests for full search flow"""

    @pytest.mark.asyncio
    async def test_search_full_flow(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test complete search flow with AI"""
        # Mock query analysis
        mock_saig_assistant._call_anthropic.side_effect = [
            # First call: query analysis
            json.dumps({
                "intent": "find meeting emails",
                "key_concepts": ["meeting", "planning"],
                "related_terms": ["schedule"],
                "filters": {"date_range": "any"},
                "email_type": "meeting"
            }),
            # Second call: ranking
            "[0]"
        ]

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant

        results = await search.search(db_session, test_user.id, "Q4 meeting", limit=10, page=1)

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_pagination(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test search pagination"""
        mock_saig_assistant._call_anthropic.return_value = json.dumps({
            "intent": "find all",
            "key_concepts": [],
            "related_terms": [],
            "filters": {"date_range": "any"},
            "email_type": "any"
        })

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant
        search.use_ai_ranking = False  # Use keyword ranking for predictability

        # Get page 1 with limit 2
        page1 = await search.search(db_session, test_user.id, "email", limit=2, page=1)
        # Get page 2
        page2 = await search.search(db_session, test_user.id, "email", limit=2, page=2)

        # Pages should have different results (if enough emails)
        if len(page1) > 0 and len(page2) > 0:
            assert page1[0].id != page2[0].id

    @pytest.mark.asyncio
    async def test_search_fallback_on_error(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test search falls back to basic search on complete failure"""
        mock_saig_assistant._call_anthropic.side_effect = Exception("Complete failure")

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant

        # Should still return results via fallback
        results = await search.search(db_session, test_user.id, "meeting", limit=10, page=1)

        # Fallback should find the meeting email
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_empty_query(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test search with empty/minimal query"""
        mock_saig_assistant._call_anthropic.return_value = json.dumps({
            "intent": "",
            "key_concepts": [],
            "related_terms": [],
            "filters": {"date_range": "any"},
            "email_type": "any"
        })

        search = SemanticEmailSearch()
        search.saig = mock_saig_assistant
        search.use_ai_ranking = False

        results = await search.search(db_session, test_user.id, "", limit=50, page=1)

        # Should return some emails even with empty query
        assert isinstance(results, list)
