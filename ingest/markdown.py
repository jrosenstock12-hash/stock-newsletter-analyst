import re

from ingest.clean import clean_newsletter_text
from ingest.models import IngestResult

SOURCE_URL_RE = re.compile(r"^Source URL:\s*(https?://\S+)\s*$", re.MULTILINE | re.IGNORECASE)
TITLE_RE = re.compile(r"^Title:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


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

    if match := SOURCE_URL_RE.search(content):
        source_url = match.group(1).strip()
    if match := TITLE_RE.search(content):
        title = match.group(1).strip()

    body = content
    for pattern in (SOURCE_URL_RE, TITLE_RE):
        body = pattern.sub("", body)

    text = _strip_markdown(body)
    text = clean_newsletter_text(text)

    if len(text) < 100:
        raise ValueError(
            "Content looks too short after cleaning. Include the full article body."
        )

    return IngestResult(
        title=title or "Markdown newsletter",
        text=text,
        source_type="paste",
        source_label=source_url or "uploaded markdown",
    )


def parse_markdown_file(file_bytes: bytes) -> IngestResult:
    return parse_markdown_content(file_bytes.decode("utf-8", errors="replace"))
