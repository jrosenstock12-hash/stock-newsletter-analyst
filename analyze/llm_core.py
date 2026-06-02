from openai import OpenAI

from analyze.companies import build_public_company_context, target_summary_words
from analyze.schema import StockAnalysis
from analyze.tickers import detect_tickers
from config import get_openai_api_key, get_openai_model
from db.database import save_analysis
from ingest.models import IngestResult

SYSTEM_PROMPT = """You are a financial research assistant analyzing newsletters and articles for public stock implications.

Rules:
1. Clearly separate what the ARTICLE states vs your AI opinion derived from that content.
2. Identify ALL publicly traded companies relevant to the article — use the verified Yahoo Finance list provided even when the article omits ticker symbols.
3. Provide a company_opinion (buy/hold/sell/avoid) for EACH verified public company that the article discusses or that is materially impacted by its thesis.
4. Write detailed_summary as a thorough narrative (~3-5 minute read) covering the article's main arguments, data points, and market implications — not a bullet list.
5. executive_summary is only 2-4 sentences for a quick skim.
6. Be conservative with ratings when evidence is weak, promotional, or macro-only.
7. Do not invent facts, prices, or events not supported by the article.
8. Private companies (OpenAI, Anthropic, etc.) may appear in mentioned_companies with is_public=false if relevant, but company_opinions are only for public tickers."""

USER_PROMPT_TEMPLATE = """Analyze this article/newsletter for public stock implications.

Source: {source_label}
Target detailed_summary length: ~{target_words} words ({read_time} minute read)
Regex-detected tickers (may be incomplete): {tickers}

{public_companies_block}

--- ARTICLE TEXT ---
{text}
--- END ---

Return structured analysis with:
- executive_summary: 2-4 sentences
- detailed_summary: ~{target_words} word narrative (3-5 min read); scale depth to article length
- mentioned_companies: all companies in article; mark is_public true/false
- company_opinions: one entry per PUBLIC company with ticker, rating, confidence, rationale, article_says
- key_claims, bull_case, bear_case, sentiment, ai_opinion (overall market thesis)"""


def _make_client() -> OpenAI:
    api_key = get_openai_api_key()
    if not api_key or api_key in ("sk-...", "sk-your-key-here"):
        raise ValueError(
            "OPENAI_API_KEY is not set. Edit ~/stock-newsletter-analyst/.env "
            "and add your key from platform.openai.com/api-keys"
        )
    return OpenAI(api_key=api_key, timeout=180.0)


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


def analyze_ingest(ingest: IngestResult) -> tuple[StockAnalysis, list[str], int]:
    tickers = detect_tickers(ingest.text)
    client = _make_client()
    model = get_openai_model()

    target_words = target_summary_words(ingest.text)
    read_time = _read_time_minutes(target_words)

    public_companies, public_block = build_public_company_context(
        client, model, ingest.text, tickers
    )

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
                        target_words=target_words,
                        read_time=read_time,
                        tickers=", ".join(tickers) if tickers else "none detected",
                        public_companies_block=public_block,
                        text=ingest.text[:120000],
                    ),
                },
            ],
            response_format=StockAnalysis,
            max_tokens=8000,
        )
    except Exception as exc:
        raise _friendly_error(exc) from exc

    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Model did not return a valid analysis.")

    # Drop false-positive tickers; keep opinions for verified public names only
    verified = {c.ticker for c in public_companies}
    parsed.company_opinions = [
        co
        for co in parsed.company_opinions
        if co.ticker in verified or co.ticker in tickers
    ]
    bogus = {"USAGE", "THE", "AND", "FOR", "AI", "GDP", "CPI", "FED", "SEC"}
    all_tickers = [t for t in all_tickers if t not in bogus]
    for co in parsed.company_opinions:
        if co.ticker and co.ticker not in all_tickers:
            all_tickers.append(co.ticker)

    analysis_id = save_analysis(
        source_type=ingest.source_type,
        source_label=ingest.source_label,
        title=parsed.title or ingest.title,
        clean_text=ingest.text,
        detected_tickers=all_tickers,
        analysis=parsed.model_dump(),
    )

    return parsed, all_tickers, analysis_id


def analyze_ingest_dict(job: dict) -> dict:
    ingest = IngestResult(
        title=job["title"],
        text=job["text"],
        source_type=job["source_type"],
        source_label=job["source_label"],
    )
    analysis, tickers, analysis_id = analyze_ingest(ingest)
    return {
        "analysis_id": analysis_id,
        "tickers": tickers,
        "analysis": analysis.model_dump(),
    }
