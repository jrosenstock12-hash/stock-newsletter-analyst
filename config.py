import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")


def apply_streamlit_secrets() -> None:
    """Load API keys from Streamlit Cloud secrets when deployed."""
    try:
        import streamlit as st

        for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "DATABASE_PATH"):
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
    except Exception:
        pass

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "analyses.db"))


def reload_env() -> None:
    """Reload .env so Streamlit picks up key changes without restart."""
    load_dotenv(PROJECT_ROOT / ".env", override=True)


def get_openai_api_key() -> str:
    reload_env()
    return os.getenv("OPENAI_API_KEY", "")


def get_openai_model() -> str:
    reload_env()
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
