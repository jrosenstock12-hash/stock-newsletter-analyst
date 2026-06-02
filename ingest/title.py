import re

SKIP_EXACT = {
    "semianalysis",
    "subscribe",
    "sign in",
    "share",
    "restacks",
    "comments",
    "previous",
    "ready for more?",
    "start your substack",
    "get the app",
}

AUTHOR_RE = re.compile(
    r"^[A-Z][A-Z0-9\s,'\.\-&]+$",
)
DATE_RE = re.compile(
    r"^(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+\d{1,2},?\s+\d{4}$",
    re.IGNORECASE,
)


def detect_title(raw_text: str) -> str:
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() in SKIP_EXACT:
            continue
        if stripped.isdigit():
            continue
        if len(stripped) < 12 or len(stripped) > 220:
            continue
        if DATE_RE.match(stripped):
            continue
        if AUTHOR_RE.match(stripped) and len(stripped.split()) >= 2:
            continue
        if stripped.lower().startswith("source:"):
            continue
        return stripped

    return "Pasted newsletter"
