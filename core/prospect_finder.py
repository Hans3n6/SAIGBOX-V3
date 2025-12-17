"""
Prospect Finder Service
Scrapes company websites to find contact information for prospecting
"""

import re
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Contact:
    """Represents a contact extracted from a website"""
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_url: Optional[str] = None
    confidence: float = 0.5  # 0-1 confidence score

    def to_dict(self) -> Dict:
        return {
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "job_title": self.job_title,
            "phone": self.phone,
            "linkedin_url": self.linkedin_url,
            "source_url": self.source_url,
            "confidence": self.confidence
        }


@dataclass
class CompanyInfo:
    """Company information extracted from website"""
    domain: str
    name: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    social_links: Dict[str, str] = field(default_factory=dict)


class ProspectFinder:
    """Finds prospects by scraping company websites for contact information"""

    # Pages most likely to contain contact info
    CONTACT_PAGES = [
        "/contact",
        "/contact-us",
        "/about",
        "/about-us",
        "/team",
        "/our-team",
        "/leadership",
        "/management",
        "/staff",
        "/people",
        "/company",
        "/about/team",
        "/about/leadership",
    ]

    # Common job titles to look for (helps identify relevant contacts)
    TARGET_TITLES = [
        "CEO", "CTO", "CFO", "COO", "CMO", "CIO",
        "President", "Vice President", "VP",
        "Director", "Manager", "Head",
        "Owner", "Founder", "Co-Founder",
        "Partner", "Principal",
        "Purchasing", "Procurement", "Buyer",
        "Operations", "Sales", "Marketing",
        "General Manager", "GM"
    ]

    def __init__(self, rate_limit_delay: float = 1.0):
        """
        Initialize the prospect finder.

        Args:
            rate_limit_delay: Delay between requests in seconds
        """
        self.rate_limit_delay = rate_limit_delay
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def find_prospects(
        self,
        website_url: str,
        max_pages: int = 10
    ) -> Dict[str, Any]:
        """
        Find prospects from a company website.

        Args:
            website_url: Company website URL
            max_pages: Maximum pages to scrape

        Returns:
            Dict with company info, contacts, and metadata
        """
        # Normalize URL
        if not website_url.startswith(("http://", "https://")):
            website_url = f"https://{website_url}"

        parsed = urlparse(website_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        domain = parsed.netloc.lower().replace("www.", "")

        result = {
            "success": True,
            "domain": domain,
            "base_url": base_url,
            "company": CompanyInfo(domain=domain),
            "contacts": [],
            "emails_found": [],
            "pages_scraped": [],
            "errors": [],
            "scraped_at": datetime.utcnow().isoformat()
        }

        # Check robots.txt
        robots_allowed = await self._check_robots_txt(base_url)
        if not robots_allowed:
            result["errors"].append("Blocked by robots.txt")
            logger.warning(f"Blocked by robots.txt: {base_url}")
            # Continue anyway but note the warning

        # Scrape pages
        emails_found: Set[str] = set()
        contacts: List[Contact] = []
        pages_scraped: Set[str] = set()

        async with httpx.AsyncClient(
            headers=self.headers,
            follow_redirects=True,
            timeout=15.0
        ) as client:
            # First scrape the homepage
            homepage_data = await self._scrape_page(client, base_url)
            if homepage_data:
                pages_scraped.add("/")
                emails_found.update(homepage_data.get("emails", []))
                result["company"].name = homepage_data.get("company_name")
                result["company"].description = homepage_data.get("meta_description")

            # Then scrape contact pages
            for page_path in self.CONTACT_PAGES:
                if len(pages_scraped) >= max_pages:
                    break

                page_url = urljoin(base_url, page_path)
                await asyncio.sleep(self.rate_limit_delay)

                page_data = await self._scrape_page(client, page_url)
                if page_data and page_data.get("text"):
                    pages_scraped.add(page_path)
                    emails_found.update(page_data.get("emails", []))

                    # Extract contacts from team/leadership pages
                    if any(p in page_path.lower() for p in ["team", "leadership", "people", "staff"]):
                        page_contacts = self._extract_contacts_from_team_page(
                            page_data.get("soup"),
                            domain,
                            page_url
                        )
                        contacts.extend(page_contacts)

        # Filter and dedupe emails
        valid_emails = self._filter_emails(emails_found, domain)

        # Generate email variants for discovered names without emails
        for contact in contacts:
            if not contact.email and contact.first_name and contact.last_name:
                variants = self._generate_email_variants(
                    contact.first_name,
                    contact.last_name,
                    domain
                )
                if variants:
                    contact.email = variants[0]  # Use first variant
                    contact.confidence = 0.6  # Lower confidence for generated

        # Add standalone emails as contacts
        existing_emails = {c.email.lower() for c in contacts if c.email}
        for email in valid_emails:
            if email.lower() not in existing_emails:
                contacts.append(Contact(
                    email=email,
                    source_url=base_url,
                    confidence=0.8
                ))

        # Dedupe contacts by email
        seen_emails = set()
        unique_contacts = []
        for contact in contacts:
            if contact.email and contact.email.lower() not in seen_emails:
                seen_emails.add(contact.email.lower())
                unique_contacts.append(contact)

        result["contacts"] = [c.to_dict() for c in unique_contacts]
        result["emails_found"] = list(valid_emails)
        result["pages_scraped"] = list(pages_scraped)
        result["company"] = {
            "domain": result["company"].domain,
            "name": result["company"].name,
            "industry": result["company"].industry,
            "size": result["company"].size,
            "location": result["company"].location,
            "description": result["company"].description,
            "social_links": result["company"].social_links
        }

        return result

    async def _check_robots_txt(self, base_url: str) -> bool:
        """Check if scraping is allowed by robots.txt"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/robots.txt")
                if response.status_code == 200:
                    content = response.text.lower()
                    # Very basic check - a real implementation would parse properly
                    if "disallow: /" in content and "user-agent: *" in content:
                        return False
        except Exception:
            pass
        return True

    async def _scrape_page(
        self,
        client: httpx.AsyncClient,
        url: str
    ) -> Optional[Dict[str, Any]]:
        """Scrape a single page"""
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "noscript"]):
                element.decompose()

            # Get title
            title = ""
            if soup.title:
                title = soup.title.string.strip() if soup.title.string else ""

            # Get meta description
            meta_desc = ""
            meta_tag = soup.find("meta", attrs={"name": "description"})
            if meta_tag:
                meta_desc = meta_tag.get("content", "")

            # Get main text
            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text)[:10000]

            # Extract emails
            emails = self._extract_emails(response.text)

            # Extract company name from title
            company_name = self._extract_company_name(title)

            return {
                "url": url,
                "title": title,
                "meta_description": meta_desc,
                "text": text,
                "emails": emails,
                "company_name": company_name,
                "soup": soup
            }

        except Exception as e:
            logger.debug(f"Error scraping {url}: {e}")
            return None

    def _extract_emails(self, html: str) -> List[str]:
        """Extract email addresses from HTML"""
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(email_pattern, html)

        # Filter out common false positives
        filtered = []
        for email in set(emails):
            email_lower = email.lower()
            if not any([
                email_lower.endswith((".png", ".jpg", ".gif", ".svg", ".css", ".js")),
                "example.com" in email_lower,
                "sentry.io" in email_lower,
                "wixpress.com" in email_lower,
                "wordpress" in email_lower,
                email_lower.startswith("info@"),  # Keep but flag as generic
                email_lower.startswith("support@"),
                email_lower.startswith("hello@"),
                email_lower.startswith("contact@"),
            ]):
                filtered.append(email)

        return filtered

    def _filter_emails(self, emails: Set[str], domain: str) -> List[str]:
        """Filter emails to only include those from the company domain"""
        company_domain = domain.replace("www.", "")
        valid = []

        for email in emails:
            email_domain = email.split("@")[-1].lower()
            # Accept emails from the company domain
            if email_domain == company_domain or email_domain.endswith(f".{company_domain}"):
                valid.append(email)

        return valid

    def _extract_company_name(self, title: str) -> Optional[str]:
        """Extract company name from page title"""
        if not title:
            return None

        # Common separators in titles
        for sep in [" | ", " - ", " :: ", " — ", " – "]:
            if sep in title:
                parts = title.split(sep)
                # Company name is usually the last or first part
                return parts[-1].strip() if len(parts[-1]) > len(parts[0]) else parts[0].strip()

        return title.strip() if len(title) < 50 else None

    def _extract_contacts_from_team_page(
        self,
        soup: Optional[BeautifulSoup],
        domain: str,
        source_url: str
    ) -> List[Contact]:
        """Extract contacts from a team/leadership page"""
        contacts = []
        if not soup:
            return contacts

        # Look for common patterns in team pages
        # Pattern 1: Cards with name and title
        team_cards = soup.find_all(class_=re.compile(
            r"team|member|person|staff|employee|card|profile",
            re.I
        ))

        for card in team_cards[:20]:  # Limit to prevent too many
            contact = self._parse_team_card(card, domain, source_url)
            if contact:
                contacts.append(contact)

        # Pattern 2: Structured data (schema.org Person)
        person_schemas = soup.find_all(attrs={"itemtype": re.compile(r"Person", re.I)})
        for schema in person_schemas[:20]:
            contact = self._parse_person_schema(schema, domain, source_url)
            if contact:
                contacts.append(contact)

        return contacts

    def _parse_team_card(
        self,
        card: BeautifulSoup,
        domain: str,
        source_url: str
    ) -> Optional[Contact]:
        """Parse a team member card element"""
        # Try to find name
        name_elem = card.find(["h2", "h3", "h4", "h5", "strong", "b"])
        name = name_elem.get_text(strip=True) if name_elem else None

        if not name or len(name) < 3 or len(name) > 50:
            return None

        # Try to find title
        title = None
        for tag in ["p", "span", "div"]:
            title_elems = card.find_all(tag)
            for elem in title_elems:
                text = elem.get_text(strip=True)
                if any(t.lower() in text.lower() for t in self.TARGET_TITLES):
                    title = text
                    break
            if title:
                break

        # Try to find email
        email = None
        email_link = card.find("a", href=re.compile(r"mailto:"))
        if email_link:
            email = email_link.get("href", "").replace("mailto:", "").split("?")[0]

        # Try to find LinkedIn
        linkedin = None
        linkedin_link = card.find("a", href=re.compile(r"linkedin\.com"))
        if linkedin_link:
            linkedin = linkedin_link.get("href")

        # Parse name into first/last
        first_name, last_name = self._parse_name(name)

        if first_name or email:
            return Contact(
                email=email,
                first_name=first_name,
                last_name=last_name,
                full_name=name,
                job_title=title,
                linkedin_url=linkedin,
                source_url=source_url,
                confidence=0.7 if email else 0.5
            )

        return None

    def _parse_person_schema(
        self,
        schema: BeautifulSoup,
        domain: str,
        source_url: str
    ) -> Optional[Contact]:
        """Parse schema.org Person markup"""
        name_elem = schema.find(attrs={"itemprop": "name"})
        name = name_elem.get_text(strip=True) if name_elem else None

        if not name:
            return None

        email_elem = schema.find(attrs={"itemprop": "email"})
        email = email_elem.get_text(strip=True) if email_elem else None

        title_elem = schema.find(attrs={"itemprop": "jobTitle"})
        title = title_elem.get_text(strip=True) if title_elem else None

        first_name, last_name = self._parse_name(name)

        return Contact(
            email=email,
            first_name=first_name,
            last_name=last_name,
            full_name=name,
            job_title=title,
            source_url=source_url,
            confidence=0.8
        )

    def _parse_name(self, full_name: str) -> tuple:
        """Parse a full name into first and last name"""
        if not full_name:
            return None, None

        parts = full_name.strip().split()
        if len(parts) == 1:
            return parts[0], None
        elif len(parts) == 2:
            return parts[0], parts[1]
        else:
            # Assume first word is first name, last word is last name
            return parts[0], parts[-1]

    def _generate_email_variants(
        self,
        first_name: str,
        last_name: str,
        domain: str
    ) -> List[str]:
        """
        Generate common email format variants.

        Returns list of possible emails ordered by likelihood.
        """
        if not first_name or not last_name:
            return []

        first = first_name.lower().strip()
        last = last_name.lower().strip()
        first_initial = first[0] if first else ""

        variants = [
            f"{first}.{last}@{domain}",  # john.smith@
            f"{first}{last}@{domain}",   # johnsmith@
            f"{first_initial}{last}@{domain}",  # jsmith@
            f"{first}@{domain}",         # john@
            f"{first}_{last}@{domain}",  # john_smith@
            f"{last}.{first}@{domain}",  # smith.john@
            f"{first_initial}.{last}@{domain}",  # j.smith@
        ]

        return variants


async def find_prospects_from_website(
    website_url: str,
    max_pages: int = 10,
    rate_limit_delay: float = 1.0
) -> Dict[str, Any]:
    """
    Convenience function to find prospects from a website.

    Args:
        website_url: Company website URL
        max_pages: Maximum pages to scrape
        rate_limit_delay: Delay between requests

    Returns:
        Dict with company info, contacts, and metadata
    """
    finder = ProspectFinder(rate_limit_delay=rate_limit_delay)
    return await finder.find_prospects(website_url, max_pages)


async def find_prospects_batch(
    website_urls: List[str],
    max_concurrent: int = 3,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Find prospects from multiple websites in parallel.

    Args:
        website_urls: List of website URLs
        max_concurrent: Maximum concurrent scrapes
        **kwargs: Additional args passed to find_prospects

    Returns:
        List of results for each website
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def scrape_with_semaphore(url: str):
        async with semaphore:
            try:
                return await find_prospects_from_website(url, **kwargs)
            except Exception as e:
                return {
                    "success": False,
                    "domain": urlparse(url).netloc,
                    "error": str(e)
                }

    tasks = [scrape_with_semaphore(url) for url in website_urls]
    return await asyncio.gather(*tasks)
