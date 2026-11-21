"""Fetch a small set of pages from one website."""

from collections import deque
from dataclasses import dataclass, field
import ipaddress
import re
import socket
from typing import List, Optional, Set, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


MAX_PAGES = 10
DEFAULT_TIMEOUT = 10.0
DEFAULT_USER_AGENT = "AI-Market-Intelligence-Audit/1.0"
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
UNSAFE_HOST_ERROR = (
    "Local, private, loopback, and link-local addresses are not allowed."
)


@dataclass
class CrawledPage:
    """The result of trying to fetch one page."""

    url: str
    final_url: Optional[str]
    status_code: Optional[int]
    html: Optional[str]
    error: Optional[str] = None


@dataclass
class CrawlResult:
    """All pages and general errors from one crawl."""

    start_url: str
    pages: List[CrawledPage] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _normalize_hostname(hostname: str) -> str:
    """Return a consistently formatted hostname or raise ValueError."""
    hostname = hostname.rstrip(".").lower()
    if not hostname:
        raise ValueError("the URL must include a hostname")

    try:
        return ipaddress.ip_address(hostname).compressed.lower()
    except ValueError:
        pass

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("the URL hostname is invalid") from error

    if len(ascii_hostname) > 253:
        raise ValueError("the URL hostname is too long")

    for label in ascii_hostname.split("."):
        if (
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not re.fullmatch(r"[a-z0-9-]+", label)
        ):
            raise ValueError("the URL hostname is invalid")

    return ascii_hostname


def _normalize_url(url: str) -> str:
    """Validate an HTTP(S) URL and remove fragments and common duplicates."""
    if not isinstance(url, str) or not url or url != url.strip():
        raise ValueError("enter a complete website URL")
    if any(character.isspace() for character in url):
        raise ValueError("the URL cannot contain spaces")

    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError("only HTTP and HTTPS URLs are supported")
        if not parts.netloc or not parts.hostname:
            raise ValueError("the URL must include a valid hostname")
        if parts.username is not None or parts.password is not None:
            raise ValueError("URLs containing a username or password are not supported")

        hostname = _normalize_hostname(parts.hostname)
        port = parts.port
    except ValueError as error:
        raise ValueError(str(error)) from error

    if ":" in hostname:
        authority = "[{}]".format(hostname)
    else:
        authority = hostname

    # Default ports do not make a URL a different page.
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        authority = "{}:{}".format(authority, port)

    return urlunsplit((scheme, authority, parts.path or "/", parts.query, ""))


def _hostname_from_url(url: str) -> str:
    """Get the normalized hostname from a URL that has already been checked."""
    hostname = urlsplit(url).hostname
    if hostname is None:
        raise ValueError("the URL must include a valid hostname")
    return _normalize_hostname(hostname)


def _check_public_host(url: str) -> Optional[str]:
    """Block local IPs and hostnames that resolve to any non-public address."""
    hostname = _hostname_from_url(url)
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return UNSAFE_HOST_ERROR

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None

    if address is not None:
        return None if address.is_global else UNSAFE_HOST_ERROR

    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as error:
        return "Could not safely resolve hostname: {}".format(error)

    if not records:
        return "Could not safely resolve hostname."

    # Reject the whole hostname if even one address is not publicly routable.
    for record in records:
        try:
            resolved_address = ipaddress.ip_address(record[4][0].split("%", 1)[0])
        except (IndexError, TypeError, ValueError):
            return "Could not safely check a resolved IP address."
        if not resolved_address.is_global:
            return UNSAFE_HOST_ERROR

    return None


def _load_robots_rules(
    session: requests.Session, start_url: str, user_agent: str, timeout: float
) -> Tuple[Optional[RobotFileParser], Optional[str]]:
    """Fetch robots.txt; stop the crawl if its rules cannot be checked safely."""
    parts = urlsplit(start_url)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    host_error = _check_public_host(robots_url)
    if host_error:
        return None, host_error

    try:
        response = session.get(
            robots_url,
            headers={"User-Agent": user_agent},
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException as error:
        return None, "Could not check robots.txt: {}".format(error)

    if response.status_code == 404:
        # A missing robots.txt file has no rules to apply.
        lines = []
    elif 200 <= response.status_code < 300:
        lines = response.text.splitlines()
    else:
        return None, "Could not check robots.txt (HTTP {}).".format(
            response.status_code
        )

    parser = RobotFileParser(robots_url)
    parser.parse(lines)
    return parser, None


def _fetch_page(
    session: requests.Session,
    page_url: str,
    robots: RobotFileParser,
    hostname: str,
    user_agent: str,
    timeout: float,
) -> CrawledPage:
    """Fetch one page, following only redirects that stay on this hostname."""
    current_url = page_url
    redirect_count = 0

    while True:
        if not robots.can_fetch(user_agent, current_url):
            return CrawledPage(
                url=page_url,
                final_url=current_url,
                status_code=None,
                html=None,
                error="Disallowed by robots.txt.",
            )

        host_error = _check_public_host(current_url)
        if host_error:
            return CrawledPage(
                url=page_url,
                final_url=current_url,
                status_code=None,
                html=None,
                error=host_error,
            )

        try:
            response = session.get(
                current_url,
                headers={"User-Agent": user_agent},
                timeout=timeout,
                allow_redirects=False,
            )
        except requests.Timeout:
            return CrawledPage(
                url=page_url,
                final_url=current_url,
                status_code=None,
                html=None,
                error="Request timed out.",
            )
        except requests.RequestException as error:
            return CrawledPage(
                url=page_url,
                final_url=current_url,
                status_code=None,
                html=None,
                error="Request failed: {}".format(error),
            )

        if response.status_code in REDIRECT_STATUS_CODES:
            location = response.headers.get("Location")
            if not location:
                return CrawledPage(
                    url=page_url,
                    final_url=current_url,
                    status_code=response.status_code,
                    html=None,
                    error="Redirect response did not include a destination.",
                )
            if redirect_count >= MAX_REDIRECTS:
                return CrawledPage(
                    url=page_url,
                    final_url=current_url,
                    status_code=response.status_code,
                    html=None,
                    error="Too many redirects.",
                )

            try:
                next_url = _normalize_url(urljoin(current_url, location))
            except ValueError:
                return CrawledPage(
                    url=page_url,
                    final_url=current_url,
                    status_code=response.status_code,
                    html=None,
                    error="Redirect destination is not a valid HTTP(S) URL.",
                )

            if _hostname_from_url(next_url) != hostname:
                return CrawledPage(
                    url=page_url,
                    final_url=current_url,
                    status_code=response.status_code,
                    html=None,
                    error="Redirect to an external hostname was blocked.",
                )

            current_url = next_url
            redirect_count += 1
            continue

        if not 200 <= response.status_code < 300:
            return CrawledPage(
                url=page_url,
                final_url=current_url,
                status_code=response.status_code,
                html=None,
                error="HTTP {} response.".format(response.status_code),
            )

        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not (
            "text/html" in content_type or "application/xhtml+xml" in content_type
        ):
            return CrawledPage(
                url=page_url,
                final_url=current_url,
                status_code=response.status_code,
                html=None,
                error="The response is not an HTML page.",
            )

        return CrawledPage(
            url=page_url,
            final_url=current_url,
            status_code=response.status_code,
            html=response.text,
        )


def _find_internal_links(
    html: str, page_url: str, hostname: str
) -> List[str]:
    """Extract unique same-hostname links and make them absolute."""
    soup = BeautifulSoup(html, "html.parser")
    links: List[str] = []
    seen: Set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href:
            continue

        try:
            absolute_url = _normalize_url(urljoin(page_url, href))
        except ValueError:
            # Skip mailto:, javascript:, malformed, and other non-page links.
            continue

        if _hostname_from_url(absolute_url) != hostname:
            continue
        if absolute_url not in seen:
            seen.add(absolute_url)
            links.append(absolute_url)

    return links


def crawl_website(
    url: str,
    max_pages: int = MAX_PAGES,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> CrawlResult:
    """Crawl up to 10 unique pages on the starting URL's hostname.

    Page-level problems are recorded on each CrawledPage. Invalid input or a
    robots.txt problem is recorded in CrawlResult.errors instead of crashing.
    """
    result = CrawlResult(start_url=url if isinstance(url, str) else "")

    try:
        start_url = _normalize_url(url)
    except ValueError as error:
        result.errors.append("Invalid website URL: {}".format(error))
        return result

    if not isinstance(max_pages, int) or max_pages < 1:
        result.errors.append("max_pages must be a positive whole number.")
        return result
    if timeout <= 0:
        result.errors.append("timeout must be greater than zero.")
        return result
    if not user_agent:
        result.errors.append("user_agent cannot be empty.")
        return result

    host_error = _check_public_host(start_url)
    if host_error:
        result.errors.append(host_error)
        return result

    # Enforce the project's maximum even if a caller requests more pages.
    page_limit = min(max_pages, MAX_PAGES)
    result.start_url = start_url
    hostname = _hostname_from_url(start_url)
    session = requests.Session()

    try:
        robots, robots_error = _load_robots_rules(
            session, start_url, user_agent, timeout
        )
        if robots_error:
            result.errors.append(robots_error)
            return result

        # The error case above returns early; this guard keeps the type explicit.
        if robots is None:
            result.errors.append("Could not check robots.txt.")
            return result

        pages_to_visit = deque([start_url])
        queued = {start_url}
        visited: Set[str] = set()

        while pages_to_visit and len(result.pages) < page_limit:
            page_url = pages_to_visit.popleft()
            if page_url in visited:
                continue
            visited.add(page_url)

            page = _fetch_page(
                session, page_url, robots, hostname, user_agent, timeout
            )
            result.pages.append(page)
            if page.final_url:
                visited.add(page.final_url)

            if page.html is None or page.status_code is None:
                continue
            if not 200 <= page.status_code < 300 or not page.final_url:
                continue

            for link in _find_internal_links(page.html, page.final_url, hostname):
                if link not in queued and link not in visited:
                    queued.add(link)
                    pages_to_visit.append(link)
    finally:
        session.close()

    return result