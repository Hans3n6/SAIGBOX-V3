"""
Base Enrichment Provider
Abstract base class for all enrichment providers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class EnrichmentResult:
    """Result from an enrichment lookup"""
    success: bool
    provider: str
    lookup_type: str  # "email", "domain", "company"
    lookup_key: str  # The email/domain/company looked up

    # Contact data
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    email_type: Optional[str] = None  # personal, generic
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None

    # Company data
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_industry: Optional[str] = None
    company_size: Optional[str] = None
    company_location: Optional[str] = None
    company_description: Optional[str] = None
    company_founded: Optional[int] = None
    company_linkedin: Optional[str] = None
    company_twitter: Optional[str] = None

    # Metadata
    confidence: float = 0.0  # 0-1
    credits_used: int = 0
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    cached: bool = False
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "provider": self.provider,
            "lookup_type": self.lookup_type,
            "lookup_key": self.lookup_key,
            "contact": {
                "email": self.email,
                "email_verified": self.email_verified,
                "email_type": self.email_type,
                "first_name": self.first_name,
                "last_name": self.last_name,
                "full_name": self.full_name,
                "job_title": self.job_title,
                "phone": self.phone,
                "linkedin_url": self.linkedin_url
            },
            "company": {
                "name": self.company_name,
                "domain": self.company_domain,
                "industry": self.company_industry,
                "size": self.company_size,
                "location": self.company_location,
                "description": self.company_description,
                "founded": self.company_founded,
                "linkedin": self.company_linkedin,
                "twitter": self.company_twitter
            },
            "metadata": {
                "confidence": self.confidence,
                "credits_used": self.credits_used,
                "cached": self.cached,
                "error": self.error,
                "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None
            }
        }


class EnrichmentProvider(ABC):
    """Abstract base class for enrichment providers"""

    PROVIDER_NAME: str = "base"
    SUPPORTS_EMAIL_LOOKUP: bool = False
    SUPPORTS_DOMAIN_LOOKUP: bool = False
    SUPPORTS_EMAIL_VERIFICATION: bool = False

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the provider.

        Args:
            api_key: API key for the provider
        """
        self.api_key = api_key
        self._credits_remaining: Optional[int] = None

    @property
    def is_configured(self) -> bool:
        """Check if the provider is properly configured"""
        return bool(self.api_key)

    @property
    def credits_remaining(self) -> Optional[int]:
        """Get remaining API credits"""
        return self._credits_remaining

    @abstractmethod
    async def find_email(
        self,
        domain: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> EnrichmentResult:
        """
        Find email address for a person at a company.

        Args:
            domain: Company domain
            first_name: Person's first name
            last_name: Person's last name

        Returns:
            EnrichmentResult with email if found
        """
        pass

    @abstractmethod
    async def verify_email(self, email: str) -> EnrichmentResult:
        """
        Verify if an email address is valid and deliverable.

        Args:
            email: Email address to verify

        Returns:
            EnrichmentResult with verification status
        """
        pass

    @abstractmethod
    async def enrich_domain(self, domain: str) -> EnrichmentResult:
        """
        Get company information from domain.

        Args:
            domain: Company domain

        Returns:
            EnrichmentResult with company data
        """
        pass

    @abstractmethod
    async def search_domain(
        self,
        domain: str,
        limit: int = 10
    ) -> List[EnrichmentResult]:
        """
        Search for all contacts at a domain.

        Args:
            domain: Company domain
            limit: Maximum number of results

        Returns:
            List of EnrichmentResults with contacts
        """
        pass

    async def get_account_info(self) -> Dict[str, Any]:
        """
        Get account information including credits.

        Returns:
            Dict with account info
        """
        return {
            "provider": self.PROVIDER_NAME,
            "configured": self.is_configured,
            "credits_remaining": self.credits_remaining
        }
