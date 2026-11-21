"""Measure the five SEO checks from pages returned by the crawler."""

from concurrent.futures import ThreadPoolExecutor
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from app.crawler import (
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    CrawlResult,
    CrawledPage,
    _check_public_host,
    _hostname_from_url,
    _load_robots_rules,
    _normalize_url,
)


TITLE_MIN_LENGTH = 30
TITLE_MAX_LENGTH = 60
DESCRIPTION_MIN_LENGTH = 70
DESCRIPTION_MAX_LENGTH = 160
IMAGE_ALT_THRESHOLD = 90.0
RATE_LIMIT_STATUS = 429
MAX_LINK_CHECK_WORKERS = 5


logger = logging.getLogger(__name__)


def _value_result(
    value: Optional[str], minimum: int, maximum: int
) -> Dict[str, Any]:
    """Return a value, its length, and whether its length is in range."""
    has_value = value is not None and bool(value.strip())
    character_count = len(value) if value is not None else 0
    status = (
        "good"
        if has_value and minimum <= character_count <= maximum
        else "needs_improvement"
    )
    return {
        "text": value,
        "character_count": character_count,
        "present": has_value,
        "status": status,
    }


def _unavailable_page(page: CrawledPage) -> Dict[str, Any]:
    """Describe a page whose HTML was not available for analysis."""
    return {
        "page_url": page.url,
        "status": "unavailable",
        "error": page.error or "Page HTML was unavailable.",
    }


def _page_status(statuses: List[str]) -> str:
    """Summarize checked pages without treating unavailable pages as passes."""
    checked_statuses = [status for status in statuses if status != "unavailable"]
    if not checked_statuses:
        return "unavailable"
    if "needs_improvement" in checked_statuses:
        return "needs_improvement"
    if len(checked_statuses) != len(statuses):
        return "partially_available"
    return "good"


def _analyze_title_and_description(page: CrawledPage) -> Dict[str, Any]:
    if page.html is None:
        result = _unavailable_page(page)
        result.update(
            {
                "title": {
                    "text": None,
                    "character_count": None,
                    "present": False,
                    "status": "unavailable",
                },
                "meta_description": {
                    "text": None,
                    "character_count": None,
                    "present": False,
                    "status": "unavailable",
                },
            }
        )
        return result

    soup = BeautifulSoup(page.html, "html.parser")
    title_tag = soup.find("title")
    title_text = (
        title_tag.get_text(" ", strip=True) if title_tag is not None else None
    )

    description_text = None
    for meta_tag in soup.find_all("meta"):
        name = meta_tag.get("name", "")
        if str(name).strip().lower() == "description":
            description_text = meta_tag.get("content")
            break

    title = _value_result(title_text, TITLE_MIN_LENGTH, TITLE_MAX_LENGTH)
    description = _value_result(
        description_text, DESCRIPTION_MIN_LENGTH, DESCRIPTION_MAX_LENGTH
    )
    status = (
        "good"
        if title["status"] == "good" and description["status"] == "good"
        else "needs_improvement"
    )
    return {
        "page_url": page.final_url or page.url,
        "status": status,
        "title": title,
        "meta_description": description,
    }


def _analyze_h1(page: CrawledPage) -> Dict[str, Any]:
    if page.html is None:
        return _unavailable_page(page)

    heading_count = len(BeautifulSoup(page.html, "html.parser").find_all("h1"))
    return {
        "page_url": page.final_url or page.url,
        "h1_count": heading_count,
        "status": "good" if heading_count == 1 else "needs_improvement",
    }


def _analyze_images(page: CrawledPage) -> Dict[str, Any]:
    if page.html is None:
        return _unavailable_page(page)

    images = BeautifulSoup(page.html, "html.parser").find_all("img")
    image_count = len(images)
    images_with_alt = sum(
        1
        for image in images
        if image.get("alt") is not None and bool(str(image.get("alt")).strip())
    )

    if image_count == 0:
        return {
            "page_url": page.final_url or page.url,
            "image_count": 0,
            "images_with_alt": 0,
            "alt_text_percentage": None,
            "status": "unavailable",
        }

    percentage = images_with_alt / image_count * 100
    return {
        "page_url": page.final_url or page.url,
        "image_count": image_count,
        "images_with_alt": images_with_alt,
        "alt_text_percentage": round(percentage, 2),
        "status": (
            "good" if percentage >= IMAGE_ALT_THRESHOLD else "needs_improvement"
        ),
    }


def _is_canonical_relation(link_tag: Any) -> bool:
    relation = link_tag.get("rel", [])
    if isinstance(relation, str):
        relation = relation.split()
    return any(str(value).lower() == "canonical" for value in relation)


def _analyze_canonical(page: CrawledPage) -> Dict[str, Any]:
    if page.html is None:
        return _unavailable_page(page)

    soup = BeautifulSoup(page.html, "html.parser")
    canonical_tags = [
        tag for tag in soup.find_all("link") if _is_canonical_relation(tag)
    ]
    canonical_urls = []
    for tag in canonical_tags:
        raw_url = tag.get("href")
        is_valid = False
        if isinstance(raw_url, str) and raw_url.strip():
            try:
                # Canonical URLs must be absolute HTTP or HTTPS URLs.
                normalized_url = _normalize_url(raw_url.strip())
                is_valid = urlsplit(normalized_url).scheme in {"http", "https"}
            except ValueError:
                pass
        canonical_urls.append({"url": raw_url, "valid": is_valid})

    status = (
        "good"
        if len(canonical_urls) == 1 and canonical_urls[0]["valid"]
        else "needs_improvement"
    )
    return {
        "page_url": page.final_url or page.url,
        "canonical_count": len(canonical_urls),
        "canonical_urls": canonical_urls,
        "status": status,
    }


def _collect_internal_link_sources(
    crawl_result: CrawlResult, hostname: str
) -> Dict[str, List[str]]:
    """Map each unique internal URL to every source link occurrence."""
    link_sources: Dict[str, List[str]] = {}
    for page in crawl_result.pages:
        if page.html is None:
            continue

        source_url = page.final_url or page.url
        soup = BeautifulSoup(page.html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            try:
                link_url = _normalize_url(urljoin(source_url, href))
            except ValueError:
                continue
            if _hostname_from_url(link_url) == hostname:
                link_sources.setdefault(link_url, []).append(source_url)
    return link_sources


def _check_internal_links(
    crawl_result: CrawlResult, timeout: float
) -> Dict[str, Any]:
    """Check unique internal links and keep unverified results separate."""
    verification_started = time.perf_counter()
    try:
        start_url = _normalize_url(crawl_result.start_url)
        hostname = _hostname_from_url(start_url)
    except ValueError:
        return {
            "status": "unavailable",
            "checked_link_count": 0,
            "checked_link_occurrence_count": 0,
            "broken_links": [],
            "unverified_links": [],
        }

    link_sources = _collect_internal_link_sources(crawl_result, hostname)
    if not link_sources:
        logger.info(
            "Internal link verification finished: duration_seconds=%.3f "
            "unique_links=0 request_attempts=0",
            time.perf_counter() - verification_started,
        )
        return {
            "status": "unavailable",
            "checked_link_count": 0,
            "checked_link_occurrence_count": 0,
            "broken_links": [],
            "unverified_links": [],
        }

    broken_links = []
    unverified_links = []
    checked_link_count = 0
    checked_link_occurrence_count = 0
    request_attempts = 0
    worker_state = threading.local()
    worker_sessions = []
    worker_sessions_lock = threading.Lock()

    def get_worker_session() -> requests.Session:
        session = getattr(worker_state, "session", None)
        if session is None:
            session = requests.Session()
            worker_state.session = session
            with worker_sessions_lock:
                worker_sessions.append(session)
        return session

    def verify_link(
        item: Tuple[str, List[str]]
    ) -> Tuple[bool, int, bool, List[Dict[str, Any]], List[Dict[str, Any]]]:
        link_url, source_urls = item
        reason = robots_error
        response = None
        broken_for_link: List[Dict[str, Any]] = []
        unverified_for_link: List[Dict[str, Any]] = []
        checked = False
        attempted = False

        if reason is None and robots is None:
            reason = "Could not check robots.txt."
        elif reason is None and not robots.can_fetch(
            DEFAULT_USER_AGENT, link_url
        ):
            reason = "Disallowed by robots.txt."
        elif reason is None:
            reason = _check_public_host(link_url)

        if reason is None:
            try:
                attempted = True
                response = get_worker_session().get(
                    link_url,
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                    timeout=timeout,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.Timeout:
                reason = "Request timed out."
            except requests.RequestException as error:
                reason = "Request failed: {}".format(error)
            else:
                if response.status_code == RATE_LIMIT_STATUS:
                    reason = "HTTP 429 rate limit; link is unverified."
                elif response.status_code >= 400:
                    checked = True
                    broken_for_link = [
                        {
                            "source_url": source_url,
                            "target_url": link_url,
                            "status_code": response.status_code,
                        }
                        for source_url in source_urls
                    ]
                else:
                    checked = True
            finally:
                if response is not None:
                    response.close()

        if reason is not None:
            unverified_for_link = [
                {
                    "source_url": source_url,
                    "target_url": link_url,
                    "reason": reason,
                    "status_code": (
                        response.status_code if response is not None else None
                    ),
                }
                for source_url in source_urls
            ]

        return (
            checked,
            len(source_urls) if checked else 0,
            attempted,
            broken_for_link,
            unverified_for_link,
        )

    try:
        robots_session = requests.Session()
        try:
            robots, robots_error = _load_robots_rules(
                robots_session, start_url, DEFAULT_USER_AGENT, timeout
            )
        finally:
            robots_session.close()

        with ThreadPoolExecutor(
            max_workers=min(MAX_LINK_CHECK_WORKERS, len(link_sources))
        ) as executor:
            for (
                checked,
                occurrence_count,
                attempted,
                broken_for_link,
                unverified_for_link,
            ) in executor.map(verify_link, link_sources.items()):
                if checked:
                    checked_link_count += 1
                    checked_link_occurrence_count += occurrence_count
                if attempted:
                    request_attempts += 1
                broken_links.extend(broken_for_link)
                unverified_links.extend(unverified_for_link)
    finally:
        for session in worker_sessions:
            session.close()
        logger.info(
            "Internal link verification finished: duration_seconds=%.3f "
            "unique_links=%d request_attempts=%d",
            time.perf_counter() - verification_started,
            len(link_sources),
            request_attempts,
        )

    if checked_link_count == 0:
        status = "unavailable"
    elif broken_links:
        status = "needs_improvement"
    elif unverified_links:
        status = "partially_available"
    else:
        status = "good"

    return {
        "status": status,
        "checked_link_count": checked_link_count,
        "checked_link_occurrence_count": checked_link_occurrence_count,
        "broken_links": broken_links,
        "unverified_links": unverified_links,
    }


def analyze_crawl(
    crawl_result: CrawlResult, timeout: float = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Analyze the HTML in a CrawlResult and check its discovered internal links."""
    title_results = [
        _analyze_title_and_description(page) for page in crawl_result.pages
    ]
    h1_results = [_analyze_h1(page) for page in crawl_result.pages]
    image_results = [_analyze_images(page) for page in crawl_result.pages]
    canonical_results = [_analyze_canonical(page) for page in crawl_result.pages]

    return {
        "website_url": crawl_result.start_url,
        "metrics": {
            "title_meta_description": {
                "status": _page_status(
                    [result["status"] for result in title_results]
                ),
                "pages": title_results,
            },
            "broken_internal_links": _check_internal_links(crawl_result, timeout),
            "h1_heading": {
                "status": _page_status(
                    [result["status"] for result in h1_results]
                ),
                "pages": h1_results,
            },
            "image_alt_text": {
                "status": _page_status(
                    [result["status"] for result in image_results]
                ),
                "pages": image_results,
            },
            "canonical_tag": {
                "status": _page_status(
                    [result["status"] for result in canonical_results]
                ),
                "pages": canonical_results,
            },
        },
    }