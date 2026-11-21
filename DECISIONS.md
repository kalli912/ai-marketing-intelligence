## 1. Key Assumptions

During development, I made the following assumptions to keep the project focused and manageable:

1. **Crawl limit:** The crawler audits a maximum of 10 pages per website. It starts from the submitted URL and discovers additional pages by following same-domain internal links.

2. **SEO thresholds:** I used project-defined thresholds for title length (30–60 characters), meta description length (70–160 characters), and image alt text coverage (90%). These are audit rules for this project, not absolute search-engine ranking requirements.

3. **Broken link classification:** Only confirmed HTTP 4xx and 5xx responses are treated as broken links. Timeouts, HTTP 429 rate limits, and other uncertain results are classified as unverified rather than broken.

4. **Scoring:** Each SEO metric has a predefined weight. If a metric is unavailable, its weight is excluded from the score, and the application reports metric-weight coverage separately.

5. **Website rendering:** The crawler uses Requests and BeautifulSoup to inspect server-returned HTML. It does not execute JavaScript to inspect dynamically rendered content.

## 2. Ambiguities and How I Handled Them

### A. What counts as a broken link?

A request failure does not always mean that a link is broken. For example, HTTP 429 indicates rate limiting, and a timeout does not confirm that the destination is unavailable.

**Decision:** I separated confirmed broken links from unverified links to avoid reporting uncertain results as failures.

### B. What does 100% audit coverage mean?

A 100% coverage value could be misunderstood as meaning that every page and every link was successfully checked.

**Decision:** I defined coverage as the percentage of total metric scoring weight available for calculation. Link verification and page crawl errors are reported separately.

### C. Does crawling 10 pages mean the entire website was audited?

A website can contain hundreds of pages, but the assignment limits the crawler to 10 pages.

**Decision:** The crawler follows same-domain internal links and stops when it reaches the configured maximum of 10 pages. The report lists the pages included in the audit.

## 3. Three Decisions I Would Revisit

### 1. JavaScript-rendered websites

The current crawler only reads server-returned HTML.

**What I would change:** Consider adding Playwright to support JavaScript-rendered pages when necessary.

**Why:** Some websites load important content dynamically, which the current crawler may not detect.

### 2. Crawl and link-check rate management

Some websites restrict automated requests. During the Mamaearth audit, several link checks returned HTTP 429.

**What I would change:** Introduce configurable request rates, more controlled retries, and better handling of rate limits.

**Why:** This could improve verification coverage while reducing the chance of overwhelming a website or triggering restrictions.

### 3. Crawl limit and page selection

The current crawler uses a fixed maximum of 10 pages and discovers pages through internal links.

**What I would change:** Allow users to configure the crawl limit and potentially introduce page-selection options, such as prioritizing product, category, or important landing pages.

**Why:** This would make the audit more flexible and useful for larger websites.

## 4. Final Reflection

I prioritised accuracy and transparent reporting over making the audit appear more complete than it actually was. In particular, I kept uncertain link results separate from confirmed failures and made the scoring logic independent of AI-generated recommendations.

These decisions helped keep the application understandable, testable, and suitable for the scope of the assessment.