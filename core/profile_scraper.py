"""
Profile Scraper Service
Scrapes company websites and uses AI to extract business profile information
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ProfileScraper:
    """Scrapes company websites and extracts business profile data using AI"""

    # Common page paths to scrape
    PAGES_TO_SCRAPE = [
        "/",
        "/about",
        "/about-us",
        "/about-us/",
        "/company",
        "/products",
        "/services",
        "/solutions",
        "/team",
        "/leadership",
        "/our-team",
        "/contact",
        "/contact-us",
        "/customers",
        "/testimonials",
        "/case-studies",
        # Sales-critical pages for competitor/pricing/objection info
        "/pricing",
        "/plans",
        "/compare",
        "/comparison",
        "/vs",
        "/faq",
        "/faqs",
        "/why-us",
        "/why-choose-us",
        "/industries",
        "/who-we-serve",
    ]

    def __init__(self, bedrock_client=None):
        """
        Initialize the scraper.

        Args:
            bedrock_client: AWS Bedrock client for AI analysis (optional)
        """
        self.bedrock_client = bedrock_client
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def scrape_website(self, url: str) -> Dict[str, Any]:
        """
        Scrape a company website and extract content from key pages.

        Args:
            url: The company website URL

        Returns:
            Dict containing scraped content from each page
        """
        # Normalize URL
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        scraped_data = {
            "base_url": base_url,
            "pages": {},
            "scraped_at": datetime.utcnow().isoformat(),
            "errors": []
        }

        async with httpx.AsyncClient(
            headers=self.headers,
            follow_redirects=True,
            timeout=15.0
        ) as client:
            for page_path in self.PAGES_TO_SCRAPE:
                page_url = urljoin(base_url, page_path)

                try:
                    response = await client.get(page_url)

                    if response.status_code == 200:
                        content = self._extract_page_content(response.text, page_url)
                        if content.get("text") and len(content["text"]) > 100:
                            scraped_data["pages"][page_path] = content
                            logger.info(f"Scraped {page_url}: {len(content['text'])} chars")

                except httpx.TimeoutException:
                    scraped_data["errors"].append(f"Timeout: {page_url}")
                except Exception as e:
                    scraped_data["errors"].append(f"Error {page_url}: {str(e)}")

        return scraped_data

    def _extract_page_content(self, html: str, url: str) -> Dict[str, Any]:
        """
        Extract relevant content from an HTML page.

        Args:
            html: Raw HTML content
            url: Source URL

        Returns:
            Dict with extracted text, title, meta description, etc.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            element.decompose()

        # Get page title
        title = ""
        if soup.title:
            title = soup.title.string.strip() if soup.title.string else ""

        # Get meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")

        # Get main content text
        main_content = soup.find("main") or soup.find("article") or soup.find("body")
        text = ""
        if main_content:
            text = main_content.get_text(separator=" ", strip=True)
            # Clean up whitespace
            text = re.sub(r"\s+", " ", text)
            # Limit length
            text = text[:15000]

        # Extract emails
        emails = self._extract_emails(html)

        # Extract phone numbers
        phones = self._extract_phones(text)

        # Extract social links
        social_links = self._extract_social_links(soup, url)

        return {
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "text": text,
            "emails": emails,
            "phones": phones,
            "social_links": social_links
        }

    def _extract_emails(self, html: str) -> List[str]:
        """Extract email addresses from HTML"""
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(email_pattern, html)
        # Filter out common false positives
        filtered = [
            e for e in set(emails)
            if not e.endswith((".png", ".jpg", ".gif", ".svg"))
            and "example.com" not in e
            and "sentry.io" not in e
        ]
        return filtered[:10]

    def _extract_phones(self, text: str) -> List[str]:
        """Extract phone numbers from text"""
        # Common phone patterns
        patterns = [
            r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
            r"\(\d{3}\)\s*\d{3}[-.\s]?\d{4}",
        ]
        phones = []
        for pattern in patterns:
            found = re.findall(pattern, text)
            phones.extend(found)
        return list(set(phones))[:5]

    def _extract_social_links(self, soup: BeautifulSoup, base_url: str) -> Dict[str, str]:
        """Extract social media profile links"""
        social = {}
        social_patterns = {
            "linkedin": r"linkedin\.com/(company|in)/",
            "twitter": r"(twitter|x)\.com/",
            "facebook": r"facebook\.com/",
            "instagram": r"instagram\.com/",
            "youtube": r"youtube\.com/"
        }

        for link in soup.find_all("a", href=True):
            href = link["href"]
            for platform, pattern in social_patterns.items():
                if re.search(pattern, href) and platform not in social:
                    social[platform] = href

        return social

    async def analyze_with_ai(self, scraped_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use AI to analyze scraped content and extract business profile data.

        Args:
            scraped_data: Dict from scrape_website()

        Returns:
            Dict with AI-extracted business profile fields
        """
        if not self.bedrock_client:
            logger.warning("No Bedrock client configured, returning raw analysis")
            return self._basic_analysis(scraped_data)

        # Prepare content for AI
        combined_content = self._prepare_content_for_ai(scraped_data)

        prompt = f"""Analyze this company website content and extract business profile information for sales purposes.
Return a JSON object with these fields (use null if not found, empty array [] for lists with no data):

{{
    "company_name": "Company's official name",
    "industry": "Primary industry (e.g., Agriculture, Manufacturing, Technology)",
    "company_size": "Estimated size (e.g., '1-10', '11-50', '51-200', '201-500', '500+')",
    "founded_year": "Year founded (integer or null)",
    "value_proposition": "Main value proposition (1-2 sentences)",
    "elevator_pitch": "Company description suitable for an elevator pitch (2-3 sentences)",
    "products_services": [
        {{"name": "Product/Service Name", "description": "Brief description", "key_benefit": "Main benefit"}}
    ],
    "key_differentiators": ["What makes them unique 1", "What makes them unique 2"],
    "unique_selling_points": ["USP 1", "USP 2"],
    "target_market": "Who they sell to",
    "notable_clients": ["Client 1", "Client 2"],
    "case_studies": [
        {{"title": "Case Study Title", "summary": "Brief summary", "result": "Key metric/outcome"}}
    ],
    "social_proof_stats": {{"customers": "number or null", "years_in_business": "number or null", "satisfaction_rate": "percentage or null"}},
    "suggested_target_industries": ["Industry 1", "Industry 2"],
    "suggested_target_titles": ["Job Title 1", "Job Title 2"],

    "competitors": [
        {{"name": "Competitor name mentioned or implied", "our_advantage": "How this company is better"}}
    ],
    "common_objections": [
        {{"objection": "Common concern (infer from FAQ or messaging)", "response": "How they address it"}}
    ],
    "customer_pain_points": ["Pain point this company solves 1", "Pain point 2"],
    "solutions_to_pain_points": [
        {{"pain": "The pain point", "solution": "How they solve it"}}
    ],
    "pricing_model": "subscription/one-time/freemium/custom/contact-sales (infer from pricing page)",
    "pricing_tiers": [
        {{"name": "Tier name", "price": "Price if shown", "features": ["Feature 1", "Feature 2"]}}
    ],
    "target_decision_makers": ["CEO", "VP Operations", "Procurement Manager"],
    "target_company_sizes": ["SMB", "Mid-market", "Enterprise"],
    "sales_cycle_hint": "short/medium/long (infer from product complexity and pricing)"
}}

EXTRACTION TIPS:
- Look for FAQ sections to infer common objections and how they're addressed
- Look for "vs" or comparison language to identify competitors
- Look for "for [role]" or "teams" language to infer target decision makers
- Look for pricing pages to understand deal sizes and model
- Look for industries served or "who we serve" sections
- Extract pain points from problem statements or "challenges" sections

Website content:
{combined_content}

Return ONLY valid JSON, no other text."""

        try:
            response = self.bedrock_client.invoke_model(
                modelId="anthropic.claude-3-haiku-20240307-v1:0",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )

            response_body = json.loads(response["body"].read())
            ai_response = response_body["content"][0]["text"]

            # Parse JSON from response
            json_match = re.search(r"\{[\s\S]*\}", ai_response)
            if json_match:
                extracted = json.loads(json_match.group())
                extracted["_source"] = "ai_analysis"
                extracted["_website"] = scraped_data.get("base_url")
                return extracted

        except Exception as e:
            logger.error(f"AI analysis failed: {e}")

        return self._basic_analysis(scraped_data)

    def _prepare_content_for_ai(self, scraped_data: Dict[str, Any]) -> str:
        """Prepare scraped content for AI analysis"""
        parts = []

        for page_path, content in scraped_data.get("pages", {}).items():
            parts.append(f"=== Page: {page_path} ===")
            if content.get("title"):
                parts.append(f"Title: {content['title']}")
            if content.get("meta_description"):
                parts.append(f"Description: {content['meta_description']}")
            if content.get("text"):
                # Truncate long text
                text = content["text"][:5000]
                parts.append(f"Content: {text}")
            parts.append("")

        combined = "\n".join(parts)
        # Limit total length for AI
        return combined[:20000]

    def _basic_analysis(self, scraped_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Basic extraction without AI (fallback).
        """
        result = {
            "_source": "basic_analysis",
            "_website": scraped_data.get("base_url"),
            "company_name": None,
            "industry": None,
            "company_size": None,
            "founded_year": None,
            "value_proposition": None,
            "elevator_pitch": None,
            "products_services": [],
            "key_differentiators": [],
            "unique_selling_points": [],
            "target_market": None,
            "notable_clients": [],
            "case_studies": [],
            "social_proof_stats": {},
            "suggested_target_industries": [],
            "suggested_target_titles": [],
            # New sales-critical fields
            "competitors": [],
            "common_objections": [],
            "customer_pain_points": [],
            "solutions_to_pain_points": [],
            "pricing_model": None,
            "pricing_tiers": [],
            "target_decision_makers": [],
            "target_company_sizes": [],
            "sales_cycle_hint": None
        }

        # Extract from homepage
        homepage = scraped_data.get("pages", {}).get("/", {})
        if homepage:
            if homepage.get("title"):
                # Company name often in title
                title = homepage["title"]
                # Remove common suffixes
                for suffix in [" | ", " - ", " : "]:
                    if suffix in title:
                        result["company_name"] = title.split(suffix)[0].strip()
                        break
                if not result["company_name"]:
                    result["company_name"] = title

            if homepage.get("meta_description"):
                result["elevator_pitch"] = homepage["meta_description"]

        # Collect all emails and phones
        all_emails = []
        all_phones = []
        social_links = {}

        for page_content in scraped_data.get("pages", {}).values():
            all_emails.extend(page_content.get("emails", []))
            all_phones.extend(page_content.get("phones", []))
            social_links.update(page_content.get("social_links", {}))

        result["_extracted_emails"] = list(set(all_emails))
        result["_extracted_phones"] = list(set(all_phones))
        result["_social_links"] = social_links

        return result


async def scrape_and_analyze_profile(
    website_url: str,
    bedrock_client=None
) -> Dict[str, Any]:
    """
    Convenience function to scrape and analyze a company website.

    Args:
        website_url: Company website URL
        bedrock_client: AWS Bedrock client (optional)

    Returns:
        Dict with extracted business profile data
    """
    scraper = ProfileScraper(bedrock_client=bedrock_client)

    # Scrape the website
    scraped_data = await scraper.scrape_website(website_url)

    # Analyze with AI
    profile_data = await scraper.analyze_with_ai(scraped_data)

    return {
        "success": True,
        "website": website_url,
        "profile_data": profile_data,
        "scraped_pages": list(scraped_data.get("pages", {}).keys()),
        "errors": scraped_data.get("errors", [])
    }
