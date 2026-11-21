from contextlib import nullcontext

from frontend import streamlit_app


class FakeStreamlit:
    def __init__(self):
        self.calls = []

    def columns(self, spec):
        self.calls.append(("columns", (spec,), {}))
        return [FakeStreamlitColumn(self) for _ in spec]

    def __getattr__(self, name):
        if name == "expander":
            return lambda *args, **kwargs: nullcontext()

        def record_call(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record_call


class FakeStreamlitColumn:
    def __init__(self, streamlit):
        self.streamlit = streamlit

    def __getattr__(self, name):
        def record_call(*args, **kwargs):
            self.streamlit.calls.append((name, args, kwargs))

        return record_call


def make_report(
    coverage_percent,
    page_error=None,
    metric_scores=None,
    crawled_pages=None,
):
    if crawled_pages is None:
        crawled_pages = []
        if page_error:
            crawled_pages.append(
                {
                    "url": "https://example.test/",
                    "final_url": "https://example.test/",
                    "status_code": 403,
                    "error": page_error,
                }
            )

    maximums = {
        "title_meta_description": 25,
        "broken_internal_links": 25,
        "h1_heading": 20,
        "image_alt_text": 15,
        "canonical_tag": 15,
    }
    if metric_scores is None:
        available = coverage_percent > 0
        metric_scores = {}
        for key, maximum in maximums.items():
            metric_scores[key] = {
                "status": "good" if available else "unavailable",
                "earned_points": maximum if available else 0,
                "weight": maximum,
                "available_points": maximum if available else 0,
            }
            if key == "broken_internal_links":
                metric_scores[key].update(
                    {"confirmed_broken_links": 0, "unverified_links": 0}
                )

    return {
        "score": {
            "score": "unavailable" if coverage_percent == 0 else "100/100",
            "coverage_percent": coverage_percent,
            "metrics": metric_scores,
        },
        "crawled_pages": crawled_pages,
        "metrics": {
            "title_meta_description": {"pages": []},
            "broken_internal_links": {
                "status": "good" if coverage_percent > 0 else "unavailable",
                "checked_link_count": 1 if coverage_percent > 0 else 0,
                "checked_link_occurrence_count": 1 if coverage_percent > 0 else 0,
                "broken_links": [],
                "unverified_links": [],
            },
            "h1_heading": {"pages": []},
            "image_alt_text": {"pages": []},
            "canonical_tag": {"pages": []},
        },
        "ai_status": "not_requested",
        "recommendations": [],
        "errors": [],
    }


def test_page_level_http_error_is_shown_prominently(monkeypatch):
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(
        make_report(0, page_error="HTTP 403 response.")
    )

    error_messages = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "error"
    ]
    subheaders = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "subheader"
    ]
    assert "Pages with crawl errors" in subheaders
    assert any(
        "https://example.test/" in message
        and "HTTP 403" in message
        and "HTTP 403 response." in message
        for message in error_messages
    )


def test_zero_coverage_without_recommendations_shows_audit_failure(
    monkeypatch,
):
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(make_report(0))

    warning_messages = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "warning"
    ]
    success_messages = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "success"
    ]
    assert (
        "Unable to generate recommendations because the website could not be "
        "audited successfully. Please try another website or check whether "
        "automated access is allowed."
    ) in warning_messages
    assert "No actionable issues were found in the available audit results." not in (
        success_messages
    )


def test_successful_audit_keeps_existing_no_actionable_issues_message(
    monkeypatch,
):
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(make_report(100))

    success_messages = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "success"
    ]
    assert (
        "No actionable issues were found in the available audit results."
        in success_messages
    )


def test_score_breakdown_displays_all_metric_scores_and_unavailable_metrics(
    monkeypatch,
):
    metric_scores = {
        "title_meta_description": {
            "status": "needs_improvement",
            "earned_points": 15,
            "weight": 25,
            "available_points": 25,
        },
        "broken_internal_links": {
            "status": "needs_improvement",
            "earned_points": 20,
            "weight": 25,
            "available_points": 25,
        },
        "h1_heading": {
            "status": "unavailable",
            "earned_points": 0,
            "weight": 20,
            "available_points": 0,
        },
        "image_alt_text": {
            "status": "needs_improvement",
            "earned_points": 12,
            "weight": 15,
            "available_points": 15,
        },
        "canonical_tag": {
            "status": "needs_improvement",
            "earned_points": 0,
            "weight": 15,
            "available_points": 15,
        },
    }
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(
        make_report(80, metric_scores=metric_scores)
    )

    rendered_text = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name in {"markdown", "write", "subheader"} and args
    ]
    progress_values = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "progress"
    ]

    assert "SEO Score Breakdown" in rendered_text
    assert "**Earned / Maximum**" in rendered_text
    assert "Title and Meta Description" in rendered_text
    assert "Broken Internal Links" in rendered_text
    assert "H1 Headings" in rendered_text
    assert "Image Alt Text" in rendered_text
    assert "Canonical Tags" in rendered_text
    assert "15 / 25 points" in rendered_text
    assert "20 / 25 points" in rendered_text
    assert "Unavailable / 20 points" in rendered_text
    assert "12 / 15 points" in rendered_text
    assert "0 / 15 points" in rendered_text
    assert progress_values == [0.6, 0.8, 0.8, 0.0]


def test_full_broken_link_score_is_limited_to_verified_checks(monkeypatch):
    report = make_report(100)
    report["metrics"]["broken_internal_links"]["unverified_links"] = [
        {
            "source_url": "https://example.test/",
            "target_url": "https://example.test/slow",
            "reason": "Request timed out.",
        }
    ]
    report["score"]["metrics"]["broken_internal_links"]["unverified_links"] = 1
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(report)

    success_messages = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "success"
    ]
    captions = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "caption"
    ]
    assert "No confirmed broken links among verified checks." in success_messages
    assert any(
        "score applies only to verified link checks" in caption
        and "not counted as confirmed broken links" in caption
        for caption in captions
    )


def test_unverified_link_occurrences_and_unique_urls_are_separate(monkeypatch):
    report = make_report(80)
    report["score"]["metrics"]["h1_heading"].update(
        {"status": "unavailable", "earned_points": 0, "available_points": 0}
    )
    report["metrics"]["broken_internal_links"]["unverified_links"] = [
        {
            "source_url": "https://example.test/one",
            "target_url": "https://example.test/slow",
            "reason": "Request timed out.",
        },
        {
            "source_url": "https://example.test/two",
            "target_url": "https://example.test/slow",
            "reason": "Request timed out.",
        },
        {
            "source_url": "https://example.test/one",
            "target_url": "https://example.test/unresolved",
            "reason": "Could not safely resolve hostname.",
        },
    ]
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(report)

    writes = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "write"
    ]
    warnings = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "warning"
    ]
    errors = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "error"
    ]
    assert "Unverified link occurrences: 3" in writes
    assert "Unique unverified URLs: 2" in writes
    assert len(warnings) == 3
    assert all(message.startswith("Unverified link:") for message in warnings)
    assert errors == []


def test_missing_unverified_target_urls_do_not_create_unique_counts(monkeypatch):
    report = make_report(100)
    report["metrics"]["broken_internal_links"]["unverified_links"] = [
        {"source_url": "https://example.test/", "reason": "Request timed out."}
    ]
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(report)

    writes = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "write"
    ]
    assert "Unverified link occurrences: 1" in writes
    assert not any(message.startswith("Unique unverified URLs:") for message in writes)


def test_confirmed_broken_links_are_red_and_labeled(monkeypatch):
    report = make_report(100)
    report["metrics"]["broken_internal_links"].update(
        {
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
        }
    )
    report["score"]["metrics"]["broken_internal_links"].update(
        {
            "status": "needs_improvement",
            "earned_points": 0,
            "confirmed_broken_links": 1,
        }
    )
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(report)

    error_messages = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "error"
    ]
    assert any(
        message.startswith("Confirmed broken link:")
        and "HTTP 404" in message
        for message in error_messages
    )


def test_metric_weight_coverage_explains_page_counts(monkeypatch):
    crawled_pages = [
        {
            "url": "https://example.test/page-{}".format(index),
            "status_code": 200,
            "error": None,
        }
        for index in range(7)
    ] + [
        {
            "url": "https://example.test/page-{}".format(index),
            "status_code": 403,
            "error": "HTTP 403 response.",
        }
        for index in range(7, 10)
    ]
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(
        make_report(80, crawled_pages=crawled_pages)
    )

    captions = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "caption"
    ]
    assert any(
        message.startswith("Metric-weight coverage: 80%")
        for message in captions
    )
    assert (
        "Metric-weight coverage indicates how much of the total SEO metric "
        "scoring weight was available. It does not represent the percentage "
        "of pages successfully crawled."
    ) in captions
    assert "7 of 10 pages successfully crawled; 3 failed." in captions


def test_page_count_is_not_reported_when_status_information_is_missing(
    monkeypatch,
):
    fake_streamlit = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_streamlit)

    streamlit_app._show_report(
        make_report(
            80,
            crawled_pages=[{"url": "https://example.test/"}],
        )
    )

    captions = [
        args[0]
        for name, args, _ in fake_streamlit.calls
        if name == "caption"
    ]
    assert not any(
        message.startswith(("1 of 1 pages successfully", "0 of 1 page records"))
        for message in captions
    )
