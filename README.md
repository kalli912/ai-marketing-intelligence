# AI Marketing Intelligence Assistant

## 1. Project Overview

The AI Marketing Intelligence Assistant is a website SEO auditing tool that analyzes up to 10 pages of a website and identifies practical SEO issues.

The application accepts a website URL, crawls internal pages, checks five SEO metrics, calculates an SEO score using Python, and generates prioritized recommendations.

The application uses deterministic Python logic for metric analysis and scoring. Gemini AI is optional and is used only to improve recommendation wording. It does not calculate or modify SEO scores.

## 2. Features

- Accepts a website URL for SEO auditing.
- Crawls up to 10 pages on the same website.
- Extracts page titles and meta descriptions with character counts.
- Identifies confirmed broken internal links.
- Checks H1 heading usage.
- Measures image alt text coverage.
- Checks canonical tags.
- Calculates an overall SEO score using Python.
- Displays metric scores and audit coverage.
- Separates unverified links from confirmed broken links.
- Generates prioritized SEO recommendations.
- Supports optional Gemini AI wording.
- Provides a Streamlit user interface and FastAPI backend.

## 3. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Main programming language |
| FastAPI | Backend API |
| Streamlit | User interface |
| Requests | Fetching website pages |
| BeautifulSoup4 | HTML parsing |
| Pydantic | Request and response validation |
| Pytest | Automated testing |
| HTTPX | API testing |
| Google Gemini API | Optional recommendation wording |
| python-dotenv | Environment variable management |

## 4. Project Structure

```text
ai-marketing-intelligence/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api.py
│   ├── models.py
│   ├── crawler.py
│   ├── analyzer.py
│   ├── scoring.py
│   └── recommendations.py
│
├── frontend/
│   └── streamlit_app.py
│
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_crawler.py
│   ├── test_analyzer.py
│   ├── test_scoring.py
│   ├── test_recommendations.py
│   └── test_streamlit_app.py
│
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── RESULTS.md
├── DECISIONS.md
└── AI_USAGE.md
```

## 5. Installation and Setup

### Prerequisites

- Python 3.10 or later
- pip
- Git (optional)

### Step 1: Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd ai-marketing-intelligence
```

If you already have the project downloaded, open its folder in VS Code instead.

### Step 2: Create a virtual environment

```bash
python -m venv .venv
```

### Step 3: Activate the virtual environment

For Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Step 4: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 5: Configure optional Gemini AI

Gemini integration is optional. The application can generate recommendations without an API key.

To enable Gemini, create a `.env` file in the project root and add:

```env
GEMINI_API_KEY=your_api_key_here
```

Never commit your actual `.env` file or expose your API key.

## 6. Running the Application

The application has a FastAPI backend and a Streamlit frontend.

### Step 1: Start the backend

Open the first terminal in the project folder, activate the virtual environment, and run:

```bash
python -m uvicorn app.main:app --reload
```

Backend URL:

`http://127.0.0.1:8000`

API documentation:

`http://127.0.0.1:8000/docs`

### Step 2: Start the frontend

Open a second terminal in the project folder, activate the virtual environment, and run:

```bash
python -m streamlit run frontend/streamlit_app.py
```

Frontend URL:

`http://localhost:8501`

Enter a website URL in the application and start the SEO audit.

## 7. SEO Metrics

The application checks five SEO metrics.

| Metric | Weight | What it checks |
|---|---:|---|
| Title and Meta Description | 25 | Page title and meta description length |
| Broken Internal Links | 25 | Confirmed broken internal links |
| H1 Headings | 20 | Main heading usage |
| Image Alt Text | 15 | Image accessibility text coverage |
| Canonical Tags | 15 | Canonical tag presence and URL validity |
| **Total** | **100** | |

The character limits and quality thresholds are project-defined audit rules, not absolute search-engine ranking requirements.

## 8. Scoring and Recommendations

SEO metrics are calculated using Python.

The scoring module calculates the overall score using the configured metric weights. If a metric cannot be evaluated, its unavailable weight is excluded and the report displays audit coverage.

The recommendation module identifies issues and prioritizes actions based on the actual audit findings.

Gemini AI is optional and only helps improve recommendation wording. If AI is unavailable, rule-based recommendations are used.

## 9. Running Automated Tests

Run the complete test suite using:

```bash
python -m pytest -v
```

The tests cover:

- API request validation and responses.
- Website crawling and URL handling.
- SEO metric analysis.
- SEO score calculations.
- Recommendation generation.
- Frontend report behavior.

## 10. Limitations

- The crawler audits a maximum of 10 discovered pages per audit.
- It follows same-domain internal links rather than checking every page on the website.
- Requests and BeautifulSoup analyze server-returned HTML; JavaScript-rendered content is not executed.
- Some websites may block automated requests or apply rate limits.
- Timeout, access restrictions, and HTTP 429 responses are treated as unverified rather than confirmed broken links.
- SEO scores reflect the configured metrics and thresholds, not a guaranteed Google ranking.

## 11. Future Improvements

- Support JavaScript-rendered websites.
- Add configurable crawl limits.
- Improve crawl progress and reporting.
- Add downloadable PDF or CSV reports.
- Support historical audits and score comparisons.
- Add more SEO metrics.s