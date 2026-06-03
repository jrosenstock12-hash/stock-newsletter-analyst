import html
import streamlit as st

from analyze.llm import analyze_content, rerun_analysis, test_openai_connection
from config import apply_streamlit_secrets, get_openai_api_key
from db.database import (
    delete_analyses,
    get_analysis,
    init_db,
    list_analyses,
    list_source_names,
    list_tickers,
)
from ingest.date import format_display_title
from ingest.email import parse_eml_file, parse_pasted_content
from ingest.markdown import parse_markdown_file
from ingest.url import fetch_url, normalize_url

st.set_page_config(
    page_title="Stock Newsletter Analyst",
    layout="wide",
)

RATING_COLORS = {
    "buy": "#16a34a",
    "hold": "#ca8a04",
    "sell": "#dc2626",
    "avoid": "#6b7280",
}

# background, text, border for pill tags
TICKER_TAG_STYLES: dict[str, tuple[str, str, str]] = {
    "buy": ("#14532d", "#86efac", "#22c55e"),
    "hold": ("#422006", "#fde047", "#ca8a04"),
    "sell": ("#450a0a", "#fca5a5", "#dc2626"),
    "avoid": ("#1f2937", "#9ca3af", "#6b7280"),
}


def yahoo_quote_url(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker.upper()}/"


def ticker_links(tickers: list[str]) -> str:
    if not tickers:
        return ""
    links = [
        f"[{t.upper()}]({yahoo_quote_url(t)})" for t in tickers if t and t.strip()
    ]
    return ", ".join(links)


def _source_tag_html(source_name: str) -> str:
    if not source_name:
        return ""
    name = html.escape(source_name)
    return (
        f'<span style="display:inline-block;background:#1e3a5f;color:#93c5fd;'
        f"border:1px solid #3b82f6;border-radius:999px;padding:0.12rem 0.55rem;"
        f'font-size:0.78rem;font-weight:600;white-space:nowrap;">'
        f"{name}</span>"
    )


def _ticker_tag_entries(
    *,
    company_opinions: list[dict] | None = None,
    tickers: list[str] | None = None,
) -> list[tuple[str, str]]:
    if company_opinions:
        entries: list[tuple[str, str]] = []
        for co in company_opinions:
            t = str(co.get("ticker", "")).strip()
            if t:
                entries.append((t, str(co.get("rating", "hold")).lower()))
        return entries
    if tickers:
        return [(t.strip(), "hold") for t in tickers if t and t.strip()]
    return []


def _ticker_tags_html(
    *,
    company_opinions: list[dict] | None = None,
    tickers: list[str] | None = None,
) -> str:
    entries = _ticker_tag_entries(
        company_opinions=company_opinions,
        tickers=tickers,
    )
    if not entries:
        return ""
    tags = []
    for t, rating in entries:
        bg, fg, border = TICKER_TAG_STYLES.get(rating, TICKER_TAG_STYLES["avoid"])
        sym = html.escape(t.upper())
        yahoo = html.escape(yahoo_quote_url(t))
        tags.append(
            f'<a href="{yahoo}" target="_blank" title="{html.escape(rating.upper())}" '
            f'style="display:inline-block;background:{bg};color:{fg};'
            f"border:1px solid {border};border-radius:999px;padding:0.12rem 0.5rem;"
            f'font-size:0.75rem;font-weight:600;margin-left:0.2rem;text-decoration:none;'
            f'white-space:nowrap;">{sym}</a>'
        )
    return "".join(tags)


def render_source_tag(source_name: str) -> None:
    markup = _source_tag_html(source_name)
    if markup:
        st.markdown(markup, unsafe_allow_html=True)


def render_ticker_tags(
    tickers: list[str] | None = None,
    *,
    company_opinions: list[dict] | None = None,
) -> None:
    markup = _ticker_tags_html(company_opinions=company_opinions, tickers=tickers)
    if markup:
        st.markdown(markup, unsafe_allow_html=True)


def display_title(analysis: dict, fallback_title: str = "Analysis") -> str:
    title = analysis.get("title") or fallback_title
    article_date = analysis.get("article_date", "")
    return format_display_title(title, article_date)


def _history_date_and_title(row: dict) -> tuple[str, str]:
    title = row.get("title", "Analysis")
    analysis = row.get("analysis", {})
    date = (analysis.get("article_date") or "").strip()

    if " — " in title:
        prefix, rest = title.split(" — ", 1)
        if len(prefix) == 10 and prefix[4] == "-" and prefix[7] == "-":
            return prefix, rest

    if date and title.startswith(f"{date} — "):
        return date, title[len(date) + 3 :]
    if date:
        return date, title
    return "", title


def _history_ticker_tags_html(row: dict) -> str:
    analysis = row.get("analysis", {})
    opinions = analysis.get("company_opinions", [])
    return _ticker_tags_html(
        company_opinions=opinions,
        tickers=None if opinions else row.get("detected_tickers", []),
    )


def _render_history_list_header(row: dict, row_id: int, *, pending: bool) -> None:
    """Always-visible list row: source + menu on line 1; date, title, tags on line 2."""
    date, article_title = _history_date_and_title(row)
    source = _source_tag_html(row.get("source_name", ""))
    tag_html = _history_ticker_tags_html(row)
    date_html = (
        f'<span style="color:#94a3b8;white-space:nowrap;">{html.escape(date)}</span>'
        f'<span style="color:#64748b;"> · </span>'
        if date
        else ""
    )
    title_html = (
        f'<span style="font-weight:600;color:#f1f5f9;">'
        f"{html.escape(article_title)}</span>"
    )
    tags_block = (
        f'<span style="flex-shrink:0;margin-left:0.25rem;">{tag_html}</span>'
        if tag_html
        else ""
    )

    source_col, menu_col = st.columns([10, 0.75], vertical_alignment="center")
    with source_col:
        if source:
            st.markdown(source, unsafe_allow_html=True)
    with menu_col:
        if not pending:
            _render_history_actions(row_id)

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;
        min-width:0;width:100%;margin-top:0.15rem;">
          <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;
          white-space:nowrap;">{date_html}{title_html}</span>
          {tags_block}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _init_history_confirm_state() -> None:
    if "pending_delete_id" not in st.session_state:
        st.session_state.pending_delete_id = None
    if "pending_rerun_id" not in st.session_state:
        st.session_state.pending_rerun_id = None


def _render_confirm_panel(
    *,
    kind: str,
    row_id: int,
    title_snippet: str,
) -> None:
    is_rerun = kind == "rerun"
    accent = "#3b82f6" if is_rerun else "#ef4444"
    bg = "#172554" if is_rerun else "#450a0a"
    icon = "↻" if is_rerun else "✕"
    heading = "Re-run this analysis?" if is_rerun else "Delete this analysis?"
    detail = (
        "Uses saved article text with your latest code (~2–5 min)."
        if is_rerun
        else "This cannot be undone."
    )
    info_col, yes_col, no_col = st.columns([9.5, 1.1, 1.1], vertical_alignment="center")
    with info_col:
        st.markdown(
            f"""
            <div style="background:{bg};border:1px solid {accent};border-radius:10px;
            padding:0.5rem 0.7rem;">
              <div style="font-weight:600;font-size:0.84rem;color:#f8fafc;">
                <span style="color:{accent};margin-right:0.35rem;">{icon}</span>
                {html.escape(heading)}
              </div>
              <div style="font-size:0.78rem;color:#e2e8f0;margin-top:0.12rem;
              overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                {html.escape(title_snippet[:80])}
              </div>
              <div style="font-size:0.72rem;color:#94a3b8;margin-top:0.15rem;">
                {html.escape(detail)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with yes_col:
        label = "Re-run" if is_rerun else "Delete"
        if st.button(
            label,
            key=f"yes_{kind}_{row_id}",
            type="primary",
            use_container_width=True,
        ):
            if is_rerun:
                try:
                    with st.spinner("Running..."):
                        rerun_analysis(row_id)
                except Exception as exc:
                    st.error(str(exc))
                    return
            else:
                delete_analyses([row_id])
            st.session_state.pending_delete_id = None
            st.session_state.pending_rerun_id = None
            st.rerun()
    with no_col:
        if st.button("Cancel", key=f"no_{kind}_{row_id}", use_container_width=True):
            st.session_state.pending_delete_id = None
            st.session_state.pending_rerun_id = None
            st.rerun()


def _render_history_actions(row_id: int) -> None:
    with st.popover("⋮"):
        if st.button(
            "Re-run",
            key=f"rerun_{row_id}",
            type="secondary",
            use_container_width=True,
        ):
            st.session_state.pending_rerun_id = row_id
            st.session_state.pending_delete_id = None
            st.rerun()
        if st.button(
            "Delete",
            key=f"delete_{row_id}",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.pending_delete_id = row_id
            st.session_state.pending_rerun_id = None
            st.rerun()


def render_stocks_mentioned(company_opinions: list[dict]) -> None:
    if not company_opinions:
        return

    st.markdown("### Stocks Mentioned")
    for co in company_opinions:
        ticker = co.get("ticker", "?")
        rating = co.get("rating", "hold")
        color = RATING_COLORS.get(rating, "#6b7280")
        yahoo = yahoo_quote_url(ticker)

        st.markdown(
            f"#### [{ticker}]({yahoo}) — {co.get('company_name', '')} "
            f"<span style='color:{color};font-weight:700'>"
            f"{rating.upper()}</span> "
            f"({co.get('confidence', 'medium')} confidence)",
            unsafe_allow_html=True,
        )
        if co.get("article_says"):
            st.markdown("**What the author said**")
            st.markdown(co["article_says"])
        if co.get("rationale"):
            st.markdown("**Opinion**")
            st.write(co["rationale"])
        st.markdown("")


def render_analysis(
    analysis: dict,
    tickers: list[str],
    source_label: str,
    source_name: str = "",
    *,
    show_tags: bool = True,
) -> None:
    st.subheader(display_title(analysis))
    if show_tags:
        tag_col1, tag_col2 = st.columns([1, 3])
        with tag_col1:
            if source_name:
                render_source_tag(source_name)
        with tag_col2:
            opinions = analysis.get("company_opinions", [])
            render_ticker_tags(
                tickers=None if opinions else tickers,
                company_opinions=opinions or None,
            )
        st.caption(f"Source detail: {source_label}")

    exec_summary = analysis.get("executive_summary", "")
    detailed = analysis.get("detailed_summary") or analysis.get("summary", "")

    if exec_summary:
        st.markdown("### At a glance")
        st.write(exec_summary)

    st.markdown("### Detailed summary")
    if detailed:
        word_count = len(detailed.split())
        st.caption(f"~{word_count} words · ~{max(3, min(5, word_count // 220))} min read")
        st.write(detailed)
    else:
        st.write("No summary available.")

    render_stocks_mentioned(analysis.get("company_opinions", []))

    st.info(analysis.get("disclaimer", ""))


def render_history_analysis_body(
    analysis: dict,
    source_label: str,
    *,
    clean_text: str | None = None,
) -> None:
    exec_summary = analysis.get("executive_summary", "")
    detailed = analysis.get("detailed_summary") or analysis.get("summary", "")

    if exec_summary:
        st.markdown("### At a glance")
        st.write(exec_summary)

    st.markdown("### Detailed summary")
    if detailed:
        word_count = len(detailed.split())
        st.caption(f"~{word_count} words · ~{max(3, min(5, word_count // 220))} min read")
        st.write(detailed)
    else:
        st.write("No summary available.")

    render_stocks_mentioned(analysis.get("company_opinions", []))
    st.caption(f"Source detail: {source_label}")
    st.info(analysis.get("disclaimer", ""))

    if clean_text:
        with st.expander("Original article", expanded=False):
            st.text(clean_text[:120000])


def page_analyze() -> None:
    st.header("Analyze a newsletter or article")

    input_mode = st.radio(
        "How do you want to add content?",
        [
            "Link (URL)",
            "Paste email / newsletter",
            "Upload .eml file",
            "Upload .md file",
        ],
        horizontal=True,
    )

    url = ""
    pasted = ""
    eml_file = None
    md_file = None

    if input_mode == "Link (URL)":
        url = st.text_input(
            "Article or newsletter web link",
            placeholder="https://newsletter.semianalysis.com/p/...",
        )
        st.caption(
            "Tracking params (?_gl=...) are stripped automatically. "
            "Subscriber-only Substack posts (SemiAnalysis, etc.) often block "
            "automated fetch — paste the article if the link returns a preview."
        )
    elif input_mode == "Paste email / newsletter":
        pasted = st.text_area(
            "Paste the full email or newsletter body",
            height=320,
            placeholder="Copy the entire newsletter from your email client and paste here...",
        )
        st.caption(
            "Title is detected automatically from the paste. "
            "Tip: Cmd+A in the article → copy → paste here."
        )
    else:
        if input_mode == "Upload .eml file":
            eml_file = st.file_uploader(
                "Upload a saved .eml email file",
                type=["eml"],
                help="In Apple Mail: File → Save As → Raw Message Source (.eml)",
            )
        else:
            md_file = st.file_uploader(
                "Upload a saved markdown file",
                type=["md", "markdown", "txt"],
                help="Export or save the newsletter as .md, or paste into a .txt file.",
            )

    if st.button("Analyze", type="primary", use_container_width=True):
        try:
            with st.spinner(
                "Reading content and running analysis (may take 2–5 minutes)..."
            ):
                if input_mode == "Link (URL)":
                    if not url.strip():
                        st.error("Please enter a URL.")
                        return
                    ingest = fetch_url(normalize_url(url))
                elif input_mode == "Paste email / newsletter":
                    if not pasted.strip():
                        st.error("Please paste newsletter content.")
                        return
                    ingest = parse_pasted_content(pasted)
                elif input_mode == "Upload .eml file":
                    if eml_file is None:
                        st.error("Please upload an .eml file.")
                        return
                    ingest = parse_eml_file(eml_file.read())
                else:
                    if md_file is None:
                        st.error("Please upload a markdown file.")
                        return
                    ingest = parse_markdown_file(md_file.read())

                analysis, tickers, analysis_id = analyze_content(ingest)

            st.success(f"Saved as analysis #{analysis_id}")
            analysis_dict = analysis.model_dump()
            shown_tickers = [
                co["ticker"]
                for co in analysis_dict.get("company_opinions", [])
                if co.get("ticker")
            ]
            render_analysis(
                analysis_dict,
                shown_tickers,
                ingest.source_label,
                ingest.source_name,
            )
        except Exception as exc:
            st.error(str(exc))


def page_history() -> None:
    st.header("Saved analyses")
    _init_history_confirm_state()

    sources = list_source_names()
    tickers_all = list_tickers()

    st.markdown(
        """
        <style>
        div[data-testid="stSelectbox"] label { font-size: 0.8rem; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            margin-bottom: 0.35rem !important;
            padding: 0.4rem 0.55rem 0.25rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            gap: 0.25rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stExpander"] {
            border: none !important;
            margin-bottom: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stExpander"] details summary {
            padding-top: 0.15rem;
            padding-bottom: 0.15rem;
            font-size: 0.85rem;
            color: #94a3b8;
        }
        div[data-testid="stPopover"] button {
            min-width: 2rem;
            padding: 0.2rem 0.55rem;
            font-size: 1.15rem;
            line-height: 1;
            float: right;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    filter_left, filter_right, _ = st.columns([1.4, 1.4, 5])
    with filter_left:
        source_options = ["All sources"] + sources
        source_pick = st.selectbox("Source", source_options, key="hist_source")
    with filter_right:
        ticker_options = ["All tickers"] + tickers_all
        ticker_pick = st.selectbox("Ticker", ticker_options, key="hist_ticker")

    source_filter = None if source_pick == "All sources" else source_pick
    ticker_filter = None if ticker_pick == "All tickers" else ticker_pick

    rows = list_analyses(
        limit=100,
        source_name=source_filter,
        ticker=ticker_filter,
    )

    if not rows:
        if source_filter or ticker_filter:
            st.info("No analyses match these filters.")
        else:
            st.info("No saved analyses yet. Run your first analysis on the Analyze tab.")
        return

    st.caption(f"Showing {len(rows)} saved analyses")

    for row in rows:
        row_id = row["id"]
        pending = (
            st.session_state.pending_delete_id == row_id
            or st.session_state.pending_rerun_id == row_id
        )
        full = get_analysis(row_id)

        with st.container(border=True):
            _render_history_list_header(row, row_id, pending=pending)

            if st.session_state.pending_delete_id == row_id:
                _render_confirm_panel(
                    kind="delete",
                    row_id=row_id,
                    title_snippet=_history_date_and_title(row)[1],
                )
            elif st.session_state.pending_rerun_id == row_id:
                _render_confirm_panel(
                    kind="rerun",
                    row_id=row_id,
                    title_snippet=_history_date_and_title(row)[1],
                )

            with st.expander("View analysis", expanded=False):
                render_history_analysis_body(
                    row["analysis"],
                    row["source_label"],
                    clean_text=full["clean_text"] if full else None,
                )


def main() -> None:
    apply_streamlit_secrets()
    init_db()

    with st.sidebar:
        st.header("Setup")
        key = get_openai_api_key()
        if key and key not in ("sk-...", "sk-your-key-here") and len(key) > 20:
            st.success("API key loaded")
        else:
            st.error("API key missing — add OPENAI_API_KEY in Streamlit Secrets")
        if st.button("Test OpenAI connection"):
            try:
                with st.spinner("Testing..."):
                    msg = test_openai_connection()
                st.success(f"Connected: {msg}")
            except Exception as exc:
                st.error(str(exc))
        st.caption(
            "If tests fail, stop this app (Ctrl+C in Terminal) and run: "
            "`cd ~/stock-newsletter-analyst && ./start.sh`"
        )

    st.title("Stock Newsletter Analyst")
    st.caption(
        "Paste a newsletter, upload an email, or drop in a link — get a stock-focused "
        "summary with buy/hold/sell opinions by stock. Personal use only; not financial advice."
    )

    tab_analyze, tab_history = st.tabs(["Analyze", "History"])
    with tab_analyze:
        page_analyze()
    with tab_history:
        page_history()


main()
