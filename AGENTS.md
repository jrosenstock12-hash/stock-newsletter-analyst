# Stock Newsletter Analyst — Agent Guide

Personal Streamlit app: paste newsletters → AI stock summary + per-company buy/hold/sell opinions.

## Open this project in Cursor

**File → Open Folder →** `/Users/jeffreyrosenstock/stock-newsletter-analyst`

The agent needs this folder as the workspace root to run git, pip, and Streamlit in terminal.

## Quick commands (run from project root)

```bash
./scripts/setup.sh      # first time: venv + deps
./scripts/start.sh      # run app at http://localhost:8503
./scripts/test-api.sh   # verify OpenAI key works
./scripts/analyze-sample.sh  # analyze SemiAnalysis sample
```

## Environment

- Secrets live in `.env` (never commit). Copy from `.env.example`.
- Required: `OPENAI_API_KEY`
- Database: `data/analyses.db` (SQLite, local)

## Architecture

| Path | Role |
|------|------|
| `app.py` | Streamlit UI |
| `analyze/llm_core.py` | OpenAI analysis + prompts |
| `analyze/llm.py` | Subprocess wrapper (Streamlit network fix) |
| `analyze/companies.py` | Extract companies + Yahoo Finance lookup |
| `analyze/worker.py` | CLI worker for subprocess |
| `ingest/` | URL, email, markdown parsing |
| `db/database.py` | SQLite persistence |

## Agent terminal rules

1. Always `cd` to project root before commands.
2. Use `source .venv/bin/activate` or `./scripts/*.sh` (scripts activate venv).
3. Never commit `.env` or `data/*.db`.
4. OpenAI calls: use `python3` with network; subprocess path in `analyze/llm.py` for Streamlit.
5. Git remote: `origin` → `jrosenstock12-hash/stock-newsletter-analyst`

## Deploy

Local only for now: `./scripts/start.sh`. Streamlit Cloud needs GitHub app access to private repo (see `DEPLOY.md`).
