# Deploy Stock Newsletter Analyst

Easiest option for a personal Streamlit app: **Streamlit Community Cloud** (free tier).

## Before you deploy

1. **Use a private GitHub repo** — your code will be public on the free tier unless the repo is private (Streamlit Cloud supports private repos).
2. **Never commit `.env`** — it is gitignored. API keys go in the host's secrets UI only.
3. **SQLite is ephemeral on Streamlit Cloud** — saved analyses reset when the app redeploys or sleeps. Fine for personal testing; use Railway with a volume if you need persistent history.

---

## Option A: Streamlit Community Cloud (recommended)

### 1. Push to GitHub

```bash
cd ~/stock-newsletter-analyst
git init
git add .
git commit -m "Stock newsletter analyst app"
gh repo create stock-newsletter-analyst --private --source=. --push
```

(Or create a repo on github.com and push manually.)

### 2. Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. **New app** → pick your repo
4. **Main file path:** `app.py`
5. **Python version:** 3.11 or 3.12 (3.14 may not be available yet — if deploy fails, add `runtime.txt` with `python-3.12`)

### 3. Add secrets

In the app **Settings → Secrets**, paste:

```toml
OPENAI_API_KEY = "sk-proj-your-key-here"
OPENAI_MODEL = "gpt-4o-mini"
```

### 4. Deploy

Click **Deploy**. Your live URL will look like:

`https://your-app-name.streamlit.app`

Share only with people you trust — there is no login on the app by default.

---

## Option B: Railway (always-on + persistent disk)

Good if you want a URL that's always on and history that survives restarts.

1. Install Railway CLI or use [railway.app](https://railway.app)
2. New project → **Deploy from GitHub** → select this repo
3. Add variables:
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL=gpt-4o-mini`
   - `PORT=8501`
4. Set start command:

```bash
streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
```

5. Attach a **volume** mounted at `/app/data` for SQLite persistence

---

## Option C: Run on your Mac (already working)

```bash
cd ~/stock-newsletter-analyst
./start.sh
```

Open `http://localhost:8503` — only on your machine unless you use a tunnel (ngrok, Cloudflare Tunnel) for temporary public access.

---

## Optional: password protect a public deploy

Add to `app.py` (top of `main()`):

```python
import streamlit as st

def check_password():
    if st.session_state.get("authenticated"):
        return True
    pwd = st.sidebar.text_input("Password", type="password")
    if pwd == st.secrets.get("APP_PASSWORD", ""):
        st.session_state["authenticated"] = True
        return True
    return False
```

Then in Secrets also set `APP_PASSWORD = "your-password"`.

---

## Checklist

| Step | Done? |
|------|-------|
| `.env` not in git | ✓ gitignored |
| OpenAI billing active | |
| GitHub repo created | |
| Secrets set on host | |
| Test live URL | |
