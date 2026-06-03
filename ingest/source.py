"""Derive a human-readable publication/source name from ingest metadata."""
from __future__ import annotations

import re
from urllib.parse import urlparse

# hostname fragment -> display name
KNOWN_HOSTS: dict[str, str] = {
    "semianalysis": "SemiAnalysis",
    "stratechery": "Stratechery",
    "notboring": "Not Boring",
    "marginalrevolution": "Marginal Revolution",
    "bloomberg": "Bloomberg",
    "wsj": "Wall Street Journal",
    "ft.com": "Financial Times",
    "substack": "Substack",
}

# Patterns in pasted email/newsletter bodies
PASTE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"semianalysis", re.I), "SemiAnalysis"),
    (re.compile(r"stratechery", re.I), "Stratechery"),
    (re.compile(r"not\s*boring", re.I), "Not Boring"),
    (re.compile(r"substack", re.I), "Substack"),
]


def _title_case_slug(slug: str) -> str:
    parts = re.split(r"[-_]+", slug.strip())
    return " ".join(p.capitalize() for p in parts if p)


def _from_hostname(host: str) -> str:
    host = host.lower().removeprefix("www.")
    for key, name in KNOWN_HOSTS.items():
        if key in host:
            if key == "substack":
                continue
            return name

    labels = host.split(".")
    if len(labels) >= 3 and labels[-2] == "substack":
        return _title_case_slug(labels[0])

    if labels[0] == "newsletter" and len(labels) >= 2:
        return _title_case_slug(labels[1])

    if len(labels) >= 2:
        return _title_case_slug(labels[0])

    return _title_case_slug(host.split(".")[0])


def _from_url(source_label: str) -> str:
    text = source_label.strip()
    if not text.startswith("http"):
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    if not parsed.netloc:
        return ""
    return _from_hostname(parsed.netloc)


def _from_email(source_label: str) -> str:
    match = re.search(r"@[\w.-]+\.(\w+)", source_label)
    if not match:
        return "Email"
    domain = source_label.lower()
    for key, name in KNOWN_HOSTS.items():
        if key in domain:
            return name
    return "Email"


def _from_paste(text: str) -> str:
    head = text[:4000]
    for pattern, name in PASTE_PATTERNS:
        if pattern.search(head):
            return name
    url_match = re.search(r"https?://[^\s<>\"']+", head)
    if url_match:
        derived = _from_url(url_match.group(0))
        if derived:
            return derived
    return "Pasted newsletter"


def derive_source_name(
    *,
    source_type: str,
    source_label: str,
    text: str = "",
) -> str:
    if source_type == "url":
        name = _from_url(source_label)
        return name or "Web article"
    if source_type == "email":
        return _from_email(source_label)
    if source_type == "paste":
        if source_label.startswith("http"):
            name = _from_url(source_label)
            if name:
                return name
        return _from_paste(text)
    return "Unknown"


def finalize_ingest(ingest) -> "IngestResult":
    """Attach source_name if missing."""
    from dataclasses import replace

    from ingest.models import IngestResult

    if ingest.source_name:
        return ingest
    return replace(
        ingest,
        source_name=derive_source_name(
            source_type=ingest.source_type,
            source_label=ingest.source_label,
            text=ingest.text,
        ),
    )
