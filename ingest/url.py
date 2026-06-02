import re
import subprocess
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx
import trafilatura

from config import USER_AGENT
from ingest.clean import clean_newsletter_text
from ingest.date import normalize_date
from ingest.models import IngestResult

TRACKING_QUERY_PREFIXES = ("_gl", "utm_", "fbclid", "gclid", "mc_", "ref")


def normalize_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    query = parse_qs(parsed.query, keep_blank_values=False)
    filtered = [
        f"{key}={value[0]}"
        for key, value in query.items()
        if not key.startswith(TRACKING_QUERY_PREFIXES)
    ]
    clean_query = "&".join(filtered)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, "")
    )


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _fetch_html_httpx(url: str) -> str:
    with httpx.Client(
        follow_redirects=True,
        timeout=45.0,
        headers=_browser_headers(),
        trust_env=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _fetch_html_curl(url: str) -> str:
    result = subprocess.run(
        [
            "curl",
            "-sL",
            "-A",
            USER_AGENT,
            "--max-time",
            "45",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            f"Could not download the page (curl exit {result.returncode}). "
            "Try pasting the newsletter content instead."
        )
    if not result.stdout.strip():
        raise ValueError("Downloaded page was empty. Try pasting the content instead.")
    return result.stdout


def _fetch_html(url: str) -> str:
    try:
        return _fetch_html_httpx(url)
    except httpx.HTTPError:
        return _fetch_html_curl(url)


def _substack_hint(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "substack.com" in host or host.endswith(".substack.com"):
        return (
            " Substack newsletters (like SemiAnalysis) often require you to be "
            "logged in as a subscriber — if the link fails or returns a preview, "
            "open the post in your browser, select all (Cmd+A), copy, and paste."
        )
    return ""


def fetch_url(url: str) -> IngestResult:
    url = normalize_url(url.strip())
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    try:
        html = _fetch_html(url)
    except httpx.HTTPStatusError as exc:
        hint = _substack_hint(url)
        if exc.response.status_code in {401, 403, 404}:
            raise ValueError(
                f"Could not access this URL (HTTP {exc.response.status_code}).{hint}"
            ) from exc
        raise ValueError(f"Could not download URL: {exc}") from exc
    except ValueError:
        raise
    except Exception as exc:
        hint = _substack_hint(url)
        raise ValueError(
            f"Could not download this URL.{hint} Details: {exc}"
        ) from exc

    downloaded = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        output_format="txt",
    )
    metadata = trafilatura.extract_metadata(html, default_url=url)

    title = (metadata.title if metadata and metadata.title else "") or url
    text = clean_newsletter_text(downloaded or "")

    if len(text) < 150:
        hint = _substack_hint(url)
        raise ValueError(
            "Could not extract enough article text from this URL. "
            "The page may be paywalled, subscriber-only, or JavaScript-only."
            f"{hint}"
        )

    article_date = ""
    if metadata and metadata.date:
        article_date = normalize_date(metadata.date)

    return IngestResult(
        title=title,
        text=text,
        source_type="url",
        source_label=url,
        article_date=article_date,
    )
