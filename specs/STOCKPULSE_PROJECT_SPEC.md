# StockPulse -- Project Specification

## 1. Project Goal

Build a lightweight market intelligence service that monitors
stock-related news and macroeconomic events, then sends alerts when
important news may affect the broader market or selected stocks.

The first version should be simple, low-cost, and easy to maintain.

## 2. Main Use Case

The user wants to receive fast alerts for important market news without
manually checking news all day.

Example events:

-   CPI / inflation report
-   Fed rate decision or Powell speech
-   Jobs report
-   Tariff news
-   War or geopolitical news
-   Oil spike
-   Major earnings or guidance changes
-   Breaking news related to selected tickers

## 3. Target Stocks / Assets

Initial watchlist:

-   QQQ / QQQM
-   VOO
-   NVDA
-   AMD
-   PLTR
-   SOFI
-   HOOD
-   META
-   AMZN

The watchlist should be configurable.

## 4. News Categories

### Macro

News affecting the whole market:

-   Fed
-   Interest rates
-   Inflation
-   CPI / PPI
-   Jobs report
-   GDP
-   Treasury yields
-   Tariffs
-   Oil
-   War / geopolitical risk

### Ticker-Specific

News related to a specific company:

-   Earnings
-   Guidance
-   SEC investigation
-   Product launch
-   Partnership
-   Analyst upgrade or downgrade
-   Insider selling
-   Lawsuit
-   Layoffs

### Sector

News affecting a group of stocks:

-   AI / semiconductor
-   Banks
-   Crypto
-   Consumer tech
-   Energy

## 5. Alert Levels

### LOW

Log only. Do not notify.

### MEDIUM

Send a push notification or Telegram message.

### HIGH

Send a push notification plus Telegram or email.

### CRITICAL

Send a push notification immediately. If the user does not acknowledge
within 2 minutes, trigger a phone call alert.

## 6. Recommended MVP Stack

### Language

-   Python

### News Sources

Start with free RSS feeds:

-   Yahoo Finance RSS
-   Google News RSS

Optional later:

-   Finnhub
-   Polygon
-   Benzinga
-   Alpha Vantage

### Alert Channels

-   Telegram Bot for MVP
-   Pushover or ntfy for phone push notifications
-   Twilio for phone calls later

### Storage

-   Start with a local JSON file or SQLite
-   Store already-seen news IDs or URLs to prevent duplicate alerts

### Hosting

-   Local machine for testing
-   Later: small VPS, Render, Railway, Fly.io, or DigitalOcean

## 7. Basic System Flow

1.  StockPulse runs every 5--15 minutes.
2.  Pull the latest news from configured sources.
3.  Remove duplicate or already-seen news.
4.  Apply a keyword filter.
5.  Send only relevant articles to the AI classifier.
6.  AI returns:
    -   category
    -   related tickers
    -   importance level
    -   short summary
    -   reason why it matters
7.  If importance is MEDIUM or higher, send an alert.
8.  Save the article URL or title as seen.

## 8. Example Alert Message

``` text
🚨 HIGH IMPACT MACRO NEWS

Title:
Fed signals rate cuts may be delayed

Why it matters:
Higher-for-longer interest rates may pressure growth and tech stocks.

Likely affected:
QQQ, NVDA, AMD, PLTR

Action:
Watch bond yields and market reaction.

Source:
Yahoo Finance
```

## 9. AI Classifier Output Format

The AI should return structured JSON:

``` json
{
  "is_market_relevant": true,
  "importance": "HIGH",
  "category": "MACRO",
  "related_tickers": ["QQQ", "NVDA", "AMD"],
  "summary": "Fed comments suggest rate cuts may be delayed.",
  "why_it_matters": "Higher rates can pressure tech and growth stocks.",
  "should_alert": true
}
```

## 10. Important Requirements

-   Avoid duplicate alerts.
-   Do not alert on every small article.
-   Only alert when news is actionable or potentially market-moving.
-   Keep cost low by filtering with keywords before using AI.
-   Make the watchlist and keywords configurable.
-   Log all processed news for debugging.
-   Start simple, then improve.

## 11. Future Features

-   Web dashboard to view alerts
-   Add or remove tickers
-   Daily market summary
-   Pre-market and after-hours summary
-   Earnings calendar integration
-   Economic calendar integration
-   Price movement confirmation
-   Critical alert phone call
-   Acknowledge button for alerts
-   Backtesting to check whether alerts matched actual price moves

## 12. MVP Success Criteria

The MVP is successful if:

-   It checks news automatically.
-   It detects important macro and ticker-specific news.
-   It sends Telegram alerts.
-   It avoids duplicate alerts.
-   It runs without manual work.
-   Monthly cost stays under \$10.
