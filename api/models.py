from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None

class EmailBase(BaseModel):
    subject: Optional[str] = None
    sender: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None

class EmailCreate(BaseModel):
    to: List[str]
    subject: str
    body: str
    cc: Optional[List[str]] = []
    bcc: Optional[List[str]] = []

class EmailReply(BaseModel):
    email_id: str
    body: str
    reply_all: bool = False

class EmailUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None

class Email(EmailBase):
    id: str
    gmail_id: Optional[str] = None
    thread_id: Optional[str] = None
    sender_name: Optional[str] = None
    recipients: List[str] = []
    cc: List[str] = []
    bcc: List[str] = []
    snippet: Optional[str] = None
    labels: List[str] = []
    is_read: bool = False
    is_starred: bool = False
    has_attachments: bool = False
    attachments: List[Dict[str, Any]] = []
    received_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ActionItemPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ActionItemStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"

class ActionItemBase(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: ActionItemPriority = ActionItemPriority.MEDIUM

class ActionItemCreate(ActionItemBase):
    email_id: Optional[str] = None

class ActionItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[ActionItemPriority] = None
    status: Optional[ActionItemStatus] = None

class ActionItem(ActionItemBase):
    id: str
    user_id: str
    email_id: Optional[str] = None
    status: ActionItemStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    updated_at: datetime
    
    class Config:
        from_attributes = True

class HuddleBase(BaseModel):
    name: str
    description: Optional[str] = None

class HuddleCreate(HuddleBase):
    member_emails: List[str] = []

class HuddleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class Huddle(HuddleBase):
    id: str
    created_by: str
    status: str
    created_at: datetime
    updated_at: datetime
    members: List[Dict[str, Any]] = []
    
    class Config:
        from_attributes = True

class HuddleMemberAdd(BaseModel):
    email: EmailStr
    role: str = "member"

class HuddleMessageCreate(BaseModel):
    message: str

class HuddleMessage(BaseModel):
    id: str
    huddle_id: str
    sender_email: str
    message: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class HuddleEmailShare(BaseModel):
    email_id: str

class ChatMessage(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str
    actions_taken: List[str] = []

class SyncStatus(BaseModel):
    is_syncing: bool
    last_sync: Optional[datetime] = None
    emails_synced: int = 0
    error: Optional[str] = None

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    
class EmailListResponse(BaseModel):
    emails: List[Email]
    total: int
    page: int
    pages: int
    has_next: bool
    has_prev: bool

class SearchQuery(BaseModel):
    query: str
    in_subject: bool = True
    in_body: bool = True
    in_sender: bool = True
    
class TrashEmptyResponse(BaseModel):
    deleted_count: int
    success: bool
    message: str