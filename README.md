# Stock Newsletter Analyst

Personal tool to analyze newsletters and articles for public stock implications. Paste an email, upload a `.eml` file, or provide a web link — get a detailed summary and a buy/hold/sell opinion saved to a local database.

**Not financial advice.** Opinions are derived from article content only.

## Quick start

```bash
cd ~/stock-newsletter-analyst
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

## Input methods

| Method | Best for |
|--------|----------|
| **Paste email / newsletter** | Most reliable — copy the full body from Gmail, Outlook, etc. |
| **Upload .md file** | Saved markdown exports (detects `Source URL:` and `Title:` headers) |
| **Upload .eml file** | Saved emails (Apple Mail: File → Save As → Raw Message Source) |
| **Link (URL)** | Public article/newsletter archive pages |

**SemiAnalysis / Substack:** Subscriber posts often can't be fetched automatically. Open the post while logged in, Cmd+A → copy → paste. Or upload a saved `.md` file.

If a link is paywalled or requires login, use paste instead.

## What you get

Each analysis is saved locally (`data/analyses.db`) and includes:

- Detailed market-focused summary
- Detected tickers and mentioned companies
- Key claims from the article (bull/bear cases)
- Article sentiment vs AI opinion (buy / hold / sell / avoid)
- Confidence, catalysts, and risks

## Configuration

Set these in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model for analysis |
| `DATABASE_PATH` | `./data/analyses.db` | SQLite file location |

## Project layout

```
stock-newsletter-analyst/
  app.py              # Streamlit UI
  config.py           # Environment config
  ingest/
    url.py            # Fetch and extract from links
    email.py          # Parse pasted content and .eml files
    clean.py          # Strip newsletter noise
  analyze/
    llm.py            # OpenAI structured analysis
    schema.py         # Output schema
    tickers.py        # Ticker detection
  db/
    database.py       # SQLite persistence
  data/               # Local database (gitignored)
```

## Deploy live

See **[DEPLOY.md](DEPLOY.md)** for Streamlit Cloud (easiest), Railway, or local-only setup.

## Later automation ideas

The core function is `analyze_content(ingest)` in `analyze/llm.py`. Future automation (Gmail API, RSS, scheduled jobs) can produce the same `IngestResult` object and call that function — no UI changes needed.
