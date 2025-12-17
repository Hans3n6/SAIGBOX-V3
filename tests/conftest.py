"""
Shared pytest fixtures for SAIGBOX tests
"""
import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Base, User, Email, ActionItem


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_user(db_session):
    """Create a test user"""
    user = User(
        id="test-user-123",
        email="test@example.com",
        name="Test User",
        provider="google",
        oauth_access_token="fake-access-token",
        oauth_refresh_token="fake-refresh-token",
        oauth_token_expires=datetime.utcnow() + timedelta(hours=1),
        last_login=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def microsoft_user(db_session):
    """Create a test Microsoft/Outlook user"""
    user = User(
        id="ms-user-456",
        email="outlook@example.com",
        name="Outlook User",
        provider="microsoft",
        oauth_access_token="ms-fake-access-token",
        oauth_refresh_token="ms-fake-refresh-token",
        oauth_token_expires=datetime.utcnow() + timedelta(hours=1),
        last_login=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def inactive_user(db_session):
    """Create a user who hasn't logged in recently"""
    user = User(
        id="inactive-user-789",
        email="inactive@example.com",
        name="Inactive User",
        provider="google",
        oauth_access_token="inactive-token",
        last_login=datetime.utcnow() - timedelta(days=7)  # Logged in 7 days ago
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_emails(db_session, test_user):
    """Create sample emails for testing"""
    emails = []

    # Meeting request email
    email1 = Email(
        id="email-001",
        user_id=test_user.id,
        gmail_id="gmail-001",
        subject="Q4 Planning Meeting - Action Required",
        sender="boss@company.com",
        sender_name="John Boss",
        body_text="""Hi Team,

Please prepare the following for our Q4 planning meeting next Friday:
1. Submit your Q3 results by Wednesday
2. Review the budget proposal attached
3. Schedule a pre-meeting with your direct reports

Let me know if you have any questions.

Best,
John""",
        snippet="Please prepare the following for our Q4 planning meeting...",
        is_urgent=True,
        is_read=False,
        received_at=datetime.utcnow() - timedelta(hours=2)
    )
    emails.append(email1)

    # Invoice email
    email2 = Email(
        id="email-002",
        user_id=test_user.id,
        gmail_id="gmail-002",
        subject="Invoice #12345 - Payment Due",
        sender="billing@vendor.com",
        sender_name="Vendor Billing",
        body_text="""Dear Customer,

Please find attached invoice #12345 for $5,000.

Payment is due by January 15, 2025.

Thank you for your business.

Regards,
Vendor Billing Team""",
        snippet="Please find attached invoice #12345...",
        has_attachments=True,
        is_urgent=False,
        is_read=True,
        received_at=datetime.utcnow() - timedelta(days=1)
    )
    emails.append(email2)

    # Newsletter (no action items)
    email3 = Email(
        id="email-003",
        user_id=test_user.id,
        gmail_id="gmail-003",
        subject="Weekly Tech News",
        sender="newsletter@tech.com",
        sender_name="Tech News",
        body_text="""This week in tech:

- Company X released new product
- Stock market update
- Industry trends

Click here to read more.""",
        snippet="This week in tech...",
        is_urgent=False,
        is_read=True,
        received_at=datetime.utcnow() - timedelta(days=3)
    )
    emails.append(email3)

    # Client follow-up email
    email4 = Email(
        id="email-004",
        user_id=test_user.id,
        gmail_id="gmail-004",
        subject="Re: Project Proposal",
        sender="client@clientco.com",
        sender_name="Sarah Client",
        body_text="""Thanks for sending the proposal.

Could you please:
- Send me the updated pricing by tomorrow
- Schedule a call for Tuesday to discuss the timeline
- Include John from our team in future communications

Looking forward to moving forward!

Sarah""",
        snippet="Thanks for sending the proposal...",
        is_urgent=True,
        is_read=False,
        received_at=datetime.utcnow() - timedelta(hours=5)
    )
    emails.append(email4)

    for email in emails:
        db_session.add(email)

    db_session.commit()
    return emails


@pytest.fixture
def mock_saig_assistant():
    """Mock SAIG Assistant for AI calls"""
    mock = MagicMock()
    mock._call_anthropic = AsyncMock()
    return mock


@pytest.fixture
def mock_gmail_service():
    """Mock Gmail service"""
    mock = MagicMock()
    mock.fetch_emails = MagicMock(return_value={
        'emails': [],
        'next_page_token': None
    })
    return mock


@pytest.fixture
def mock_outlook_service():
    """Mock Outlook service"""
    mock = MagicMock()
    mock.fetch_emails = MagicMock(return_value={
        'emails': [],
        'next_page_token': None
    })
    return mock
