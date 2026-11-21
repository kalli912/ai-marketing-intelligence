import threading

import pytest
import requests

import app.analyzer as analyzer
from app.crawler import CrawlResult, CrawledPage


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def close(self):
        pass


class MockSession:
    def __init__(self, response_for_url):
        self.response_for_url = response_for_url
        self.calls = []
        self.thread_id = threading.get_ident()
        self.calls_lock = threading.Lock()

    def get(self, url, **kwargs):
        with self.calls_lock:
            self.calls.append((url, kwargs))
        return self.response_for_url(url)

    def close(self):
        pass


class AllowAllRobots:
    def can_fetch(self, user_agent, url):
        return True


def make_page(html, url="https://example.test/"):
    return CrawledPage(
        url=url,
        final_url=url,
        status_code=200,
        html=html,
    )


def make_crawl(*pages):
    return CrawlResult(start_url="https://example.test/", pages=list(pages))


def mock_link_checks(monkeypatch, response_for_url):
    sessions = []
    sessions_lock = threading.Lock()

    def create_session():
        session = MockSession(response_for_url)
        with sessions_lock:
            sessions.append(session)
        return session

    monkeypatch.setattr(analyzer.requests, "Session", create_session)
    monkeypatch.setattr(analyzer, "_check_public_host", lambda url: None)
    monkeypatch.setattr(
        analyzer,
        "_load_robots_rules",
        lambda *args: (AllowAllRobots(), None),
    )
    return sessions


def test_extracts_title_and_meta_description_with_character_counts():
    title = "A Carefully Crafted Organic Skin Care Title"
    description = (
        "Explore gentle daily skin care made with thoughtfully selected "
        "ingredients for the whole family."
    )
    html = (
        "<html><head><title>{}</title>"
        '<meta name="description" content="{}"></head></html>'
    ).format(title, description)

    result = analyzer.analyze_crawl(make_crawl(make_page(html)))
    metric = result["metrics"]["title_meta_description"]["pages"][0]

    assert metric["title"]["text"] == title
    assert metric["title"]["character_count"] == len(title)
    assert metric["title"]["status"] == "good"
    assert metric["meta_description"]["text"] == description
    assert metric["meta_description"]["character_count"] == len(description)
    assert metric["meta_description"]["status"] == "good"


def test_reports_missing_and_out_of_range_metadata():
    html = "<html><head><title>Short</title></head></html>"

    result = analyzer.analyze_crawl(make_crawl(make_page(html)))
    metric = result["metrics"]["title_meta_description"]["pages"][0]

    assert metric["title"]["present"] is True
    assert metric["title"]["status"] == "needs_improvement"
    assert metric["meta_description"]["text"] is None
    assert metric["meta_description"]["present"] is False
    assert metric["meta_description"]["status"] == "needs_improvement"


def test_counts_h1_headings_and_flags_zero_or_multiple():
    no_h1 = make_page("<html><body><h2>Other heading</h2></body></html>")
    two_h1 = make_page("<html><body><h1>One</h1><h1>Two</h1></body></html>")

    result = analyzer.analyze_crawl(make_crawl(no_h1, two_h1))
    pages = result["metrics"]["h1_heading"]["pages"]

    assert [page["h1_count"] for page in pages] == [0, 2]
    assert all(page["status"] == "needs_improvement" for page in pages)


def test_calculates_image_alt_percentage():
    html = (
        '<img src="one.jpg" alt="First">'
        '<img src="two.jpg" alt="  ">'
        '<img src="three.jpg">'
    )

    result = analyzer.analyze_crawl(make_crawl(make_page(html)))
    metric = result["metrics"]["image_alt_text"]["pages"][0]

    assert metric["image_count"] == 3
    assert metric["images_with_alt"] == 1
    assert metric["alt_text_percentage"] == 33.33
    assert metric["status"] == "needs_improvement"


def test_zero_images_is_unavailable_without_division_by_zero():
    result = analyzer.analyze_crawl(make_crawl(make_page("<html></html>")))
    metric = result["metrics"]["image_alt_text"]

    assert metric["pages"][0]["image_count"] == 0
    assert metric["pages"][0]["alt_text_percentage"] is None
    assert metric["pages"][0]["status"] == "unavailable"
    assert metric["status"] == "unavailable"


def test_canonical_tag_must_be_one_absolute_http_url():
    page = make_page(
        '<link rel="canonical" href="https://example.test/canonical">'
    )

    result = analyzer.analyze_crawl(make_crawl(page))
    metric = result["metrics"]["canonical_tag"]["pages"][0]

    assert metric["canonical_count"] == 1
    assert metric["canonical_urls"] == [
        {"url": "https://example.test/canonical", "valid": True}
    ]
    assert metric["status"] == "good"


def test_reports_missing_multiple_and_invalid_canonical_tags():
    missing = make_page("<html></html>")
    multiple = make_page(
        '<link rel="canonical" href="/relative">'
        '<link rel="canonical" href="https://example.test/other">'
    )

    result = analyzer.analyze_crawl(make_crawl(missing, multiple))
    pages = result["metrics"]["canonical_tag"]["pages"]

    assert pages[0]["canonical_count"] == 0
    assert pages[0]["status"] == "needs_improvement"
    assert pages[1]["canonical_count"] == 2
    assert pages[1]["canonical_urls"][0]["valid"] is False
    assert pages[1]["status"] == "needs_improvement"


@pytest.mark.parametrize("status_code", [404, 500])
def test_reports_broken_internal_link_and_source_but_skips_external(
    monkeypatch, status_code
):
    html = (
        '<a href="/missing#section">Broken link</a>'
        '<a href="https://outside.test/page">External link</a>'
    )
    sessions = mock_link_checks(
        monkeypatch, lambda url: MockResponse(status_code)
    )

    result = analyzer.analyze_crawl(
        make_crawl(make_page(html, "https://example.test/source"))
    )
    metric = result["metrics"]["broken_internal_links"]

    assert metric["status"] == "needs_improvement"
    assert metric["checked_link_count"] == 1
    assert metric["broken_links"] == [
        {
            "source_url": "https://example.test/source",
            "target_url": "https://example.test/missing",
            "status_code": status_code,
        }
    ]
    assert all(
        "outside.test" not in url
        for session in sessions
        for url, _ in session.calls
    )


def test_timeout_and_rate_limit_are_unverified_not_broken(monkeypatch):
    html = '<a href="/timeout">Timeout</a><a href="/limited">Rate limited</a>'

    def response_for_url(url):
        if url.endswith("/timeout"):
            raise requests.Timeout("simulated timeout")
        return MockResponse(429)

    mock_link_checks(monkeypatch, response_for_url)

    result = analyzer.analyze_crawl(make_crawl(make_page(html)))
    metric = result["metrics"]["broken_internal_links"]

    assert metric["status"] == "unavailable"
    assert metric["checked_link_count"] == 0
    assert metric["broken_links"] == []
    assert len(metric["unverified_links"]) == 2
    assert "timed out" in metric["unverified_links"][0]["reason"]
    assert "429" in metric["unverified_links"][1]["reason"]


def test_internal_link_checking_is_concurrent_and_uses_worker_sessions(
    monkeypatch, caplog
):
    active_requests = 0
    peak_active_requests = 0
    barrier_participants = 0
    request_lock = threading.Lock()
    request_barrier = threading.Barrier(analyzer.MAX_LINK_CHECK_WORKERS)

    def response_for_url(url):
        nonlocal active_requests, peak_active_requests, barrier_participants
        with request_lock:
            active_requests += 1
            peak_active_requests = max(peak_active_requests, active_requests)
            wait_for_barrier = (
                barrier_participants < analyzer.MAX_LINK_CHECK_WORKERS
            )
            if wait_for_barrier:
                barrier_participants += 1
        try:
            if wait_for_barrier:
                request_barrier.wait(timeout=5)
            return MockResponse(200)
        finally:
            with request_lock:
                active_requests -= 1

    links = "".join(
        '<a href="/page-{}">Page</a>'.format(number)
        for number in range(12)
    )
    sessions = mock_link_checks(monkeypatch, response_for_url)
    main_thread_id = threading.get_ident()

    with caplog.at_level("INFO", logger="app.analyzer"):
        result = analyzer.analyze_crawl(make_crawl(make_page(links)))

    metric = result["metrics"]["broken_internal_links"]
    link_calls = [
        (url, kwargs)
        for session in sessions
        for url, kwargs in session.calls
    ]
    worker_sessions = [
        session for session in sessions if session.thread_id != main_thread_id
    ]

    assert peak_active_requests == analyzer.MAX_LINK_CHECK_WORKERS
    assert peak_active_requests <= 5
    assert len(worker_sessions) == analyzer.MAX_LINK_CHECK_WORKERS
    assert len({session.thread_id for session in worker_sessions}) == len(
        worker_sessions
    )
    assert len(link_calls) == 12
    assert metric["checked_link_count"] == 12
    assert metric["checked_link_occurrence_count"] == 12
    assert all(
        kwargs["timeout"] == analyzer.DEFAULT_TIMEOUT
        and kwargs["allow_redirects"] is False
        and kwargs["stream"] is True
        for _, kwargs in link_calls
    )
    assert "unique_links=12 request_attempts=12" in caplog.text
    assert "example.test" not in caplog.text


def test_link_classification_and_duplicate_occurrences_are_preserved(monkeypatch):
    first_page = make_page(
        '<a href="/missing#first">Missing</a>'
        '<a href="/missing#second">Missing again</a>'
        '<a href="/timeout">Timeout</a>',
        "https://example.test/first",
    )
    second_page = make_page(
        '<a href="https://example.test/missing">Missing again</a>'
        '<a href="/limited">Limited</a>'
        '<a href="/good">Good</a>',
        "https://example.test/second",
    )

    def response_for_url(url):
        if url.endswith("/missing"):
            return MockResponse(404)
        if url.endswith("/timeout"):
            raise requests.Timeout("simulated timeout")
        if url.endswith("/limited"):
            return MockResponse(429)
        return MockResponse(200)

    sessions = mock_link_checks(monkeypatch, response_for_url)
    result = analyzer.analyze_crawl(make_crawl(first_page, second_page))
    metric = result["metrics"]["broken_internal_links"]
    requested_urls = [
        url for session in sessions for url, _ in session.calls
    ]

    assert metric["status"] == "needs_improvement"
    assert metric["checked_link_count"] == 2
    assert metric["checked_link_occurrence_count"] == 4
    assert [item["source_url"] for item in metric["broken_links"]] == [
        "https://example.test/first",
        "https://example.test/first",
        "https://example.test/second",
    ]
    assert len(metric["unverified_links"]) == 2
    assert {item["reason"] for item in metric["unverified_links"]} == {
        "Request timed out.",
        "HTTP 429 rate limit; link is unverified.",
    }
    assert len(requested_urls) == 4
    assert requested_urls.count("https://example.test/missing") == 1


def test_link_request_errors_and_policy_blocks_remain_unverified(monkeypatch):
    html = (
        '<a href="/offline">Offline</a>'
        '<a href="/robots-blocked">Robots blocked</a>'
        '<a href="/unsafe">Unsafe host</a>'
        '<a href="/good">Good</a>'
    )
    sessions = mock_link_checks(
        monkeypatch,
        lambda url: (
            (_ for _ in ()).throw(requests.ConnectionError("offline"))
            if url.endswith("/offline")
            else MockResponse(200)
        ),
    )

    class SelectiveRobots:
        def can_fetch(self, user_agent, url):
            return not url.endswith("/robots-blocked")

    monkeypatch.setattr(
        analyzer,
        "_load_robots_rules",
        lambda *args: (SelectiveRobots(), None),
    )
    monkeypatch.setattr(
        analyzer,
        "_check_public_host",
        lambda url: "Unsafe host blocked." if url.endswith("/unsafe") else None,
    )

    result = analyzer.analyze_crawl(make_crawl(make_page(html)))
    metric = result["metrics"]["broken_internal_links"]
    requested_urls = [
        url for session in sessions for url, _ in session.calls
    ]

    assert metric["status"] == "partially_available"
    assert metric["checked_link_count"] == 1
    assert len(metric["unverified_links"]) == 3
    assert any("Request failed: offline" in item["reason"] for item in metric["unverified_links"])
    assert "https://example.test/robots-blocked" not in requested_urls
    assert "https://example.test/unsafe" not in requested_urls


def test_missing_page_html_is_unavailable_not_a_failure():
    page = CrawledPage(
        url="https://example.test/private",
        final_url=None,
        status_code=None,
        html=None,
        error="Disallowed by robots.txt.",
    )

    result = analyzer.analyze_crawl(make_crawl(page))

    assert result["metrics"]["h1_heading"]["status"] == "unavailable"
    assert result["metrics"]["h1_heading"]["pages"][0]["error"] == (
        "Disallowed by robots.txt."
    )
    assert result["metrics"]["title_meta_description"]["status"] == "unavailable"