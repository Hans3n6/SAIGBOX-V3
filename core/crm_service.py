"""
CRM Service
Orchestrates CRM integrations and bi-directional sync
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session

from core.database import (
    CRMConnection, CRMFieldMapping, CRMSyncLog,
    ColdEmailProspect, BusinessProfile
)
from core.crm_providers import CRMProvider, CRMContact, CRMDeal, HubSpotProvider

logger = logging.getLogger(__name__)


class CRMService:
    """
    Service for managing CRM integrations.

    Features:
    - Multiple CRM support (HubSpot, Salesforce, Pipedrive)
    - Bi-directional sync
    - Field mapping
    - Sync logging
    """

    SUPPORTED_PROVIDERS = {
        "hubspot": HubSpotProvider,
        # "salesforce": SalesforceProvider,  # Future
        # "pipedrive": PipedriveProvider,    # Future
    }

    def __init__(self, db: Session, user_id: str):
        """
        Initialize the CRM service.

        Args:
            db: Database session
            user_id: User ID for CRM connections
        """
        self.db = db
        self.user_id = user_id
        self._providers: Dict[str, CRMProvider] = {}

    def _get_connection(self, provider: str) -> Optional[CRMConnection]:
        """Get active CRM connection for provider"""
        return self.db.query(CRMConnection).filter(
            CRMConnection.user_id == self.user_id,
            CRMConnection.provider == provider,
            CRMConnection.is_active == True
        ).first()

    def _get_provider(self, provider: str) -> Optional[CRMProvider]:
        """Get or create CRM provider instance"""
        if provider in self._providers:
            return self._providers[provider]

        connection = self._get_connection(provider)
        if not connection:
            return None

        provider_class = self.SUPPORTED_PROVIDERS.get(provider)
        if not provider_class:
            return None

        instance = provider_class(
            access_token=connection.access_token,
            refresh_token=connection.refresh_token
        )

        self._providers[provider] = instance
        return instance

    async def get_connections(self) -> List[Dict[str, Any]]:
        """Get all CRM connections for user"""
        connections = self.db.query(CRMConnection).filter(
            CRMConnection.user_id == self.user_id
        ).all()

        result = []
        for conn in connections:
            provider = self._get_provider(conn.provider)
            status = {"connected": False}

            if provider and provider.is_configured:
                try:
                    status = await provider.test_connection()
                except Exception as e:
                    status = {"connected": False, "error": str(e)}

            result.append({
                "id": conn.id,
                "provider": conn.provider,
                "is_active": conn.is_active,
                "last_sync": conn.last_sync.isoformat() if conn.last_sync else None,
                "sync_error": conn.sync_error,
                "status": status
            })

        return result

    async def connect_hubspot(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Connect to HubSpot CRM.

        Args:
            api_key: HubSpot API key (for free tier)
            access_token: OAuth access token
            refresh_token: OAuth refresh token

        Returns:
            Connection result
        """
        provider = HubSpotProvider(
            api_key=api_key,
            access_token=access_token,
            refresh_token=refresh_token
        )

        # Test connection
        test_result = await provider.test_connection()
        if not test_result.get("success"):
            return {
                "success": False,
                "error": test_result.get("error", "Connection failed")
            }

        # Save or update connection
        existing = self._get_connection("hubspot")
        if existing:
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.is_active = True
            existing.sync_error = None
        else:
            connection = CRMConnection(
                user_id=self.user_id,
                provider="hubspot",
                access_token=access_token,
                refresh_token=refresh_token,
                is_active=True
            )
            self.db.add(connection)

        self.db.commit()
        self._providers["hubspot"] = provider

        return {
            "success": True,
            "provider": "hubspot",
            "message": "HubSpot connected successfully"
        }

    async def disconnect(self, provider: str) -> Dict[str, Any]:
        """Disconnect a CRM provider"""
        connection = self._get_connection(provider)
        if not connection:
            return {"success": False, "error": "Connection not found"}

        connection.is_active = False
        connection.access_token = None
        connection.refresh_token = None
        self.db.commit()

        if provider in self._providers:
            del self._providers[provider]

        return {"success": True, "message": f"{provider} disconnected"}

    async def import_contacts(
        self,
        provider: str,
        limit: int = 100,
        modified_after: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Import contacts from CRM to SAIGBOX prospects.

        Args:
            provider: CRM provider name
            limit: Maximum contacts to import
            modified_after: Only import contacts modified after this date

        Returns:
            Import results
        """
        crm_provider = self._get_provider(provider)
        if not crm_provider:
            return {"success": False, "error": f"{provider} not connected"}

        # Start sync log
        sync_log = CRMSyncLog(
            user_id=self.user_id,
            crm_connection_id=self._get_connection(provider).id,
            sync_type="incremental" if modified_after else "full",
            direction="import"
        )
        self.db.add(sync_log)
        self.db.flush()

        try:
            contacts = await crm_provider.get_contacts(
                limit=limit,
                modified_after=modified_after
            )

            imported = 0
            updated = 0
            failed = 0
            errors = []

            for contact in contacts:
                try:
                    # Check if prospect exists (by email)
                    existing = None
                    if contact.email:
                        existing = self.db.query(ColdEmailProspect).filter(
                            ColdEmailProspect.email == contact.email
                        ).first()

                    if existing:
                        # Update existing prospect
                        self._update_prospect_from_contact(existing, contact)
                        updated += 1
                    else:
                        # Create new prospect
                        self._create_prospect_from_contact(contact)
                        imported += 1

                except Exception as e:
                    failed += 1
                    errors.append(f"Error importing {contact.email}: {str(e)}")

            self.db.commit()

            # Update sync log
            sync_log.completed_at = datetime.utcnow()
            sync_log.records_processed = len(contacts)
            sync_log.records_created = imported
            sync_log.records_updated = updated
            sync_log.records_failed = failed
            sync_log.errors = errors if errors else None

            # Update connection last sync
            connection = self._get_connection(provider)
            connection.last_sync = datetime.utcnow()
            connection.sync_error = None
            self.db.commit()

            return {
                "success": True,
                "imported": imported,
                "updated": updated,
                "failed": failed,
                "total": len(contacts),
                "errors": errors
            }

        except Exception as e:
            sync_log.completed_at = datetime.utcnow()
            sync_log.errors = [str(e)]

            connection = self._get_connection(provider)
            connection.sync_error = str(e)
            self.db.commit()

            return {"success": False, "error": str(e)}

    def _update_prospect_from_contact(
        self,
        prospect: ColdEmailProspect,
        contact: CRMContact
    ):
        """Update a prospect with CRM contact data"""
        if contact.first_name:
            prospect.first_name = contact.first_name
        if contact.last_name:
            prospect.last_name = contact.last_name
        if contact.phone:
            prospect.phone = contact.phone
        if contact.job_title:
            prospect.job_title = contact.job_title
        if contact.company_name:
            prospect.company_name = contact.company_name
        if contact.linkedin_url:
            prospect.linkedin_url = contact.linkedin_url

    def _create_prospect_from_contact(self, contact: CRMContact):
        """Create a new prospect from CRM contact"""
        prospect = ColdEmailProspect(
            email=contact.email,
            first_name=contact.first_name,
            last_name=contact.last_name,
            job_title=contact.job_title,
            phone=contact.phone,
            linkedin_url=contact.linkedin_url,
            company_name=contact.company_name,
            review_status="pending",
            email_status="draft"
        )
        self.db.add(prospect)

    async def export_prospects(
        self,
        provider: str,
        prospect_ids: Optional[List[str]] = None,
        export_all: bool = False
    ) -> Dict[str, Any]:
        """
        Export SAIGBOX prospects to CRM as contacts.

        Args:
            provider: CRM provider name
            prospect_ids: Specific prospects to export
            export_all: Export all prospects

        Returns:
            Export results
        """
        crm_provider = self._get_provider(provider)
        if not crm_provider:
            return {"success": False, "error": f"{provider} not connected"}

        # Get prospects to export
        query = self.db.query(ColdEmailProspect)
        if prospect_ids:
            query = query.filter(ColdEmailProspect.id.in_(prospect_ids))
        elif not export_all:
            return {"success": False, "error": "No prospects specified"}

        prospects = query.all()

        # Start sync log
        sync_log = CRMSyncLog(
            user_id=self.user_id,
            crm_connection_id=self._get_connection(provider).id,
            sync_type="manual",
            direction="export"
        )
        self.db.add(sync_log)
        self.db.flush()

        created = 0
        failed = 0
        errors = []

        for prospect in prospects:
            try:
                # Convert to CRM contact
                contact = CRMContact(
                    email=prospect.email,
                    first_name=prospect.first_name,
                    last_name=prospect.last_name,
                    phone=prospect.phone,
                    job_title=prospect.job_title,
                    company_name=prospect.company_name,
                    linkedin_url=prospect.linkedin_url,
                    lead_source="SAIGBOX"
                )

                # Create in CRM
                created_contact = await crm_provider.create_contact(contact)
                created += 1

            except Exception as e:
                failed += 1
                errors.append(f"Error exporting {prospect.email}: {str(e)}")

        # Update sync log
        sync_log.completed_at = datetime.utcnow()
        sync_log.records_processed = len(prospects)
        sync_log.records_created = created
        sync_log.records_failed = failed
        sync_log.errors = errors if errors else None
        self.db.commit()

        return {
            "success": True,
            "created": created,
            "failed": failed,
            "total": len(prospects),
            "errors": errors
        }

    async def export_deal(
        self,
        provider: str,
        opportunity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Export an opportunity as a CRM deal.

        Args:
            provider: CRM provider name
            opportunity_data: Opportunity data to export

        Returns:
            Export result with deal ID
        """
        crm_provider = self._get_provider(provider)
        if not crm_provider:
            return {"success": False, "error": f"{provider} not connected"}

        try:
            # Create deal
            deal = CRMDeal(
                name=opportunity_data.get("name") or f"Deal with {opportunity_data.get('company', 'Unknown')}",
                amount=opportunity_data.get("deal_value"),
                stage="qualifiedtobuy",  # HubSpot default stage
                close_date=datetime.utcnow()  # Can be updated
            )

            # If we have contact email, try to find/create contact first
            if opportunity_data.get("email"):
                contacts = await crm_provider.search_contacts(opportunity_data["email"], limit=1)
                if contacts:
                    deal.contact_id = contacts[0].crm_id

            created_deal = await crm_provider.create_deal(deal)

            return {
                "success": True,
                "deal_id": created_deal.crm_id,
                "provider": provider
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_sync_history(
        self,
        provider: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get sync history logs"""
        query = self.db.query(CRMSyncLog).filter(
            CRMSyncLog.user_id == self.user_id
        )

        if provider:
            connection = self._get_connection(provider)
            if connection:
                query = query.filter(CRMSyncLog.crm_connection_id == connection.id)

        logs = query.order_by(CRMSyncLog.started_at.desc()).limit(limit).all()

        return [{
            "id": log.id,
            "sync_type": log.sync_type,
            "direction": log.direction,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "records_processed": log.records_processed,
            "records_created": log.records_created,
            "records_updated": log.records_updated,
            "records_failed": log.records_failed,
            "errors": log.errors
        } for log in logs]
