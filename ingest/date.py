"""Extract and format article dates from ingest sources."""
from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime


def normalize_date(value: datetime | str | None) -> str:
    """Return YYYY-MM-DD or empty string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return ""
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(text[:19] if "T" in fmt else text, fmt).strftime(
                "%Y-%m-%d"
            )
        except ValueError:
            continue
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


def parse_email_date_header(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return normalize_date(parsedate_to_datetime(raw))
    except (TypeError, ValueError, OverflowError):
        return ""


def detect_date_in_text(text: str, limit: int = 2000) -> str:
    """Heuristic: find a date near the top of pasted content."""
    head = text[:limit]
    patterns = [
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
        r"\d{4}-\d{2}-\d{2}",
    ]
    for pattern in patterns:
        if match := re.search(pattern, head, re.IGNORECASE):
            return normalize_date(match.group(0))
    return ""


def format_display_title(title: str, article_date: str = "") -> str:
    title = title.strip()
    if article_date and article_date not in title:
        return f"{article_date} — {title}"
    return title
