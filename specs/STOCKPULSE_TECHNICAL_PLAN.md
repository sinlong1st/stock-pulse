# StockPulse -- Technical Architecture & Implementation Plan

## 1. Purpose of This Document

This document defines the technical architecture, implementation
boundaries, development phases, and coding expectations for StockPulse.

It is intended to be used as context for an AI coding assistant before
implementation begins.

The AI should:

-   Read this document before writing code.
-   Follow the architecture and phase boundaries defined here.
-   Avoid adding unnecessary technologies or features.
-   Ask before making major architectural changes.
-   Implement one phase at a time.
-   Prefer simple, maintainable solutions over premature optimization.

------------------------------------------------------------------------

## 2. Project Overview

StockPulse is a lightweight market intelligence service that
continuously monitors financial news, identifies potentially
market-moving events, classifies their importance, and sends alerts
through configured notification channels.

The system is designed primarily for a single user during the MVP stage.

The core problem:

> Important stock and macroeconomic news appears throughout the day, but
> manually monitoring multiple news sources is inefficient. StockPulse
> should automatically detect what matters and notify the user without
> overwhelming them with low-value alerts.

The first version must remain:

-   Low cost
-   Easy to run locally
-   Easy to deploy
-   Easy to debug
-   Modular enough to add more news sources and alert channels later

------------------------------------------------------------------------

## 3. Core Product Principles

### 3.1 Filter Before AI

Do not send every article to the AI model.

The pipeline should first use cheap deterministic filtering such as:

-   Watchlist ticker matching
-   Company name matching
-   Macro keyword matching
-   Sector keyword matching
-   Basic duplicate detection

Only potentially relevant articles should reach the AI classifier.

This keeps API cost low and reduces unnecessary processing.

### 3.2 Avoid Alert Fatigue

The system should not notify the user about every article.

The goal is not maximum news volume.

The goal is:

> Detect important information early while keeping alerts meaningful.

LOW-impact news should normally be stored but not sent.

### 3.3 Modular Components

Each major responsibility should be separated:

-   Collecting news
-   Normalizing articles
-   Deduplicating articles
-   Rule-based filtering
-   AI classification
-   Alert decision logic
-   Notification delivery
-   Persistence

Adding a new news source or notification channel should not require
rewriting the entire system.

### 3.4 Start Simple

Do not introduce the following during the MVP unless a clear technical
need appears:

-   Kubernetes
-   Kafka
-   Redis
-   Microservices
-   Celery
-   Complex event streaming
-   Multiple databases
-   Frontend dashboard

StockPulse should begin as one Python service.

------------------------------------------------------------------------

## 4. Recommended Technology Stack

### Core Language

-   Python 3.12+

### API Framework

-   FastAPI

Use FastAPI for:

-   Application startup
-   Health checks
-   Future alert acknowledgment endpoints
-   Future configuration endpoints
-   Future dashboard backend APIs

The MVP does not need a large REST API.

### HTTP Client

-   httpx

Use for:

-   News API requests
-   Telegram requests if needed
-   External service integrations

### RSS Parsing

-   feedparser

Use for RSS-based news sources.

### Data Validation

-   Pydantic

Use structured models for:

-   News articles
-   Classification results
-   Alert decisions
-   Application configuration

### Database

MVP:

-   SQLite

Later production option:

-   PostgreSQL

Use:

-   SQLAlchemy for ORM/database access
-   Alembic for migrations

Do not use a JSON file as the main persistence layer.

### Scheduling

MVP:

-   APScheduler

Use it to trigger the news monitoring jobs every configurable number of
minutes.

As implemented, the two news sources run as separate scheduled jobs, each
with its own interval, so their cadence can be tuned independently:

``` text
WATCHLIST_FETCH_INTERVAL_MINUTES=5
MACRO_FETCH_INTERVAL_MINUTES=30
```

### AI Classification

Initial provider:

-   OpenAI API

The AI integration must be isolated behind a classifier interface so
another provider can be added later.

### Notifications

Phase 1:

-   Telegram Bot API

Future:

-   Pushover or ntfy
-   Email
-   Twilio phone calls

### Testing

-   pytest
-   pytest-asyncio when needed

### Packaging and Dependency Management

Use:

-   `pyproject.toml`

Prefer a modern Python project structure.

### Deployment

-   Docker
-   GitHub Actions for CI

------------------------------------------------------------------------

## 5. High-Level Architecture

``` text
                    ┌───────────────────┐
                    │   News Sources    │
                    │ RSS / News APIs   │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │  News Collectors  │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │    Normalizer     │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │   Deduplicator    │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Rule-Based Filter │
                    └─────────┬─────────┘
                              │
                     Relevant articles only
                              │
                              ▼
                    ┌───────────────────┐
                    │   AI Classifier   │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Alert Decision    │
                    │     Engine        │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Notification      │
                    │ Router            │
                    └─────────┬─────────┘
                              │
                 ┌────────────┼────────────┐
                 ▼            ▼            ▼
             Telegram       Push         Phone
             Phase 1        Future       Future
```

------------------------------------------------------------------------

## 6. Core Domain Models

### 6.1 NewsArticle

Represents a normalized article regardless of source.

Suggested fields:

``` python
id: str | None
source: str
external_id: str | None
title: str
summary: str | None
url: str
published_at: datetime | None
collected_at: datetime
content_hash: str
```

Possible future fields:

``` python
author: str | None
raw_content: str | None
language: str | None
```

### 6.2 ClassificationResult

Represents the AI analysis of an article.

Suggested fields:

``` python
is_market_relevant: bool
importance: LOW | MEDIUM | HIGH | CRITICAL
category: MACRO | TICKER | SECTOR | OTHER
related_tickers: list[str]
summary: str
why_it_matters: str
should_alert: bool
confidence: float | None
```

### 6.3 Alert

Represents an alert generated by the system.

Suggested fields:

``` python
id: str | None
article_id: str
importance: str
channel: str
status: PENDING | SENT | FAILED | ACKNOWLEDGED
created_at: datetime
sent_at: datetime | None
acknowledged_at: datetime | None
error_message: str | None
```

------------------------------------------------------------------------

## 7. Database Responsibilities

The database should store enough information to:

-   Prevent duplicate processing
-   Prevent duplicate alerts
-   Review previously processed articles
-   Debug AI classifications
-   Review alert delivery history

Suggested initial tables:

### articles

Stores normalized articles.

Important constraints:

-   URL should be unique when possible.
-   `content_hash` should be indexed.
-   Duplicate detection should not depend only on article title.

### classifications

Stores AI classification results.

Each classification should reference an article.

### alerts

Stores notification attempts and statuses.

The database design should remain simple during the MVP.

------------------------------------------------------------------------

## 8. News Processing Pipeline

The processing order is important.

### Step 1: Collect

Fetch recent articles from configured news sources.

Collectors should return normalized or partially normalized article
objects.

### Step 2: Normalize

Convert source-specific data into the common `NewsArticle` model.

Examples:

-   Standardize timestamps.
-   Clean article titles.
-   Normalize URLs when reasonable.
-   Generate a content hash.

### Step 3: Deduplicate

Check whether the article has already been processed.

Possible signals:

-   Exact URL
-   External source ID
-   Content hash

Do not send the same story repeatedly.

Advanced semantic duplicate detection is not required for Phase 1.

### Step 4: Rule-Based Relevance Filter

Check for configured signals.

Examples:

#### Macro Keywords

``` text
Federal Reserve
Fed
Powell
interest rate
rate cut
rate hike
CPI
PPI
inflation
jobs report
nonfarm payroll
unemployment
GDP
Treasury yield
tariff
sanctions
oil
geopolitical
war
```

#### Watchlist

Initial examples:

``` text
QQQ
QQQM
VOO
NVDA
AMD
PLTR
SOFI
HOOD
META
AMZN
```

The watchlist must be configurable.

The filter should support:

-   Ticker symbols
-   Company names
-   Macro keywords

If an article does not pass the cheap relevance filter, store its
processing result if useful, but do not send it to AI.

### Step 5: AI Classification

Only relevant candidates should be sent to the AI model.

The classifier must return structured data.

Expected output:

``` json
{
  "is_market_relevant": true,
  "importance": "HIGH",
  "category": "MACRO",
  "related_tickers": ["QQQ", "NVDA", "AMD"],
  "summary": "Fed comments suggest rate cuts may be delayed.",
  "why_it_matters": "Higher-for-longer rates may pressure growth and technology stocks.",
  "should_alert": true,
  "confidence": 0.91
}
```

The application must validate AI output before using it.

Never assume raw AI output is valid.

### Step 6: Alert Decision

The application, not the AI alone, should make the final alert decision.

Example rules:

``` text
LOW:
- Store only
- No notification

MEDIUM:
- Telegram

HIGH:
- Telegram
- Future: push notification

CRITICAL:
- Immediate push and Telegram
- Future: start acknowledgment timer
- Future: phone call if not acknowledged
```

The AI provides a recommendation.

The application owns the final policy.

### Step 7: Deliver Notification

The notification router selects channels based on:

-   Importance level
-   User configuration
-   Available integrations

### Step 8: Persist Results

Store:

-   Article
-   Classification
-   Alert decision
-   Delivery result
-   Error information when applicable

------------------------------------------------------------------------

## 9. Telegram MVP

Telegram is the first notification channel.

The implementation should:

-   Use environment variables for credentials.
-   Never commit bot tokens.
-   Support sending formatted messages.
-   Handle delivery failures.
-   Log failures.
-   Save alert status to the database.

Required environment variables may include:

``` text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Example alert:

``` text
🚨 HIGH IMPACT MACRO NEWS

Fed signals rate cuts may be delayed

Why it matters:
Higher-for-longer interest rates may pressure growth and technology stocks.

Likely affected:
QQQ, NVDA, AMD, PLTR

Source:
Yahoo Finance
```

The original article URL should be included when available.

### As implemented

The message leads with the AI summary and "why it matters" (in
`OUTPUT_LANGUAGE`), then `Source:` and the article title — the title comes
last since it is also in the link. Two toggles control the link:
`ALERT_INCLUDE_LINK` (include the URL) and `ALERT_LINK_PREVIEW` (show
Telegram's preview thumbnail; off by default to keep messages short).

------------------------------------------------------------------------

## 10. Configuration

Configuration should come from environment variables and typed
application settings.

Suggested values:

``` text
APP_ENV=development

DATABASE_URL=sqlite:///./stockpulse.db

# Scheduling (two independent source cadences)
SCHEDULER_ENABLED=false
WATCHLIST_FETCH_INTERVAL_MINUTES=5
MACRO_FETCH_INTERVAL_MINUTES=30
MAX_CLASSIFICATIONS_PER_RUN=5
MAX_ALERTS_PER_RUN=20

# AI classifier
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OUTPUT_LANGUAGE=English

# Alerting
ALERT_MIN_IMPORTANCE=MEDIUM
ALERT_INCLUDE_LINK=true
ALERT_LINK_PREVIEW=false

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

WATCHLIST_FILE=watchlist.json
KEYWORDS_FILE=keywords.json
```

See `.env.example` for the authoritative, always-current list.

Create:

``` text
.env.example
```

Never commit:

``` text
.env
```

### Watchlist configuration (as implemented)

The watchlist needs both ticker symbols **and** company-name aliases
(e.g. `NVDA` should match "Nvidia"). That is a ticker-to-names mapping,
which does not fit cleanly in a single environment variable, so it lives
in a dedicated JSON file instead:

``` json
// watchlist.json  (git-ignored; copy from watchlist.example.json)
{
  "NVDA": ["Nvidia"],
  "MSFT": ["Microsoft"],
  "TSLA": ["Tesla"]
}
```

- `WATCHLIST_FILE` (env, default `watchlist.json`) points to this file.
- `watchlist.example.json` is committed as a template; `watchlist.json`
  is git-ignored, like `.env`.
- If the file is missing or invalid, the app falls back to built-in
  defaults, so it always runs.
- Loaded by `app/watchlist.py`; consumed by the rule filter.

Macro and sector keywords follow the same pattern in a separate
`keywords.json` file (`KEYWORDS_FILE`, default `keywords.json`), loaded by
`app/keyword_config.py`:

``` json
// keywords.json  (git-ignored; copy from keywords.example.json)
{
  "macro": ["Federal Reserve", "CPI", "tariff"],
  "sectors": { "AI/Semiconductor": ["AI", "semiconductor", "GPU"] }
}
```

Omitting a top-level key keeps the built-in default for that part; an empty
list/object disables it. So all rule-filter tuning — tickers, company
names, macro, and sector keywords — lives in two editable JSON files.

------------------------------------------------------------------------

## 11. Recommended Project Structure

``` text
stock-pulse/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   │
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── rss.py
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── normalizer.py
│   │   ├── deduplicator.py
│   │   ├── rule_filter.py
│   │   └── classifier.py
│   │
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── telegram.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── article.py
│   │   ├── classification.py
│   │   └── alert.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── models.py
│   │
│   └── jobs/
│       ├── __init__.py
│       └── news_monitor.py
│
├── tests/
│   ├── test_normalizer.py
│   ├── test_deduplicator.py
│   ├── test_rule_filter.py
│   └── test_classifier.py
│
├── alembic/
├── .env.example
├── .gitignore
├── watchlist.example.json   # template; copy to watchlist.json (git-ignored)
├── keywords.example.json    # template; copy to keywords.json (git-ignored)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── PROJECT_SPEC.md
├── TECHNICAL_PLAN.md
└── README.md
```

The AI may suggest small improvements, but should not significantly
change this structure without explaining why.

------------------------------------------------------------------------

## 12. Development Phases

# Phase 0 -- Project Foundation

Goal:

Create a clean, runnable Python project.

Tasks:

-   Initialize Python project.
-   Create `pyproject.toml`.
-   Add FastAPI.
-   Add application configuration.
-   Add `.env.example`.
-   Add `.gitignore`.
-   Create health check endpoint.
-   Add basic logging.
-   Add pytest configuration.
-   Confirm the app starts successfully.

Expected result:

``` text
GET /health
```

Returns a successful response.

No news collection or AI integration yet.

------------------------------------------------------------------------

# Phase 1 -- News Collection

Goal:

Collect real news articles from one source.

Tasks:

-   Define the `NewsArticle` model.
-   Define a collector interface.
-   Implement one RSS collector.
-   Normalize collected data.
-   Add unit tests.
-   Add a manual command or endpoint to test collection.

Important:

Use only one news source initially.

Do not add multiple APIs before the first source works correctly.

Expected result:

The application can fetch and print or return normalized recent
articles.

------------------------------------------------------------------------

# Phase 2 -- Persistence and Deduplication

Goal:

Store articles and prevent repeated processing.

Tasks:

-   Configure SQLite.
-   Add SQLAlchemy.
-   Add Alembic.
-   Create article table.
-   Save collected articles.
-   Implement duplicate checks.
-   Add tests.

Expected result:

Running the collector multiple times does not create duplicate article
records.

------------------------------------------------------------------------

# Phase 3 -- Rule-Based Filtering

Goal:

Reduce the number of articles sent to AI.

Tasks:

-   Add configurable watchlist.
-   Add company-name aliases.
-   Add macro keywords.
-   Implement relevance scoring or matching.
-   Store filter results when useful.
-   Add tests for relevant and irrelevant articles.

Expected result:

The system can separate likely relevant articles from obvious noise
without using AI.

------------------------------------------------------------------------

# Phase 4 -- AI Classification

Goal:

Classify filtered articles using structured AI output.

Tasks:

-   Define classifier interface.
-   Implement OpenAI classifier.
-   Define strict Pydantic output model.
-   Validate responses.
-   Handle API errors and invalid output.
-   Store classifications.
-   Add mocked tests.

Important:

Do not call the real AI API in normal unit tests.

Expected result:

A filtered article receives:

-   Relevance
-   Importance
-   Category
-   Related tickers
-   Summary
-   Why it matters
-   Alert recommendation

------------------------------------------------------------------------

# Phase 5 -- Alert Decision Engine

Goal:

Decide whether an alert should be sent.

Tasks:

-   Define alert policies.
-   Separate AI recommendation from application decision.
-   Map importance levels to channels.
-   Create alert records.
-   Add tests.

Expected result:

The system consistently decides:

``` text
LOW      → no alert
MEDIUM   → Telegram
HIGH     → Telegram
CRITICAL → Telegram for MVP
```

Future channels should be easy to add.

------------------------------------------------------------------------

# Phase 6 -- Telegram Notifications

Goal:

Send useful alerts to the user's phone.

Tasks:

-   Implement Telegram notifier.
-   Format alert messages.
-   Add source URL.
-   Handle errors.
-   Save delivery status.
-   Add mocked tests.

Expected result:

A HIGH-impact test article generates a real Telegram notification during
manual testing.

------------------------------------------------------------------------

# Phase 7 -- Scheduled End-to-End Pipeline

Goal:

Run StockPulse automatically.

Tasks:

-   Create `news_monitor` job.
-   Connect all pipeline stages.
-   Add APScheduler.
-   Make interval configurable.
-   Prevent overlapping job runs.
-   Add structured logs.
-   Handle individual article failures without stopping the full batch.

Expected result:

StockPulse automatically:

``` text
collects
→ normalizes
→ deduplicates
→ filters
→ classifies
→ decides
→ alerts
→ persists
```

------------------------------------------------------------------------

# Phase 8 -- Docker and CI

Goal:

Make the project easy to run and validate.

Tasks:

-   Add Dockerfile.
-   Add docker-compose configuration if useful.
-   Add GitHub Actions.
-   Run tests in CI.
-   Add linting and formatting.
-   Document local setup.

Expected result:

A new developer can clone the repository and run StockPulse using
documented steps.

------------------------------------------------------------------------

## 13. Future Phases

Do not implement these during the MVP unless explicitly requested.

### Push Notifications

Possible providers:

-   Pushover
-   ntfy

### Alert Acknowledgment

Allow the user to acknowledge a CRITICAL alert.

Possible flow:

``` text
CRITICAL alert
→ push notification
→ wait 2 minutes
→ if acknowledged: stop
→ if not acknowledged: escalate
```

### Phone Call Escalation

Possible provider:

-   Twilio

Only CRITICAL alerts should be eligible.

The phone call should be treated as an escalation mechanism, not a
normal notification channel.

### Dashboard

Possible stack:

-   Next.js
-   TypeScript
-   Tailwind CSS

Possible features:

-   Alert history
-   Article history
-   Watchlist management
-   Keyword management
-   Notification settings
-   System health

The dashboard should be a later phase.

------------------------------------------------------------------------

## 14. Testing Strategy

Tests should focus on business logic.

Required unit test areas:

-   Article normalization
-   Duplicate detection
-   Keyword filtering
-   Ticker matching
-   AI output validation
-   Alert decision rules
-   Notification formatting

External services should be mocked in automated tests.

Do not require:

-   Real OpenAI calls
-   Real Telegram messages
-   Real news API calls

for normal test execution.

Integration tests may be added separately.

------------------------------------------------------------------------

## 15. Logging and Error Handling

The service should produce useful logs for:

-   Job start and completion
-   Number of articles collected
-   Number of duplicates skipped
-   Number of articles passing filters
-   AI classification failures
-   Alerts sent
-   Notification failures

One bad article should not crash the entire monitoring cycle.

Example:

``` text
Collected: 50
Duplicates skipped: 31
Passed rule filter: 7
AI classified: 7
Alerts sent: 2
Failures: 0
```

Do not log secrets.

------------------------------------------------------------------------

## 16. Security Requirements

-   Never commit API keys.
-   Never commit Telegram bot tokens.
-   Use environment variables.
-   Add `.env` to `.gitignore`.
-   Validate external input.
-   Add reasonable HTTP timeouts.
-   Avoid storing unnecessary sensitive information.

------------------------------------------------------------------------

## 17. Cost Control Requirements

The MVP target is under \$10 per month.

To reduce cost:

-   Use free RSS sources first.
-   Filter before calling AI.
-   Avoid sending duplicate articles to AI.
-   Use a small/low-cost model suitable for classification.
-   Keep AI prompts concise.
-   Store classification results.
-   Do not reclassify unchanged articles.

------------------------------------------------------------------------

## 18. Definition of MVP Complete

The MVP is complete when StockPulse can:

1.  Run automatically on a schedule.
2.  Fetch news from at least one real source.
3.  Normalize articles.
4.  Prevent duplicate processing.
5.  Filter by watchlist and macro keywords.
6.  Use AI to classify relevant articles.
7.  Decide whether an alert is needed.
8.  Send Telegram notifications.
9.  Store article, classification, and alert history.
10. Run tests successfully.
11. Run locally with documented setup.
12. Stay within the low-cost design goal.

------------------------------------------------------------------------

## 19. Instructions for AI Coding Assistants

Before implementing any task:

1.  Read `PROJECT_SPEC.md`.
2.  Read this document.
3.  Identify the current development phase.
4.  Inspect the existing codebase.
5.  Do not rebuild working components unnecessarily.
6.  Propose a short implementation plan.
7.  Implement only the requested phase or task.
8.  Add or update tests.
9.  Run relevant tests.
10. Summarize what changed and any remaining issues.

The AI should not:

-   Build all phases at once.
-   Add a frontend during the MVP.
-   Add infrastructure that is not needed.
-   Replace the chosen stack without a clear reason.
-   Hardcode secrets.
-   Skip tests for core business logic.
-   Mix news collection, AI classification, and alert delivery into one
    large file.

The preferred development style is:

> Small phases, clear interfaces, testable components, and working
> software at the end of every phase.
