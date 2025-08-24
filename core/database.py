from sqlalchemy import create_engine, Column, String, Text, DateTime, Boolean, Integer, ForeignKey, JSON
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
    
    # Timestamps
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    emails = relationship("Email", back_populates="user")
    action_items = relationship("ActionItem", back_populates="user")
    huddles_created = relationship("Huddle", back_populates="creator")

class Email(Base):
    __tablename__ = "emails"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    gmail_id = Column(String, unique=True, index=True)
    thread_id = Column(String, index=True)
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

# Create all tables
Base.metadata.create_all(bind=engine)