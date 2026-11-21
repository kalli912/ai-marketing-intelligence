"""FastAPI route that runs the SEO audit workflow."""

import logging
import time

from fastapi import APIRouter

from app.analyzer import analyze_crawl
from app.crawler import crawl_website
from app.models import AuditRequest, AuditResponse, CrawledPageSummary
from app.recommendations import generate_recommendations
from app.scoring import calculate_score


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/audit", response_model=AuditResponse)
def run_audit(request: AuditRequest) -> AuditResponse:
    """Crawl a website, measure its SEO metrics, and return a report."""
    website_url = str(request.url)
    crawl_started = time.perf_counter()
    try:
        crawl_result = crawl_website(website_url)
    finally:
        logger.info(
            "Website crawl finished: duration_seconds=%.3f",
            time.perf_counter() - crawl_started,
        )
    analyzer_result = analyze_crawl(crawl_result)
    score_result = calculate_score(analyzer_result)

    try:
        recommendation_result = generate_recommendations(
            analyzer_result, use_ai=request.use_ai
        )
        ai_status = recommendation_result["ai_status"]
        recommendations = recommendation_result["recommendations"]
    except Exception as error:
        # A recommendation failure must not discard the measured audit.
        logger.warning(
            "Recommendation generation failed (%s); using rule-based fallback.",
            type(error).__name__,
        )
        fallback = generate_recommendations(analyzer_result, use_ai=False)
        recommendations = fallback["recommendations"]
        ai_status = "failed"

    page_summaries = [
        CrawledPageSummary(
            url=page.url,
            final_url=page.final_url,
            status_code=page.status_code,
            error=page.error,
        )
        for page in crawl_result.pages
    ]

    return AuditResponse(
        website_url=website_url,
        crawled_pages=page_summaries,
        metrics=analyzer_result.get("metrics", {}),
        score=score_result,
        errors=list(crawl_result.errors),
        recommendations=recommendations,
        ai_status=ai_status,
    )