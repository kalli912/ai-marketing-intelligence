import socket

import pytest
import requests

import app.crawler as crawler


PUBLIC_IP = "93.184.216.34"


class MockResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {"Content-Type": "text/html"}


class MockSession:
    def __init__(self, response_for_url):
        self.response_for_url = response_for_url
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response_for_url(url)

    def close(self):
        pass


@pytest.fixture
def public_dns(monkeypatch):
    """Make every test hostname resolve to a public IP without using the network."""
    def resolve(hostname, port, type=0):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (PUBLIC_IP, port),
            )
        ]

    monkeypatch.setattr(crawler.socket, "getaddrinfo", resolve)


def install_session(monkeypatch, response_for_url):
    session = MockSession(response_for_url)
    monkeypatch.setattr(crawler.requests, "Session", lambda: session)
    return session


def robots_response(rules="User-agent: *\nAllow: /\n"):
    return MockResponse(text=rules, headers={})


def test_invalid_url_returns_error_without_requests(monkeypatch):
    monkeypatch.setattr(
        crawler.requests,
        "Session",
        lambda: pytest.fail("invalid URL should not create a session"),
    )

    result = crawler.crawl_website("ftp://example.test")

    assert result.errors
    assert "Invalid website URL" in result.errors[0]
    assert result.pages == []


def test_finds_internal_links_and_removes_duplicate_fragments(
    monkeypatch, public_dns
):
    def response_for_url(url):
        if url.endswith("/robots.txt"):
            return robots_response()
        if url == "https://example.test/":
            return MockResponse(
                text=(
                    '<a href="/about#first">About</a>'
                    '<a href="/about#second">About again</a>'
                    '<a href="https://example.test/about">Absolute link</a>'
                )
            )
        return MockResponse(text="<html></html>")

    session = install_session(monkeypatch, response_for_url)

    result = crawler.crawl_website("https://example.test/#start")

    assert [page.url for page in result.pages] == [
        "https://example.test/",
        "https://example.test/about",
    ]
    page_requests = [url for url, _ in session.calls if not url.endswith("/robots.txt")]
    assert page_requests == ["https://example.test/", "https://example.test/about"]


def test_skips_external_links(monkeypatch, public_dns):
    def response_for_url(url):
        if url.endswith("/robots.txt"):
            return robots_response()
        return MockResponse(
            text='<a href="https://outside.test/page">External</a>'
        )

    session = install_session(monkeypatch, response_for_url)

    result = crawler.crawl_website("https://example.test/")

    assert len(result.pages) == 1
    assert all("outside.test" not in url for url, _ in session.calls)


def test_never_visits_more_than_ten_unique_pages(monkeypatch, public_dns):
    def response_for_url(url):
        if url.endswith("/robots.txt"):
            return robots_response()
        if url == "https://example.test/":
            links = "".join(
                '<a href="/page-{}">Page</a>'.format(number)
                for number in range(1, 15)
            )
            return MockResponse(text=links)
        return MockResponse(text="<html></html>")

    session = install_session(monkeypatch, response_for_url)

    result = crawler.crawl_website("https://example.test/", max_pages=50)

    page_requests = [url for url, _ in session.calls if not url.endswith("/robots.txt")]
    assert len(result.pages) == 10
    assert len(page_requests) == 10
    assert len(set(page_requests)) == 10


def test_does_not_fetch_robots_disallowed_page(monkeypatch, public_dns):
    def response_for_url(url):
        if url.endswith("/robots.txt"):
            return robots_response("User-agent: *\nDisallow: /blocked\n")
        if url == "https://example.test/":
            return MockResponse(text='<a href="/blocked">Blocked page</a>')
        pytest.fail("robots-disallowed page should not be requested")

    session = install_session(monkeypatch, response_for_url)

    result = crawler.crawl_website("https://example.test/")

    assert len(result.pages) == 2
    assert result.pages[1].error == "Disallowed by robots.txt."
    assert all("/blocked" not in url for url, _ in session.calls)


def test_records_request_timeout(monkeypatch, public_dns):
    def response_for_url(url):
        if url.endswith("/robots.txt"):
            return robots_response()
        raise requests.Timeout("simulated timeout")

    install_session(monkeypatch, response_for_url)

    result = crawler.crawl_website("https://example.test/")

    assert result.pages[0].error == "Request timed out."
    assert result.pages[0].status_code is None


def test_records_http_404(monkeypatch, public_dns):
    def response_for_url(url):
        if url.endswith("/robots.txt"):
            return robots_response()
        return MockResponse(status_code=404)

    install_session(monkeypatch, response_for_url)

    result = crawler.crawl_website("https://example.test/missing")

    assert result.pages[0].status_code == 404
    assert result.pages[0].error == "HTTP 404 response."


def test_blocks_external_redirect(monkeypatch, public_dns):
    def response_for_url(url):
        if url.endswith("/robots.txt"):
            return robots_response()
        return MockResponse(
            status_code=302,
            headers={"Location": "https://outside.test/page"},
        )

    session = install_session(monkeypatch, response_for_url)

    result = crawler.crawl_website("https://example.test/")

    assert "external hostname was blocked" in result.pages[0].error
    assert all("outside.test" not in url for url, _ in session.calls)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://sub.localhost/",
        "http://127.0.0.1/",
        "http://192.168.1.10/",
        "http://[::1]/",
        "http://[fe80::1]/",
    ],
)
def test_blocks_localhost_and_non_public_ip_addresses(monkeypatch, url):
    monkeypatch.setattr(
        crawler.requests,
        "Session",
        lambda: pytest.fail("unsafe address should be blocked before requests"),
    )

    result = crawler.crawl_website(url)

    assert result.errors
    assert crawler.UNSAFE_HOST_ERROR in result.errors[0]
    assert result.pages == []


def test_blocks_hostname_that_resolves_to_private_ip(monkeypatch):
    def resolve_to_private_ip(hostname, port, type=0):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("10.20.30.40", port),
            )
        ]

    monkeypatch.setattr(crawler.socket, "getaddrinfo", resolve_to_private_ip)
    monkeypatch.setattr(
        crawler.requests,
        "Session",
        lambda: pytest.fail("private DNS result should be blocked before requests"),
    )

    result = crawler.crawl_website("https://public-looking.example/")

    assert result.errors
    assert crawler.UNSAFE_HOST_ERROR in result.errors[0]
    assert result.pages == []