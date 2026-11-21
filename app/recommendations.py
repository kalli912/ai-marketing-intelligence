"""Create findings-based recommendations with an optional Gemini rewrite."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv


GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT = 15
VALID_PRIORITIES = {"High", "Medium", "Low"}


def _add_recommendation(
    recommendations: List[Dict[str, Any]],
    recommendation_id: str,
    priority: str,
    issue: str,
    action: str,
    evidence: List[str],
) -> None:
    """Append one recommendation while keeping finding evidence attached."""
    recommendations.append(
        {
            "id": recommendation_id,
            "priority": priority,
            "issue": issue,
            "action": action,
            "evidence": evidence,
        }
    )


def _make_rule_based_recommendations(
    analyzer_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Create actions only for findings present in analyzer results."""
    metrics = analyzer_result.get("metrics", {})
    if not isinstance(metrics, dict):
        return []

    recommendations: List[Dict[str, Any]] = []
    title_metric = metrics.get("title_meta_description", {})
    title_issues = []
    missing_title_value = False
    title_pages = []
    if isinstance(title_metric, dict):
        for page in title_metric.get("pages", []):
            if not isinstance(page, dict) or page.get("status") == "unavailable":
                continue
            page_url = page.get("page_url")
            for field, label in (
                ("title", "title"),
                ("meta_description", "meta description"),
            ):
                value = page.get(field)
                if isinstance(value, dict) and value.get("status") == "needs_improvement":
                    title_issues.append(
                        "{} on {}".format(label, page_url or "an audited page")
                    )
                    if not value.get("present", True):
                        missing_title_value = True
                    if page_url and page_url not in title_pages:
                        title_pages.append(page_url)
    if title_issues:
        _add_recommendation(
            recommendations,
            "title-meta",
            "High" if missing_title_value else "Medium",
            "Some page titles or meta descriptions are missing or outside the recommended length.",
            "Update the listed titles to 30–60 characters and meta descriptions to 70–160 characters.",
            title_issues,
        )

    link_metric = metrics.get("broken_internal_links", {})
    if isinstance(link_metric, dict):
        broken_links = link_metric.get("broken_links", [])
        if isinstance(broken_links, list) and broken_links:
            evidence = []
            for link in broken_links:
                if not isinstance(link, dict):
                    continue
                source = link.get("source_url", "unknown source page")
                target = link.get("target_url", "unknown target")
                status_code = link.get("status_code")
                detail = "{} links to {} (HTTP {})".format(
                    source, target, status_code
                )
                if detail not in evidence:
                    evidence.append(detail)
            if evidence:
                _add_recommendation(
                    recommendations,
                    "broken-links",
                    "High",
                    "Verified internal links returned HTTP 4xx or 5xx responses.",
                    "Repair each destination or update/remove the internal link on its source page.",
                    evidence,
                )

    h1_metric = metrics.get("h1_heading", {})
    h1_evidence = []
    if isinstance(h1_metric, dict):
        for page in h1_metric.get("pages", []):
            if (
                isinstance(page, dict)
                and page.get("status") == "needs_improvement"
            ):
                h1_evidence.append(
                    "{} has {} H1 headings".format(
                        page.get("page_url", "An audited page"),
                        page.get("h1_count", "an unexpected number of"),
                    )
                )
    if h1_evidence:
        _add_recommendation(
            recommendations,
            "h1-heading",
            "Medium",
            "Some audited pages do not have exactly one H1 heading.",
            "Review the listed pages and use one clear H1 heading per page. This is the project's audit rule, not a Google ranking guarantee.",
            h1_evidence,
        )

    image_metric = metrics.get("image_alt_text", {})
    image_evidence = []
    if isinstance(image_metric, dict):
        for page in image_metric.get("pages", []):
            if (
                isinstance(page, dict)
                and page.get("status") == "needs_improvement"
            ):
                image_evidence.append(
                    "{} has alt text on {}% of {} images".format(
                        page.get("page_url", "An audited page"),
                        page.get("alt_text_percentage"),
                        page.get("image_count"),
                    )
                )
    if image_evidence:
        _add_recommendation(
            recommendations,
            "image-alt-text",
            "Medium",
            "Some audited pages have non-empty alt text on less than 90% of images.",
            "Add concise, descriptive alt text to the listed images where the image conveys useful information.",
            image_evidence,
        )

    canonical_metric = metrics.get("canonical_tag", {})
    canonical_evidence = []
    if isinstance(canonical_metric, dict):
        for page in canonical_metric.get("pages", []):
            if (
                isinstance(page, dict)
                and page.get("status") == "needs_improvement"
            ):
                canonical_evidence.append(
                    "{} has {} canonical tags".format(
                        page.get("page_url", "An audited page"),
                        page.get("canonical_count", "an unexpected number of"),
                    )
                )
    if canonical_evidence:
        _add_recommendation(
            recommendations,
            "canonical-tag",
            "Medium",
            "Some audited pages are missing a single valid canonical URL.",
            "Add exactly one absolute HTTP or HTTPS canonical URL to each listed page.",
            canonical_evidence,
        )

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    recommendations.sort(key=lambda item: priority_order[item["priority"]])
    return recommendations


def _get_ai_actions(
    recommendations: List[Dict[str, Any]], api_key: str, timeout: int
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """Ask Gemini to rewrite actions without altering evidence or priorities."""
    if not recommendations:
        return {}, None

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    url = GEMINI_API_URL.format(model=model)
    prompt = (
        "Rewrite the action text for the supplied SEO recommendations so it "
        "is concise, practical, and understandable to a marketing manager. "
        "Use only facts and suggested actions already present in the input. "
        "Do not add issues, findings, measurements, URLs, or recommendations. "
        "Return only a JSON object mapping each existing id to its rewritten "
        "action string. Include every id exactly once.\n\n"
        + json.dumps(recommendations, ensure_ascii=True)
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": api_key},
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as error:
        return None, "Gemini request failed: {}".format(error)

    try:
        if not 200 <= response.status_code < 300:
            return None, "Gemini returned HTTP {}.".format(response.status_code)

        try:
            response_data = response.json()
            text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            actions = json.loads(text)
        except (ValueError, KeyError, IndexError, TypeError) as error:
            return None, (
                "Gemini returned an unreadable recommendation response: {}".format(
                    error
                )
            )
    finally:
        response.close()

    if not isinstance(actions, dict):
        return None, "Gemini response must be a JSON object of recommendation actions."

    expected_ids = {item["id"] for item in recommendations}
    if set(actions) != expected_ids or not all(
        isinstance(action, str) and action.strip() for action in actions.values()
    ):
        return None, "Gemini response did not match the existing recommendation IDs."

    return {key: value.strip() for key, value in actions.items()}, None


def generate_recommendations(
    analyzer_result: Dict[str, Any],
    use_ai: bool = True,
    api_key: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Return evidence-based recommendations and optional AI-written actions.

    Without a Gemini API key, or if the optional service fails, the useful
    rule-based recommendations are returned and the AI status explains why.
    """
    recommendations = _make_rule_based_recommendations(analyzer_result)
    result = {
        "recommendations": recommendations,
        "ai_status": "not_requested",
        "ai_error": None,
    }
    if not use_ai:
        return result

    key = api_key
    if not key:
        # Load the project-root .env without overriding variables already set.
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        key = os.getenv("GEMINI_API_KEY")
    if not key:
        result["ai_status"] = "unavailable"
        result["ai_error"] = (
            "No Gemini API key was provided. Set the GEMINI_API_KEY environment variable to enable AI wording."
        )
        return result

    actions, error = _get_ai_actions(recommendations, key, timeout)
    if error:
        result["ai_status"] = "failed"
        result["ai_error"] = error
        return result

    for recommendation in recommendations:
        recommendation["action"] = actions[recommendation["id"]]
    result["ai_status"] = "used" if recommendations else "no_findings"
    return result