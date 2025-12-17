from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean, Integer, Float, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///saigbox.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    picture = Column(String)  # Profile picture URL
    provider = Column(String)  # OAuth provider (google, microsoft, demo)
    
    # OAuth tokens (encrypted in production)
    oauth_provider = Column(String)
    oauth_access_token = Column(Text)
    oauth_refresh_token = Column(Text)
    oauth_token_expires = Column(DateTime)
    
    # Legacy fields for compatibility
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expiry = Column(DateTime)
    
    # AWS Cognito integration
    cognito_sub = Column(String, unique=True, index=True)  # Cognito user ID
    cognito_confirmed = Column(Boolean, default=False)  # Email confirmed status
    cognito_access_token = Column(Text)  # Current Cognito access token
    cognito_refresh_token = Column(Text)  # Cognito refresh token
    cognito_temp_password = Column(String)  # Temporary password for migration (to be removed after migration)
    
    # Timestamps
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    emails = relationship("Email", back_populates="user")
    action_items = relationship("ActionItem", back_populates="user")
    huddles_created = relationship("Huddle", back_populates="creator")
    business_profile = relationship("BusinessProfile", back_populates="user", uselist=False)
    cold_campaigns = relationship("ColdEmailCampaign", back_populates="user")

class Email(Base):
    __tablename__ = "emails"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    gmail_id = Column(String, unique=True, index=True, nullable=True)  # Gmail message ID
    outlook_id = Column(String, unique=True, index=True, nullable=True)  # Outlook message ID
    thread_id = Column(String, index=True)  # Gmail thread ID
    conversation_id = Column(String, index=True, nullable=True)  # Outlook conversation ID
    subject = Column(String)
    sender = Column(String)
    sender_name = Column(String)
    recipients = Column(JSON)
    cc = Column(JSON)
    bcc = Column(JSON)
    body_text = Column(Text)
    body_html = Column(Text)
    snippet = Column(Text)
    labels = Column(JSON)
    is_read = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)  # True if sent by user, False if received
    has_attachments = Column(Boolean, default=False)
    attachments = Column(JSON)
    received_at = Column(DateTime)
    deleted_at = Column(DateTime, nullable=True)
    
    # Urgency fields
    is_urgent = Column(Boolean, default=False, index=True)
    urgency_score = Column(Integer, default=0)  # 0-100 scale
    urgency_reason = Column(String)  # Why it was marked urgent
    urgency_analyzed_at = Column(DateTime, nullable=True)
    auto_actions_created = Column(Boolean, default=False)
    action_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="emails")
    action_items = relationship("ActionItem", back_populates="email")

class ActionItem(Base):
    __tablename__ = "action_items"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    email_id = Column(String, ForeignKey("emails.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    due_date = Column(DateTime, nullable=True)
    priority = Column(Integer, default=2)  # 1=High, 2=Medium, 3=Low
    status = Column(String, default="pending")  # pending, completed, overdue
    auto_created = Column(Boolean, default=False)  # True if created by AI
    confidence_score = Column(Integer, nullable=True)  # AI confidence 0-100
    source_quote = Column(Text, nullable=True)  # Text that triggered this action
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="action_items")
    email = relationship("Email", back_populates="action_items")

class Huddle(Base):
    __tablename__ = "huddles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="active")  # active, archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    creator = relationship("User", back_populates="huddles_created")
    members = relationship("HuddleMember", back_populates="huddle", cascade="all, delete-orphan")
    messages = relationship("HuddleMessage", back_populates="huddle", cascade="all, delete-orphan")
    shared_emails = relationship("HuddleEmail", back_populates="huddle", cascade="all, delete-orphan")

class HuddleMember(Base):
    __tablename__ = "huddle_members"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    huddle_id = Column(String, ForeignKey("huddles.id"), nullable=False)
    user_email = Column(String, nullable=False)
    role = Column(String, default="member")  # owner, admin, member
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    huddle = relationship("Huddle", back_populates="members")

class HuddleMessage(Base):
    __tablename__ = "huddle_messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    huddle_id = Column(String, ForeignKey("huddles.id"), nullable=False)
    sender_email = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    huddle = relationship("Huddle", back_populates="messages")

class HuddleEmail(Base):
    __tablename__ = "huddle_emails"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    huddle_id = Column(String, ForeignKey("huddles.id"), nullable=False)
    email_id = Column(String, ForeignKey("emails.id"), nullable=False)
    shared_by = Column(String, nullable=False)
    shared_at = Column(DateTime, default=datetime.utcnow)
    
    huddle = relationship("Huddle", back_populates="shared_emails")

class ChatHistory(Base):
    __tablename__ = "chat_history"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)  # user, assistant
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class UrgencyPattern(Base):
    __tablename__ = "urgency_patterns"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    pattern_type = Column(String)  # 'sender', 'keyword', 'domain'
    pattern_value = Column(String)
    times_marked_urgent = Column(Integer, default=0)
    times_marked_not_urgent = Column(Integer, default=0)
    is_vip = Column(Boolean, default=False)
    is_ignored = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User")


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    
    # Company Information
    company_name = Column(String)
    company_website = Column(String)
    industry = Column(String)
    company_size = Column(String)  # e.g., "1-10", "11-50", "51-200", etc.
    founded_year = Column(Integer)
    
    # Business Details
    value_proposition = Column(Text)
    elevator_pitch = Column(Text)
    key_differentiators = Column(JSON)  # List of differentiators
    target_market = Column(Text)
    ideal_customer_profile = Column(JSON)  # Dict with criteria
    
    # Products/Services
    products_services = Column(JSON)  # List of products/services with descriptions
    pricing_model = Column(Text)
    average_deal_size = Column(Integer)  # Legacy - use min/max instead

    # Sales Context (NEW)
    sales_cycle_length = Column(String)  # "1-2 weeks", "1-3 months", "6+ months"
    average_deal_size_min = Column(Integer)  # Minimum typical deal size
    average_deal_size_max = Column(Integer)  # Maximum typical deal size
    decision_makers = Column(JSON)  # ["CEO", "CTO", "Procurement Manager"]
    common_objections = Column(JSON)  # [{"objection": "price", "response": "..."}]
    competitors = Column(JSON)  # [{"name": "CompetitorX", "differentiator": "We offer..."}]
    sales_methodology = Column(String)  # "SPIN", "Challenger", "Solution Selling", etc.

    # Target Market for Prospecting (NEW)
    target_industries = Column(JSON)  # ["Agriculture", "Manufacturing"]
    target_company_sizes = Column(JSON)  # ["50-200", "200-500"]
    target_job_titles = Column(JSON)  # ["Purchasing Manager", "Operations Director"]
    target_locations = Column(JSON)  # ["Midwest US", "California"]
    excluded_industries = Column(JSON)  # ["Restaurants", "Healthcare"]

    # Pain Points & Solutions (NEW)
    customer_pain_points = Column(JSON)  # ["High equipment downtime", "Inefficient processes"]
    solutions_offered = Column(JSON)  # [{"pain": "downtime", "solution": "24/7 support"}]
    unique_selling_points = Column(JSON)  # ["Only provider with X", "Patented technology"]

    # Success Stories
    case_studies = Column(JSON)  # List of case studies
    testimonials = Column(JSON)  # List of testimonials
    notable_clients = Column(JSON)  # List of client names

    # Marketing Materials
    email_signature = Column(Text)
    email_signature_html = Column(Text)  # Rich HTML signature
    boilerplate = Column(Text)  # Standard company description
    social_proof_stats = Column(JSON)  # e.g., {"customers": 1000, "satisfaction": "98%"}

    # Communication Preferences (NEW)
    preferred_outreach_channels = Column(JSON)  # ["email", "phone", "linkedin"]
    follow_up_cadence = Column(String)  # "aggressive", "moderate", "conservative"
    calendar_link = Column(String)  # Calendly/HubSpot meeting link

    # Success Metrics (NEW)
    win_rate = Column(Float)  # Historical win rate %
    average_response_time = Column(String)  # "Same day", "24 hours", etc.
    nps_score = Column(Integer)  # Net Promoter Score
    customer_retention_rate = Column(Float)  # Retention rate %

    # Learned Patterns (auto-updated)
    successful_subject_lines = Column(JSON)  # List of high-performing subject lines
    successful_email_patterns = Column(JSON)  # Patterns that get responses
    best_sending_times = Column(JSON)  # Optimal times by day

    # Settings
    cold_email_tone = Column(String, default="professional")  # professional, casual, technical
    max_emails_per_day = Column(Integer, default=50)
    quality_threshold = Column(Integer, default=70)  # Minimum quality score (0-100)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="business_profile")


class ColdEmailCampaign(Base):
    __tablename__ = "cold_email_campaigns"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    
    name = Column(String)
    status = Column(String, default="draft")  # draft, active, paused, completed
    campaign_type = Column(String)  # product_launch, lead_generation, event_invitation, etc.
    
    # Targeting
    target_industries = Column(JSON)
    target_roles = Column(JSON)
    target_company_sizes = Column(JSON)
    
    # Email Content
    email_template_id = Column(String)
    subject_line_variants = Column(JSON)  # A/B testing variants
    
    # Metrics
    total_prospects = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    emails_opened = Column(Integer, default=0)
    emails_responded = Column(Integer, default=0)
    meetings_booked = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="cold_campaigns")
    prospects = relationship("ColdEmailProspect", back_populates="campaign")


class ColdEmailProspect(Base):
    __tablename__ = "cold_email_prospects"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String, ForeignKey("cold_email_campaigns.id"))
    
    # Contact Information
    email = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    job_title = Column(String)
    linkedin_url = Column(String)
    phone = Column(String)
    
    # Company Information
    company_name = Column(String)
    company_website = Column(String)
    company_industry = Column(String)
    company_size = Column(String)
    company_linkedin = Column(String)
    
    # Enriched Data
    company_description = Column(Text)
    recent_news = Column(JSON)  # Recent company news/updates
    technologies_used = Column(JSON)  # Tech stack
    pain_points = Column(JSON)  # Identified pain points
    buying_signals = Column(JSON)  # Triggers like funding, expansion
    
    # Personalization Data
    mutual_connections = Column(JSON)
    relevant_case_study = Column(String)
    personalization_notes = Column(Text)
    
    # Scoring
    lead_score = Column(Integer, default=0)
    personalization_score = Column(Integer, default=0)
    quality_score = Column(Integer, default=0)
    
    # Review Status
    review_status = Column(String, default="pending")  # pending, approved, rejected, edited
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    
    # Email Status
    email_status = Column(String, default="draft")  # draft, ready, sent, opened, responded, bounced
    email_sent_at = Column(DateTime)
    email_opened_at = Column(DateTime)
    email_responded_at = Column(DateTime)
    response_sentiment = Column(String)  # positive, neutral, negative
    
    # Generated Email
    generated_subject = Column(String)
    generated_body = Column(Text)
    email_version = Column(String)  # A/B test variant
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    campaign = relationship("ColdEmailCampaign", back_populates="prospects")


# ============================================
# LEAD ACQUISITION MODELS (NEW)
# ============================================

class ProspectSource(Base):
    """Tracks websites scraped for prospect data"""
    __tablename__ = "prospect_sources"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    source_type = Column(String)  # "website", "linkedin_csv", "crm_import", "manual"
    source_url = Column(String)  # URL that was scraped
    domain = Column(String, index=True)  # Domain extracted from URL
    scraped_at = Column(DateTime)
    contacts_found = Column(Integer, default=0)
    emails_verified = Column(Integer, default=0)
    raw_data = Column(JSON)  # Raw scraped content
    status = Column(String, default="pending")  # pending, processing, completed, failed
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TargetingCriteria(Base):
    """User-defined targeting criteria for prospecting relevance"""
    __tablename__ = "targeting_criteria"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, default="Default")  # Name for this targeting profile
    is_default = Column(Boolean, default=False)  # Is this the default profile?

    # Include criteria
    target_industries = Column(JSON)  # ["Agriculture", "Manufacturing"]
    target_job_titles = Column(JSON)  # ["Purchasing Manager", "Operations Director"]
    target_company_sizes = Column(JSON)  # ["50-200", "200-500"]
    target_locations = Column(JSON)  # ["Midwest US", "California"]

    # Exclude criteria
    excluded_industries = Column(JSON)  # ["Restaurants", "Healthcare"]
    excluded_domains = Column(JSON)  # ["competitor.com", "spam.com"]

    # Scoring settings
    min_relevance_score = Column(Integer, default=50)  # 0-100 threshold

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EnrichmentCache(Base):
    """Cache for enrichment API responses to avoid duplicate calls"""
    __tablename__ = "enrichment_cache"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    lookup_key = Column(String, index=True, nullable=False)  # email or domain
    lookup_type = Column(String)  # "email", "domain", "company"
    provider = Column(String)  # "hunter", "apollo", "clearbit"
    data = Column(JSON)  # Enriched data response
    expires_at = Column(DateTime)  # Cache expiration
    created_at = Column(DateTime, default=datetime.utcnow)


class EnrichmentCredits(Base):
    """Track API credits for enrichment providers"""
    __tablename__ = "enrichment_credits"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)  # "hunter", "apollo", "zerobounce"
    credits_remaining = Column(Integer, default=0)
    credits_used_this_month = Column(Integer, default=0)
    monthly_limit = Column(Integer, default=50)  # Free tier default
    reset_date = Column(DateTime)  # When credits reset
    api_key_configured = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LinkedInConnection(Base):
    """LinkedIn connections imported from CSV export"""
    __tablename__ = "linkedin_connections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    linkedin_url = Column(String, index=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, index=True)  # If available
    company = Column(String)
    position = Column(String)
    connected_on = Column(DateTime)
    matched_prospect_id = Column(String, ForeignKey("cold_email_prospects.id"), nullable=True)
    imported_at = Column(DateTime, default=datetime.utcnow)


class CRMConnection(Base):
    """OAuth connections to external CRMs"""
    __tablename__ = "crm_connections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)  # "hubspot", "salesforce", "pipedrive"
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime)
    instance_url = Column(String)  # For Salesforce
    portal_id = Column(String)  # For HubSpot
    is_active = Column(Boolean, default=True)
    last_sync = Column(DateTime)
    sync_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CRMFieldMapping(Base):
    """Custom field mappings between SAIGBOX and CRM fields"""
    __tablename__ = "crm_field_mappings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    crm_connection_id = Column(String, ForeignKey("crm_connections.id"), nullable=False)
    saigbox_field = Column(String, nullable=False)  # e.g., "email", "company_name"
    crm_field = Column(String, nullable=False)  # e.g., "properties.email"
    direction = Column(String, default="bidirectional")  # "to_crm", "from_crm", "bidirectional"
    transform = Column(String)  # Optional transformation function
    created_at = Column(DateTime, default=datetime.utcnow)


class CRMSyncLog(Base):
    """Log of CRM sync operations"""
    __tablename__ = "crm_sync_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    crm_connection_id = Column(String, ForeignKey("crm_connections.id"), nullable=False)
    sync_type = Column(String)  # "full", "incremental", "manual"
    direction = Column(String)  # "import", "export", "bidirectional"
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    records_processed = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    errors = Column(JSON)  # List of error messages


class ABTestResult(Base):
    """A/B test results for email campaigns"""
    __tablename__ = "ab_test_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String, ForeignKey("cold_email_campaigns.id"), nullable=False)
    variant_id = Column(String)  # "A", "B", "C"
    variant_type = Column(String)  # "subject_line", "body", "cta", "send_time"
    variant_content = Column(Text)  # The actual variant content
    emails_sent = Column(Integer, default=0)
    emails_opened = Column(Integer, default=0)
    emails_clicked = Column(Integer, default=0)
    emails_replied = Column(Integer, default=0)
    open_rate = Column(Float)
    reply_rate = Column(Float)
    is_winner = Column(Boolean, default=False)
    statistical_significance = Column(Float)  # p-value
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReferralOpportunity(Base):
    """Detected opportunities for warm introductions"""
    __tablename__ = "referral_opportunities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # The person who can make the introduction
    connector_email = Column(String, nullable=False)
    connector_name = Column(String)

    # The target prospect
    target_email = Column(String)
    target_name = Column(String)
    target_company = Column(String)
    target_title = Column(String)

    # How they're connected
    connection_type = Column(String)  # "direct", "mutual_connection", "same_company"
    connection_strength = Column(Integer)  # 0-100
    evidence = Column(JSON)  # Email IDs showing relationship

    # Status
    status = Column(String, default="identified")  # identified, requested, introduced, converted
    intro_requested_at = Column(DateTime)
    intro_received_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RelationshipEdge(Base):
    """Graph edges representing relationships between contacts"""
    __tablename__ = "relationship_edges"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    person_a_email = Column(String, index=True, nullable=False)
    person_b_email = Column(String, index=True, nullable=False)
    relationship_type = Column(String)  # "colleague", "vendor", "client", "introduction"
    interaction_count = Column(Integer, default=1)
    last_interaction = Column(DateTime)
    strength_score = Column(Integer, default=50)  # 0-100
    evidence = Column(JSON)  # Email IDs showing interactions
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CompanyMention(Base):
    """Companies mentioned in emails (for second-degree network mining)"""
    __tablename__ = "company_mentions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    email_id = Column(String, ForeignKey("emails.id"), nullable=False)
    company_name = Column(String, index=True, nullable=False)
    company_domain = Column(String, index=True)  # Extracted or looked up
    mention_context = Column(Text)  # Surrounding text
    mention_type = Column(String)  # "selling_to", "buying_from", "partnering", "mentioned"
    sentiment = Column(String)  # "positive", "neutral", "negative"
    is_prospect_company = Column(Boolean, default=False)  # Potential prospect?
    created_at = Column(DateTime, default=datetime.utcnow)


class SecondDegreeContact(Base):
    """Contacts discovered through second-degree network analysis"""
    __tablename__ = "second_degree_contacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Contact info
    contact_email = Column(String, index=True)
    contact_name = Column(String)
    contact_company = Column(String)
    contact_title = Column(String)

    # How discovered
    introduced_by_email = Column(String)  # Email of person who introduced them
    introduced_by_name = Column(String)
    source_type = Column(String)  # "forward", "cc", "mention", "intro_email"
    source_email_id = Column(String, ForeignKey("emails.id"))

    # Status
    converted_to_prospect = Column(Boolean, default=False)
    prospect_id = Column(String, ForeignKey("cold_email_prospects.id"), nullable=True)
    relevance_score = Column(Integer)  # 0-100

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Create all tables
Base.metadata.create_all(bind=engine)