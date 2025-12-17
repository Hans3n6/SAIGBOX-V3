"""
Hunter.io Enrichment Provider
Adapter for Hunter.io email finding and verification API
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

import httpx

from .base import EnrichmentProvider, EnrichmentResult

logger = logging.getLogger(__name__)


class HunterProvider(EnrichmentProvider):
    """Hunter.io email finding and verification provider"""

    PROVIDER_NAME = "hunter"
    SUPPORTS_EMAIL_LOOKUP = True
    SUPPORTS_DOMAIN_LOOKUP = True
    SUPPORTS_EMAIL_VERIFICATION = True

    BASE_URL = "https://api.hunter.io/v2"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Hunter.io provider.

        Args:
            api_key: Hunter.io API key
        """
        super().__init__(api_key)
        self._monthly_requests = None
        self._requests_remaining = None

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a request to Hunter.io API"""
        if not self.api_key:
            raise ValueError("Hunter.io API key not configured")

        params = params or {}
        params["api_key"] = self.api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params
            )

            # Update credits from headers
            if "X-RateLimit-Remaining" in response.headers:
                self._requests_remaining = int(response.headers["X-RateLimit-Remaining"])
                self._credits_remaining = self._requests_remaining

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                raise ValueError("Invalid Hunter.io API key")
            elif response.status_code == 429:
                raise ValueError("Hunter.io rate limit exceeded")
            else:
                data = response.json()
                raise ValueError(data.get("errors", [{}])[0].get("details", "Unknown error"))

    async def find_email(
        self,
        domain: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> EnrichmentResult:
        """
        Find email for a person at a company using Hunter.io.

        Uses the email-finder endpoint if name is provided,
        otherwise uses domain-search to find generic emails.
        """
        try:
            if first_name and last_name:
                # Use email finder for specific person
                data = await self._make_request(
                    "email-finder",
                    {
                        "domain": domain,
                        "first_name": first_name,
                        "last_name": last_name
                    }
                )

                result_data = data.get("data", {})
                email = result_data.get("email")
                confidence = result_data.get("score", 0) / 100

                return EnrichmentResult(
                    success=bool(email),
                    provider=self.PROVIDER_NAME,
                    lookup_type="email_finder",
                    lookup_key=f"{first_name}.{last_name}@{domain}",
                    email=email,
                    email_verified=result_data.get("verification", {}).get("status") == "valid",
                    first_name=result_data.get("first_name", first_name),
                    last_name=result_data.get("last_name", last_name),
                    full_name=f"{first_name} {last_name}",
                    job_title=result_data.get("position"),
                    linkedin_url=result_data.get("linkedin"),
                    company_name=result_data.get("company"),
                    company_domain=domain,
                    confidence=confidence,
                    credits_used=1,
                    raw_response=data
                )

            else:
                # Use domain search for any email
                results = await self.search_domain(domain, limit=1)
                if results:
                    return results[0]

                return EnrichmentResult(
                    success=False,
                    provider=self.PROVIDER_NAME,
                    lookup_type="email_finder",
                    lookup_key=domain,
                    company_domain=domain,
                    error="No emails found for domain",
                    credits_used=1
                )

        except Exception as e:
            logger.error(f"Hunter.io email finder error: {e}")
            return EnrichmentResult(
                success=False,
                provider=self.PROVIDER_NAME,
                lookup_type="email_finder",
                lookup_key=domain,
                error=str(e),
                credits_used=0
            )

    async def verify_email(self, email: str) -> EnrichmentResult:
        """
        Verify an email address using Hunter.io.

        Note: This uses 1 request from your monthly quota.
        """
        try:
            data = await self._make_request(
                "email-verifier",
                {"email": email}
            )

            result_data = data.get("data", {})
            status = result_data.get("status")
            is_valid = status in ["valid", "accept_all"]

            return EnrichmentResult(
                success=True,
                provider=self.PROVIDER_NAME,
                lookup_type="email_verification",
                lookup_key=email,
                email=email,
                email_verified=is_valid,
                email_type="generic" if result_data.get("type") == "generic" else "personal",
                first_name=result_data.get("first_name"),
                last_name=result_data.get("last_name"),
                confidence=result_data.get("score", 0) / 100 if is_valid else 0,
                credits_used=1,
                raw_response=data
            )

        except Exception as e:
            logger.error(f"Hunter.io email verification error: {e}")
            return EnrichmentResult(
                success=False,
                provider=self.PROVIDER_NAME,
                lookup_type="email_verification",
                lookup_key=email,
                email=email,
                error=str(e),
                credits_used=0
            )

    async def enrich_domain(self, domain: str) -> EnrichmentResult:
        """
        Get company information from domain using Hunter.io.

        Uses the domain-search endpoint to get organization info.
        """
        try:
            data = await self._make_request(
                "domain-search",
                {"domain": domain, "limit": 1}
            )

            result_data = data.get("data", {})
            org = result_data.get("organization") or ""
            industry = result_data.get("industry") or ""
            country = result_data.get("country") or ""

            # Get pattern for email generation
            pattern = result_data.get("pattern")

            return EnrichmentResult(
                success=True,
                provider=self.PROVIDER_NAME,
                lookup_type="domain_enrichment",
                lookup_key=domain,
                company_name=org,
                company_domain=domain,
                company_industry=industry,
                company_location=country,
                confidence=0.8 if org else 0.5,
                credits_used=1,
                raw_response={
                    **data,
                    "email_pattern": pattern
                }
            )

        except Exception as e:
            logger.error(f"Hunter.io domain enrichment error: {e}")
            return EnrichmentResult(
                success=False,
                provider=self.PROVIDER_NAME,
                lookup_type="domain_enrichment",
                lookup_key=domain,
                company_domain=domain,
                error=str(e),
                credits_used=0
            )

    async def search_domain(
        self,
        domain: str,
        limit: int = 10
    ) -> List[EnrichmentResult]:
        """
        Search for all contacts at a domain using Hunter.io.

        This is the main endpoint for finding emails at a company.
        """
        try:
            data = await self._make_request(
                "domain-search",
                {"domain": domain, "limit": limit}
            )

            result_data = data.get("data", {})
            emails = result_data.get("emails", [])
            org = result_data.get("organization", "")
            pattern = result_data.get("pattern")

            results = []
            for email_data in emails:
                results.append(EnrichmentResult(
                    success=True,
                    provider=self.PROVIDER_NAME,
                    lookup_type="domain_search",
                    lookup_key=domain,
                    email=email_data.get("value"),
                    email_verified=email_data.get("verification", {}).get("status") == "valid",
                    email_type=email_data.get("type"),
                    first_name=email_data.get("first_name"),
                    last_name=email_data.get("last_name"),
                    full_name=f"{email_data.get('first_name', '')} {email_data.get('last_name', '')}".strip(),
                    job_title=email_data.get("position"),
                    phone=email_data.get("phone_number"),
                    linkedin_url=email_data.get("linkedin"),
                    company_name=org,
                    company_domain=domain,
                    confidence=email_data.get("confidence", 0) / 100,
                    credits_used=0,  # Only first request uses credit
                    raw_response=email_data
                ))

            # Mark first result as using the credit
            if results:
                results[0].credits_used = 1

            return results

        except Exception as e:
            logger.error(f"Hunter.io domain search error: {e}")
            return [EnrichmentResult(
                success=False,
                provider=self.PROVIDER_NAME,
                lookup_type="domain_search",
                lookup_key=domain,
                error=str(e),
                credits_used=0
            )]

    async def get_account_info(self) -> Dict[str, Any]:
        """Get Hunter.io account information"""
        try:
            data = await self._make_request("account")
            account_data = data.get("data", {})

            requests = account_data.get("requests", {})
            self._monthly_requests = requests.get("searches", {}).get("available", 0)
            self._credits_remaining = requests.get("searches", {}).get("available", 0)

            return {
                "provider": self.PROVIDER_NAME,
                "configured": self.is_configured,
                "plan": account_data.get("plan_name"),
                "email": account_data.get("email"),
                "credits_remaining": self._credits_remaining,
                "monthly_limit": requests.get("searches", {}).get("used", 0) + self._credits_remaining,
                "verifications_remaining": requests.get("verifications", {}).get("available", 0)
            }

        except Exception as e:
            logger.error(f"Hunter.io account info error: {e}")
            return {
                "provider": self.PROVIDER_NAME,
                "configured": self.is_configured,
                "error": str(e)
            }
