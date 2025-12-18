"""
Deep Website Crawler for Company Intelligence Agent
Crawls entire websites, follows links, extracts content for knowledge store
"""

import re
import asyncio
import hashlib
import logging
from typing import Dict, List, Optional, Set, Any, AsyncGenerator
from urllib.parse import urljoin, urlparse, urlunparse
from datetime import datetime
from dataclasses import dataclass, field
import mimetypes

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class CrawledPage:
    """Represents a single crawled page"""
    url: str
    title: str
    content: str
    content_type: str
    meta_description: str = ""
    headings: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    content_hash: str = ""
    crawled_at: str = ""
    word_count: int = 0
    page_type: str = "unknown"  # homepage, about, product, pricing, blog, etc.


@dataclass
class CrawlResult:
    """Result of a full website crawl"""
    domain: str
    pages: List[CrawledPage]
    total_pages: int
    total_words: int
    crawl_duration_seconds: float
    errors: List[str]
    started_at: str
    completed_at: str


class DeepCrawler:
    """
    Deep website crawler that follows links and extracts all content.
    Designed for the Company Intelligence Agent knowledge store.
    """

    # Page type classification patterns
    PAGE_TYPE_PATTERNS = {
        "homepage": [r"^/$", r"^/index", r"^/home"],
        "about": [r"/about", r"/our-story", r"/who-we-are", r"/company"],
        "product": [r"/product", r"/solution", r"/service", r"/feature", r"/platform"],
        "pricing": [r"/pricing", r"/plans", r"/packages", r"/cost"],
        "contact": [r"/contact", r"/get-in-touch", r"/reach-us"],
        "team": [r"/team", r"/leadership", r"/people", r"/staff", r"/our-team"],
        "blog": [r"/blog", r"/news", r"/articles", r"/insights", r"/resources"],
        "case_study": [r"/case-stud", r"/success-stor", r"/customer-stor", r"/testimonial"],
        "faq": [r"/faq", r"/help", r"/support", r"/knowledge"],
        "legal": [r"/privacy", r"/terms", r"/legal", r"/cookie"],
        "careers": [r"/career", r"/jobs", r"/join-us", r"/work-with-us"],
        "comparison": [r"/vs", r"/compare", r"/alternative", r"/versus"],
        "industries": [r"/industr", r"/vertical", r"/sector", r"/who-we-serve"],
    }

    # URLs to skip
    SKIP_PATTERNS = [
        r"\.(jpg|jpeg|png|gif|svg|ico|webp|bmp)$",
        r"\.(css|js|json|xml|txt|map)$",
        r"\.(pdf|doc|docx|xls|xlsx|ppt|pptx)$",  # Handle separately
        r"\.(zip|tar|gz|rar)$",
        r"\.(mp3|mp4|wav|avi|mov|webm)$",
        r"#",  # Anchor links
        r"mailto:",
        r"tel:",
        r"javascript:",
        r"/wp-admin",
        r"/admin",
        r"/login",
        r"/logout",
        r"/cart",
        r"/checkout",
        r"/account",
        r"\?",  # Query strings often lead to duplicates
    ]

    # Priority pages to crawl first
    PRIORITY_PATHS = [
        "/", "/about", "/about-us", "/products", "/services", "/solutions",
        "/pricing", "/plans", "/contact", "/team", "/case-studies",
        "/testimonials", "/faq", "/why-us", "/industries", "/customers"
    ]

    def __init__(
        self,
        max_pages: int = 100,
        max_depth: int = 4,
        request_delay: float = 0.5,
        timeout: float = 15.0,
        max_content_length: int = 50000
    ):
        """
        Initialize the deep crawler.

        Args:
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum link depth from homepage
            request_delay: Delay between requests (be a good citizen)
            timeout: Request timeout in seconds
            max_content_length: Maximum content length per page
        """
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.request_delay = request_delay
        self.timeout = timeout
        self.max_content_length = max_content_length

        self.headers = {
            "User-Agent": "SAIGBOX-Crawler/1.0 (Company Intelligence Agent)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        # State during crawl
        self._visited: Set[str] = set()
        self._queued: Set[str] = set()
        self._errors: List[str] = []
        self._domain: str = ""

    def _normalize_url(self, url: str, base_url: str) -> Optional[str]:
        """Normalize a URL and check if it should be crawled"""
        # Handle relative URLs
        if not url.startswith(("http://", "https://")):
            url = urljoin(base_url, url)

        parsed = urlparse(url)

        # Only crawl same domain
        if parsed.netloc != self._domain:
            return None

        # Skip certain patterns
        for pattern in self.SKIP_PATTERNS:
            if re.search(pattern, url.lower()):
                return None

        # Normalize: remove fragments, trailing slashes
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/") or "/",
            "",  # params
            "",  # query - skip to avoid duplicates
            ""   # fragment
        ))

        return normalized

    def _classify_page_type(self, url: str) -> str:
        """Classify the page type based on URL patterns"""
        path = urlparse(url).path.lower()

        for page_type, patterns in self.PAGE_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, path):
                    return page_type

        return "other"

    def _extract_content(self, html: str, url: str) -> CrawledPage:
        """Extract structured content from HTML"""
        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "noscript", "iframe", "svg"]):
            element.decompose()

        # Get title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Get meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")

        # Get headings for structure
        headings = []
        for h in soup.find_all(["h1", "h2", "h3"]):
            text = h.get_text(strip=True)
            if text and len(text) < 200:
                headings.append(text)

        # Get main content
        main_content = soup.find("main") or soup.find("article") or soup.find("body")
        content = ""
        if main_content:
            content = main_content.get_text(separator=" ", strip=True)
            content = re.sub(r"\s+", " ", content)
            content = content[:self.max_content_length]

        # Extract links
        links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            normalized = self._normalize_url(href, url)
            if normalized:
                links.append(normalized)

        # Extract emails
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = list(set(re.findall(email_pattern, html)))
        emails = [e for e in emails if not e.endswith((".png", ".jpg", ".gif"))][:10]

        # Extract phones
        phone_pattern = r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
        phones = list(set(re.findall(phone_pattern, content)))[:5]

        # Calculate content hash for deduplication
        content_hash = hashlib.md5(content.encode()).hexdigest()[:12]

        return CrawledPage(
            url=url,
            title=title,
            content=content,
            content_type="text/html",
            meta_description=meta_desc,
            headings=headings[:20],
            links=links,
            emails=emails,
            phones=phones,
            content_hash=content_hash,
            crawled_at=datetime.utcnow().isoformat(),
            word_count=len(content.split()),
            page_type=self._classify_page_type(url)
        )

    async def crawl(
        self,
        start_url: str,
        progress_callback: Optional[callable] = None
    ) -> CrawlResult:
        """
        Crawl a website starting from the given URL.

        Args:
            start_url: The starting URL (usually homepage)
            progress_callback: Optional async callback(pages_crawled, total_queued)

        Returns:
            CrawlResult with all crawled pages
        """
        start_time = datetime.utcnow()

        # Normalize start URL
        if not start_url.startswith(("http://", "https://")):
            start_url = f"https://{start_url}"

        parsed = urlparse(start_url)
        self._domain = parsed.netloc
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Reset state
        self._visited = set()
        self._queued = set()
        self._errors = []
        pages: List[CrawledPage] = []

        # Priority queue: (depth, url)
        queue: List[tuple] = []

        # Add priority pages first
        for path in self.PRIORITY_PATHS:
            priority_url = urljoin(base_url, path)
            if priority_url not in self._queued:
                queue.append((0, priority_url))
                self._queued.add(priority_url)

        # Add start URL if not already queued
        if start_url not in self._queued:
            queue.insert(0, (0, start_url))
            self._queued.add(start_url)

        async with httpx.AsyncClient(
            headers=self.headers,
            follow_redirects=True,
            timeout=self.timeout
        ) as client:
            while queue and len(pages) < self.max_pages:
                # Get next URL (FIFO for BFS-like behavior)
                depth, url = queue.pop(0)

                if url in self._visited:
                    continue

                if depth > self.max_depth:
                    continue

                self._visited.add(url)

                try:
                    response = await client.get(url)

                    if response.status_code == 200:
                        content_type = response.headers.get("content-type", "")

                        if "text/html" in content_type:
                            page = self._extract_content(response.text, url)

                            # Only keep pages with meaningful content
                            if page.word_count > 50:
                                pages.append(page)
                                logger.info(f"Crawled [{len(pages)}/{self.max_pages}]: {url} ({page.word_count} words)")

                                # Add new links to queue
                                for link in page.links:
                                    if link not in self._visited and link not in self._queued:
                                        queue.append((depth + 1, link))
                                        self._queued.add(link)

                                # Progress callback
                                if progress_callback:
                                    await progress_callback(len(pages), len(queue))

                except httpx.TimeoutException:
                    self._errors.append(f"Timeout: {url}")
                    logger.warning(f"Timeout crawling: {url}")
                except Exception as e:
                    self._errors.append(f"Error {url}: {str(e)}")
                    logger.warning(f"Error crawling {url}: {e}")

                # Rate limiting
                await asyncio.sleep(self.request_delay)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        total_words = sum(p.word_count for p in pages)

        logger.info(f"Crawl complete: {len(pages)} pages, {total_words} words in {duration:.1f}s")

        return CrawlResult(
            domain=self._domain,
            pages=pages,
            total_pages=len(pages),
            total_words=total_words,
            crawl_duration_seconds=duration,
            errors=self._errors,
            started_at=start_time.isoformat(),
            completed_at=end_time.isoformat()
        )

    async def crawl_streaming(
        self,
        start_url: str
    ) -> AsyncGenerator[CrawledPage, None]:
        """
        Crawl a website and yield pages as they're found.
        Useful for real-time progress updates.
        """
        if not start_url.startswith(("http://", "https://")):
            start_url = f"https://{start_url}"

        parsed = urlparse(start_url)
        self._domain = parsed.netloc
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        self._visited = set()
        self._queued = set()
        pages_crawled = 0

        queue: List[tuple] = []

        # Add priority pages
        for path in self.PRIORITY_PATHS:
            priority_url = urljoin(base_url, path)
            if priority_url not in self._queued:
                queue.append((0, priority_url))
                self._queued.add(priority_url)

        if start_url not in self._queued:
            queue.insert(0, (0, start_url))
            self._queued.add(start_url)

        async with httpx.AsyncClient(
            headers=self.headers,
            follow_redirects=True,
            timeout=self.timeout
        ) as client:
            while queue and pages_crawled < self.max_pages:
                depth, url = queue.pop(0)

                if url in self._visited or depth > self.max_depth:
                    continue

                self._visited.add(url)

                try:
                    response = await client.get(url)

                    if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
                        page = self._extract_content(response.text, url)

                        if page.word_count > 50:
                            pages_crawled += 1

                            for link in page.links:
                                if link not in self._visited and link not in self._queued:
                                    queue.append((depth + 1, link))
                                    self._queued.add(link)

                            yield page

                except Exception as e:
                    logger.warning(f"Error crawling {url}: {e}")

                await asyncio.sleep(self.request_delay)


def chunk_content(page: CrawledPage, chunk_size: int = 1000, overlap: int = 100) -> List[Dict[str, Any]]:
    """
    Split a page's content into chunks suitable for vector embeddings.

    Args:
        page: The crawled page
        chunk_size: Target chunk size in characters
        overlap: Overlap between chunks

    Returns:
        List of chunk dictionaries with content and metadata
    """
    content = page.content
    chunks = []

    if len(content) <= chunk_size:
        chunks.append({
            "content": content,
            "url": page.url,
            "title": page.title,
            "page_type": page.page_type,
            "chunk_index": 0,
            "total_chunks": 1
        })
    else:
        # Split into overlapping chunks
        start = 0
        chunk_index = 0

        while start < len(content):
            end = start + chunk_size

            # Try to break at sentence boundary
            if end < len(content):
                # Look for sentence end
                for sep in [". ", "! ", "? ", "\n"]:
                    last_sep = content[start:end].rfind(sep)
                    if last_sep > chunk_size * 0.5:
                        end = start + last_sep + 1
                        break

            chunk_text = content[start:end].strip()

            if chunk_text:
                chunks.append({
                    "content": chunk_text,
                    "url": page.url,
                    "title": page.title,
                    "page_type": page.page_type,
                    "chunk_index": chunk_index,
                    "total_chunks": -1  # Will update after
                })
                chunk_index += 1

            start = end - overlap

        # Update total chunks
        for chunk in chunks:
            chunk["total_chunks"] = len(chunks)

    return chunks


async def crawl_website(url: str, max_pages: int = 100) -> CrawlResult:
    """
    Convenience function to crawl a website.

    Args:
        url: Website URL to crawl
        max_pages: Maximum pages to crawl

    Returns:
        CrawlResult with all pages
    """
    crawler = DeepCrawler(max_pages=max_pages)
    return await crawler.crawl(url)
