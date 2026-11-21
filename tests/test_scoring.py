import pytest

import app.analyzer as analyzer
from app.crawler import CrawlResult, CrawledPage
from app.scoring import calculate_score


def page_result(status):
    return {"status": status}


def make_analyzer_result(**metric_results):
    return {"metrics": metric_results}


def test_full_score_when_every_metric_passes():
    result = make_analyzer_result(
        title_meta_description={"pages": [page_result("good")]},
        broken_internal_links={
            "status": "good",
            "checked_link_count": 2,
            "checked_link_occurrence_count": 2,
            "broken_links": [],
            "unverified_links": [],
        },
        h1_heading={"pages": [page_result("good")]},
        image_alt_text={"pages": [page_result("good")]},
        canonical_tag={"pages": [page_result("good")]},
    )

    score = calculate_score(result)

    assert score["score"] == "100/100"
    assert score["earned_points"] == 100
    assert score["available_points"] == 100
    assert score["coverage_percent"] == 100


def test_partial_score_uses_available_pages_and_ignores_unavailable_metrics():
    result = make_analyzer_result(
        title_meta_description={
            "pages": [
                page_result("good"),
                page_result("needs_improvement"),
                page_result("unavailable"),
            ]
        },
        broken_internal_links={
            "status": "partially_available",
            "checked_link_count": 4,
            "checked_link_occurrence_count": 5,
            "broken_links": [
                {"source_url": "/one", "target_url": "/broken"},
                {"source_url": "/two", "target_url": "/broken"},
            ],
            "unverified_links": [{"target_url": "/unknown"}],
        },
        h1_heading={
            "pages": [
                page_result("good"),
                page_result("needs_improvement"),
            ]
        },
        image_alt_text={"pages": [page_result("good")]},
        canonical_tag={"pages": [page_result("unavailable")]},
    )

    score = calculate_score(result)

    assert score["metrics"]["title_meta_description"]["earned_points"] == 12.5
    assert score["metrics"]["title_meta_description"]["available_pages"] == 2
    assert score["metrics"]["broken_internal_links"]["earned_points"] == 15
    assert score["metrics"]["broken_internal_links"]["confirmed_broken_links"] == 2
    assert score["metrics"]["h1_heading"]["earned_points"] == 10
    assert score["metrics"]["canonical_tag"]["available_points"] == 0
    assert score["score"] == "52.5/85"
    assert score["earned_points"] == 52.5
    assert score["available_points"] == 85
    assert score["coverage_percent"] == 85


def test_unavailable_metric_is_excluded_not_treated_as_pass_or_failure():
    result = make_analyzer_result(
        title_meta_description={"pages": [page_result("unavailable")]},
        broken_internal_links={
            "status": "unavailable",
            "checked_link_count": 0,
            "checked_link_occurrence_count": 0,
            "broken_links": [],
            "unverified_links": [{"reason": "Request timed out"}],
        },
        h1_heading={"pages": [page_result("good")]},
        image_alt_text={"pages": [page_result("unavailable")]},
        canonical_tag={"pages": [page_result("unavailable")]},
    )

    score = calculate_score(result)

    assert score["score"] == "20/20"
    assert score["metrics"]["broken_internal_links"]["earned_points"] == 0
    assert score["metrics"]["broken_internal_links"]["available_points"] == 0
    assert score["metrics"]["h1_heading"]["earned_points"] == 20
    assert score["coverage_percent"] == 20


def test_zero_available_metrics_returns_unavailable_score():
    result = make_analyzer_result(
        title_meta_description={"pages": [page_result("unavailable")]},
        broken_internal_links={
            "status": "unavailable",
            "checked_link_count": 0,
            "checked_link_occurrence_count": 0,
            "broken_links": [],
            "unverified_links": [{"reason": "HTTP 429"}],
        },
        h1_heading={"pages": []},
        image_alt_text={"pages": [page_result("unavailable")]},
        canonical_tag={"pages": [page_result("unavailable")]},
    )

    score = calculate_score(result)

    assert score["score"] == "unavailable"
    assert score["earned_points"] == 0
    assert score["available_points"] == 0
    assert score["coverage_percent"] == 0


@pytest.mark.parametrize(
    ("checked_occurrences", "broken_links", "expected_points"),
    [
        (0, [{"source_url": "/source", "target_url": "/broken"}], 0),
        (
            2,
            [
                {"source_url": "/source", "target_url": "/one"},
                {"source_url": "/source", "target_url": "/two"},
            ],
            0,
        ),
        (2, [{"source_url": "/source", "target_url": "/one"}], 12.5),
        (2, [], 25),
    ],
)
def test_broken_link_scoring_edge_cases(
    checked_occurrences, broken_links, expected_points
):
    result = make_analyzer_result(
        broken_internal_links={
            "status": "good" if checked_occurrences else "unavailable",
            "checked_link_count": checked_occurrences,
            "checked_link_occurrence_count": checked_occurrences,
            "broken_links": broken_links,
            "unverified_links": [{"reason": "Request timed out"}],
        }
    )

    metric_score = calculate_score(result)["metrics"]["broken_internal_links"]

    assert metric_score["earned_points"] == expected_points
    assert metric_score["confirmed_broken_links"] == min(
        len(broken_links), checked_occurrences
    )
    assert metric_score["unverified_links"] == 1


def test_unknown_page_status_is_not_accidentally_scored_as_a_pass():
    result = make_analyzer_result(
        title_meta_description={"pages": [page_result("unknown")]},
    )

    score = calculate_score(result)

    assert score["score"] == "unavailable"
    assert score["metrics"]["title_meta_description"]["available_points"] == 0


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def close(self):
        pass


class MockSession:
    def get(self, url, **kwargs):
        if url.endswith("/broken"):
            return MockResponse(404)
        return MockResponse(200)

    def close(self):
        pass


class AllowAllRobots:
    def can_fetch(self, user_agent, url):
        return True


def test_same_broken_url_on_three_pages_counts_all_occurrences(monkeypatch):
    monkeypatch.setattr(analyzer.requests, "Session", MockSession)
    monkeypatch.setattr(analyzer, "_check_public_host", lambda url: None)
    monkeypatch.setattr(
        analyzer,
        "_load_robots_rules",
        lambda *args: (AllowAllRobots(), None),
    )
    pages = [
        CrawledPage(
            url="https://example.test/one",
            final_url="https://example.test/one",
            status_code=200,
            html='<a href="/broken">Broken</a><a href="/working">Working</a>',
        ),
        CrawledPage(
            url="https://example.test/two",
            final_url="https://example.test/two",
            status_code=200,
            html='<a href="/broken">Broken</a>',
        ),
        CrawledPage(
            url="https://example.test/three",
            final_url="https://example.test/three",
            status_code=200,
            html='<a href="/broken">Broken</a>',
        ),
    ]

    analyzer_result = analyzer.analyze_crawl(
        CrawlResult(start_url="https://example.test/", pages=pages)
    )
    link_metric = analyzer_result["metrics"]["broken_internal_links"]
    score = calculate_score(analyzer_result)
    scored_metric = score["metrics"]["broken_internal_links"]

    assert link_metric["checked_link_count"] == 2
    assert link_metric["checked_link_occurrence_count"] == 4
    assert [link["source_url"] for link in link_metric["broken_links"]] == [
        "https://example.test/one",
        "https://example.test/two",
        "https://example.test/three",
    ]
    assert scored_metric["verified_links"] == 2
    assert scored_metric["verified_link_occurrences"] == 4
    assert scored_metric["confirmed_broken_links"] == 3
    assert scored_metric["earned_points"] == 6.25