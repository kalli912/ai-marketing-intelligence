"""Calculate a transparent, deterministic score from analyzer results."""

from copy import deepcopy
from typing import Any, Dict


TOTAL_WEIGHT = 100.0

SCORING_RULES = {
    "title_meta_description": {
        "label": "Title and Meta Description",
        "weight": 25.0,
        "method": (
            "Divide the weight equally across pages with available results. "
            "A page passes only when both its title and meta description pass."
        ),
    },
    "broken_internal_links": {
        "label": "Broken Internal Links",
        "weight": 25.0,
        "method": (
            "Award full points when no confirmed broken link occurrences are "
            "found. Otherwise, award weight × (verified occurrences - broken "
            "occurrences) / verified occurrences. Unverified occurrences do "
            "not count."
        ),
    },
    "h1_heading": {
        "label": "H1 Heading",
        "weight": 20.0,
        "method": (
            "Divide the weight equally across available pages. A page passes "
            "when it has exactly one H1."
        ),
    },
    "image_alt_text": {
        "label": "Image Alt Text",
        "weight": 15.0,
        "method": (
            "Divide the weight equally across pages with available image "
            "results. A page passes when at least 90% of its images have "
            "non-empty alt text. Pages with no images are unavailable."
        ),
    },
    "canonical_tag": {
        "label": "Canonical Tag",
        "weight": 15.0,
        "method": (
            "Divide the weight equally across available pages. A page passes "
            "when it has exactly one valid HTTP or HTTPS canonical URL."
        ),
    },
}


def _rounded_points(value: float) -> float:
    """Round points consistently and avoid displaying values such as 25.0."""
    rounded = round(value, 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _page_metric_score(
    metric_result: Any, weight: float
) -> Dict[str, Any]:
    """Score one page-based metric, excluding unavailable pages."""
    pages = metric_result.get("pages", []) if isinstance(metric_result, dict) else []
    if not isinstance(pages, list):
        pages = []

    available_pages = [
        page
        for page in pages
        if isinstance(page, dict)
        and page.get("status") in {"good", "needs_improvement"}
    ]
    passed_pages = sum(
        1 for page in available_pages if page.get("status") == "good"
    )

    if not available_pages:
        return {
            "status": "unavailable",
            "weight": weight,
            "earned_points": 0,
            "available_points": 0,
            "available_pages": 0,
            "passed_pages": 0,
            "unavailable_pages": len(pages),
            "formula": "No pages had an available result.",
        }

    earned = weight * passed_pages / len(available_pages)
    unavailable_pages = len(pages) - len(available_pages)
    if passed_pages < len(available_pages):
        status = "needs_improvement"
    elif unavailable_pages:
        status = "partially_available"
    else:
        status = "good"

    return {
        "status": status,
        "weight": weight,
        "earned_points": _rounded_points(earned),
        "available_points": weight,
        "available_pages": len(available_pages),
        "passed_pages": passed_pages,
        "unavailable_pages": unavailable_pages,
        "formula": (
            "{} × {} passing pages / {} available pages".format(
                weight, passed_pages, len(available_pages)
            )
        ),
    }


def _broken_occurrence_count(broken_links: Any) -> int:
    """Count confirmed broken occurrences while requiring source evidence."""
    if not isinstance(broken_links, list):
        return 0

    occurrence_count = 0
    for link in broken_links:
        if (
            isinstance(link, dict)
            and isinstance(link.get("target_url"), str)
            and link["target_url"]
            and isinstance(link.get("source_url"), str)
            and link["source_url"]
        ):
            occurrence_count += 1
    return occurrence_count


def _broken_link_score(metric_result: Any, weight: float) -> Dict[str, Any]:
    """Score only links with a confirmed HTTP response."""
    if not isinstance(metric_result, dict):
        metric_result = {}

    try:
        checked_occurrences = max(
            0, int(metric_result.get("checked_link_occurrence_count", 0))
        )
    except (TypeError, ValueError):
        checked_occurrences = 0

    broken_count = _broken_occurrence_count(metric_result.get("broken_links", []))
    unverified_links = metric_result.get("unverified_links", [])
    unverified_count = (
        len(unverified_links) if isinstance(unverified_links, list) else 0
    )

    if checked_occurrences == 0 or metric_result.get("status") == "unavailable":
        return {
            "status": "unavailable",
            "weight": weight,
            "earned_points": 0,
            "available_points": 0,
            "verified_links": 0,
            "verified_link_occurrences": checked_occurrences,
            "confirmed_broken_links": 0,
            "unverified_links": unverified_count,
            "formula": "No verified link occurrences were available to score.",
        }

    # A defensive cap prevents malformed analyzer data from earning negative points.
    broken_count = min(broken_count, checked_occurrences)
    earned = weight * (checked_occurrences - broken_count) / checked_occurrences
    if broken_count:
        status = "needs_improvement"
    elif unverified_count:
        status = "partially_available"
    else:
        status = "good"

    return {
        "status": status,
        "weight": weight,
        "earned_points": _rounded_points(earned),
        "available_points": weight,
        "verified_links": metric_result.get("checked_link_count", 0),
        "verified_link_occurrences": checked_occurrences,
        "confirmed_broken_links": broken_count,
        "unverified_links": unverified_count,
        "formula": (
            "{} × ({} verified occurrences - {} broken occurrences) / {} "
            "verified occurrences".format(
                weight, checked_occurrences, broken_count, checked_occurrences
            )
        ),
    }


def _format_score_points(value: float) -> str:
    rounded = _rounded_points(value)
    return str(rounded)


def calculate_score(analyzer_result: Dict[str, Any]) -> Dict[str, Any]:
    """Return earned points, available points, coverage, and scoring details."""
    source_metrics = analyzer_result.get("metrics", {})
    if not isinstance(source_metrics, dict):
        source_metrics = {}

    metric_scores: Dict[str, Dict[str, Any]] = {}
    for metric_name, rule in SCORING_RULES.items():
        metric_result = source_metrics.get(metric_name, {})
        if metric_name == "broken_internal_links":
            score = _broken_link_score(metric_result, rule["weight"])
        else:
            score = _page_metric_score(metric_result, rule["weight"])
        score["label"] = rule["label"]
        metric_scores[metric_name] = score

    earned_points = _rounded_points(
        sum(score["earned_points"] for score in metric_scores.values())
    )
    available_points = _rounded_points(
        sum(score["available_points"] for score in metric_scores.values())
    )
    coverage = _rounded_points(available_points / TOTAL_WEIGHT * 100)

    if available_points == 0:
        score_display = "unavailable"
    else:
        score_display = "{}/{}".format(
            _format_score_points(earned_points),
            _format_score_points(available_points),
        )

    return {
        "score": score_display,
        "earned_points": earned_points,
        "available_points": available_points,
        "coverage_percent": coverage,
        "metrics": metric_scores,
        "scoring_rules": deepcopy(SCORING_RULES),
    }