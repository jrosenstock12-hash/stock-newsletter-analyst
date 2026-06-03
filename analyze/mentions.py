"""Detect whether a company is actually named in article text."""

import re

from analyze.schema import CompanyOpinion
from analyze.tickers import detect_tickers

NAME_STOPWORDS = {
    "inc",
    "corp",
    "corporation",
    "ltd",
    "llc",
    "plc",
    "co",
    "company",
    "technologies",
    "technology",
    "holdings",
    "group",
    "the",
    "and",
}

NOT_MENTIONED_RE = re.compile(
    r"""
    not\s+(?:directly\s+|explicitly\s+)?mentioned
    | not\s+discussed
    | not\s+referenced
    | not\s+cited
    | not\s+named
    | no\s+mention\s+of
    | (?:while|although|though)\s+not\s+(?:directly\s+)?mentioned
    | (?:was|were|is|are)\s+not\s+(?:directly\s+)?mentioned
    | (?:does|do)\s+not\s+(?:directly\s+)?mention
    """,
    re.VERBOSE | re.IGNORECASE,
)


def opinion_claims_not_mentioned(opinion: CompanyOpinion) -> bool:
    combined = f"{opinion.article_says} {opinion.rationale}"
    return bool(NOT_MENTIONED_RE.search(combined))


def _significant_name_tokens(company_name: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z]{3,}", company_name)
    out: list[str] = []
    for token in tokens:
        if token.lower() not in NAME_STOPWORDS:
            out.append(token)
    return out


def _known_names_for_ticker(ticker: str) -> list[str]:
    from analyze.companies import KNOWN_PUBLIC

    names: list[str] = []
    upper = ticker.upper()
    for key, known in KNOWN_PUBLIC.items():
        if known and known[0].upper() == upper:
            names.append(key)
    return names


def company_mentioned_in_article(
    article_text: str,
    ticker: str,
    company_name: str,
) -> bool:
    if not article_text.strip():
        return False

    lower = article_text.lower()
    upper_ticker = (ticker or "").upper().strip()

    for name in _known_names_for_ticker(upper_ticker):
        if re.search(rf"\b{re.escape(name)}\b", lower):
            return True

    for token in _significant_name_tokens(company_name):
        if len(token) >= 4 and re.search(
            rf"\b{re.escape(token)}\b", article_text, re.IGNORECASE
        ):
            return True

    if not upper_ticker:
        return False

    if re.search(rf"\${re.escape(upper_ticker)}\b", article_text):
        return True
    if re.search(
        rf"\((?:NYSE|NASDAQ|AMEX|OTC):\s*{re.escape(upper_ticker)}\)",
        article_text,
        re.IGNORECASE,
    ):
        return True

    detected = set(detect_tickers(article_text))
    if upper_ticker in detected:
        return True

    if len(upper_ticker) >= 5 and re.search(
        rf"\b{re.escape(upper_ticker)}\b", article_text
    ):
        return True

    return False


def filter_company_opinions(
    article_text: str,
    opinions: list[CompanyOpinion],
) -> list[CompanyOpinion]:
    kept: list[CompanyOpinion] = []
    for opinion in opinions:
        if opinion_claims_not_mentioned(opinion):
            continue
        if not company_mentioned_in_article(
            article_text, opinion.ticker, opinion.company_name
        ):
            continue
        kept.append(opinion)
    return kept
