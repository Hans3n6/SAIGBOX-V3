"""
Company Intelligence Agent API Routes
Endpoints for the AI-powered company knowledge system
"""

import logging
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from core.company_intelligence import CompanyIntelligenceAgent
from core.database import User
from api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/company-agent", tags=["Company Agent"])

# Store agent instances per user
_agent_cache = {}


def get_bedrock_client():
    """Get the Bedrock client from app state"""
    import boto3
    import os

    # Use existing Bedrock setup
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1")
    )


def get_agent(user_email: str) -> CompanyIntelligenceAgent:
    """Get or create agent instance for user"""
    if user_email not in _agent_cache:
        bedrock_client = get_bedrock_client()
        _agent_cache[user_email] = CompanyIntelligenceAgent(
            bedrock_client=bedrock_client,
            user_id=user_email,
            db_path="data"
        )
    return _agent_cache[user_email]


# Request/Response Models

class LearnCompanyRequest(BaseModel):
    website_url: str = Field(..., description="Company website URL to crawl")
    max_pages: int = Field(default=100, ge=10, le=500, description="Maximum pages to crawl")


class AskQuestionRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Question to ask the agent")
    context: Optional[str] = Field(default=None, description="Additional context")


class EmailContextRequest(BaseModel):
    prospect_industry: str = Field(default="", description="Prospect's industry")
    prospect_role: str = Field(default="", description="Prospect's role/title")
    prospect_company: str = Field(default="", description="Prospect's company name")
    email_purpose: str = Field(default="cold outreach", description="Purpose of the email")
    pain_points: list = Field(default=[], description="Known pain points")


class CompetitorIntelRequest(BaseModel):
    competitor_name: str = Field(..., min_length=1, description="Competitor name")


# Endpoints

@router.get("/status")
async def get_agent_status(user: User = Depends(get_current_user)):
    """Get the current status and knowledge summary of the agent"""
    agent = get_agent(user.email)
    knowledge = agent.get_knowledge_summary()

    return {
        "status": knowledge.status,
        "domain": knowledge.domain,
        "company_name": knowledge.company_name,
        "total_pages": knowledge.total_pages,
        "total_chunks": knowledge.total_chunks,
        "knowledge_areas": knowledge.knowledge_areas,
        "last_updated": knowledge.last_updated,
        "crawl_progress": agent.get_crawl_progress()
    }


@router.post("/learn")
async def learn_company(
    request: LearnCompanyRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user)
):
    """
    Start crawling a company website to build the knowledge base.
    This runs in the background and progress can be monitored via /status.
    """
    agent = get_agent(user.email)

    # Check if already crawling
    progress = agent.get_crawl_progress()
    if progress.get("in_progress"):
        raise HTTPException(
            status_code=409,
            detail="Crawl already in progress. Check /status for progress."
        )

    # Start crawl in background
    async def run_crawl():
        try:
            result = await agent.learn_company(
                website_url=request.website_url,
                max_pages=request.max_pages
            )
            logger.info(f"Crawl completed for {user.email}: {result}")
        except Exception as e:
            logger.error(f"Crawl failed for {user.email}: {e}")

    # Run async task in background
    loop = asyncio.get_event_loop()
    loop.create_task(run_crawl())

    return {
        "message": "Crawl started",
        "website_url": request.website_url,
        "max_pages": request.max_pages,
        "status": "crawling"
    }


@router.post("/learn/sync")
async def learn_company_sync(
    request: LearnCompanyRequest,
    user: User = Depends(get_current_user)
):
    """
    Crawl a company website synchronously.
    Useful for smaller sites or when you need the result immediately.
    """
    agent = get_agent(user.email)

    result = await agent.learn_company(
        website_url=request.website_url,
        max_pages=min(request.max_pages, 50)  # Limit for sync
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Crawl failed"))

    return result


@router.post("/ask")
async def ask_question(
    request: AskQuestionRequest,
    user: User = Depends(get_current_user)
):
    """
    Ask the agent a question about your company.
    Returns an AI-generated answer based on the knowledge base.
    """
    agent = get_agent(user.email)

    response = await agent.ask(
        question=request.question,
        context=request.context
    )

    return {
        "answer": response.answer,
        "sources": response.sources,
        "confidence": response.confidence,
        "suggested_followups": response.suggested_followups
    }


@router.post("/email-context")
async def get_email_context(
    request: EmailContextRequest,
    user: User = Depends(get_current_user)
):
    """
    Get relevant company context for composing an email to a prospect.
    Returns products, benefits, and talking points tailored to the prospect.
    """
    agent = get_agent(user.email)

    prospect_info = {
        "industry": request.prospect_industry,
        "role": request.prospect_role,
        "company": request.prospect_company,
        "pain_points": request.pain_points
    }

    context = await agent.get_email_context(
        prospect_info=prospect_info,
        email_purpose=request.email_purpose
    )

    return context


@router.post("/competitor-intel")
async def get_competitor_intel(
    request: CompetitorIntelRequest,
    user: User = Depends(get_current_user)
):
    """
    Get competitive intelligence and positioning against a competitor.
    Returns advantages, talking points, and objection handlers.
    """
    agent = get_agent(user.email)

    intel = await agent.get_competitor_intel(request.competitor_name)

    return intel


@router.get("/search")
async def search_knowledge(
    query: str,
    top_k: int = 5,
    page_types: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """
    Search the knowledge base directly.
    Returns raw search results for advanced use cases.
    """
    agent = get_agent(user.email)

    # Parse page types if provided
    types_list = None
    if page_types:
        types_list = [t.strip() for t in page_types.split(",")]

    results = await agent.knowledge_store.search(
        query=query,
        top_k=top_k,
        page_types=types_list
    )

    return {
        "results": [
            {
                "content": r.chunk.content[:500],
                "url": r.chunk.url,
                "title": r.chunk.title,
                "page_type": r.chunk.page_type,
                "score": r.score
            }
            for r in results
        ],
        "total_results": len(results)
    }


@router.delete("/knowledge")
async def clear_knowledge(user: User = Depends(get_current_user)):
    """
    Clear all knowledge for the current user.
    This removes all crawled data and resets the agent.
    """
    agent = get_agent(user.email)
    agent.knowledge_store.clear_knowledge()

    return {"message": "Knowledge cleared", "status": "none"}


@router.get("/progress")
async def get_crawl_progress(user: User = Depends(get_current_user)):
    """Get real-time crawl progress"""
    agent = get_agent(user.email)
    return agent.get_crawl_progress()


class GenerateDemoEmailsRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50, description="Number of demo emails to generate")
    clear_existing: bool = Field(default=True, description="Clear existing demo emails first")


@router.post("/generate-demo-emails")
async def generate_demo_emails(
    request: GenerateDemoEmailsRequest,
    user: User = Depends(get_current_user)
):
    """
    Generate realistic demo emails based on company knowledge.
    These emails simulate real sales inquiries, pricing requests, etc.
    """
    from sqlalchemy.orm import Session
    from core.database import get_db
    from core.demo_email_generator import generate_and_insert_demo_emails

    agent = get_agent(user.email)

    # Get database session
    db = next(get_db())

    try:
        result = await generate_and_insert_demo_emails(
            db=db,
            user=user,
            bedrock_client=get_bedrock_client(),
            knowledge_store=agent.knowledge_store,
            count=request.count,
            clear_existing=request.clear_existing
        )
        return result
    except Exception as e:
        logger.error(f"Error generating demo emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
