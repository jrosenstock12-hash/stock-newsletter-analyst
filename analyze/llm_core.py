from typing import Any

from openai import OpenAI

from analyze.companies import build_public_company_context, target_summary_words
from analyze.schema import StockAnalysis
from analyze.tickers import detect_tickers
from config import get_openai_api_key, get_openai_model
from db.database import get_analysis, save_analysis, update_analysis
from ingest.date import format_display_title, normalize_date
from ingest.models import IngestResult
from ingest.source import finalize_ingest

SYSTEM_PROMPT = """You are a financial research assistant analyzing newsletters and articles for public stock implications.

Rules:
1. Clearly separate what the ARTICLE states vs your AI opinion derived from that content.
2. Identify ALL publicly traded companies relevant to the article — use the verified Yahoo Finance list provided even when the article omits ticker symbols.
3. Provide a company_opinion (buy/hold/sell/avoid) for EACH verified public company that the article discusses or that is materially impacted by its thesis.
4. For each company_opinion (max 8 tickers; omit tickers the article does not materially discuss):
   - article_says: a full paragraph (5-8 sentences) summarizing what the author said about
     this stock — include specific metrics, trends, Bedrock/TaaS/capacity details, and
     comparisons to peers when present in the article. Only use 2-3 sentences if the
     company is mentioned in passing.
   - rationale: 3-5 sentences with buy/hold/sell/avoid and clear reasoning tied to article_says.
5. Write detailed_summary as a narrative within the target word count — not a bullet list.
6. executive_summary is only 2-4 sentences for a quick skim.
7. Set article_date to YYYY-MM-DD when the publish date appears in the article; otherwise leave empty.
8. Be conservative with ratings when evidence is weak, promotional, or macro-only.
9. Do not invent facts, prices, or events not supported by the article.
10. Do NOT produce an overall article-level buy/sell rating — only per-stock opinions in company_opinions.
11. At most 8 company_opinions — only tickers the article materially discusses; do not
    include peripheral hardware suppliers (e.g. NVIDIA) unless the author analyzes them."""

USER_PROMPT_TEMPLATE = """Analyze this article/newsletter for public stock implications.

Source: {source_label}
Known article date (if any): {article_date_hint}
Target detailed_summary length: ~{target_words} words ({read_time} minute read)
Regex-detected tickers (may be incomplete): {tickers}

{public_companies_block}

--- ARTICLE TEXT ---
{text}
--- END ---

Return structured analysis with:
- title: concise article title (no date prefix)
- article_date: YYYY-MM-DD if known
- executive_summary: 2-4 sentences
- detailed_summary: ~{target_words} word narrative (3-5 min read)
- company_opinions: up to 8 entries; substantive article_says paragraphs per ticker"""


def _make_client() -> OpenAI:
    api_key = get_openai_api_key()
    if not api_key or api_key in ("sk-...", "sk-your-key-here"):
        raise ValueError(
            "OPENAI_API_KEY is not set. Edit ~/stock-newsletter-analyst/.env "
            "and add your key from platform.openai.com/api-keys"
        )
    return OpenAI(api_key=api_key, timeout=300.0)


def _friendly_error(exc: Exception) -> ValueError:
    err = str(exc).lower()
    if "insufficient_quota" in err or "exceeded your current quota" in err:
        return ValueError(
            "OpenAI billing is not set up or you're out of credits. "
            "Go to platform.openai.com/settings/organization/billing "
            "→ add a payment method and at least $5 credit, then retry."
        )
    if "connection" in err or "connect" in err:
        return ValueError(
            "Could not reach OpenAI. Run the app from Terminal: "
            "cd ~/stock-newsletter-analyst && ./start.sh"
        )
    if "authentication" in err or "api key" in err or "401" in err:
        return ValueError(
            "OpenAI rejected your API key. Check ~/stock-newsletter-analyst/.env"
        )
    if "length limit" in err or "length_limit" in err:
        return ValueError(
            "Analysis output was too long and got cut off. "
            "Retry once; if it persists, paste a shorter excerpt of the article."
        )
    return ValueError(str(exc))


def test_connection() -> str:
    client = _make_client()
    response = client.chat.completions.create(
        model=get_openai_model(),
        messages=[{"role": "user", "content": "Reply with exactly: connected"}],
        max_tokens=5,
    )
    return response.choices[0].message.content or "connected"


def _read_time_minutes(word_target: int) -> str:
    minutes = word_target / 220
    if minutes < 3.5:
        return "3-4"
    if minutes < 4.5:
        return "4-5"
    return "5"


def _resolve_article_date(ingest: IngestResult, parsed: StockAnalysis) -> str:
    for candidate in (ingest.article_date, parsed.article_date):
        normalized = normalize_date(candidate)
        if normalized:
            return normalized
    return ""


def analyze_ingest(
    ingest: IngestResult, *, replace_id: int | None = None
) -> tuple[StockAnalysis, list[str], int]:
    ingest = finalize_ingest(ingest)
    tickers = detect_tickers(ingest.text)
    client = _make_client()
    model = get_openai_model()

    public_companies, public_block = build_public_company_context(
        client, model, ingest.text, tickers
    )

    target_words = target_summary_words(
        ingest.text, company_count=len(public_companies)
    )
    read_time = _read_time_minutes(target_words)

    all_tickers = list(
        dict.fromkeys(tickers + [c.ticker for c in public_companies])
    )

    try:
        completion = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(
                        source_label=ingest.source_label,
                        article_date_hint=ingest.article_date or "unknown",
                        target_words=target_words,
                        read_time=read_time,
                        tickers=", ".join(tickers) if tickers else "none detected",
                        public_companies_block=public_block,
                        text=ingest.text[:120000],
                    ),
                },
            ],
            response_format=StockAnalysis,
            max_tokens=16384,
        )
    except Exception as exc:
        raise _friendly_error(exc) from exc

    choice = completion.choices[0]
    parsed = choice.message.parsed
    if parsed is None:
        finish = getattr(choice, "finish_reason", None)
        if finish == "length":
            raise ValueError(
                "Analysis output was too long and got cut off. "
                "Retry once; if it persists, paste a shorter excerpt of the article."
            )
        raise ValueError("Model did not return a valid analysis.")

    article_date = _resolve_article_date(ingest, parsed)
    parsed.article_date = article_date

    verified = {c.ticker for c in public_companies}
    parsed.company_opinions = [
        co
        for co in parsed.company_opinions
        if co.ticker in verified or co.ticker in tickers
    ]
    mentioned_tickers = [
        co.ticker.upper() for co in parsed.company_opinions if co.ticker
    ]

    display_title = format_display_title(
        parsed.title or ingest.title,
        article_date,
    )

    payload = dict(
        source_type=ingest.source_type,
        source_label=ingest.source_label,
        source_name=ingest.source_name,
        title=display_title,
        clean_text=ingest.text,
        detected_tickers=mentioned_tickers,
        analysis=parsed.model_dump(),
    )
    if replace_id is not None:
        analysis_id = update_analysis(replace_id, **payload)
    else:
        analysis_id = save_analysis(**payload)

    return parsed, mentioned_tickers, analysis_id


def ingest_from_saved(record: dict[str, Any]) -> IngestResult:
    """Rebuild ingest input from a stored analysis for re-run."""
    analysis = record["analysis"]
    title = analysis.get("title") or record["title"]
    return IngestResult(
        title=title,
        text=record["clean_text"],
        source_type=record["source_type"],
        source_label=record["source_label"],
        article_date=analysis.get("article_date", ""),
        source_name=record.get("source_name", ""),
    )


def rerun_saved_analysis(analysis_id: int) -> tuple[StockAnalysis, list[str], int]:
    record = get_analysis(analysis_id)
    if not record:
        raise ValueError(f"Analysis #{analysis_id} not found.")
    return analyze_ingest(ingest_from_saved(record), replace_id=analysis_id)


def analyze_ingest_dict(job: dict) -> dict:
    replace_id = job.get("replace_id")
    if replace_id:
        analysis, tickers, analysis_id = rerun_saved_analysis(int(replace_id))
    else:
        ingest = IngestResult(
            title=job["title"],
            text=job["text"],
            source_type=job["source_type"],
            source_label=job["source_label"],
            article_date=job.get("article_date", ""),
            source_name=job.get("source_name", ""),
        )
        analysis, tickers, analysis_id = analyze_ingest(ingest)
    return {
        "analysis_id": analysis_id,
        "tickers": tickers,
        "analysis": analysis.model_dump(),
    }
