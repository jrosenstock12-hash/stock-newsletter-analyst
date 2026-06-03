import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from analyze.mentions import company_mentioned_in_article
from config import USER_AGENT

YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
PUBLIC_QUOTE_TYPES = {"EQUITY", "ETF"}
MAX_LLM_COMPANY_NAMES = 18
MAX_YAHOO_LOOKUPS = 8
YAHOO_TIMEOUT_SEC = 8.0

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


MAX_COMPANIES_FOR_ANALYSIS = 8


def target_summary_words(article_text: str, *, company_count: int = 0) -> int:
    """~3–5 min read at ~200 wpm; scales with article length."""
    word_count = len(article_text.split())
    target = int(word_count * 0.18)
    cap = 750 if company_count > 5 else 950
    return max(400, min(target, cap))


def _yahoo_search(query: str) -> list[dict]:
    with httpx.Client(
        trust_env=False,
        timeout=YAHOO_TIMEOUT_SEC,
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


def known_companies_from_text(article_text: str) -> list[PublicCompany]:
    """Resolve well-known names from article text without Yahoo API calls."""
    seen: set[str] = set()
    resolved: list[PublicCompany] = []
    lower = article_text.lower()
    for key, known in KNOWN_PUBLIC.items():
        if known is None:
            continue
        if re.search(rf"\b{re.escape(key)}\b", lower):
            ticker, display = known
            if ticker not in seen:
                seen.add(ticker)
                resolved.append(
                    PublicCompany(name=display, ticker=ticker, source="known")
                )
    return resolved


def resolve_company_names(
    names: list[str], *, max_yahoo: int = MAX_YAHOO_LOOKUPS
) -> list[PublicCompany]:
    seen: set[str] = set()
    resolved: list[PublicCompany] = []
    yahoo_lookups = 0
    pending_yahoo: list[str] = []

    for name in names:
        cleaned = name.strip()
        if not cleaned or len(cleaned) < 2:
            continue
        key = cleaned.lower()
        if key in KNOWN_PUBLIC:
            known = KNOWN_PUBLIC[key]
            if known is None:
                continue
            ticker, display = known
            if ticker not in seen:
                seen.add(ticker)
                resolved.append(
                    PublicCompany(name=display, ticker=ticker, source="known")
                )
            continue
        if cleaned.upper() in seen:
            continue
        if yahoo_lookups < max_yahoo:
            pending_yahoo.append(cleaned)
            yahoo_lookups += 1

    if pending_yahoo:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(resolve_company_name, n): n for n in pending_yahoo
            }
            for future in as_completed(futures):
                try:
                    company = future.result()
                except Exception:
                    continue
                if company and company.ticker not in seen:
                    seen.add(company.ticker)
                    resolved.append(company)

    return resolved


def extract_company_names_llm(client, model: str, article_text: str) -> list[str]:
    """Ask the model for organization names mentioned in the article."""
    excerpt = article_text[:30000]
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract company, corporation, or brand names that appear explicitly "
                    "in the article text and could be publicly traded. Do NOT infer "
                    "companies that might be affected but are not named. Include index "
                    "nicknames only if stated (e.g. Magnificent 7). "
                    'Return JSON only: {"companies": ["Name1", "Name2"]}. No commentary.'
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
    names = [str(c).strip() for c in companies if c and str(c).strip()]
    return names[:MAX_LLM_COMPANY_NAMES]


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
    companies = known_companies_from_text(article_text)
    seen = {c.ticker for c in companies}

    names = extract_company_names_llm(client, model, article_text)

    for ticker in detected_tickers:
        if ticker not in seen:
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

    for company in resolve_company_names(names):
        if company.ticker not in seen:
            seen.add(company.ticker)
            companies.append(company)

    if re.search(r"magnificent\s*7|mag\s*7|mag7", article_text, re.I):
        companies = enrich_mag7(companies)

    companies = [
        c
        for c in companies
        if company_mentioned_in_article(article_text, c.ticker, c.name)
    ]

    if not companies:
        return [], "No public companies resolved via Yahoo Finance."

    companies = companies[:MAX_COMPANIES_FOR_ANALYSIS]
    lines = [c.to_prompt_line() for c in companies]
    return companies, "Verified public listings (Yahoo Finance):\n" + "\n".join(
        f"- {line}" for line in lines
    )
