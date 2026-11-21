import json

import requests

import app.recommendations as recommendations


def finding_result():
    return {
        "website_url": "https://example.test/",
        "metrics": {
            "title_meta_description": {
                "status": "needs_improvement",
                "pages": [
                    {
                        "page_url": "https://example.test/",
                        "status": "needs_improvement",
                        "title": {
                            "text": None,
                            "present": False,
                            "status": "needs_improvement",
                        },
                        "meta_description": {
                            "text": "Good description",
                            "present": True,
                            "status": "good",
                        },
                    }
                ],
            },
            "broken_internal_links": {
                "status": "needs_improvement",
                "broken_links": [
                    {
                        "source_url": "https://example.test/",
                        "target_url": "https://example.test/missing",
                        "status_code": 404,
                    }
                ],
                "unverified_links": [
                    {"target_url": "https://example.test/unknown"}
                ],
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
                "status": "needs_improvement",
                "pages": [
                    {
                        "page_url": "https://example.test/",
                        "image_count": 2,
                        "images_with_alt": 1,
                        "alt_text_percentage": 50,
                        "status": "needs_improvement",
                    }
                ],
            },
            "canonical_tag": {
                "status": "good",
                "pages": [
                    {
                        "page_url": "https://example.test/",
                        "canonical_count": 1,
                        "status": "good",
                    }
                ],
            },
        },
    }


class MockResponse:
    def __init__(self, status_code=200, text="{}"):
        self.status_code = status_code
        self.text = text
        self.closed = False

    def json(self):
        return {
            "candidates": [
                {"content": {"parts": [{"text": self.text}]}}
            ]
        }

    def close(self):
        self.closed = True


def test_rule_based_recommendations_only_use_actual_findings():
    result = recommendations.generate_recommendations(
        finding_result(), use_ai=False
    )

    items = result["recommendations"]
    ids = {item["id"] for item in items}

    assert ids == {"title-meta", "broken-links", "h1-heading", "image-alt-text"}
    assert all(item["evidence"] for item in items)
    assert items[0]["priority"] == "High"
    assert result["ai_status"] == "not_requested"


def test_missing_api_key_keeps_rule_based_recommendations(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    result = recommendations.generate_recommendations(finding_result())

    assert result["recommendations"]
    assert result["ai_status"] == "unavailable"
    assert "GEMINI_API_KEY" in result["ai_error"]


def test_reads_api_key_from_local_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=local-test-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    expected_actions = {
        "title-meta": "Update the page metadata.",
        "broken-links": "Repair the broken internal link.",
        "h1-heading": "Add one H1.",
        "image-alt-text": "Add useful image alt text.",
    }
    response = MockResponse(text=json.dumps(expected_actions))
    captured = {}

    def fake_post(url, **kwargs):
        captured["headers"] = kwargs["headers"]
        return response

    monkeypatch.setattr(recommendations.requests, "post", fake_post)

    result = recommendations.generate_recommendations(finding_result())

    assert result["ai_status"] == "used"
    assert captured["headers"]["x-goog-api-key"] == "local-test-key"
    assert response.closed
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_gemini_only_rewrites_actions_for_existing_recommendations(monkeypatch):
    expected_actions = {
        "title-meta": "Write an in-range title and description.",
        "broken-links": "Repair the verified broken destination.",
        "h1-heading": "Add one clear H1.",
        "image-alt-text": "Add helpful alt text to the image.",
    }
    response = MockResponse(text=json.dumps(expected_actions))
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return response

    monkeypatch.setattr(recommendations.requests, "post", fake_post)
    original = recommendations.generate_recommendations(
        finding_result(), use_ai=False
    )["recommendations"]

    result = recommendations.generate_recommendations(
        finding_result(), api_key="test-key"
    )

    assert result["ai_status"] == "used"
    assert {item["id"]: item["action"] for item in result["recommendations"]} == (
        expected_actions
    )
    assert [item["evidence"] for item in result["recommendations"]] == [
        item["evidence"] for item in original
    ]
    assert [item["issue"] for item in result["recommendations"]] == [
        item["issue"] for item in original
    ]
    assert captured["kwargs"]["headers"]["x-goog-api-key"] == "test-key"
    assert captured["kwargs"]["timeout"] == recommendations.DEFAULT_TIMEOUT
    assert response.closed


def test_invalid_gemini_response_falls_back_without_changing_findings(monkeypatch):
    response = MockResponse(text='{"invented": "New SEO issue"}')
    monkeypatch.setattr(
        recommendations.requests, "post", lambda *args, **kwargs: response
    )

    result = recommendations.generate_recommendations(
        finding_result(), api_key="test-key"
    )
    fallback = recommendations.generate_recommendations(
        finding_result(), use_ai=False
    )

    assert result["ai_status"] == "failed"
    assert "recommendation IDs" in result["ai_error"]
    assert result["recommendations"] == fallback["recommendations"]
    assert response.closed


def test_gemini_network_failure_keeps_rule_based_recommendations(monkeypatch):
    def fail_request(*args, **kwargs):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(recommendations.requests, "post", fail_request)

    result = recommendations.generate_recommendations(
        finding_result(), api_key="test-key"
    )

    assert result["ai_status"] == "failed"
    assert "request failed" in result["ai_error"].lower()
    assert len(result["recommendations"]) == 4


def test_empty_findings_do_not_call_gemini(monkeypatch):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("Gemini must not be called with no findings")

    monkeypatch.setattr(recommendations.requests, "post", unexpected_request)

    result = recommendations.generate_recommendations(
        {"metrics": {}}, api_key="test-key"
    )

    assert result["recommendations"] == []
    assert result["ai_status"] == "no_findings"
