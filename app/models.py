"""Typed request and response models for the audit API."""

from typing import Any, Dict, List, Optional

from pydantic import AnyHttpUrl, BaseModel


class AuditRequest(BaseModel):
    """Values accepted when starting an audit."""

    url: AnyHttpUrl
    use_ai: bool = False


class CrawledPageSummary(BaseModel):
    """Safe page details returned to clients (HTML is kept private)."""

    url: str
    final_url: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None


class AuditResponse(BaseModel):
    """Complete measured audit report returned by the API."""

    website_url: str
    crawled_pages: List[CrawledPageSummary]
    metrics: Dict[str, Any]
    score: Dict[str, Any]
    errors: List[str]
    recommendations: List[Dict[str, Any]]
    ai_status: str