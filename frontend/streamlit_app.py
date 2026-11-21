"""Streamlit interface for running and viewing website SEO audits."""

import os
from typing import Any, Dict

import requests
import streamlit as st


DEFAULT_WEBSITE_URL = "https://mamaearth.in/"
DEFAULT_API_URL = "http://127.0.0.1:8000/audit"
DEFAULT_REQUEST_TIMEOUT = 900


def _show_page_details(pages, fields):
    """Show metric details grouped by the page the crawler inspected."""
    for page in pages:
        page_url = page.get("page_url", "Unknown page")
        with st.expander(page_url):
            if page.get("status") == "unavailable" and page.get("error"):
                st.warning(page.get("error", "This page could not be checked."))
                continue
            for label, field in fields:
                st.write("{}: {}".format(label, page.get(field)))
            if page.get("image_count") == 0:
                st.info("This page has no images, so an alt-text percentage is unavailable.")
            st.write("Status: {}".format(page.get("status", "unknown")))


def _show_page_crawl_summary(crawled_pages) -> None:
    """Summarize only page results with enough data to classify their outcome."""
    if not isinstance(crawled_pages, list) or not crawled_pages:
        return

    successful = 0
    failed = 0
    unclassified = 0
    for page in crawled_pages:
        if not isinstance(page, dict):
            unclassified += 1
            continue

        status_code = page.get("status_code")
        if page.get("error"):
            failed += 1
        elif (
            isinstance(status_code, int)
            and not isinstance(status_code, bool)
            and 200 <= status_code < 300
        ):
            successful += 1
        elif isinstance(status_code, int) and not isinstance(status_code, bool):
            failed += 1
        else:
            unclassified += 1

    if successful + failed == 0:
        return

    if unclassified:
        st.caption(
            "{} of {} page records successfully crawled; {} failed; {} "
            "could not be classified.".format(
                successful, len(crawled_pages), failed, unclassified
            )
        )
    else:
        st.caption(
            "{} of {} pages successfully crawled; {} failed.".format(
                successful, len(crawled_pages), failed
            )
        )


def _show_unverified_link_counts(unverified_links) -> None:
    """Show occurrence counts and unique URLs only when URL data is complete."""
    if not isinstance(unverified_links, list):
        return

    if not all(isinstance(link, dict) for link in unverified_links):
        st.write("Unverified link occurrence count unavailable.")
        return

    st.write("Unverified link occurrences: {}".format(len(unverified_links)))
    if all(
        isinstance(link.get("target_url"), str)
        and bool(link["target_url"])
        for link in unverified_links
    ):
        unique_urls = {link["target_url"] for link in unverified_links}
        st.write("Unique unverified URLs: {}".format(len(unique_urls)))


def _show_score_breakdown(score: Dict[str, Any]) -> None:
    """Display backend-calculated points and availability for each SEO metric."""
    metric_rows = (
        ("title_meta_description", "Title and Meta Description"),
        ("broken_internal_links", "Broken Internal Links"),
        ("h1_heading", "H1 Headings"),
        ("image_alt_text", "Image Alt Text"),
        ("canonical_tag", "Canonical Tags"),
    )

    st.subheader("SEO Score Breakdown")
    header = st.columns([2, 1.5, 2])
    header[0].markdown("**Metric**")
    header[1].markdown("**Earned / Maximum**")
    header[2].markdown("**Progress**")

    for metric_key, label in metric_rows:
        metric_score = score["metrics"][metric_key]
        maximum = metric_score["weight"]
        row = st.columns([2, 1.5, 2])
        row[0].write(label)

        if (
            metric_score["status"] == "unavailable"
            or metric_score["available_points"] == 0
        ):
            row[1].write("Unavailable / {:g} points".format(maximum))
            row[2].write("Unavailable")
            continue

        earned = metric_score["earned_points"]
        progress = earned / maximum
        row[1].write(
            "{:g} / {:g} points".format(earned, maximum)
        )
        row[2].progress(progress, text="{:.0f}%".format(progress * 100))


def _show_report(report: Dict[str, Any]) -> None:
    """Display the returned score, metrics, and recommendations."""
    score = report["score"]
    st.subheader("Overall SEO score")
    st.metric(
        "Earned points / available points",
        score["score"],
        help="Unavailable metrics are excluded from the score.",
    )
    st.caption(
        "Metric-weight coverage: {}% of the total SEO metric weight was available.".format(
            score["coverage_percent"]
        )
    )
    st.caption(
        "Metric-weight coverage indicates how much of the total SEO metric "
        "scoring weight was available. It does not represent the percentage "
        "of pages successfully crawled."
    )
    _show_page_crawl_summary(report.get("crawled_pages"))
    _show_score_breakdown(score)

    page_errors = [
        page for page in report["crawled_pages"] if page.get("error")
    ]
    if page_errors:
        st.subheader("Pages with crawl errors")
        for page in page_errors:
            page_url = page.get("final_url") or page.get("url", "Unknown page")
            status_code = page.get("status_code")
            http_status = (
                "HTTP {}".format(status_code)
                if status_code is not None
                else "HTTP status unavailable"
            )
            st.error(
                "{} — {}: {}".format(page_url, http_status, page["error"])
            )

    metrics = report["metrics"]
    st.subheader("SEO metrics")

    title_metric = metrics["title_meta_description"]
    st.markdown("#### Title and Meta Description")
    st.caption("Why it matters: Search snippets and page titles help people understand what a page offers.")
    st.caption("Measurement: Title 30–60 characters; meta description 70–160 characters.")
    for page in title_metric["pages"]:
        with st.expander(page.get("page_url", "Unknown page")):
            if page.get("status") == "unavailable":
                st.warning(page.get("error", "This page could not be checked."))
                continue
            for field, label in (
                ("title", "Title"),
                ("meta_description", "Meta description"),
            ):
                value = page[field]
                st.write(
                    "{}: {} ({} characters) — {}".format(
                        label,
                        value["text"] if value["text"] is not None else "Missing",
                        value["character_count"],
                        value["status"].replace("_", " "),
                    )
                )

    link_metric = metrics["broken_internal_links"]
    st.markdown("#### Broken Internal Links")
    st.caption("Why it matters: Broken links can interrupt customer journeys and make important pages harder to reach.")
    st.caption("Measurement: Only confirmed HTTP 4xx/5xx responses are broken; unverified links are listed separately.")
    st.caption(
        "This score applies only to verified link checks. Unverified checks "
        "are not counted as confirmed broken links."
    )
    st.write("Metric status: {}".format(link_metric["status"].replace("_", " ")))
    if link_metric["status"] == "unavailable":
        st.info("No internal links could be verified.")
    unverified_links = link_metric.get("unverified_links")
    if isinstance(unverified_links, list):
        _show_unverified_link_counts(unverified_links)

    link_score = score.get("metrics", {}).get("broken_internal_links", {})
    broken_links = link_metric.get("broken_links")
    if (
        isinstance(link_score, dict)
        and link_score.get("weight") == 25
        and link_score.get("earned_points") == 25
        and link_score.get("available_points", 0) > 0
        and link_score.get("confirmed_broken_links") == 0
        and isinstance(broken_links, list)
        and not broken_links
    ):
        st.success("No confirmed broken links among verified checks.")

    if isinstance(broken_links, list):
        for link in broken_links:
            st.error(
                "Confirmed broken link: {} → {} (HTTP {})".format(
                    link["source_url"], link["target_url"], link["status_code"]
                )
            )
    if isinstance(unverified_links, list):
        for link in unverified_links:
            if not isinstance(link, dict):
                st.warning("Unverified link details unavailable.")
                continue
            st.warning(
                "Unverified link: {} → {} ({})".format(
                    link.get("source_url", "Unknown source page"),
                    link.get("target_url", "Unknown target URL"),
                    link.get("reason", "Reason unavailable"),
                )
            )

    h1_metric = metrics["h1_heading"]
    st.markdown("#### H1 Heading")
    st.caption("Why it matters: A clear main heading helps visitors quickly understand a page.")
    st.caption("Measurement: This project’s rule is exactly one H1 per page; it is not an official Google ranking guarantee.")
    _show_page_details(h1_metric["pages"], [("H1 count", "h1_count")])

    image_metric = metrics["image_alt_text"]
    st.markdown("#### Image Alt Text")
    st.caption("Why it matters: Descriptive alt text can help accessibility and make image content understandable.")
    st.caption("Measurement: At least 90% of a page’s images should have non-empty alt text.")
    _show_page_details(
        image_metric["pages"],
        [
            ("Image count", "image_count"),
            ("Images with alt text", "images_with_alt"),
            ("Alt-text percentage", "alt_text_percentage"),
        ],
    )

    canonical_metric = metrics["canonical_tag"]
    st.markdown("#### Canonical Tag")
    st.caption("Why it matters: Canonical URLs signal which URL should represent duplicate or similar pages.")
    st.caption("Measurement: Exactly one valid absolute HTTP or HTTPS canonical URL per page.")
    for page in canonical_metric["pages"]:
        with st.expander(page.get("page_url", "Unknown page")):
            if page.get("status") == "unavailable":
                st.warning(page.get("error", "This page could not be checked."))
                continue
            st.write("Canonical count: {}".format(page["canonical_count"]))
            for canonical in page["canonical_urls"]:
                st.write(
                    "{} — {}".format(
                        canonical["url"] or "Missing URL",
                        "valid" if canonical["valid"] else "invalid",
                    )
                )
            st.write("Status: {}".format(page["status"].replace("_", " ")))

    st.subheader("Prioritized recommendations")
    if report["ai_status"] == "used":
        st.caption("Gemini helped phrase these actions. Findings and measurements are from the Python audit.")
    elif report["ai_status"] in {"unavailable", "failed"}:
        st.caption("Rule-based recommendations are shown; optional AI wording was not available.")

    if not report["recommendations"]:
        if score["coverage_percent"] == 0:
            st.warning(
                "Unable to generate recommendations because the website could "
                "not be audited successfully. Please try another website or "
                "check whether automated access is allowed."
            )
        else:
            st.success(
                "No actionable issues were found in the available audit results."
            )
    else:
        for recommendation in report["recommendations"]:
            st.markdown(
                "**{} priority — {}**".format(
                    recommendation["priority"], recommendation["issue"]
                )
            )
            st.write(recommendation["action"])
            st.caption("Observed evidence: " + "; ".join(recommendation["evidence"]))

    for error in report["errors"]:
        st.warning(error)

    st.caption(
        "The crawler reads the HTML returned by the website; it does not inspect content rendered only by JavaScript."
    )


def main() -> None:
    st.set_page_config(
        page_title="Website SEO Audit",
        page_icon="📊",
        layout="wide",
    )
    st.title("Website SEO Audit")
    st.write(
        "Check five practical SEO metrics across up to 10 pages on the same website."
    )

    with st.form("seo_audit_form"):
        website_url = st.text_input(
            "Website URL",
            value=DEFAULT_WEBSITE_URL,
            placeholder="https://example.com/",
        )
        use_ai = st.checkbox(
            "Use optional Gemini wording",
            value=False,
            help=(
                "Only enable this if your Gemini API key has free-tier quota "
                "available. Rule-based recommendations work without Gemini."
            ),
        )
        submitted = st.form_submit_button("Run SEO Audit", type="primary")

    if submitted:
        api_url = os.getenv("SEO_AUDIT_API_URL", DEFAULT_API_URL)
        try:
            request_timeout = int(
                os.getenv("SEO_AUDIT_REQUEST_TIMEOUT", str(DEFAULT_REQUEST_TIMEOUT))
            )
            if request_timeout <= 0:
                raise ValueError
        except ValueError:
            st.error("SEO_AUDIT_REQUEST_TIMEOUT must be a positive whole number of seconds.")
            return

        st.info("The SEO audit may take several minutes. Please keep this page open.")
        try:
            with st.spinner("Crawling and analyzing the website..."):
                response = requests.post(
                    api_url,
                    json={"url": website_url, "use_ai": use_ai},
                    timeout=request_timeout,
                )
        except requests.Timeout:
            st.error(
                "The audit API did not respond before the {}-second request timeout. "
                "Try again, increase SEO_AUDIT_REQUEST_TIMEOUT, or check the backend."
                .format(request_timeout)
            )
            return
        except requests.RequestException:
            st.error("Could not reach the audit API. Make sure the FastAPI server is running.")
            return

        if not response.ok:
            try:
                detail = response.json().get("detail", "The request was rejected.")
            except ValueError:
                detail = "The request was rejected (HTTP {}).".format(
                    response.status_code
                )
            st.error("Audit could not run: {}".format(detail))
            return

        st.session_state["seo_audit_report"] = response.json()

    report = st.session_state.get("seo_audit_report")
    if report:
        _show_report(report)


if __name__ == "__main__":
    main()