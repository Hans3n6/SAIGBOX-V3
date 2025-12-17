"""
LinkedIn Service
Handles LinkedIn connections CSV import and matching
"""

import csv
import io
import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session

from core.database import LinkedInConnection, ColdEmailProspect

logger = logging.getLogger(__name__)


class LinkedInService:
    """
    Service for importing and matching LinkedIn connections.

    Features:
    - Parse LinkedIn connections CSV export
    - Match connections to existing prospects
    - Extract LinkedIn URLs from email signatures
    """

    # LinkedIn CSV columns mapping
    CSV_COLUMNS = {
        "first_name": ["First Name", "first_name"],
        "last_name": ["Last Name", "last_name"],
        "email": ["Email Address", "email"],
        "company": ["Company", "company"],
        "position": ["Position", "position", "title"],
        "connected_on": ["Connected On", "connected_on"],
        "linkedin_url": ["URL", "Profile URL", "linkedin_url"]
    }

    def __init__(self, db: Session, user_id: str):
        """
        Initialize the LinkedIn service.

        Args:
            db: Database session
            user_id: User ID for storing connections
        """
        self.db = db
        self.user_id = user_id

    def parse_csv(self, csv_content: str) -> List[Dict[str, Any]]:
        """
        Parse LinkedIn connections CSV content.

        Args:
            csv_content: CSV file content as string

        Returns:
            List of parsed connection dicts
        """
        connections = []

        try:
            # Try to detect delimiter
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(csv_content[:1024])
            reader = csv.DictReader(io.StringIO(csv_content), dialect=dialect)
        except Exception:
            # Fallback to comma delimiter
            reader = csv.DictReader(io.StringIO(csv_content))

        for row in reader:
            connection = self._parse_row(row)
            if connection:
                connections.append(connection)

        return connections

    def _parse_row(self, row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Parse a single CSV row into a connection dict"""
        connection = {}

        for field, possible_columns in self.CSV_COLUMNS.items():
            for col in possible_columns:
                if col in row and row[col]:
                    connection[field] = row[col].strip()
                    break

        # Must have at least first name or company
        if not connection.get("first_name") and not connection.get("company"):
            return None

        # Parse connected_on date
        if connection.get("connected_on"):
            try:
                # Try common date formats
                date_str = connection["connected_on"]
                for fmt in ["%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"]:
                    try:
                        connection["connected_on"] = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    connection["connected_on"] = None
            except Exception:
                connection["connected_on"] = None

        return connection

    def import_connections(
        self,
        csv_content: str,
        skip_existing: bool = True
    ) -> Dict[str, Any]:
        """
        Import connections from CSV content.

        Args:
            csv_content: CSV file content
            skip_existing: Skip connections that already exist

        Returns:
            Dict with import results
        """
        connections = self.parse_csv(csv_content)

        imported = 0
        skipped = 0
        errors = []

        for conn_data in connections:
            try:
                # Check if already exists
                if skip_existing:
                    existing = self.db.query(LinkedInConnection).filter(
                        LinkedInConnection.user_id == self.user_id,
                        LinkedInConnection.first_name == conn_data.get("first_name"),
                        LinkedInConnection.last_name == conn_data.get("last_name"),
                        LinkedInConnection.company == conn_data.get("company")
                    ).first()

                    if existing:
                        skipped += 1
                        continue

                # Create new connection
                connection = LinkedInConnection(
                    user_id=self.user_id,
                    linkedin_url=conn_data.get("linkedin_url"),
                    first_name=conn_data.get("first_name"),
                    last_name=conn_data.get("last_name"),
                    email=conn_data.get("email"),
                    company=conn_data.get("company"),
                    position=conn_data.get("position"),
                    connected_on=conn_data.get("connected_on"),
                    imported_at=datetime.utcnow()
                )

                self.db.add(connection)
                imported += 1

            except Exception as e:
                errors.append(f"Error importing {conn_data.get('first_name')} {conn_data.get('last_name')}: {str(e)}")
                continue

        self.db.commit()

        return {
            "success": True,
            "total_parsed": len(connections),
            "imported": imported,
            "skipped": skipped,
            "errors": errors
        }

    def get_connections(
        self,
        search: Optional[str] = None,
        company: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get imported LinkedIn connections.

        Args:
            search: Search term for name/company
            company: Filter by company
            limit: Maximum results
            offset: Pagination offset

        Returns:
            Dict with connections and pagination info
        """
        query = self.db.query(LinkedInConnection).filter(
            LinkedInConnection.user_id == self.user_id
        )

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (LinkedInConnection.first_name.ilike(search_term)) |
                (LinkedInConnection.last_name.ilike(search_term)) |
                (LinkedInConnection.company.ilike(search_term)) |
                (LinkedInConnection.position.ilike(search_term))
            )

        if company:
            query = query.filter(LinkedInConnection.company.ilike(f"%{company}%"))

        total = query.count()
        connections = query.order_by(
            LinkedInConnection.imported_at.desc()
        ).offset(offset).limit(limit).all()

        return {
            "connections": [self._serialize_connection(c) for c in connections],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }

    def _serialize_connection(self, conn: LinkedInConnection) -> Dict[str, Any]:
        """Serialize a connection for API response"""
        return {
            "id": conn.id,
            "first_name": conn.first_name,
            "last_name": conn.last_name,
            "full_name": f"{conn.first_name or ''} {conn.last_name or ''}".strip(),
            "email": conn.email,
            "company": conn.company,
            "position": conn.position,
            "linkedin_url": conn.linkedin_url,
            "connected_on": conn.connected_on.isoformat() if conn.connected_on else None,
            "imported_at": conn.imported_at.isoformat() if conn.imported_at else None,
            "matched_prospect_id": conn.matched_prospect_id
        }

    def match_connections_to_prospects(self) -> Dict[str, Any]:
        """
        Match LinkedIn connections to existing prospects.

        Returns:
            Dict with matching results
        """
        matched = 0
        connections = self.db.query(LinkedInConnection).filter(
            LinkedInConnection.user_id == self.user_id,
            LinkedInConnection.matched_prospect_id.is_(None)
        ).all()

        for conn in connections:
            # Try to match by email
            if conn.email:
                prospect = self.db.query(ColdEmailProspect).filter(
                    ColdEmailProspect.email == conn.email
                ).first()

                if prospect:
                    conn.matched_prospect_id = prospect.id
                    matched += 1
                    continue

            # Try to match by name and company
            if conn.first_name and conn.last_name and conn.company:
                prospect = self.db.query(ColdEmailProspect).filter(
                    ColdEmailProspect.first_name.ilike(conn.first_name),
                    ColdEmailProspect.last_name.ilike(conn.last_name),
                    ColdEmailProspect.company_name.ilike(f"%{conn.company}%")
                ).first()

                if prospect:
                    conn.matched_prospect_id = prospect.id
                    matched += 1

        self.db.commit()

        return {
            "connections_checked": len(connections),
            "matched": matched
        }

    def convert_to_prospect(
        self,
        connection_id: str,
        campaign_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convert a LinkedIn connection to a prospect.

        Args:
            connection_id: LinkedIn connection ID
            campaign_id: Optional campaign to add prospect to

        Returns:
            Dict with created prospect info
        """
        connection = self.db.query(LinkedInConnection).filter(
            LinkedInConnection.id == connection_id,
            LinkedInConnection.user_id == self.user_id
        ).first()

        if not connection:
            return {"success": False, "error": "Connection not found"}

        # Check if already a prospect
        if connection.matched_prospect_id:
            return {
                "success": False,
                "error": "Connection already linked to a prospect",
                "prospect_id": connection.matched_prospect_id
            }

        # Create prospect
        prospect = ColdEmailProspect(
            campaign_id=campaign_id,
            email=connection.email,
            first_name=connection.first_name,
            last_name=connection.last_name,
            job_title=connection.position,
            linkedin_url=connection.linkedin_url,
            company_name=connection.company,
            review_status="pending",
            email_status="draft"
        )

        self.db.add(prospect)
        self.db.flush()

        # Link connection to prospect
        connection.matched_prospect_id = prospect.id
        self.db.commit()

        return {
            "success": True,
            "prospect_id": prospect.id,
            "connection_id": connection_id
        }

    @staticmethod
    def extract_linkedin_from_signature(text: str) -> Optional[str]:
        """
        Extract LinkedIn URL from email signature text.

        Args:
            text: Email signature or body text

        Returns:
            LinkedIn URL if found
        """
        # Pattern for LinkedIn URLs
        patterns = [
            r'https?://(?:www\.)?linkedin\.com/in/[\w-]+/?',
            r'linkedin\.com/in/[\w-]+/?',
            r'https?://(?:www\.)?linkedin\.com/pub/[\w/-]+/?'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                url = match.group(0)
                if not url.startswith("http"):
                    url = f"https://{url}"
                return url

        return None

    def find_mutual_connections(
        self,
        prospect_company: str
    ) -> List[Dict[str, Any]]:
        """
        Find LinkedIn connections at a prospect's company.

        Args:
            prospect_company: Company name to search for

        Returns:
            List of matching connections
        """
        connections = self.db.query(LinkedInConnection).filter(
            LinkedInConnection.user_id == self.user_id,
            LinkedInConnection.company.ilike(f"%{prospect_company}%")
        ).all()

        return [self._serialize_connection(c) for c in connections]
