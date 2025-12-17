"""
Tests for AI-powered action item extraction from emails
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.action_extractor import ActionItemExtractor
from core.database import ActionItem


class TestActionItemExtractor:
    """Tests for ActionItemExtractor class"""

    def test_init_defaults(self):
        """Test default initialization values"""
        extractor = ActionItemExtractor()

        assert extractor.confidence_threshold == 70

    @patch.dict(os.environ, {'ACTION_CONFIDENCE_THRESHOLD': '80'})
    def test_init_custom_threshold(self):
        """Test initialization with custom threshold"""
        extractor = ActionItemExtractor()

        assert extractor.confidence_threshold == 80


class TestExtractFromEmail:
    """Tests for extraction functionality"""

    @pytest.mark.asyncio
    async def test_extract_action_items_from_meeting_email(self, sample_emails, test_user, mock_saig_assistant):
        """Test extracting action items from a meeting request email"""
        meeting_email = sample_emails[0]  # Q4 Planning Meeting email

        mock_saig_assistant._call_anthropic.return_value = json.dumps([
            {
                "title": "Submit Q3 results by Wednesday",
                "description": "Prepare and submit quarterly results before the planning meeting",
                "due_date": "2025-01-08",
                "priority": "high",
                "confidence": 95,
                "source_quote": "Submit your Q3 results by Wednesday"
            },
            {
                "title": "Review budget proposal",
                "description": "Review the attached budget proposal before the meeting",
                "due_date": None,
                "priority": "medium",
                "confidence": 85,
                "source_quote": "Review the budget proposal attached"
            },
            {
                "title": "Schedule pre-meeting with direct reports",
                "description": "Set up a preliminary meeting with your direct reports",
                "due_date": "end of week",
                "priority": "medium",
                "confidence": 90,
                "source_quote": "Schedule a pre-meeting with your direct reports"
            }
        ])

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        items = await extractor.extract_from_email(meeting_email, test_user)

        assert len(items) == 3
        assert items[0]['title'] == "Submit Q3 results by Wednesday"
        assert items[0]['priority'] == "high"
        assert items[0]['confidence'] == 95

    @pytest.mark.asyncio
    async def test_extract_filters_by_confidence(self, sample_emails, test_user, mock_saig_assistant):
        """Test that low confidence items are filtered out"""
        email = sample_emails[0]

        mock_saig_assistant._call_anthropic.return_value = json.dumps([
            {
                "title": "High confidence task",
                "description": "This is clear",
                "due_date": None,
                "priority": "high",
                "confidence": 90,
                "source_quote": "Please do this"
            },
            {
                "title": "Low confidence task",
                "description": "This is vague",
                "due_date": None,
                "priority": "low",
                "confidence": 50,  # Below threshold
                "source_quote": "Maybe consider..."
            }
        ])

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant
        extractor.confidence_threshold = 70

        items = await extractor.extract_from_email(email, test_user)

        assert len(items) == 1
        assert items[0]['confidence'] == 90

    @pytest.mark.asyncio
    async def test_extract_returns_empty_for_newsletter(self, sample_emails, test_user, mock_saig_assistant):
        """Test that newsletters return no action items"""
        newsletter = sample_emails[2]  # Weekly Tech News

        mock_saig_assistant._call_anthropic.return_value = "[]"

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        items = await extractor.extract_from_email(newsletter, test_user)

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_extract_handles_empty_email(self, test_user, mock_saig_assistant):
        """Test handling of email with no content"""
        from core.database import Email

        empty_email = Email(
            id="empty-email",
            user_id=test_user.id,
            subject="Empty",
            body_text="",
            body_html="",
            snippet=""
        )

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        items = await extractor.extract_from_email(empty_email, test_user)

        assert len(items) == 0
        # Should not call AI for empty content
        mock_saig_assistant._call_anthropic.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_handles_ai_error(self, sample_emails, test_user, mock_saig_assistant):
        """Test graceful handling of AI errors"""
        email = sample_emails[0]

        mock_saig_assistant._call_anthropic.side_effect = Exception("API Error")

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        items = await extractor.extract_from_email(email, test_user)

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_extract_handles_malformed_json(self, sample_emails, test_user, mock_saig_assistant):
        """Test handling of malformed AI response"""
        email = sample_emails[0]

        mock_saig_assistant._call_anthropic.return_value = "This is not valid JSON {{"

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        items = await extractor.extract_from_email(email, test_user)

        assert len(items) == 0


class TestDueDateParsing:
    """Tests for due date parsing"""

    def test_parse_iso_date(self):
        """Test parsing ISO format dates"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("2025-01-15")

        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_today(self):
        """Test parsing 'today'"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("today")

        assert result is not None
        assert result.date() == datetime.utcnow().date()
        assert result.hour == 17  # 5 PM

    def test_parse_tomorrow(self):
        """Test parsing 'tomorrow'"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("tomorrow")

        expected = (datetime.utcnow() + timedelta(days=1)).date()
        assert result is not None
        assert result.date() == expected

    def test_parse_end_of_week(self):
        """Test parsing 'end of week'"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("end of week")

        assert result is not None
        # Should be a Friday
        assert result.weekday() == 4

    def test_parse_eow_abbreviation(self):
        """Test parsing 'eow' abbreviation"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("EOW")

        assert result is not None
        assert result.weekday() == 4

    def test_parse_next_week(self):
        """Test parsing 'next week'"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("next week")

        expected = datetime.utcnow() + timedelta(weeks=1)
        assert result is not None
        assert abs((result - expected).days) <= 1

    def test_parse_friday(self):
        """Test parsing 'Friday'"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("Friday")

        assert result is not None
        assert result.weekday() == 4

    def test_parse_monday(self):
        """Test parsing 'Monday'"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("Monday")

        assert result is not None
        assert result.weekday() == 0

    def test_parse_end_of_month(self):
        """Test parsing 'end of month'"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("end of month")

        assert result is not None
        # Should be last day of current month
        next_month = (datetime.utcnow().month % 12) + 1
        if next_month == 1:
            expected_first_of_next = datetime(datetime.utcnow().year + 1, 1, 1)
        else:
            expected_first_of_next = datetime(datetime.utcnow().year, next_month, 1)
        expected = expected_first_of_next - timedelta(days=1)
        assert result.day == expected.day

    def test_parse_asap(self):
        """Test parsing 'ASAP'"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("ASAP")

        expected = (datetime.utcnow() + timedelta(days=1)).date()
        assert result is not None
        assert result.date() == expected

    def test_parse_null_values(self):
        """Test parsing null/none values"""
        extractor = ActionItemExtractor()

        assert extractor._parse_due_date(None) is None
        assert extractor._parse_due_date("null") is None
        assert extractor._parse_due_date("None") is None
        assert extractor._parse_due_date("") is None
        assert extractor._parse_due_date("n/a") is None

    def test_parse_us_date_format(self):
        """Test parsing US date format MM/DD/YYYY"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("01/15/2025")

        assert result is not None
        assert result.month == 1
        assert result.day == 15
        assert result.year == 2025

    def test_parse_invalid_date(self):
        """Test parsing invalid date returns None"""
        extractor = ActionItemExtractor()

        result = extractor._parse_due_date("not a date at all")

        assert result is None


class TestCreateActionItems:
    """Tests for database action item creation"""

    @pytest.mark.asyncio
    async def test_create_action_items_success(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test successful creation of action items in database"""
        email = sample_emails[3]  # Client follow-up email

        mock_saig_assistant._call_anthropic.return_value = json.dumps([
            {
                "title": "Send updated pricing by tomorrow",
                "description": "Client requested updated pricing",
                "due_date": "tomorrow",
                "priority": "high",
                "confidence": 95,
                "source_quote": "Send me the updated pricing by tomorrow"
            },
            {
                "title": "Schedule call for Tuesday",
                "description": "Discuss timeline with client",
                "due_date": "Tuesday",
                "priority": "medium",
                "confidence": 90,
                "source_quote": "Schedule a call for Tuesday"
            }
        ])

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        created = await extractor.create_action_items(db_session, email, test_user)

        assert len(created) == 2
        assert all(isinstance(item, ActionItem) for item in created)
        assert created[0].title == "Send updated pricing by tomorrow"
        assert created[0].priority == 1  # high -> 1
        assert created[0].auto_created == True
        assert created[0].confidence_score == 95
        assert created[0].email_id == email.id
        assert created[0].user_id == test_user.id

    @pytest.mark.asyncio
    async def test_create_prevents_duplicates(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test that duplicate action items are not created"""
        email = sample_emails[0]

        mock_saig_assistant._call_anthropic.return_value = json.dumps([
            {
                "title": "Test task",
                "description": "Test",
                "due_date": None,
                "priority": "medium",
                "confidence": 85,
                "source_quote": "Test"
            }
        ])

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        # First extraction
        first_result = await extractor.create_action_items(db_session, email, test_user)
        assert len(first_result) == 1

        # Second extraction should skip (existing items)
        second_result = await extractor.create_action_items(db_session, email, test_user)
        assert len(second_result) == 0

    @pytest.mark.asyncio
    async def test_create_handles_priority_mapping(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test priority string to integer mapping"""
        email = sample_emails[0]

        mock_saig_assistant._call_anthropic.return_value = json.dumps([
            {"title": "High priority", "description": "", "due_date": None, "priority": "high", "confidence": 85, "source_quote": ""},
            {"title": "Medium priority", "description": "", "due_date": None, "priority": "medium", "confidence": 85, "source_quote": ""},
            {"title": "Low priority", "description": "", "due_date": None, "priority": "low", "confidence": 85, "source_quote": ""}
        ])

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        created = await extractor.create_action_items(db_session, email, test_user)

        assert len(created) == 3
        assert created[0].priority == 1  # high
        assert created[1].priority == 2  # medium
        assert created[2].priority == 3  # low

    @pytest.mark.asyncio
    async def test_create_truncates_long_fields(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test that long titles and quotes are truncated"""
        email = sample_emails[0]

        long_title = "A" * 300  # Longer than 200 char limit
        long_quote = "B" * 600  # Longer than 500 char limit

        mock_saig_assistant._call_anthropic.return_value = json.dumps([
            {
                "title": long_title,
                "description": "Test",
                "due_date": None,
                "priority": "medium",
                "confidence": 85,
                "source_quote": long_quote
            }
        ])

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        created = await extractor.create_action_items(db_session, email, test_user)

        assert len(created) == 1
        assert len(created[0].title) <= 200
        assert len(created[0].source_quote) <= 500

    @pytest.mark.asyncio
    async def test_create_sets_status_pending(self, db_session, test_user, sample_emails, mock_saig_assistant):
        """Test that new items have pending status"""
        email = sample_emails[0]

        mock_saig_assistant._call_anthropic.return_value = json.dumps([
            {
                "title": "Test task",
                "description": "Test",
                "due_date": None,
                "priority": "medium",
                "confidence": 85,
                "source_quote": "Test"
            }
        ])

        extractor = ActionItemExtractor()
        extractor.saig = mock_saig_assistant

        created = await extractor.create_action_items(db_session, email, test_user)

        assert len(created) == 1
        assert created[0].status == "pending"


class TestParseActionItems:
    """Tests for parsing AI response"""

    def test_parse_valid_json_array(self):
        """Test parsing valid JSON array"""
        extractor = ActionItemExtractor()

        response = '[{"title": "Task 1"}, {"title": "Task 2"}]'
        result = extractor._parse_action_items(response)

        assert len(result) == 2
        assert result[0]['title'] == "Task 1"

    def test_parse_json_with_surrounding_text(self):
        """Test parsing JSON embedded in text"""
        extractor = ActionItemExtractor()

        response = 'Here are the action items:\n[{"title": "Task 1"}]\nThank you!'
        result = extractor._parse_action_items(response)

        assert len(result) == 1
        assert result[0]['title'] == "Task 1"

    def test_parse_empty_array(self):
        """Test parsing empty array"""
        extractor = ActionItemExtractor()

        response = '[]'
        result = extractor._parse_action_items(response)

        assert len(result) == 0

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty list"""
        extractor = ActionItemExtractor()

        response = 'This is not JSON at all'
        result = extractor._parse_action_items(response)

        assert len(result) == 0

    def test_parse_object_instead_of_array(self):
        """Test parsing object instead of array returns empty"""
        extractor = ActionItemExtractor()

        response = '{"title": "Not an array"}'
        result = extractor._parse_action_items(response)

        assert len(result) == 0
