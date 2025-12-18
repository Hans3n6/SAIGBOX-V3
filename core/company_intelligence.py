"""
Company Intelligence Agent
Main orchestrator for deep company knowledge and AI-powered assistance
"""

import json
import logging
import asyncio
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
from dataclasses import dataclass

from .deep_crawler import DeepCrawler, CrawlResult, CrawledPage, chunk_content
from .knowledge_store import KnowledgeStore, KnowledgeChunk, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from the Company Intelligence Agent"""
    answer: str
    sources: List[Dict[str, str]]
    confidence: float
    suggested_followups: List[str]


@dataclass
class CompanyKnowledge:
    """Summary of what the agent knows about the company"""
    domain: str
    company_name: Optional[str]
    total_pages: int
    total_chunks: int
    knowledge_areas: Dict[str, int]  # page_type -> count
    last_updated: Optional[str]
    status: str  # none, crawling, ready


class CompanyIntelligenceAgent:
    """
    AI Agent that deeply learns a company and assists with sales tasks.

    Capabilities:
    - Crawl and index entire company websites
    - Answer questions about the company
    - Provide contextual information for emails
    - Generate sales insights
    """

    CLAUDE_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"

    def __init__(
        self,
        bedrock_client,
        user_id: str,
        db_path: str = "data"
    ):
        """
        Initialize the Company Intelligence Agent.

        Args:
            bedrock_client: AWS Bedrock client
            user_id: User ID for multi-tenant storage
            db_path: Directory for databases
        """
        self.bedrock_client = bedrock_client
        self.user_id = user_id
        self.db_path = db_path

        # Initialize knowledge store
        self.knowledge_store = KnowledgeStore(
            bedrock_client=bedrock_client,
            db_path=f"{db_path}/knowledge.db",
            user_id=user_id
        )

        # Crawl state
        self._crawl_in_progress = False
        self._crawl_progress = {"pages": 0, "chunks": 0, "status": "idle"}

    async def learn_company(
        self,
        website_url: str,
        max_pages: int = 100,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Crawl a company website and build knowledge base.

        Args:
            website_url: Company website URL
            max_pages: Maximum pages to crawl
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with crawl results
        """
        if self._crawl_in_progress:
            return {"error": "Crawl already in progress"}

        self._crawl_in_progress = True
        self._crawl_progress = {"pages": 0, "chunks": 0, "status": "crawling"}

        try:
            # Clear existing knowledge
            self.knowledge_store.clear_knowledge()

            # Initialize crawler
            crawler = DeepCrawler(max_pages=max_pages)

            # Crawl the website
            async def track_progress(pages_crawled, queued):
                self._crawl_progress["pages"] = pages_crawled
                self._crawl_progress["status"] = f"Crawling... {pages_crawled} pages found"
                if progress_callback:
                    await progress_callback(self._crawl_progress)

            result = await crawler.crawl(website_url, progress_callback=track_progress)

            # Extract domain for company profile
            domain = result.domain

            # Process pages into chunks and add to knowledge store
            self._crawl_progress["status"] = "Processing content..."
            total_chunks = 0

            for page in result.pages:
                chunks = chunk_content(page)

                for chunk_data in chunks:
                    knowledge_chunk = KnowledgeChunk(
                        id="",
                        content=chunk_data["content"],
                        url=chunk_data["url"],
                        title=chunk_data["title"],
                        page_type=chunk_data["page_type"],
                        chunk_index=chunk_data["chunk_index"],
                        total_chunks=chunk_data["total_chunks"]
                    )

                    await self.knowledge_store.add_chunk(knowledge_chunk)
                    total_chunks += 1

                    self._crawl_progress["chunks"] = total_chunks
                    if progress_callback:
                        await progress_callback(self._crawl_progress)

            # Try to extract company name from homepage
            company_name = None
            for page in result.pages:
                if page.page_type == "homepage" and page.title:
                    # Often "Company Name | Tagline" or "Company Name - Home"
                    title = page.title
                    for sep in [" | ", " - ", " : ", " – "]:
                        if sep in title:
                            company_name = title.split(sep)[0].strip()
                            break
                    if not company_name:
                        company_name = title
                    break

            # Update company profile
            self.knowledge_store.update_company_profile(
                domain=domain,
                company_name=company_name,
                total_chunks=total_chunks,
                total_pages=result.total_pages,
                crawl_status="ready"
            )

            # Log the crawl
            self.knowledge_store.log_crawl(
                domain=domain,
                pages_crawled=result.total_pages,
                chunks_created=total_chunks,
                started_at=result.started_at,
                completed_at=result.completed_at,
                status="success",
                errors=result.errors
            )

            self._crawl_progress = {
                "pages": result.total_pages,
                "chunks": total_chunks,
                "status": "complete"
            }

            return {
                "success": True,
                "domain": domain,
                "company_name": company_name,
                "pages_crawled": result.total_pages,
                "chunks_created": total_chunks,
                "words_indexed": result.total_words,
                "duration_seconds": result.crawl_duration_seconds,
                "errors": result.errors[:10]  # Limit errors
            }

        except Exception as e:
            logger.error(f"Crawl failed: {e}")
            self._crawl_progress = {"status": f"Error: {str(e)}"}
            return {"success": False, "error": str(e)}

        finally:
            self._crawl_in_progress = False

    async def ask(
        self,
        question: str,
        context: Optional[str] = None
    ) -> AgentResponse:
        """
        Ask the agent a question about the company.

        Args:
            question: The question to ask
            context: Optional additional context (e.g., prospect info)

        Returns:
            AgentResponse with answer and sources
        """
        # Search knowledge base
        results = await self.knowledge_store.search(question, top_k=8)

        if not results:
            return AgentResponse(
                answer="I don't have enough information about your company yet. Please teach me by entering your website URL above.",
                sources=[],
                confidence=0.0,
                suggested_followups=["What is your company website?"]
            )

        # Build context from search results
        knowledge_context = self._build_context(results)

        # Generate answer using Claude
        prompt = self._build_prompt(question, knowledge_context, context)

        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.CLAUDE_MODEL,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )

            response_body = json.loads(response["body"].read())
            answer_text = response_body["content"][0]["text"]

            # Parse JSON response
            try:
                answer_data = json.loads(answer_text)
                return AgentResponse(
                    answer=answer_data.get("answer", answer_text),
                    sources=[{"url": r.chunk.url, "title": r.chunk.title} for r in results[:3]],
                    confidence=answer_data.get("confidence", 0.8),
                    suggested_followups=answer_data.get("followups", [])
                )
            except json.JSONDecodeError:
                # If not JSON, return raw answer
                return AgentResponse(
                    answer=answer_text,
                    sources=[{"url": r.chunk.url, "title": r.chunk.title} for r in results[:3]],
                    confidence=0.7,
                    suggested_followups=[]
                )

        except Exception as e:
            logger.error(f"Ask failed: {e}")
            return AgentResponse(
                answer=f"I encountered an error: {str(e)}",
                sources=[],
                confidence=0.0,
                suggested_followups=[]
            )

    async def get_email_context(
        self,
        prospect_info: Dict[str, Any],
        email_purpose: str
    ) -> Dict[str, Any]:
        """
        Get relevant company context for composing an email.

        Args:
            prospect_info: Information about the prospect (industry, role, company, etc.)
            email_purpose: Purpose of the email (cold outreach, follow-up, proposal, etc.)

        Returns:
            Dict with relevant context for email composition
        """
        # Build search query from prospect info
        industry = prospect_info.get("industry", "")
        role = prospect_info.get("role", "")
        company = prospect_info.get("company", "")
        pain_points = prospect_info.get("pain_points", [])

        queries = [
            f"products services for {industry}",
            f"value proposition for {role}",
            f"case study {industry}",
            f"benefits for {industry}",
        ]

        if pain_points:
            queries.append(f"solution for {' '.join(pain_points[:2])}")

        # Search for each query and collect unique results
        all_results = []
        seen_urls = set()

        for query in queries:
            results = await self.knowledge_store.search(query, top_k=3)
            for r in results:
                if r.chunk.url not in seen_urls:
                    all_results.append(r)
                    seen_urls.add(r.chunk.url)

        # Sort by relevance
        all_results.sort(key=lambda x: x.score, reverse=True)
        top_results = all_results[:8]

        # Generate contextual summary
        context_text = self._build_context(top_results)

        prompt = f"""Based on the following company knowledge, provide sales context for emailing a prospect.

PROSPECT INFO:
- Industry: {industry}
- Role: {role}
- Company: {company}
- Email Purpose: {email_purpose}

COMPANY KNOWLEDGE:
{context_text}

Provide a JSON response with:
{{
    "relevant_products": ["Products/services relevant to this prospect"],
    "key_benefits": ["Benefits to emphasize for their industry/role"],
    "case_study_mention": "Brief mention of relevant case study if available",
    "talking_points": ["Key talking points for the email"],
    "avoid": ["Topics to avoid or not relevant"]
}}

Return ONLY valid JSON."""

        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.CLAUDE_MODEL,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )

            response_body = json.loads(response["body"].read())
            context_data = json.loads(response_body["content"][0]["text"])
            context_data["sources"] = [{"url": r.chunk.url, "title": r.chunk.title} for r in top_results[:3]]
            return context_data

        except Exception as e:
            logger.error(f"Get email context failed: {e}")
            return {
                "relevant_products": [],
                "key_benefits": [],
                "case_study_mention": None,
                "talking_points": [],
                "avoid": [],
                "error": str(e)
            }

    async def get_competitor_intel(self, competitor_name: str) -> Dict[str, Any]:
        """
        Get intelligence about how to position against a competitor.

        Args:
            competitor_name: Name of the competitor

        Returns:
            Dict with competitive positioning info
        """
        queries = [
            f"vs {competitor_name}",
            f"compare {competitor_name}",
            f"better than {competitor_name}",
            f"advantage over {competitor_name}",
            "our differentiators",
            "why choose us",
            "unique features"
        ]

        all_results = []
        seen_urls = set()

        for query in queries:
            results = await self.knowledge_store.search(query, top_k=3)
            for r in results:
                if r.chunk.url not in seen_urls:
                    all_results.append(r)
                    seen_urls.add(r.chunk.url)

        all_results.sort(key=lambda x: x.score, reverse=True)
        context = self._build_context(all_results[:8])

        prompt = f"""Based on company knowledge, provide competitive positioning against {competitor_name}.

COMPANY KNOWLEDGE:
{context}

Provide a JSON response:
{{
    "our_advantages": ["Key advantages we have over {competitor_name}"],
    "talking_points": ["Points to emphasize when competing"],
    "potential_weaknesses": ["Areas where we might be weaker (be honest)"],
    "objection_handlers": [{{"objection": "Common objection", "response": "How to handle it"}}],
    "win_themes": ["Themes that help us win against this competitor"]
}}

Return ONLY valid JSON."""

        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.CLAUDE_MODEL,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )

            response_body = json.loads(response["body"].read())
            return json.loads(response_body["content"][0]["text"])

        except Exception as e:
            logger.error(f"Competitor intel failed: {e}")
            return {"error": str(e)}

    def get_knowledge_summary(self) -> CompanyKnowledge:
        """Get a summary of what the agent knows"""
        stats = self.knowledge_store.get_statistics()

        return CompanyKnowledge(
            domain=stats.get("domain", ""),
            company_name=stats.get("company_name"),
            total_pages=stats.get("unique_pages", 0),
            total_chunks=stats.get("total_chunks", 0),
            knowledge_areas=stats.get("by_page_type", {}),
            last_updated=stats.get("last_crawl"),
            status="ready" if stats.get("total_chunks", 0) > 0 else "none"
        )

    def get_crawl_progress(self) -> Dict[str, Any]:
        """Get current crawl progress"""
        return {
            **self._crawl_progress,
            "in_progress": self._crawl_in_progress
        }

    def _build_context(self, results: List[SearchResult]) -> str:
        """Build context string from search results"""
        parts = []
        for r in results:
            chunk = r.chunk
            part = f"[{chunk.page_type.upper()} - {chunk.title}]\n{chunk.content[:1500]}"
            parts.append(part)
        return "\n\n---\n\n".join(parts)

    def _build_prompt(
        self,
        question: str,
        knowledge_context: str,
        additional_context: Optional[str]
    ) -> str:
        """Build the prompt for answering questions"""
        prompt = f"""You are a Company Intelligence Agent helping a salesperson understand their company.

Based on the following company knowledge, answer the question accurately and helpfully.

COMPANY KNOWLEDGE:
{knowledge_context}

"""
        if additional_context:
            prompt += f"""ADDITIONAL CONTEXT:
{additional_context}

"""

        prompt += f"""QUESTION: {question}

Provide a helpful, accurate answer based on the company knowledge above.
Return a JSON response:
{{
    "answer": "Your detailed answer here",
    "confidence": 0.0-1.0 based on how well the knowledge supports the answer,
    "followups": ["Suggested follow-up question 1", "Suggested follow-up question 2"]
}}

Return ONLY valid JSON."""

        return prompt


# Convenience functions

async def create_agent(
    bedrock_client,
    user_id: str,
    db_path: str = "data"
) -> CompanyIntelligenceAgent:
    """Create a Company Intelligence Agent instance"""
    return CompanyIntelligenceAgent(
        bedrock_client=bedrock_client,
        user_id=user_id,
        db_path=db_path
    )
