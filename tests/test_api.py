import asyncio
import json

import httpx

import app.api as audit_api
import app.recommendations as recommendations
from app.crawler import CrawlResult, CrawledPage
from app.main import app


def post_audit(payload):
    """Send an in-process HTTP request through the FastAPI ASGI application."""
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.post("/audit", json=payload)

    return asyncio.run(send_request())


def make_analyzer_result():
    return {
        "website_url": "https://example.test/",
        "metrics": {
            "title_meta_description": {
                "status": "good",
                "pages": [
                    {
                        "page_url": "https://example.test/",
                        "status": "good",
                        "title": {
                            "text": "A Good SEO Title With Enough Characters",
                            "character_count": 40,
                            "present": True,
                            "status": "good",
                        },
                        "meta_description": {
                            "text": "A sample description long enough to meet the configured minimum length.",
                            "character_count": 70,
                            "present": True,
                            "status": "good",
                        },
                    }
                ],
            },
            "broken_internal_links": {
                "status": "needs_improvement",
                "checked_link_count": 1,
                "checked_link_occurrence_count": 1,
                "broken_links": [
                    {
                        "source_url": "https://example.test/",
                        "target_url": "https://example.test/missing",
                        "status_code": 404,
                    }
                ],
                "unverified_links": [],
            },
            "h1_heading": {
                "status": "needs_improvement",
                "pages": [
                    {
                        "page_url": "https://example.test/",
                        "h1_count": 0,
                        "status": "needs_improvement",
                    }
                ],
            },
            "image_alt_text": {
                "status": "good",
                "pages": [
                    {
                        "page_url": "https://example.test/",
                        "image_count": 1,
                        "images_with_alt": 1,
                        "alt_text_percentage": 100.0,
                        "status": "good",
                    }
                ],
            },
            "canonical_tag": {
                "status": "good",
                "pages": [
                    {
                        "page_url": "https://example.test/",
                        "canonical_count": 1,
                        "canonical_urls": [
                            {
                                "url": "https://example.test/",
                                "valid": True,
                            }
                        ],
                        "status": "good",
                    }
                ],
            },
        },
    }


def mock_audit_inputs(monkeypatch):
    page = CrawledPage(
        url="https://example.test/",
        final_url="https://example.test/",
        status_code=200,
        html="<html>private page HTML</html>",
    )
    crawl_result = CrawlResult(
        start_url="https://example.test/",
        pages=[page],
        errors=[],
    )
    monkeypatch.setattr(audit_api, "crawl_website", lambda url: crawl_result)
    monkeypatch.setattr(
        audit_api, "analyze_crawl", lambda result: make_analyzer_result()
    )


def test_audit_response_includes_recommendations_score_and_sanitized_pages(
    monkeypatch,
):
    mock_audit_inputs(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    response = post_audit(
        {"url": "https://example.test/", "use_ai": False}
    )

    assert response.status_code == 200
    report = response.json()
    assert report["ai_status"] == "not_requested"
    assert report["recommendations"]
    assert report["recommendations"][0]["id"] == "broken-links"
    assert report["score"]["score"] == "55/100"
    assert report["crawled_pages"] == [
        {
            "url": "https://example.test/",
            "final_url": "https://example.test/",
            "status_code": 200,
            "error": None,
        }
    ]
    assert "private page HTML" not in response.text


def test_audit_logs_crawl_duration_without_logging_the_website(monkeypatch, caplog):
    mock_audit_inputs(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with caplog.at_level("INFO", logger="app.api"):
        response = post_audit(
            {"url": "https://example.test/", "use_ai": False}
        )

    crawl_logs = [
        record.getMessage()
        for record in caplog.records
        if "Website crawl finished" in record.getMessage()
    ]

    assert response.status_code == 200
    assert len(crawl_logs) == 1
    assert "duration_seconds=" in crawl_logs[0]
    assert "example.test" not in crawl_logs[0]


def test_audit_can_use_mocked_gemini_without_returning_the_api_key(
    monkeypatch,
):
    mock_audit_inputs(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    def fake_ai_actions(items, api_key, timeout):
        assert api_key == "test-api-key"
        return (
            {item["id"]: "Take this measured action." for item in items},
            None,
        )

    monkeypatch.setattr(recommendations, "_get_ai_actions", fake_ai_actions)

    response = post_audit(
        {"url": "https://example.test/", "use_ai": True}
    )

    assert response.status_code == 200
    report = response.json()
    assert report["ai_status"] == "used"
    assert all(
        item["action"] == "Take this measured action."
        for item in report["recommendations"]
    )
    assert "test-api-key" not in response.text


def test_recommendation_failure_does_not_fail_the_audit(monkeypatch):
    mock_audit_inputs(monkeypatch)

    def fail_when_ai_enabled(analyzer_result, use_ai=True):
        if use_ai:
            raise RuntimeError("simulated recommendation failure")
        return recommendations.generate_recommendations(
            analyzer_result, use_ai=False
        )

    monkeypatch.setattr(audit_api, "generate_recommendations", fail_when_ai_enabled)

    response = post_audit(
        {"url": "https://example.test/", "use_ai": True}
    )

    assert response.status_code == 200
    report = response.json()
    assert report["ai_status"] == "failed"
    assert report["recommendations"]
    assert report["score"]["score"] == "55/100"


def test_invalid_url_returns_http_422_without_crawling(monkeypatch):
    monkeypatch.setattr(
        audit_api,
        "crawl_website",
        lambda url: (_ for _ in ()).throw(
            AssertionError("invalid URLs must fail request validation")
        ),
    )

    response = post_audit(
        {"url": "file:///private.txt", "use_ai": False}
    )

    assert response.status_code == 422
    assert "detail" in response.json()