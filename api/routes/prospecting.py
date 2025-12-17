"""
Prospecting API Routes
Handles prospect finding, enrichment, LinkedIn, and CRM operations
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from core.database import (
    get_db, User, BusinessProfile, ProspectSource, TargetingCriteria,
    LinkedInConnection, CRMConnection
)
from api.routes.emails import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prospecting", tags=["prospecting"])


# ============================================
# PROSPECT FINDING ENDPOINTS
# ============================================

@router.post("/find")
async def find_prospects(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find prospects from a company website.

    Request body:
        website_url: Company website to scrape
        max_pages: Maximum pages to scrape (default: 10)
    """
    from core.prospect_finder import find_prospects_from_website

    website_url = request.get("website_url")
    if not website_url:
        raise HTTPException(status_code=400, detail="Website URL is required")

    try:
        result = await find_prospects_from_website(
            website_url,
            max_pages=request.get("max_pages", 10)
        )

        # Save source to database
        source = ProspectSource(
            user_id=current_user.id,
            source_type="website",
            source_url=website_url,
            domain=result.get("domain"),
            scraped_at=datetime.utcnow(),
            contacts_found=len(result.get("contacts", [])),
            raw_data=result,
            status="completed" if result.get("success") else "failed"
        )
        db.add(source)
        db.commit()

        return result

    except Exception as e:
        logger.error(f"Error finding prospects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/find-batch")
async def find_prospects_batch(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find prospects from multiple websites.

    Request body:
        website_urls: List of website URLs
        max_concurrent: Maximum concurrent scrapes (default: 3)
    """
    from core.prospect_finder import find_prospects_batch

    urls = request.get("website_urls", [])
    if not urls:
        raise HTTPException(status_code=400, detail="Website URLs required")

    if len(urls) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 URLs per batch")

    try:
        results = await find_prospects_batch(
            urls,
            max_concurrent=request.get("max_concurrent", 3)
        )

        # Save sources
        for result in results:
            source = ProspectSource(
                user_id=current_user.id,
                source_type="website",
                source_url=result.get("base_url"),
                domain=result.get("domain"),
                scraped_at=datetime.utcnow(),
                contacts_found=len(result.get("contacts", [])),
                status="completed" if result.get("success") else "failed",
                error_message=result.get("error")
            )
            db.add(source)

        db.commit()

        return {
            "success": True,
            "results": results,
            "total_websites": len(urls),
            "total_contacts": sum(len(r.get("contacts", [])) for r in results)
        }

    except Exception as e:
        logger.error(f"Error in batch prospect finding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/score")
async def score_prospects(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Score prospects based on targeting criteria.

    Request body:
        prospects: List of prospect dicts
        criteria: Optional targeting criteria (uses profile default if not provided)
    """
    from core.prospect_targeting import ProspectTargeting, create_targeting_from_profile

    prospects = request.get("prospects", [])
    if not prospects:
        raise HTTPException(status_code=400, detail="Prospects list required")

    # Get targeting criteria
    criteria = request.get("criteria")
    if not criteria:
        # Use profile targeting
        profile = db.query(BusinessProfile).filter(
            BusinessProfile.user_id == current_user.id
        ).first()

        if profile:
            targeting = create_targeting_from_profile({
                "target_industries": profile.target_industries,
                "target_job_titles": profile.target_job_titles,
                "target_company_sizes": profile.target_company_sizes,
                "target_locations": profile.target_locations,
                "excluded_industries": profile.excluded_industries
            })
        else:
            targeting = ProspectTargeting({})
    else:
        targeting = ProspectTargeting(criteria)

    # Analyze prospects
    analysis = targeting.analyze_batch(prospects)

    return analysis


@router.get("/sources")
async def get_prospect_sources(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of scraped prospect sources"""
    sources = db.query(ProspectSource).filter(
        ProspectSource.user_id == current_user.id
    ).order_by(ProspectSource.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "sources": [{
            "id": s.id,
            "source_type": s.source_type,
            "source_url": s.source_url,
            "domain": s.domain,
            "contacts_found": s.contacts_found,
            "emails_verified": s.emails_verified,
            "status": s.status,
            "scraped_at": s.scraped_at.isoformat() if s.scraped_at else None
        } for s in sources]
    }


# ============================================
# TARGETING CRITERIA ENDPOINTS
# ============================================

@router.get("/targeting")
async def get_targeting_criteria(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user's targeting criteria"""
    criteria = db.query(TargetingCriteria).filter(
        TargetingCriteria.user_id == current_user.id
    ).all()

    return {
        "criteria": [{
            "id": c.id,
            "name": c.name,
            "is_default": c.is_default,
            "target_industries": c.target_industries,
            "target_job_titles": c.target_job_titles,
            "target_company_sizes": c.target_company_sizes,
            "target_locations": c.target_locations,
            "excluded_industries": c.excluded_industries,
            "excluded_domains": c.excluded_domains,
            "min_relevance_score": c.min_relevance_score
        } for c in criteria]
    }


@router.post("/targeting")
async def save_targeting_criteria(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save targeting criteria"""
    criteria_id = request.get("id")

    if criteria_id:
        criteria = db.query(TargetingCriteria).filter(
            TargetingCriteria.id == criteria_id,
            TargetingCriteria.user_id == current_user.id
        ).first()
        if not criteria:
            raise HTTPException(status_code=404, detail="Criteria not found")
    else:
        criteria = TargetingCriteria(user_id=current_user.id)
        db.add(criteria)

    # Update fields
    criteria.name = request.get("name", "Default")
    criteria.is_default = request.get("is_default", False)
    criteria.target_industries = request.get("target_industries", [])
    criteria.target_job_titles = request.get("target_job_titles", [])
    criteria.target_company_sizes = request.get("target_company_sizes", [])
    criteria.target_locations = request.get("target_locations", [])
    criteria.excluded_industries = request.get("excluded_industries", [])
    criteria.excluded_domains = request.get("excluded_domains", [])
    criteria.min_relevance_score = request.get("min_relevance_score", 50)

    db.commit()

    return {"success": True, "id": criteria.id}


# ============================================
# ENRICHMENT ENDPOINTS
# ============================================

@router.post("/enrich/email")
async def enrich_find_email(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find email for a person at a company.

    Request body:
        domain: Company domain
        first_name: Person's first name
        last_name: Person's last name
    """
    from core.enrichment_service import EnrichmentService

    domain = request.get("domain")
    if not domain:
        raise HTTPException(status_code=400, detail="Domain required")

    service = EnrichmentService(db, current_user.id)

    result = await service.find_email(
        domain=domain,
        first_name=request.get("first_name"),
        last_name=request.get("last_name")
    )

    return result.to_dict()


@router.post("/enrich/verify")
async def enrich_verify_email(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Verify an email address"""
    from core.enrichment_service import EnrichmentService

    email = request.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    service = EnrichmentService(db, current_user.id)
    result = await service.verify_email(email)

    return result.to_dict()


@router.post("/enrich/domain")
async def enrich_domain(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get company information from domain"""
    from core.enrichment_service import EnrichmentService

    domain = request.get("domain")
    if not domain:
        raise HTTPException(status_code=400, detail="Domain required")

    service = EnrichmentService(db, current_user.id)
    result = await service.enrich_domain(domain)

    return result.to_dict()


@router.post("/enrich/search")
async def enrich_search_domain(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search for all contacts at a domain"""
    from core.enrichment_service import EnrichmentService

    domain = request.get("domain")
    if not domain:
        raise HTTPException(status_code=400, detail="Domain required")

    service = EnrichmentService(db, current_user.id)
    results = await service.search_domain(
        domain,
        limit=request.get("limit", 10)
    )

    return {"contacts": [r.to_dict() for r in results]}


@router.get("/enrich/credits")
async def get_enrichment_credits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get enrichment API credits status"""
    from core.enrichment_service import EnrichmentService

    service = EnrichmentService(db, current_user.id)
    return await service.get_credits_status()


# ============================================
# LINKEDIN ENDPOINTS
# ============================================

@router.post("/linkedin/import")
async def import_linkedin_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Import LinkedIn connections from CSV file"""
    from core.linkedin_service import LinkedInService

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    csv_content = content.decode("utf-8")

    service = LinkedInService(db, current_user.id)
    result = service.import_connections(csv_content)

    return result


@router.get("/linkedin/connections")
async def get_linkedin_connections(
    search: Optional[str] = None,
    company: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get imported LinkedIn connections"""
    from core.linkedin_service import LinkedInService

    service = LinkedInService(db, current_user.id)
    return service.get_connections(
        search=search,
        company=company,
        limit=limit,
        offset=offset
    )


@router.post("/linkedin/match")
async def match_linkedin_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Match LinkedIn connections to existing prospects"""
    from core.linkedin_service import LinkedInService

    service = LinkedInService(db, current_user.id)
    return service.match_connections_to_prospects()


@router.post("/linkedin/convert/{connection_id}")
async def convert_linkedin_to_prospect(
    connection_id: str,
    request: Dict = {},
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Convert a LinkedIn connection to a prospect"""
    from core.linkedin_service import LinkedInService

    service = LinkedInService(db, current_user.id)
    return service.convert_to_prospect(
        connection_id,
        campaign_id=request.get("campaign_id")
    )


@router.post("/linkedin/find-mutual")
async def find_mutual_connections(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Find LinkedIn connections at a prospect's company"""
    from core.linkedin_service import LinkedInService

    company = request.get("company")
    if not company:
        raise HTTPException(status_code=400, detail="Company name required")

    service = LinkedInService(db, current_user.id)
    return {"connections": service.find_mutual_connections(company)}


# ============================================
# CRM ENDPOINTS
# ============================================

@router.get("/crm/connections")
async def get_crm_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all CRM connections"""
    from core.crm_service import CRMService

    service = CRMService(db, current_user.id)
    return {"connections": await service.get_connections()}


@router.post("/crm/connect/hubspot")
async def connect_hubspot(
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Connect to HubSpot CRM"""
    from core.crm_service import CRMService

    service = CRMService(db, current_user.id)
    return await service.connect_hubspot(
        api_key=request.get("api_key"),
        access_token=request.get("access_token"),
        refresh_token=request.get("refresh_token")
    )


@router.post("/crm/disconnect/{provider}")
async def disconnect_crm(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Disconnect a CRM provider"""
    from core.crm_service import CRMService

    service = CRMService(db, current_user.id)
    return await service.disconnect(provider)


@router.post("/crm/import/{provider}")
async def import_from_crm(
    provider: str,
    request: Dict = {},
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Import contacts from CRM"""
    from core.crm_service import CRMService

    service = CRMService(db, current_user.id)
    return await service.import_contacts(
        provider,
        limit=request.get("limit", 100)
    )


@router.post("/crm/export/{provider}")
async def export_to_crm(
    provider: str,
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export prospects to CRM"""
    from core.crm_service import CRMService

    service = CRMService(db, current_user.id)
    return await service.export_prospects(
        provider,
        prospect_ids=request.get("prospect_ids"),
        export_all=request.get("export_all", False)
    )


@router.post("/crm/export-deal/{provider}")
async def export_deal_to_crm(
    provider: str,
    request: Dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export an opportunity as a CRM deal"""
    from core.crm_service import CRMService

    service = CRMService(db, current_user.id)
    return await service.export_deal(provider, request)


@router.get("/crm/sync-history")
async def get_crm_sync_history(
    provider: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get CRM sync history"""
    from core.crm_service import CRMService

    service = CRMService(db, current_user.id)
    return {"history": await service.get_sync_history(provider, limit)}
