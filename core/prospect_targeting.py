"""
Prospect Targeting Service
Scores and filters prospects based on user-defined targeting criteria
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RelevanceScore:
    """Detailed relevance score breakdown"""
    total: float  # 0-100
    industry_score: float  # 0-40
    title_score: float  # 0-25
    size_score: float  # 0-20
    location_score: float  # 0-15
    is_excluded: bool  # If prospect matches exclusion criteria
    exclusion_reason: Optional[str] = None
    details: Dict[str, Any] = None

    def to_dict(self) -> Dict:
        return {
            "total": round(self.total, 1),
            "industry_score": round(self.industry_score, 1),
            "title_score": round(self.title_score, 1),
            "size_score": round(self.size_score, 1),
            "location_score": round(self.location_score, 1),
            "is_excluded": self.is_excluded,
            "exclusion_reason": self.exclusion_reason,
            "details": self.details or {}
        }


class ProspectTargeting:
    """
    Scores prospects based on targeting criteria.

    Relevance Scoring Formula:
    - Industry match: 40%
    - Job title match: 25%
    - Company size match: 20%
    - Location match: 15%
    """

    # Weights for each criterion
    WEIGHTS = {
        "industry": 40,
        "title": 25,
        "size": 20,
        "location": 15
    }

    # Default minimum score threshold
    DEFAULT_MIN_SCORE = 50

    def __init__(self, targeting_criteria: Dict[str, Any]):
        """
        Initialize with targeting criteria.

        Args:
            targeting_criteria: Dict with target_industries, target_job_titles,
                              target_company_sizes, target_locations,
                              excluded_industries, excluded_domains
        """
        self.criteria = targeting_criteria
        self.target_industries = self._normalize_list(
            targeting_criteria.get("target_industries", [])
        )
        self.target_titles = self._normalize_list(
            targeting_criteria.get("target_job_titles", [])
        )
        self.target_sizes = self._normalize_list(
            targeting_criteria.get("target_company_sizes", [])
        )
        self.target_locations = self._normalize_list(
            targeting_criteria.get("target_locations", [])
        )
        self.excluded_industries = self._normalize_list(
            targeting_criteria.get("excluded_industries", [])
        )
        self.excluded_domains = self._normalize_list(
            targeting_criteria.get("excluded_domains", [])
        )
        self.min_score = targeting_criteria.get(
            "min_relevance_score",
            self.DEFAULT_MIN_SCORE
        )

    def _normalize_list(self, items: Any) -> List[str]:
        """Normalize a list of items to lowercase strings"""
        if not items:
            return []
        if isinstance(items, str):
            return [items.lower().strip()]
        return [str(item).lower().strip() for item in items if item]

    def score_prospect(self, prospect: Dict[str, Any]) -> RelevanceScore:
        """
        Score a prospect based on targeting criteria.

        Args:
            prospect: Dict with company_industry, job_title, company_size,
                     company_location, email, company_domain

        Returns:
            RelevanceScore with detailed breakdown
        """
        # Check exclusions first
        exclusion = self._check_exclusions(prospect)
        if exclusion:
            return RelevanceScore(
                total=0,
                industry_score=0,
                title_score=0,
                size_score=0,
                location_score=0,
                is_excluded=True,
                exclusion_reason=exclusion
            )

        # Calculate individual scores
        industry_score = self._score_industry(prospect)
        title_score = self._score_title(prospect)
        size_score = self._score_size(prospect)
        location_score = self._score_location(prospect)

        total = industry_score + title_score + size_score + location_score

        return RelevanceScore(
            total=total,
            industry_score=industry_score,
            title_score=title_score,
            size_score=size_score,
            location_score=location_score,
            is_excluded=False,
            details={
                "matched_industry": self._get_matched_industry(prospect),
                "matched_title": self._get_matched_title(prospect),
                "matched_size": self._get_matched_size(prospect),
                "matched_location": self._get_matched_location(prospect)
            }
        )

    def _check_exclusions(self, prospect: Dict[str, Any]) -> Optional[str]:
        """Check if prospect matches any exclusion criteria"""
        # Check excluded industries
        industry = str(prospect.get("company_industry", "")).lower()
        for excluded in self.excluded_industries:
            if excluded and (excluded in industry or industry in excluded):
                return f"Excluded industry: {excluded}"

        # Check excluded domains
        domain = str(prospect.get("company_domain", "")).lower()
        email = str(prospect.get("email", "")).lower()
        email_domain = email.split("@")[-1] if "@" in email else ""

        for excluded in self.excluded_domains:
            if excluded:
                if excluded in domain or domain.endswith(excluded):
                    return f"Excluded domain: {excluded}"
                if excluded in email_domain or email_domain.endswith(excluded):
                    return f"Excluded domain: {excluded}"

        return None

    def _score_industry(self, prospect: Dict[str, Any]) -> float:
        """Score industry match (0-40)"""
        if not self.target_industries:
            return self.WEIGHTS["industry"]  # Full score if no targeting

        industry = str(prospect.get("company_industry", "")).lower()
        if not industry:
            return 0

        for target in self.target_industries:
            # Exact match
            if target == industry:
                return self.WEIGHTS["industry"]
            # Partial match (target contains industry or vice versa)
            if target in industry or industry in target:
                return self.WEIGHTS["industry"] * 0.8

        return 0

    def _score_title(self, prospect: Dict[str, Any]) -> float:
        """Score job title match (0-25)"""
        if not self.target_titles:
            return self.WEIGHTS["title"]  # Full score if no targeting

        title = str(prospect.get("job_title", "")).lower()
        if not title:
            return 0

        for target in self.target_titles:
            # Exact match
            if target == title:
                return self.WEIGHTS["title"]
            # Partial match
            if target in title or title in target:
                return self.WEIGHTS["title"] * 0.8
            # Word overlap
            target_words = set(target.split())
            title_words = set(title.split())
            overlap = target_words & title_words
            if overlap:
                return self.WEIGHTS["title"] * (len(overlap) / len(target_words)) * 0.7

        return 0

    def _score_size(self, prospect: Dict[str, Any]) -> float:
        """Score company size match (0-20)"""
        if not self.target_sizes:
            return self.WEIGHTS["size"]  # Full score if no targeting

        size = str(prospect.get("company_size", "")).lower()
        if not size:
            return 0

        for target in self.target_sizes:
            if target in size or size in target:
                return self.WEIGHTS["size"]

        # Try to parse numeric ranges
        prospect_range = self._parse_size_range(size)
        if prospect_range:
            for target in self.target_sizes:
                target_range = self._parse_size_range(target)
                if target_range and self._ranges_overlap(prospect_range, target_range):
                    return self.WEIGHTS["size"]

        return 0

    def _score_location(self, prospect: Dict[str, Any]) -> float:
        """Score location match (0-15)"""
        if not self.target_locations:
            return self.WEIGHTS["location"]  # Full score if no targeting

        location = str(prospect.get("company_location", "")).lower()
        if not location:
            return 0

        for target in self.target_locations:
            # Exact match
            if target == location:
                return self.WEIGHTS["location"]
            # Partial match (city in state, state in country)
            if target in location or location in target:
                return self.WEIGHTS["location"] * 0.8

        return 0

    def _parse_size_range(self, size_str: str) -> Optional[tuple]:
        """Parse a size string like '50-200' into (50, 200)"""
        # Match patterns like "50-200", "51-200", "200+", "1000+"
        match = re.search(r"(\d+)\s*[-–]\s*(\d+)", size_str)
        if match:
            return (int(match.group(1)), int(match.group(2)))

        # Match "X+" pattern
        match = re.search(r"(\d+)\s*\+", size_str)
        if match:
            return (int(match.group(1)), float("inf"))

        return None

    def _ranges_overlap(self, range1: tuple, range2: tuple) -> bool:
        """Check if two numeric ranges overlap"""
        return range1[0] <= range2[1] and range2[0] <= range1[1]

    def _get_matched_industry(self, prospect: Dict) -> Optional[str]:
        """Get the matched industry target"""
        industry = str(prospect.get("company_industry", "")).lower()
        for target in self.target_industries:
            if target in industry or industry in target:
                return target
        return None

    def _get_matched_title(self, prospect: Dict) -> Optional[str]:
        """Get the matched title target"""
        title = str(prospect.get("job_title", "")).lower()
        for target in self.target_titles:
            if target in title or title in target:
                return target
        return None

    def _get_matched_size(self, prospect: Dict) -> Optional[str]:
        """Get the matched size target"""
        size = str(prospect.get("company_size", "")).lower()
        for target in self.target_sizes:
            if target in size or size in target:
                return target
        return None

    def _get_matched_location(self, prospect: Dict) -> Optional[str]:
        """Get the matched location target"""
        location = str(prospect.get("company_location", "")).lower()
        for target in self.target_locations:
            if target in location or location in target:
                return target
        return None

    def filter_prospects(
        self,
        prospects: List[Dict[str, Any]],
        min_score: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter and score a list of prospects.

        Args:
            prospects: List of prospect dicts
            min_score: Minimum score threshold (defaults to criteria setting)

        Returns:
            List of prospects with relevance_score added, sorted by score
        """
        threshold = min_score if min_score is not None else self.min_score
        scored = []

        for prospect in prospects:
            score = self.score_prospect(prospect)

            if not score.is_excluded and score.total >= threshold:
                prospect_copy = prospect.copy()
                prospect_copy["relevance_score"] = score.to_dict()
                scored.append(prospect_copy)

        # Sort by score descending
        scored.sort(key=lambda p: p["relevance_score"]["total"], reverse=True)

        return scored

    def analyze_batch(
        self,
        prospects: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze a batch of prospects and return statistics.

        Args:
            prospects: List of prospect dicts

        Returns:
            Dict with statistics and categorized prospects
        """
        high_relevance = []  # 70+
        medium_relevance = []  # 50-69
        low_relevance = []  # <50
        excluded = []

        for prospect in prospects:
            score = self.score_prospect(prospect)
            prospect_with_score = prospect.copy()
            prospect_with_score["relevance_score"] = score.to_dict()

            if score.is_excluded:
                excluded.append(prospect_with_score)
            elif score.total >= 70:
                high_relevance.append(prospect_with_score)
            elif score.total >= 50:
                medium_relevance.append(prospect_with_score)
            else:
                low_relevance.append(prospect_with_score)

        return {
            "total_analyzed": len(prospects),
            "high_relevance": {
                "count": len(high_relevance),
                "prospects": sorted(
                    high_relevance,
                    key=lambda p: p["relevance_score"]["total"],
                    reverse=True
                )
            },
            "medium_relevance": {
                "count": len(medium_relevance),
                "prospects": sorted(
                    medium_relevance,
                    key=lambda p: p["relevance_score"]["total"],
                    reverse=True
                )
            },
            "low_relevance": {
                "count": len(low_relevance),
                "prospects": sorted(
                    low_relevance,
                    key=lambda p: p["relevance_score"]["total"],
                    reverse=True
                )
            },
            "excluded": {
                "count": len(excluded),
                "prospects": excluded
            },
            "statistics": {
                "avg_score": sum(
                    p["relevance_score"]["total"]
                    for p in high_relevance + medium_relevance + low_relevance
                ) / max(1, len(high_relevance) + len(medium_relevance) + len(low_relevance)),
                "qualified_rate": len(high_relevance + medium_relevance) / max(1, len(prospects)) * 100
            }
        }


def create_targeting_from_profile(business_profile: Dict[str, Any]) -> ProspectTargeting:
    """
    Create a ProspectTargeting instance from a BusinessProfile.

    Args:
        business_profile: BusinessProfile dict with targeting fields

    Returns:
        ProspectTargeting instance
    """
    return ProspectTargeting({
        "target_industries": business_profile.get("target_industries", []),
        "target_job_titles": business_profile.get("target_job_titles", []),
        "target_company_sizes": business_profile.get("target_company_sizes", []),
        "target_locations": business_profile.get("target_locations", []),
        "excluded_industries": business_profile.get("excluded_industries", []),
        "excluded_domains": [],  # Can be added if needed
        "min_relevance_score": 50
    })
