import json
import re

import httpx

from config import USER_AGENT

YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
PUBLIC_QUOTE_TYPES = {"EQUITY", "ETF"}

# Well-known names articles reference without tickers
KNOWN_PUBLIC = {
    "apple": ("AAPL", "Apple Inc."),
    "microsoft": ("MSFT", "Microsoft Corporation"),
    "google": ("GOOGL", "Alphabet Inc."),
    "alphabet": ("GOOGL", "Alphabet Inc."),
    "amazon": ("AMZN", "Amazon.com Inc."),
    "meta": ("META", "Meta Platforms Inc."),
    "facebook": ("META", "Meta Platforms Inc."),
    "nvidia": ("NVDA", "NVIDIA Corporation"),
    "tesla": ("TSLA", "Tesla Inc."),
    "anthropic": None,  # private
    "openai": None,
    "magnificent 7": None,
    "mag 7": None,
    "mag7": None,
}


class PublicCompany:
    def __init__(
        self,
        *,
        name: str,
        ticker: str,
        exchange: str = "",
        quote_type: str = "EQUITY",
        sector: str = "",
        source: str = "yahoo",
    ):
        self.name = name
        self.ticker = ticker
        self.exchange = exchange
        self.quote_type = quote_type
        self.sector = sector
        self.source = source

    def to_prompt_line(self) -> str:
        parts = [f"{self.ticker} ({self.name})"]
        if self.exchange:
            parts.append(f"exchange: {self.exchange}")
        if self.sector:
            parts.append(f"sector: {self.sector}")
        return " — ".join(parts)


def target_summary_words(article_text: str) -> int:
    """~3–5 min read at ~200 wpm; scales with article length."""
    word_count = len(article_text.split())
    # Roughly 18–22% of article length, bounded for read time
    target = int(word_count * 0.20)
    return max(500, min(target, 1200))


def _yahoo_search(query: str) -> list[dict]:
    with httpx.Client(
        trust_env=False,
        timeout=15.0,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = client.get(
            YAHOO_SEARCH_URL,
            params={"q": query, "quotesCount": 5, "newsCount": 0},
        )
        response.raise_for_status()
        data = response.json()

    quotes = data.get("quotes", [])
    results = []
    for q in quotes:
        quote_type = (q.get("quoteType") or "").upper()
        symbol = q.get("symbol", "")
        if not symbol or quote_type not in PUBLIC_QUOTE_TYPES:
            continue
        results.append(
            {
                "ticker": symbol.upper(),
                "name": q.get("longname") or q.get("shortname") or query,
                "exchange": q.get("exchange", ""),
                "quote_type": quote_type,
                "sector": q.get("sector", "") or "",
            }
        )
    return results


def resolve_company_name(name: str) -> PublicCompany | None:
    cleaned = name.strip()
    if not cleaned or len(cleaned) < 2:
        return None

    key = cleaned.lower()
    if key in KNOWN_PUBLIC:
        known = KNOWN_PUBLIC[key]
        if known is None:
            return None
        ticker, display = known
        return PublicCompany(name=display, ticker=ticker, source="known")

    try:
        hits = _yahoo_search(cleaned)
    except Exception:
        return None

    if not hits:
        return None

    best = hits[0]
    return PublicCompany(
        name=best["name"],
        ticker=best["ticker"],
        exchange=best.get("exchange", ""),
        quote_type=best.get("quote_type", "EQUITY"),
        sector=best.get("sector", ""),
        source="yahoo",
    )


def resolve_company_names(names: list[str]) -> list[PublicCompany]:
    seen: set[str] = set()
    resolved: list[PublicCompany] = []

    for name in names:
        company = resolve_company_name(name)
        if company and company.ticker not in seen:
            seen.add(company.ticker)
            resolved.append(company)

    return resolved


def extract_company_names_llm(client, model: str, article_text: str) -> list[str]:
    """Ask the model for organization names mentioned in the article."""
    excerpt = article_text[:50000]
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract every company, corporation, or brand name mentioned in the "
                    "article that could be a publicly traded business. Include tech firms, "
                    "banks, utilities, AI vendors, and index nicknames (e.g. Magnificent 7). "
                    "Return JSON only: {\"companies\": [\"Name1\", \"Name2\"]}. "
                    "No commentary."
                ),
            },
            {"role": "user", "content": excerpt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    companies = data.get("companies", [])
    if not isinstance(companies, list):
        return []
    return [str(c).strip() for c in companies if c and str(c).strip()]


def enrich_mag7(companies: list[PublicCompany]) -> list[PublicCompany]:
    """If article references Mag 7, ensure all seven are in the list."""
    mag7_names = [
        ("AAPL", "Apple Inc."),
        ("MSFT", "Microsoft Corporation"),
        ("GOOGL", "Alphabet Inc."),
        ("AMZN", "Amazon.com Inc."),
        ("META", "Meta Platforms Inc."),
        ("NVDA", "NVIDIA Corporation"),
        ("TSLA", "Tesla Inc."),
    ]
    seen = {c.ticker for c in companies}
    for ticker, name in mag7_names:
        if ticker not in seen:
            seen.add(ticker)
            companies.append(
                PublicCompany(name=name, ticker=ticker, source="mag7")
            )
    return companies


def build_public_company_context(
    client,
    model: str,
    article_text: str,
    detected_tickers: list[str],
) -> tuple[list[PublicCompany], str]:
    names = extract_company_names_llm(client, model, article_text)

    # Also try resolving detected tickers as company names
    for ticker in detected_tickers:
        names.append(ticker)

    if re.search(r"magnificent\s*7|mag\s*7|mag7", article_text, re.I):
        names.extend(
            [
                "Apple",
                "Microsoft",
                "Alphabet",
                "Amazon",
                "Meta",
                "NVIDIA",
                "Tesla",
            ]
        )

    companies = resolve_company_names(names)
    if re.search(r"magnificent\s*7|mag\s*7|mag7", article_text, re.I):
        companies = enrich_mag7(companies)

    if not companies:
        return [], "No public companies resolved via Yahoo Finance."

    lines = [c.to_prompt_line() for c in companies]
    return companies, "Verified public listings (Yahoo Finance):\n" + "\n".join(
        f"- {line}" for line in lines
    )
