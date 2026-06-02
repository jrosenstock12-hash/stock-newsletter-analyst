#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python <<'PY'
from pathlib import Path
from ingest.markdown import parse_markdown_file
from analyze.llm import analyze_content

ingest = parse_markdown_file(Path("samples/semianalysis-dark-output.md").read_bytes())
print(f"Analyzing: {ingest.title}\n")
analysis, tickers, analysis_id = analyze_content(ingest)

print("=" * 60)
print(f"SAVED AS ANALYSIS #{analysis_id}")
print("=" * 60)
print(f"RATING: {analysis.ai_opinion.rating.upper()} | Confidence: {analysis.ai_opinion.confidence}")
print(f"Horizon: {analysis.ai_opinion.time_horizon}\n")
print(f"RATIONALE: {analysis.ai_opinion.rationale}\n")
print(f"SUMMARY:\n{analysis.summary}\n")
if analysis.mentioned_companies:
    print("COMPANIES:")
    for c in analysis.mentioned_companies:
        print(f"  {c.ticker} — {c.company_name} ({c.relevance})")
PY
