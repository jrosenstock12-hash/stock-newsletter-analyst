from email import policy
from email.parser import BytesParser
from pathlib import Path

from bs4 import BeautifulSoup

from ingest.clean import clean_newsletter_text
from ingest.date import detect_date_in_text, parse_email_date_header
from ingest.models import IngestResult
from ingest.source import finalize_ingest
from ingest.title import detect_title


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def parse_pasted_content(content: str, title: str = "") -> IngestResult:
    content = content.strip()
    if not content:
        raise ValueError("Pasted content is empty.")

    if content.lstrip().startswith("<"):
        text = _html_to_text(content)
    else:
        text = content

    text = clean_newsletter_text(text)
    if len(text) < 100:
        raise ValueError(
            "Content looks too short after cleaning. Paste the full newsletter body."
        )

    resolved_title = title.strip() or detect_title(content)

    return finalize_ingest(
        IngestResult(
            title=resolved_title,
            text=text,
            source_type="paste",
            source_label="pasted content",
            article_date=detect_date_in_text(text),
        )
    )


def parse_eml_file(file_bytes: bytes) -> IngestResult:
    msg = BytesParser(policy=policy.default).parsebytes(file_bytes)

    subject = msg.get("Subject", "Email newsletter")
    parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_content()
                if isinstance(payload, str):
                    parts.append(payload)
            elif content_type == "text/html" and not parts:
                payload = part.get_content()
                if isinstance(payload, str):
                    parts.append(_html_to_text(payload))
    else:
        content_type = msg.get_content_type()
        payload = msg.get_content()
        if isinstance(payload, str):
            if content_type == "text/html":
                parts.append(_html_to_text(payload))
            else:
                parts.append(payload)

    if not parts:
        raise ValueError("Could not extract readable text from the .eml file.")

    text = clean_newsletter_text("\n\n".join(parts))
    if len(text) < 100:
        raise ValueError("Email body is too short after cleaning.")

    return finalize_ingest(
        IngestResult(
            title=subject,
            text=text,
            source_type="email",
            source_label=msg.get("From", "uploaded .eml"),
            article_date=parse_email_date_header(msg.get("Date")),
        )
    )


def parse_eml_path(path: str | Path) -> IngestResult:
    return parse_eml_file(Path(path).read_bytes())
