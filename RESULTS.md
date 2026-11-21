SEO Audit Report: Mamaearth.in
Project: AI Marketing Intelligence Assistant Website audited: https://mamaearth.in/ Audit date: 21 November 2026 Pages audited: 10 of a maximum 10 Overall SEO score: 64/100
1. Overview
For this audit I chose Mamaearth because it is a well-established e-commerce site with plenty of product and category pages. That makes it a good real-world test for the things my tool checks: page metadata, internal links, headings, image alt text, and canonical tags.
The tool crawls up to 10 pages, starting from the homepage and following internal links on the same domain. It reads each page, scores five SEO metrics using Python, and turns the results into recommendations. All five metrics were available this time, so the score reflects 100% of the total scoring weight.
2. Overall Score
Mamaearth scored 64 out of 100. Here is how the points broke down:
SEO metric
Points earned
Maximum points
Title and meta description      15/25
Broken internal links   25/25
H1 headings   6/20
Image alt text    3/15
Canonical tags    15/15
Total       64/100
If a metric can't be measured, its weight is left out of the score, and the tool reports how much of the total weight was available. In this run, nothing was left out.
3. Pages Audited
The crawler found and audited these 10 pages:
1.  https://mamaearth.in/
2.  https://mamaearth.in/collections/b1g1-offer
3.  https://mamaearth.in/collections/redeem35
4.  https://mamaearth.in/account/login?return_url=%2Faccount
5.  https://mamaearth.in/cart
6.  https://mamaearth.in/collections/face-wash
7.  https://mamaearth.in/collections/sunscreen
8.  https://mamaearth.in/collections/face-serum
9.  https://mamaearth.in/collections/face-cream
10.  https://mamaearth.in/collections/face-moisturizer
Ten pages is simply the limit I set for the crawler. It doesn't mean the website only has ten pages.
4. Detailed Findings
4.1 Title and meta description (15/25)
Pages passing: 6 of 10
The tool expects a page title between 30 and 60 characters and a meta description between 70 and 160 characters.
What I found:
• The B1G1 offer page has a meta description that is too short.
• The account login page has a title outside the expected length and no meta description.
• The cart page has the same two problems: a title outside the range and no meta description.
• The face serum page has a meta description that is too long.
Recommendation: Go through the pages with missing or badly sized titles and descriptions, and write clear, relevant ones for each.
4.2 Broken internal links (25/25)
The tool treats a link as broken only when it gets a confirmed HTTP 4xx or 5xx response.
What I found:
• Confirmed broken links: 0
• Unverified link occurrences: 420
• Unique unverified URLs: 144
Many of the checks came back with HTTP 429, which means the website was rate-limiting my requests. Since a 429 doesn't tell us whether a link actually works, I labelled those links "unverified" rather than "broken".
It's worth being clear about what the full score means here. It is based only on the links that could be verified, so it does not prove that every internal link on the site works.
Recommendation: Run the check again later at a slower request rate, and look into any link that returns a confirmed 4xx or 5xx error.
4.3 H1 headings (6/20)
Pages passing: 3 of 10
The rule is simple: each page should have exactly one H1 heading. Several pages had more than one, and the account login page had none.
Pages that need attention:
• B1G1 offer
• Account login
• Face wash
• Sunscreen
• Face serum
• Face cream
• Face moisturizer
Recommendation: Review the heading structure on these pages and give each one a single, clear H1 that describes the page.
4.4 Image alt text (3/15)
Pages passing: 2 of 10
Here the tool measures what share of images on a page have non-empty alt text. The passing mark is 90%. Most of the pages I checked landed just below it:
Page
Alt text coverage
B1G1 offer
85.71%
Account login
80.00%
Cart
80.00%
Face wash
87.27%
Sunscreen
87.72%
Face serum
86.79%
Face cream
87.27%
Face moisturizer
87.04%
So the gap is fairly small on most pages, but it adds up to a low score because the threshold is strict.
Recommendation: Add meaningful alt text to the images that are missing it. It should describe what the image actually shows, not fall back on something generic.
4.5 Canonical tags (15/15)
Pages passing: 10 of 10
The tool checks that each page has exactly one canonical tag and that its URL is an absolute HTTP or HTTPS address. Every audited page passed.
Recommendation: Keep an eye on canonical tags whenever new pages are added or URLs change.
5. Limitations of This Audit
This audit is a useful snapshot, but it has some limits worth knowing about:
• It reads only the HTML the server returns. It does not run JavaScript, so content that loads dynamically isn't inspected.
• It covers up to 10 discovered pages, not the whole website.
• Rate limiting, timeouts, and access restrictions on the website can affect how complete the results are.
• Some internal link checks returned HTTP 429 and were not counted as broken.
One more point to avoid confusion: the "100% coverage" shown in the app refers to the share of scoring weight that was available. It does not mean every page or every link was successfully verified.
6. Prioritized Recommendations
Priority
Action
High
Fix missing or incorrectly sized page titles and meta descriptions.
High
Recheck the unverified internal links and investigate any confirmed broken ones.
Medium
Fix pages with missing or multiple H1 headings.
Medium
Raise image alt text coverage to the 90% threshold.
Low
Keep monitoring canonical tags on new and updated pages.
7. Conclusion
Mamaearth received an overall score of about 64/100. Its strongest area was canonical tags, where all 10 pages passed. The biggest room for improvement is in H1 headings, image alt text, and page titles and meta descriptions.
The broken-link metric earned full marks, but only on the links that could be verified. Because so many checks were rate-limited, I kept those results separate from confirmed failures rather than report uncertain results as errors.
Overall, this project shows how my application crawls a limited set of pages, extracts SEO data, scores it with Python, and turns the findings into practical, prioritized recommendations.