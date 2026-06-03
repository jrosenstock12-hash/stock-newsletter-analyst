import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from analyze.llm_core import analyze_ingest_dict, rerun_saved_analysis
from analyze.schema import StockAnalysis
from config import PROJECT_ROOT
from ingest.models import IngestResult

WORKER = PROJECT_ROOT / "analyze" / "worker.py"
WORKER_TIMEOUT_SEC = 600


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if "proxy" in key.lower():
            env.pop(key, None)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return env


def _on_streamlit_cloud() -> bool:
    return Path("/mount/src").is_dir() or bool(
        os.environ.get("STREAMLIT_SHARING_MODE")
    )


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
            timeout=WORKER_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            "Analysis took too long (over 10 minutes). "
            "Try a shorter article or paste a smaller excerpt."
        ) from exc
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
    if _on_streamlit_cloud():
        from analyze.llm_core import test_connection

        return test_connection()
    result = _run_worker({"action": "test"})
    return result.get("message", "connected")


def _result_to_tuple(result: dict) -> tuple[StockAnalysis, list[str], int]:
    analysis = StockAnalysis.model_validate(result["analysis"])
    return analysis, result["tickers"], result["analysis_id"]


def analyze_content(
    ingest: IngestResult,
    *,
    replace_id: int | None = None,
) -> tuple[StockAnalysis, list[str], int]:
    if replace_id is not None:
        return rerun_analysis(replace_id)

    job = {
        "title": ingest.title,
        "text": ingest.text,
        "source_type": ingest.source_type,
        "source_label": ingest.source_label,
        "article_date": ingest.article_date,
        "source_name": ingest.source_name,
    }

    if _on_streamlit_cloud():
        result = analyze_ingest_dict(job)
    else:
        result = _run_worker(job)

    return _result_to_tuple(result)


def _use_in_process_worker() -> bool:
    return _on_streamlit_cloud() or Path("/mount/src").is_dir()


def rerun_analysis(analysis_id: int) -> tuple[StockAnalysis, list[str], int]:
    """Re-analyze stored article text and update the same history entry."""
    if _use_in_process_worker():
        return rerun_saved_analysis(analysis_id)

    result = _run_worker({"replace_id": analysis_id})
    return _result_to_tuple(result)
