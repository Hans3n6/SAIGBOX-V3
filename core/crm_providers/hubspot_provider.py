"""
HubSpot CRM Provider
Adapter for HubSpot CRM API
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import urlencode

import httpx

from .base import CRMProvider, CRMContact, CRMDeal

logger = logging.getLogger(__name__)


class HubSpotProvider(CRMProvider):
    """HubSpot CRM provider using API key or OAuth"""

    PROVIDER_NAME = "hubspot"
    SUPPORTS_OAUTH = True
    SUPPORTS_API_KEY = True

    BASE_URL = "https://api.hubapi.com"
    AUTH_URL = "https://app.hubspot.com/oauth/authorize"
    TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"

    # Required OAuth scopes
    OAUTH_SCOPES = [
        "crm.objects.contacts.read",
        "crm.objects.contacts.write",
        "crm.objects.deals.read",
        "crm.objects.deals.write",
        "crm.objects.companies.read"
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        """
        Initialize HubSpot provider.

        For API Key auth: Pass api_key
        For OAuth: Pass access_token (and optionally refresh_token)
        For OAuth setup: Pass client_id and client_secret
        """
        super().__init__(api_key, access_token, refresh_token)
        self.client_id = client_id or os.getenv("HUBSPOT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("HUBSPOT_CLIENT_SECRET")

    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        headers = {"Content-Type": "application/json"}

        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif self.api_key:
            # Legacy API key method (deprecated but still works)
            pass  # API key is passed as query param

        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a request to HubSpot API"""
        url = f"{self.BASE_URL}/{endpoint}"
        params = params or {}

        # Add API key to params if using key auth
        if self.api_key and not self.access_token:
            params["hapikey"] = self.api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                headers=self._get_headers(),
                params=params,
                json=data
            )

            if response.status_code == 401:
                raise ValueError("Invalid HubSpot credentials")
            elif response.status_code == 429:
                raise ValueError("HubSpot rate limit exceeded")
            elif response.status_code >= 400:
                error_data = response.json()
                raise ValueError(error_data.get("message", f"HubSpot error: {response.status_code}"))

            return response.json() if response.content else {}

    async def test_connection(self) -> Dict[str, Any]:
        """Test the HubSpot connection"""
        try:
            data = await self._make_request("GET", "crm/v3/objects/contacts", {"limit": 1})
            return {
                "success": True,
                "provider": self.PROVIDER_NAME,
                "message": "Connection successful"
            }
        except Exception as e:
            return {
                "success": False,
                "provider": self.PROVIDER_NAME,
                "error": str(e)
            }

    async def get_contacts(
        self,
        limit: int = 100,
        offset: int = 0,
        modified_after: Optional[datetime] = None
    ) -> List[CRMContact]:
        """Get contacts from HubSpot"""
        params = {
            "limit": min(limit, 100),  # HubSpot max is 100
            "properties": "email,firstname,lastname,phone,mobilephone,jobtitle,company,lifecyclestage,hs_lead_status,linkedin_url"
        }

        if modified_after:
            params["filterGroups"] = [{
                "filters": [{
                    "propertyName": "lastmodifieddate",
                    "operator": "GTE",
                    "value": int(modified_after.timestamp() * 1000)
                }]
            }]

        data = await self._make_request("GET", "crm/v3/objects/contacts", params)

        contacts = []
        for result in data.get("results", []):
            props = result.get("properties", {})
            contacts.append(CRMContact(
                crm_id=result.get("id"),
                email=props.get("email"),
                first_name=props.get("firstname"),
                last_name=props.get("lastname"),
                phone=props.get("phone"),
                mobile=props.get("mobilephone"),
                job_title=props.get("jobtitle"),
                company_name=props.get("company"),
                status=props.get("lifecyclestage"),
                linkedin_url=props.get("linkedin_url"),
                created_at=datetime.fromisoformat(result.get("createdAt").replace("Z", "+00:00")) if result.get("createdAt") else None,
                updated_at=datetime.fromisoformat(result.get("updatedAt").replace("Z", "+00:00")) if result.get("updatedAt") else None
            ))

        return contacts

    async def get_contact(self, contact_id: str) -> Optional[CRMContact]:
        """Get a single contact by ID"""
        try:
            params = {
                "properties": "email,firstname,lastname,phone,mobilephone,jobtitle,company,lifecyclestage,hs_lead_status,linkedin_url,notes_last_updated"
            }
            data = await self._make_request("GET", f"crm/v3/objects/contacts/{contact_id}", params)

            props = data.get("properties", {})
            return CRMContact(
                crm_id=data.get("id"),
                email=props.get("email"),
                first_name=props.get("firstname"),
                last_name=props.get("lastname"),
                phone=props.get("phone"),
                mobile=props.get("mobilephone"),
                job_title=props.get("jobtitle"),
                company_name=props.get("company"),
                status=props.get("lifecyclestage"),
                linkedin_url=props.get("linkedin_url"),
                created_at=datetime.fromisoformat(data.get("createdAt").replace("Z", "+00:00")) if data.get("createdAt") else None,
                updated_at=datetime.fromisoformat(data.get("updatedAt").replace("Z", "+00:00")) if data.get("updatedAt") else None
            )
        except Exception as e:
            logger.error(f"Error getting HubSpot contact: {e}")
            return None

    async def create_contact(self, contact: CRMContact) -> CRMContact:
        """Create a new contact in HubSpot"""
        properties = {}

        if contact.email:
            properties["email"] = contact.email
        if contact.first_name:
            properties["firstname"] = contact.first_name
        if contact.last_name:
            properties["lastname"] = contact.last_name
        if contact.phone:
            properties["phone"] = contact.phone
        if contact.mobile:
            properties["mobilephone"] = contact.mobile
        if contact.job_title:
            properties["jobtitle"] = contact.job_title
        if contact.company_name:
            properties["company"] = contact.company_name
        if contact.linkedin_url:
            properties["linkedin_url"] = contact.linkedin_url
        if contact.status:
            properties["lifecyclestage"] = contact.status
        if contact.lead_source:
            properties["hs_lead_status"] = contact.lead_source

        data = await self._make_request(
            "POST",
            "crm/v3/objects/contacts",
            data={"properties": properties}
        )

        contact.crm_id = data.get("id")
        return contact

    async def update_contact(
        self,
        contact_id: str,
        contact: CRMContact
    ) -> CRMContact:
        """Update an existing contact"""
        properties = {}

        if contact.email:
            properties["email"] = contact.email
        if contact.first_name:
            properties["firstname"] = contact.first_name
        if contact.last_name:
            properties["lastname"] = contact.last_name
        if contact.phone:
            properties["phone"] = contact.phone
        if contact.mobile:
            properties["mobilephone"] = contact.mobile
        if contact.job_title:
            properties["jobtitle"] = contact.job_title
        if contact.company_name:
            properties["company"] = contact.company_name
        if contact.linkedin_url:
            properties["linkedin_url"] = contact.linkedin_url
        if contact.status:
            properties["lifecyclestage"] = contact.status

        await self._make_request(
            "PATCH",
            f"crm/v3/objects/contacts/{contact_id}",
            data={"properties": properties}
        )

        contact.crm_id = contact_id
        return contact

    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact"""
        try:
            await self._make_request("DELETE", f"crm/v3/objects/contacts/{contact_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting HubSpot contact: {e}")
            return False

    async def search_contacts(
        self,
        query: str,
        limit: int = 50
    ) -> List[CRMContact]:
        """Search contacts by name/email"""
        data = await self._make_request(
            "POST",
            "crm/v3/objects/contacts/search",
            data={
                "query": query,
                "limit": min(limit, 100),
                "properties": ["email", "firstname", "lastname", "phone", "jobtitle", "company"]
            }
        )

        contacts = []
        for result in data.get("results", []):
            props = result.get("properties", {})
            contacts.append(CRMContact(
                crm_id=result.get("id"),
                email=props.get("email"),
                first_name=props.get("firstname"),
                last_name=props.get("lastname"),
                phone=props.get("phone"),
                job_title=props.get("jobtitle"),
                company_name=props.get("company")
            ))

        return contacts

    async def get_deals(
        self,
        limit: int = 100,
        offset: int = 0,
        contact_id: Optional[str] = None
    ) -> List[CRMDeal]:
        """Get deals from HubSpot"""
        params = {
            "limit": min(limit, 100),
            "properties": "dealname,amount,dealstage,closedate,pipeline,hs_deal_stage_probability"
        }

        endpoint = "crm/v3/objects/deals"

        # If filtering by contact, use associations
        if contact_id:
            endpoint = f"crm/v3/objects/contacts/{contact_id}/associations/deals"

        data = await self._make_request("GET", endpoint, params)

        deals = []
        for result in data.get("results", []):
            props = result.get("properties", {})

            # Parse close date
            close_date = None
            if props.get("closedate"):
                try:
                    close_date = datetime.fromisoformat(props["closedate"].replace("Z", "+00:00"))
                except Exception:
                    pass

            deals.append(CRMDeal(
                crm_id=result.get("id"),
                name=props.get("dealname"),
                amount=float(props.get("amount", 0)) if props.get("amount") else None,
                stage=props.get("dealstage"),
                probability=float(props.get("hs_deal_stage_probability", 0)) if props.get("hs_deal_stage_probability") else None,
                close_date=close_date,
                pipeline_id=props.get("pipeline"),
                contact_id=contact_id
            ))

        return deals

    async def create_deal(self, deal: CRMDeal) -> CRMDeal:
        """Create a new deal in HubSpot"""
        properties = {}

        if deal.name:
            properties["dealname"] = deal.name
        if deal.amount is not None:
            properties["amount"] = str(deal.amount)
        if deal.stage:
            properties["dealstage"] = deal.stage
        if deal.close_date:
            properties["closedate"] = deal.close_date.strftime("%Y-%m-%d")
        if deal.pipeline_id:
            properties["pipeline"] = deal.pipeline_id

        data = await self._make_request(
            "POST",
            "crm/v3/objects/deals",
            data={"properties": properties}
        )

        deal.crm_id = data.get("id")

        # Associate with contact if provided
        if deal.contact_id:
            await self._associate_deal_contact(deal.crm_id, deal.contact_id)

        return deal

    async def update_deal(self, deal_id: str, deal: CRMDeal) -> CRMDeal:
        """Update an existing deal"""
        properties = {}

        if deal.name:
            properties["dealname"] = deal.name
        if deal.amount is not None:
            properties["amount"] = str(deal.amount)
        if deal.stage:
            properties["dealstage"] = deal.stage
        if deal.close_date:
            properties["closedate"] = deal.close_date.strftime("%Y-%m-%d")

        await self._make_request(
            "PATCH",
            f"crm/v3/objects/deals/{deal_id}",
            data={"properties": properties}
        )

        deal.crm_id = deal_id
        return deal

    async def _associate_deal_contact(self, deal_id: str, contact_id: str):
        """Associate a deal with a contact"""
        await self._make_request(
            "PUT",
            f"crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact"
        )

    async def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Get HubSpot OAuth authorization URL"""
        if not self.client_id:
            raise ValueError("HubSpot client_id not configured")

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.OAUTH_SCOPES),
            "state": state
        }

        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str
    ) -> Dict[str, str]:
        """Exchange OAuth code for tokens"""
        if not self.client_id or not self.client_secret:
            raise ValueError("HubSpot OAuth credentials not configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code
                }
            )

            if response.status_code != 200:
                raise ValueError(f"OAuth error: {response.text}")

            data = response.json()
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")

            return {
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in")
            }

    async def refresh_access_token(self) -> Dict[str, str]:
        """Refresh the HubSpot access token"""
        if not self.refresh_token:
            raise ValueError("No refresh token available")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token
                }
            )

            if response.status_code != 200:
                raise ValueError(f"Token refresh error: {response.text}")

            data = response.json()
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token", self.refresh_token)

            return {
                "access_token": data.get("access_token"),
                "refresh_token": self.refresh_token,
                "expires_in": data.get("expires_in")
            }
