import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from analyze.llm_core import analyze_ingest
from analyze.schema import StockAnalysis
from config import PROJECT_ROOT
from ingest.models import IngestResult

WORKER = PROJECT_ROOT / "analyze" / "worker.py"


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if "proxy" in key.lower():
            env.pop(key, None)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return env


def _run_worker(job: dict) -> dict:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=PROJECT_ROOT / "data"
    ) as f:
        json.dump(job, f)
        job_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, str(WORKER), job_path],
            capture_output=True,
            text=True,
            env=_clean_env(),
            cwd=str(PROJECT_ROOT),
            timeout=180,
        )
    finally:
        Path(job_path).unlink(missing_ok=True)

    if proc.returncode != 0 and not proc.stdout.strip():
        raise ValueError(
            proc.stderr.strip()
            or "Analysis worker failed. Run: cd ~/stock-newsletter-analyst && ./start.sh"
        )

    try:
        result = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Worker returned invalid output: {proc.stderr or proc.stdout}"
        ) from exc

    if not result.get("ok"):
        raise ValueError(result.get("error", "Unknown worker error"))

    return result


def test_openai_connection() -> str:
    result = _run_worker({"action": "test"})
    return result.get("message", "connected")


def analyze_content(
    ingest: IngestResult,
) -> tuple[StockAnalysis, list[str], int]:
    job = {
        "title": ingest.title,
        "text": ingest.text,
        "source_type": ingest.source_type,
        "source_label": ingest.source_label,
    }
    result = _run_worker(job)
    analysis = StockAnalysis.model_validate(result["analysis"])
    return analysis, result["tickers"], result["analysis_id"]
