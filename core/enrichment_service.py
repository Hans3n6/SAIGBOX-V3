"""
Enrichment Service
Orchestrates contact and company enrichment using multiple providers
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from core.database import EnrichmentCache, EnrichmentCredits
from core.enrichment_providers import EnrichmentProvider, EnrichmentResult, HunterProvider

logger = logging.getLogger(__name__)


class EnrichmentService:
    """
    Service for enriching contact and company data.

    Features:
    - Abstract provider interface for swappable sources
    - Caching layer to avoid duplicate API calls
    - Fallback chain between providers
    - Credit/quota tracking
    """

    # Cache expiration times
    CACHE_TTL_HOURS = {
        "email_finder": 24 * 7,  # 1 week
        "email_verification": 24 * 30,  # 1 month
        "domain_enrichment": 24 * 7,  # 1 week
        "domain_search": 24 * 3,  # 3 days
    }

    def __init__(
        self,
        db: Session,
        user_id: str,
        hunter_api_key: Optional[str] = None
    ):
        """
        Initialize the enrichment service.

        Args:
            db: Database session
            user_id: User ID for credit tracking
            hunter_api_key: Hunter.io API key (or from env)
        """
        self.db = db
        self.user_id = user_id

        # Initialize providers
        self.providers: Dict[str, EnrichmentProvider] = {}

        # Hunter.io (default provider)
        hunter_key = hunter_api_key or os.getenv("HUNTER_API_KEY")
        if hunter_key:
            self.providers["hunter"] = HunterProvider(hunter_key)

        # Future: Add more providers here
        # self.providers["apollo"] = ApolloProvider(os.getenv("APOLLO_API_KEY"))
        # self.providers["clearbit"] = ClearbitProvider(os.getenv("CLEARBIT_API_KEY"))

    @property
    def configured_providers(self) -> List[str]:
        """Get list of configured providers"""
        return [
            name for name, provider in self.providers.items()
            if provider.is_configured
        ]

    def _get_cache_key(self, lookup_type: str, lookup_key: str) -> str:
        """Generate cache key"""
        return f"{lookup_type}:{lookup_key.lower()}"

    def _get_cached(
        self,
        lookup_type: str,
        lookup_key: str
    ) -> Optional[EnrichmentResult]:
        """Get cached enrichment result if valid"""
        cache_key = self._get_cache_key(lookup_type, lookup_key)

        cached = self.db.query(EnrichmentCache).filter(
            EnrichmentCache.lookup_key == cache_key
        ).first()

        if cached and cached.expires_at > datetime.utcnow():
            data = cached.data or {}
            return EnrichmentResult(
                success=data.get("success", False),
                provider=cached.provider,
                lookup_type=lookup_type,
                lookup_key=lookup_key,
                email=data.get("email"),
                email_verified=data.get("email_verified"),
                email_type=data.get("email_type"),
                first_name=data.get("first_name"),
                last_name=data.get("last_name"),
                full_name=data.get("full_name"),
                job_title=data.get("job_title"),
                phone=data.get("phone"),
                linkedin_url=data.get("linkedin_url"),
                company_name=data.get("company_name"),
                company_domain=data.get("company_domain"),
                company_industry=data.get("company_industry"),
                company_size=data.get("company_size"),
                company_location=data.get("company_location"),
                company_description=data.get("company_description"),
                confidence=data.get("confidence", 0),
                credits_used=0,  # Cached, no credits used
                cached=True
            )

        return None

    def _cache_result(
        self,
        lookup_type: str,
        lookup_key: str,
        result: EnrichmentResult
    ):
        """Cache an enrichment result"""
        cache_key = self._get_cache_key(lookup_type, lookup_key)
        ttl_hours = self.CACHE_TTL_HOURS.get(lookup_type, 24)

        # Prepare data for caching
        cache_data = {
            "success": result.success,
            "email": result.email,
            "email_verified": result.email_verified,
            "email_type": result.email_type,
            "first_name": result.first_name,
            "last_name": result.last_name,
            "full_name": result.full_name,
            "job_title": result.job_title,
            "phone": result.phone,
            "linkedin_url": result.linkedin_url,
            "company_name": result.company_name,
            "company_domain": result.company_domain,
            "company_industry": result.company_industry,
            "company_size": result.company_size,
            "company_location": result.company_location,
            "company_description": result.company_description,
            "confidence": result.confidence
        }

        # Check if exists
        existing = self.db.query(EnrichmentCache).filter(
            EnrichmentCache.lookup_key == cache_key
        ).first()

        if existing:
            existing.data = cache_data
            existing.provider = result.provider
            existing.expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
        else:
            cache = EnrichmentCache(
                lookup_key=cache_key,
                lookup_type=lookup_type,
                provider=result.provider,
                data=cache_data,
                expires_at=datetime.utcnow() + timedelta(hours=ttl_hours)
            )
            self.db.add(cache)

        self.db.commit()

    def _track_credit_usage(self, provider: str, credits: int):
        """Track credit usage for a provider"""
        if credits <= 0:
            return

        credit_record = self.db.query(EnrichmentCredits).filter(
            EnrichmentCredits.user_id == self.user_id,
            EnrichmentCredits.provider == provider
        ).first()

        if not credit_record:
            credit_record = EnrichmentCredits(
                user_id=self.user_id,
                provider=provider,
                credits_remaining=50,  # Free tier default
                credits_used_this_month=0,
                monthly_limit=50
            )
            self.db.add(credit_record)

        credit_record.credits_used_this_month += credits
        credit_record.credits_remaining = max(
            0,
            credit_record.monthly_limit - credit_record.credits_used_this_month
        )
        self.db.commit()

    async def find_email(
        self,
        domain: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        use_cache: bool = True,
        provider: Optional[str] = None
    ) -> EnrichmentResult:
        """
        Find email for a person at a company.

        Args:
            domain: Company domain
            first_name: Person's first name
            last_name: Person's last name
            use_cache: Whether to check cache first
            provider: Specific provider to use (or fallback chain)

        Returns:
            EnrichmentResult with email if found
        """
        lookup_key = f"{first_name or ''}.{last_name or ''}@{domain}"

        # Check cache first
        if use_cache:
            cached = self._get_cached("email_finder", lookup_key)
            if cached:
                return cached

        # Try specified provider or fallback chain
        providers_to_try = (
            [self.providers[provider]] if provider and provider in self.providers
            else [p for p in self.providers.values() if p.SUPPORTS_EMAIL_LOOKUP]
        )

        for p in providers_to_try:
            try:
                result = await p.find_email(domain, first_name, last_name)
                if result.success or result.error:
                    # Cache the result
                    self._cache_result("email_finder", lookup_key, result)
                    # Track credit usage
                    self._track_credit_usage(p.PROVIDER_NAME, result.credits_used)
                    return result
            except Exception as e:
                logger.error(f"Provider {p.PROVIDER_NAME} error: {e}")
                continue

        return EnrichmentResult(
            success=False,
            provider="none",
            lookup_type="email_finder",
            lookup_key=lookup_key,
            error="No configured providers available"
        )

    async def verify_email(
        self,
        email: str,
        use_cache: bool = True,
        provider: Optional[str] = None
    ) -> EnrichmentResult:
        """
        Verify if an email is valid and deliverable.

        Args:
            email: Email address to verify
            use_cache: Whether to check cache first
            provider: Specific provider to use

        Returns:
            EnrichmentResult with verification status
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached("email_verification", email)
            if cached:
                return cached

        # Try providers
        providers_to_try = (
            [self.providers[provider]] if provider and provider in self.providers
            else [p for p in self.providers.values() if p.SUPPORTS_EMAIL_VERIFICATION]
        )

        for p in providers_to_try:
            try:
                result = await p.verify_email(email)
                if result.success:
                    self._cache_result("email_verification", email, result)
                    self._track_credit_usage(p.PROVIDER_NAME, result.credits_used)
                    return result
            except Exception as e:
                logger.error(f"Provider {p.PROVIDER_NAME} error: {e}")
                continue

        return EnrichmentResult(
            success=False,
            provider="none",
            lookup_type="email_verification",
            lookup_key=email,
            error="No configured providers available"
        )

    async def enrich_domain(
        self,
        domain: str,
        use_cache: bool = True,
        provider: Optional[str] = None
    ) -> EnrichmentResult:
        """
        Get company information from domain.

        Args:
            domain: Company domain
            use_cache: Whether to check cache first
            provider: Specific provider to use

        Returns:
            EnrichmentResult with company data
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached("domain_enrichment", domain)
            if cached:
                return cached

        # Try providers
        providers_to_try = (
            [self.providers[provider]] if provider and provider in self.providers
            else [p for p in self.providers.values() if p.SUPPORTS_DOMAIN_LOOKUP]
        )

        for p in providers_to_try:
            try:
                result = await p.enrich_domain(domain)
                if result.success:
                    self._cache_result("domain_enrichment", domain, result)
                    self._track_credit_usage(p.PROVIDER_NAME, result.credits_used)
                    return result
            except Exception as e:
                logger.error(f"Provider {p.PROVIDER_NAME} error: {e}")
                continue

        return EnrichmentResult(
            success=False,
            provider="none",
            lookup_type="domain_enrichment",
            lookup_key=domain,
            error="No configured providers available"
        )

    async def search_domain(
        self,
        domain: str,
        limit: int = 10,
        use_cache: bool = True,
        provider: Optional[str] = None
    ) -> List[EnrichmentResult]:
        """
        Search for all contacts at a domain.

        Args:
            domain: Company domain
            limit: Maximum number of results
            use_cache: Whether to check cache first
            provider: Specific provider to use

        Returns:
            List of EnrichmentResults with contacts
        """
        # For search, we don't cache individual results
        # but could implement a cache for the full search

        providers_to_try = (
            [self.providers[provider]] if provider and provider in self.providers
            else [p for p in self.providers.values() if p.SUPPORTS_DOMAIN_LOOKUP]
        )

        for p in providers_to_try:
            try:
                results = await p.search_domain(domain, limit)
                if results and results[0].success:
                    # Track credit usage (usually 1 for the search)
                    total_credits = sum(r.credits_used for r in results)
                    self._track_credit_usage(p.PROVIDER_NAME, total_credits)
                    return results
            except Exception as e:
                logger.error(f"Provider {p.PROVIDER_NAME} error: {e}")
                continue

        return [EnrichmentResult(
            success=False,
            provider="none",
            lookup_type="domain_search",
            lookup_key=domain,
            error="No configured providers available"
        )]

    async def enrich_contact(
        self,
        email: Optional[str] = None,
        domain: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Full enrichment for a contact.

        Combines email finding, verification, and company enrichment.

        Args:
            email: Known email (will be verified)
            domain: Company domain (for email finding)
            first_name: Person's first name
            last_name: Person's last name

        Returns:
            Dict with combined enrichment data
        """
        result = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "email_verified": None,
            "company": None,
            "enriched": False
        }

        # If no email but have domain and name, try to find email
        if not email and domain and first_name and last_name:
            email_result = await self.find_email(domain, first_name, last_name)
            if email_result.success and email_result.email:
                email = email_result.email
                result["email"] = email
                result["first_name"] = email_result.first_name or first_name
                result["last_name"] = email_result.last_name or last_name
                result["job_title"] = email_result.job_title
                result["linkedin_url"] = email_result.linkedin_url

        # Verify email if we have one
        if email:
            verify_result = await self.verify_email(email)
            result["email_verified"] = verify_result.email_verified

        # Get domain from email if not provided
        if not domain and email and "@" in email:
            domain = email.split("@")[-1]

        # Enrich company info
        if domain:
            company_result = await self.enrich_domain(domain)
            if company_result.success:
                result["company"] = {
                    "name": company_result.company_name,
                    "domain": domain,
                    "industry": company_result.company_industry,
                    "location": company_result.company_location,
                    "description": company_result.company_description
                }

        result["enriched"] = bool(result.get("email_verified") is not None or result.get("company"))

        return result

    async def get_credits_status(self) -> Dict[str, Any]:
        """Get credit status for all providers"""
        credits = {}

        # Get from database
        db_credits = self.db.query(EnrichmentCredits).filter(
            EnrichmentCredits.user_id == self.user_id
        ).all()

        for credit in db_credits:
            credits[credit.provider] = {
                "remaining": credit.credits_remaining,
                "used_this_month": credit.credits_used_this_month,
                "monthly_limit": credit.monthly_limit,
                "reset_date": credit.reset_date.isoformat() if credit.reset_date else None
            }

        # Update with live data from providers
        for name, provider in self.providers.items():
            try:
                account_info = await provider.get_account_info()
                if name not in credits:
                    credits[name] = {}
                credits[name].update({
                    "configured": provider.is_configured,
                    "live_remaining": account_info.get("credits_remaining")
                })
            except Exception as e:
                logger.error(f"Error getting credits for {name}: {e}")

        return {
            "providers": credits,
            "configured_providers": self.configured_providers
        }
