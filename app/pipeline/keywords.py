"""Default keyword and alias data for rule-based relevance filtering.

These are the built-in fallbacks. At runtime they are overridden by the
editable config files: aliases/tickers via ``watchlist.json`` (loaded by
``app.watchlist``) and macro/sector keywords via ``keywords.json`` (loaded
by ``app.keyword_config``). The defaults here are used when a file is
missing or invalid.
"""

# Ticker -> company name aliases (matched case-insensitively as whole words).
DEFAULT_COMPANY_ALIASES: dict[str, list[str]] = {
    "QQQ": ["Invesco QQQ", "Nasdaq 100", "Nasdaq-100"],
    "QQQM": ["Invesco Nasdaq 100"],
    "VOO": ["Vanguard S&P 500", "S&P 500"],
    "NVDA": ["Nvidia"],
    "AMD": ["Advanced Micro Devices"],
    "PLTR": ["Palantir"],
    "SOFI": ["SoFi", "SoFi Technologies"],
    "HOOD": ["Robinhood"],
    "META": ["Meta", "Meta Platforms", "Facebook", "Instagram", "WhatsApp"],
    "AMZN": ["Amazon", "AWS"],
}

# Macro / market-wide keywords (matched case-insensitively as whole words).
DEFAULT_MACRO_KEYWORDS: list[str] = [
    "Federal Reserve",
    "Fed",
    "FOMC",
    "Powell",
    "interest rate",
    "rate cut",
    "rate hike",
    "CPI",
    "PPI",
    "inflation",
    "jobs report",
    "nonfarm payroll",
    "unemployment",
    "GDP",
    "Treasury yield",
    "tariff",
    "tariffs",
    "sanctions",
    "oil",
    "crude",
    "geopolitical",
    "war",
]

# Sector -> keywords. A match on any keyword flags that sector.
DEFAULT_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "AI/Semiconductor": [
        "AI",
        "artificial intelligence",
        "semiconductor",
        "chip",
        "chips",
        "GPU",
        "data center",
    ],
    "Banks": ["bank", "banks", "banking"],
    "Crypto": ["crypto", "cryptocurrency", "bitcoin", "ethereum"],
    "Energy": ["oil", "crude", "energy"],
}
