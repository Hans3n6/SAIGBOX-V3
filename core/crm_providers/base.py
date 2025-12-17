"""
Base CRM Provider
Abstract base class for all CRM integrations
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class CRMContactStatus(Enum):
    """Standard contact statuses"""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CUSTOMER = "customer"
    LOST = "lost"


class CRMDealStage(Enum):
    """Standard deal stages"""
    LEAD = "lead"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


@dataclass
class CRMContact:
    """Standardized CRM contact representation"""
    id: Optional[str] = None
    crm_id: Optional[str] = None  # ID in the CRM system
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    company_id: Optional[str] = None
    status: Optional[str] = None
    lead_source: Optional[str] = None
    owner_id: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "crm_id": self.crm_id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name or f"{self.first_name or ''} {self.last_name or ''}".strip(),
            "phone": self.phone,
            "mobile": self.mobile,
            "job_title": self.job_title,
            "company_name": self.company_name,
            "company_id": self.company_id,
            "status": self.status,
            "lead_source": self.lead_source,
            "owner_id": self.owner_id,
            "linkedin_url": self.linkedin_url,
            "notes": self.notes,
            "tags": self.tags,
            "custom_fields": self.custom_fields,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


@dataclass
class CRMDeal:
    """Standardized CRM deal/opportunity representation"""
    id: Optional[str] = None
    crm_id: Optional[str] = None  # ID in the CRM system
    name: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "USD"
    stage: Optional[str] = None
    probability: Optional[float] = None
    close_date: Optional[datetime] = None
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    owner_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    notes: Optional[str] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "crm_id": self.crm_id,
            "name": self.name,
            "amount": self.amount,
            "currency": self.currency,
            "stage": self.stage,
            "probability": self.probability,
            "close_date": self.close_date.isoformat() if self.close_date else None,
            "contact_id": self.contact_id,
            "company_id": self.company_id,
            "owner_id": self.owner_id,
            "pipeline_id": self.pipeline_id,
            "notes": self.notes,
            "custom_fields": self.custom_fields,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class CRMProvider(ABC):
    """Abstract base class for CRM providers"""

    PROVIDER_NAME: str = "base"
    SUPPORTS_OAUTH: bool = False
    SUPPORTS_API_KEY: bool = False

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None
    ):
        """
        Initialize the provider.

        Args:
            api_key: API key for key-based auth
            access_token: OAuth access token
            refresh_token: OAuth refresh token
        """
        self.api_key = api_key
        self.access_token = access_token
        self.refresh_token = refresh_token

    @property
    def is_configured(self) -> bool:
        """Check if the provider is properly configured"""
        if self.SUPPORTS_API_KEY and self.api_key:
            return True
        if self.SUPPORTS_OAUTH and self.access_token:
            return True
        return False

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """Test the CRM connection"""
        pass

    @abstractmethod
    async def get_contacts(
        self,
        limit: int = 100,
        offset: int = 0,
        modified_after: Optional[datetime] = None
    ) -> List[CRMContact]:
        """Get contacts from CRM"""
        pass

    @abstractmethod
    async def get_contact(self, contact_id: str) -> Optional[CRMContact]:
        """Get a single contact by ID"""
        pass

    @abstractmethod
    async def create_contact(self, contact: CRMContact) -> CRMContact:
        """Create a new contact in CRM"""
        pass

    @abstractmethod
    async def update_contact(
        self,
        contact_id: str,
        contact: CRMContact
    ) -> CRMContact:
        """Update an existing contact"""
        pass

    @abstractmethod
    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact"""
        pass

    @abstractmethod
    async def search_contacts(
        self,
        query: str,
        limit: int = 50
    ) -> List[CRMContact]:
        """Search contacts by name/email"""
        pass

    @abstractmethod
    async def get_deals(
        self,
        limit: int = 100,
        offset: int = 0,
        contact_id: Optional[str] = None
    ) -> List[CRMDeal]:
        """Get deals from CRM"""
        pass

    @abstractmethod
    async def create_deal(self, deal: CRMDeal) -> CRMDeal:
        """Create a new deal in CRM"""
        pass

    @abstractmethod
    async def update_deal(self, deal_id: str, deal: CRMDeal) -> CRMDeal:
        """Update an existing deal"""
        pass

    async def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Get OAuth authorization URL"""
        raise NotImplementedError("OAuth not supported by this provider")

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str
    ) -> Dict[str, str]:
        """Exchange OAuth code for tokens"""
        raise NotImplementedError("OAuth not supported by this provider")

    async def refresh_access_token(self) -> Dict[str, str]:
        """Refresh the access token"""
        raise NotImplementedError("OAuth not supported by this provider")
