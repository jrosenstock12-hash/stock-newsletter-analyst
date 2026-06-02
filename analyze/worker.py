"""Run OpenAI analysis in a subprocess (avoids Streamlit sandbox network issues)."""
import json
import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analyze.llm_core import analyze_ingest_dict, test_connection  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: worker.py <job.json>"}))
        sys.exit(1)

    job_path = Path(sys.argv[1])
    job = json.loads(job_path.read_text())

    if job.get("action") == "test":
        try:
            msg = test_connection()
            print(json.dumps({"ok": True, "message": msg}))
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            sys.exit(1)
        return

    try:
        result = analyze_ingest_dict(job)
        print(json.dumps({"ok": True, **result}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
