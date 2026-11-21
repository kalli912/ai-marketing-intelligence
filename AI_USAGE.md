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

4. What I'd Improve With One More Day

Make the crawler handle rate-limited websites better, since this was the biggest limitation I ran into.
Test the app on a wider variety of websites.
Look into supporting JavaScript-rendered pages with Playwright.
Review the recommendations across different sites to make sure they are practical and tied directly to what the audit found.
