1. AI Tools Used

I used AI tools as helpers while building this project, not as a replacement for my own work.

ChatGPT/CLAUDE: Used to understand assignment requirements, learn unfamiliar technical concepts, plan implementation steps, identify and resolve technical issues, and improve documentation.
GitHub Copilot: I used it inside VS Code for code suggestions and implementation help, and to improve parts of the application and its tests.
Gemini API: I added this as an optional feature that rewords the SEO recommendations so they read more clearly. It has no say in calculating the SEO metrics or the overall score.
2. How I Built It

I worked through the project one step at a time:
I started by reading the assignment carefully and choosing five SEO metrics to measure.
I set up the project structure and my development environment.
I built the website crawler and the HTML analysis.
I wrote the scoring logic, the API, and the Streamlit interface.
I tested the app on real websites and went through the audit results to see if they made sense.
I ran automated tests as I went to check that my changes didn't break anything.
I refined how the app handles uncertain link responses, unavailable metrics, scoring coverage, and websites that restrict access.
I improved the interface so the results and their limitations are easier to understand.

AI helped throughout with explanations, suggestions, and debugging, but I checked every decision against the project requirements and against how the application actually behaved.

3. One Important Technical Decision

I deliberately kept all SEO metric calculations and the overall score in Python instead of handing them to an LLM.

My reasoning was that an SEO result should come from what is actually on the page: the real HTML and the real HTTP responses. Doing the calculations in Python means the results are consistent, measurable, and testable. An LLM could give a different answer each time. So AI only plays a supporting role, which is making the recommendation wording clearer.

4. Examples of AI Limitations

Example 1: API Testing
Problem: My initial API test setup did not work because of a compatibility issue with the testing dependencies.
How I checked: I looked at the error and checked the installed package versions.
What I changed: I installed the required httpx dependency and updated the tests to use ASGITransport and AsyncClient.
Result: The API tests started working correctly.

Example 2: Website Crawling Timeout

Problem: Some website audits took a long time because checking internal links could take time, especially when websites restricted requests.
How I checked: I looked into the timeout settings and the crawler's request handling.
What I changed: I increased the frontend timeout from 300 to 900 seconds and reviewed how the crawler handled website restrictions.
Result: The frontend had more time to complete longer audits. However, this did not remove website rate-limiting problems.