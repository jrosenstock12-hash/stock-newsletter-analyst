import re

from ingest.clean import clean_newsletter_text
from ingest.date import detect_date_in_text, normalize_date
from ingest.models import IngestResult
from ingest.source import finalize_ingest

SOURCE_URL_RE = re.compile(r"^Source URL:\s*(https?://\S+)\s*$", re.MULTILINE | re.IGNORECASE)
TITLE_RE = re.compile(r"^Title:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
DATE_RE = re.compile(
    r"^Date:\s*(\d{4}-\d{2}-\d{2}|[\w\s,]+)\s*$", re.MULTILINE | re.IGNORECASE
)


def _strip_markdown(text: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def parse_markdown_content(content: str, fallback_title: str = "") -> IngestResult:
    content = content.strip()
    if not content:
        raise ValueError("Markdown content is empty.")

    source_url = ""
    title = fallback_title.strip()
    article_date = ""

    if match := SOURCE_URL_RE.search(content):
        source_url = match.group(1).strip()
    if match := TITLE_RE.search(content):
        title = match.group(1).strip()
    if match := DATE_RE.search(content):
        article_date = normalize_date(match.group(1).strip())

    body = content
    for pattern in (SOURCE_URL_RE, TITLE_RE, DATE_RE):
        body = pattern.sub("", body)

    text = _strip_markdown(body)
    text = clean_newsletter_text(text)

    if len(text) < 100:
        raise ValueError(
            "Content looks too short after cleaning. Include the full article body."
        )

    if not article_date:
        article_date = detect_date_in_text(text)

    return finalize_ingest(
        IngestResult(
            title=title or "Markdown newsletter",
            text=text,
            source_type="paste",
            source_label=source_url or "uploaded markdown",
            article_date=article_date,
        )
    )


def parse_markdown_file(file_bytes: bytes) -> IngestResult:
    return parse_markdown_content(file_bytes.decode("utf-8", errors="replace"))
