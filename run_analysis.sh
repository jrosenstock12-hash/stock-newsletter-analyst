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
print(f"Tickers: {', '.join(tickers)}\n")
print(f"EXECUTIVE:\n{analysis.executive_summary}\n")
print(f"DETAILED ({len(analysis.detailed_summary.split())} words):\n{analysis.detailed_summary[:500]}...\n")
print("STOCKS MENTIONED:")
for co in analysis.company_opinions:
    print(f"  {co.ticker}: {co.rating.upper()} ({co.confidence})")
    print(f"    Article: {co.article_says[:120]}...")
    print(f"    Opinion: {co.rationale[:120]}...")
PY
