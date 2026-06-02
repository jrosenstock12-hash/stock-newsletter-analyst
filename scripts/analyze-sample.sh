#!/bin/bash
cd "$(dirname "$0")/.."
source .venv/bin/activate
python3 <<'PY'
from pathlib import Path
from ingest.markdown import parse_markdown_file
from analyze.llm import analyze_content

path = Path("samples/semianalysis-dark-output.md")
ingest = parse_markdown_file(path.read_bytes())
print("Analyzing:", ingest.title)
a, tickers, aid = analyze_content(ingest)
print(f"\nSaved #{aid} | Tickers: {', '.join(tickers)}")
print(f"Summary: {len(a.detailed_summary.split())} words")
print("\n--- Executive ---\n", a.executive_summary)
print("\n--- Stocks Mentioned ---")
for co in a.company_opinions:
    print(f"  {co.ticker}: {co.rating.upper()} — {co.rationale[:100]}...")
PY
