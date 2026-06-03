import html
from dataclasses import replace

import streamlit as st

from analyze.llm import analyze_content, rerun_analysis, test_openai_connection
from config import apply_streamlit_secrets, get_openai_api_key
from db.database import (
    add_website,
    delete_analyses,
    delete_website,
    get_analysis,
    init_db,
    list_analyses,
    list_filter_source_names,
    list_tickers,
    list_websites,
    update_analysis_source_name,
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


def _history_source_inline_html(source_name: str) -> str:
    if not source_name:
        return ""
    return (
        f'<span style="color:#64748b;font-size:0.88rem;font-weight:600;'
        f'white-space:nowrap;">{html.escape(source_name)}</span>'
    )


def _history_tickers_inline_html(row: dict) -> str:
    analysis = row.get("analysis", {})
    opinions = analysis.get("company_opinions", [])
    entries = _ticker_tag_entries(
        company_opinions=opinions,
        tickers=None if opinions else row.get("detected_tickers", []),
    )
    if not entries:
        return ""
    parts = []
    for t, rating in entries:
        color = RATING_COLORS.get(rating, "#9ca3af")
        sym = html.escape(t.upper())
        yahoo = html.escape(yahoo_quote_url(t))
        parts.append(
            f'<a href="{yahoo}" target="_blank" title="{html.escape(rating.upper())}" '
            f'style="color:{color};font-weight:600;font-size:0.88rem;'
            f'text-decoration:none;white-space:nowrap;">{sym}</a>'
        )
    return f'<span style="display:inline;">{" · ".join(parts)}</span>'


def _hist_open_key(row_id: int) -> str:
    return f"hist_open_{row_id}"


def _render_history_list_header(row: dict, row_id: int) -> bool:
    """Two-line header: chevron + date/title; then source + tickers."""
    open_key = _hist_open_key(row_id)
    if open_key not in st.session_state:
        st.session_state[open_key] = False

    date, article_title = _history_date_and_title(row)
    source = _history_source_inline_html(row.get("source_name", ""))
    tickers = _history_tickers_inline_html(row)
    dot = '<span style="color:#475569;"> · </span>'

    date_html = (
        f'<span style="color:#94a3b8;white-space:nowrap;font-size:0.92rem;">'
        f"{html.escape(date)}</span>"
        if date
        else ""
    )
    title_html = (
        f'<span style="font-weight:600;color:#f1f5f9;font-size:0.98rem;'
        f"display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;"
        f'overflow:hidden;">{html.escape(article_title)}</span>'
    )
    if date:
        headline = f"{date_html}{dot}{title_html}"
    else:
        headline = title_html

    meta_parts: list[str] = []
    if source:
        meta_parts.append(source)
    if tickers:
        meta_parts.append(tickers)
    meta_html = dot.join(meta_parts)

    chev_col, title_col = st.columns([0.5, 11.5], vertical_alignment="center")
    with chev_col:
        chevron = "▾" if st.session_state[open_key] else "▸"
        if st.button(
            chevron,
            key=f"hist_toggle_{row_id}",
            type="tertiary",
            help="Show or hide analysis",
        ):
            st.session_state[open_key] = not st.session_state[open_key]
            st.rerun()
    with title_col:
        st.markdown(
            f'<div style="line-height:1.45;min-width:0;">{headline}</div>',
            unsafe_allow_html=True,
        )

    if meta_html:
        _, meta_col = st.columns([0.5, 11.5])
        with meta_col:
            st.markdown(
                f"""
                <div style="display:flex;flex-wrap:wrap;align-items:center;gap:0.1rem 0;
                line-height:1.45;margin-top:0.1rem;font-size:0.88rem;min-width:0;">
                  {meta_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

    return st.session_state[open_key]


def _init_history_confirm_state() -> None:
    if "pending_delete_id" not in st.session_state:
        st.session_state.pending_delete_id = None
    if "pending_rerun_id" not in st.session_state:
        st.session_state.pending_rerun_id = None
    if "pending_edit_source_id" not in st.session_state:
        st.session_state.pending_edit_source_id = None


def _clear_pending_history_actions() -> None:
    st.session_state.pending_delete_id = None
    st.session_state.pending_rerun_id = None
    st.session_state.pending_edit_source_id = None


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
            _clear_pending_history_actions()
            st.rerun()
    with no_col:
        if st.button("Cancel", key=f"no_{kind}_{row_id}", use_container_width=True):
            _clear_pending_history_actions()
            st.rerun()


def _render_edit_source_panel(row_id: int, *, current_source: str) -> None:
    websites = list_websites()
    if not websites:
        st.warning("Add sources on the **Websites** tab first.")
        return

    names = [w["name"] for w in websites]
    default_idx = names.index(current_source) if current_source in names else 0

    st.markdown(
        """
        <div style="background:#1e293b;border:1px solid #475569;border-radius:10px;
        padding:0.5rem 0.7rem;margin-bottom:0.35rem;">
          <div style="font-weight:600;font-size:0.84rem;color:#f8fafc;">
            Edit source tag
          </div>
          <div style="font-size:0.72rem;color:#94a3b8;margin-top:0.15rem;">
            Updates the source label on this saved analysis (no re-run).
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    pick_col, save_col, cancel_col = st.columns([6, 1, 1], vertical_alignment="bottom")
    with pick_col:
        new_source = st.selectbox(
            "Source",
            names,
            index=default_idx,
            key=f"edit_source_pick_{row_id}",
            label_visibility="collapsed",
        )
    with save_col:
        if st.button("Save", key=f"save_source_{row_id}", type="primary", use_container_width=True):
            try:
                update_analysis_source_name(row_id, new_source)
            except ValueError as exc:
                st.error(str(exc))
                return
            _clear_pending_history_actions()
            st.rerun()
    with cancel_col:
        if st.button("Cancel", key=f"cancel_source_{row_id}", use_container_width=True):
            _clear_pending_history_actions()
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
            st.session_state.pending_edit_source_id = None
            st.rerun()
        if st.button(
            "Edit source",
            key=f"edit_source_{row_id}",
            type="secondary",
            use_container_width=True,
        ):
            st.session_state.pending_edit_source_id = row_id
            st.session_state.pending_delete_id = None
            st.session_state.pending_rerun_id = None
            st.rerun()
        if st.button(
            "Delete",
            key=f"delete_{row_id}",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.pending_delete_id = row_id
            st.session_state.pending_rerun_id = None
            st.session_state.pending_edit_source_id = None
            st.rerun()


def _render_history_section_heading(title: str, row_id: int, *, pending: bool) -> None:
    heading_col, menu_col = st.columns([10, 1], vertical_alignment="center")
    with heading_col:
        st.markdown(f"### {title}")
    with menu_col:
        if not pending:
            _render_history_actions(row_id)


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
    row_id: int,
    pending: bool = False,
    clean_text: str | None = None,
) -> None:
    exec_summary = analysis.get("executive_summary", "")
    detailed = analysis.get("detailed_summary") or analysis.get("summary", "")

    if exec_summary:
        _render_history_section_heading("At a glance", row_id, pending=pending)
        st.write(exec_summary)
    else:
        _render_history_section_heading("Detailed summary", row_id, pending=pending)

    if exec_summary:
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

    websites = list_websites()
    if not websites:
        st.warning("Add newsletter sources on the **Websites** tab first.")
        return

    source_names = [w["name"] for w in websites]
    source_pick = st.selectbox("Source", source_names, key="analyze_source")

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
        clear_col, _ = st.columns([1, 5])
        with clear_col:
            if st.button("Clear paste", key="clear_paste", type="secondary"):
                st.session_state.paste_newsletter = ""
                st.rerun()
        pasted = st.text_area(
            "Paste the full email or newsletter body",
            height=320,
            placeholder="Copy the entire newsletter from your email client and paste here...",
            key="paste_newsletter",
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

                ingest = replace(ingest, source_name=source_pick)
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


def page_websites() -> None:
    st.header("Newsletter sources")
    st.caption("Manage publication names and homepages. The **Source** picker on Analyze uses this list.")

    with st.form("add_website", clear_on_submit=True):
        name_col, url_col = st.columns(2)
        with name_col:
            new_name = st.text_input("Name", placeholder="SemiAnalysis")
        with url_col:
            new_url = st.text_input("URL", placeholder="https://semianalysis.com")
        if st.form_submit_button("Add source", type="primary"):
            try:
                add_website(new_name, new_url)
                st.success(f"Added {new_name.strip()}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    rows = list_websites()
    if not rows:
        st.info("No sources yet.")
        return

    st.subheader(f"{len(rows)} sources")
    for site in rows:
        link_col, action_col = st.columns([8, 1], vertical_alignment="center")
        with link_col:
            safe_name = html.escape(site["name"])
            safe_url = html.escape(site["url"])
            st.markdown(
                f"**{safe_name}** — "
                f'<a href="{safe_url}" target="_blank" rel="noopener">{safe_url}</a>',
                unsafe_allow_html=True,
            )
        with action_col:
            if st.button("Delete", key=f"del_site_{site['id']}", type="secondary"):
                delete_website(site["id"])
                st.rerun()


def page_history() -> None:
    st.header("Saved analyses")
    _init_history_confirm_state()

    sources = list_filter_source_names()
    tickers_all = list_tickers()

    st.markdown(
        """
        <style>
        /* Compact history filters — 16px prevents iOS zoom on focus */
        div[data-testid="stSelectbox"] {
            max-width: 11rem;
        }
        div[data-testid="stSelectbox"] label {
            font-size: 0.75rem !important;
            margin-bottom: 0.1rem !important;
        }
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            min-height: 2rem !important;
            font-size: 16px !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            margin-bottom: 0.3rem !important;
            padding: 0.35rem 0.45rem 0.3rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            gap: 0.15rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            align-items: center !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"] {
            min-width: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] button[data-testid="stBaseButton-tertiary"] {
            min-width: 1.65rem;
            min-height: 1.65rem;
            padding: 0.1rem 0.25rem;
            font-size: 1rem;
            line-height: 1;
        }
        @media (max-width: 640px) {
            div[data-testid="stSelectbox"] {
                max-width: 9.5rem;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                padding: 0.35rem 0.4rem 0.28rem !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: 1.75rem minmax(0, 1fr) !important;
                column-gap: 0.3rem !important;
                align-items: start !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    filter_left, filter_right, _ = st.columns([0.95, 0.95, 6])
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
            or st.session_state.pending_edit_source_id == row_id
        )
        full = get_analysis(row_id)

        with st.container(border=True):
            expanded = _render_history_list_header(row, row_id)

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
            elif st.session_state.pending_edit_source_id == row_id:
                _render_edit_source_panel(
                    row_id,
                    current_source=row.get("source_name", ""),
                )

            if expanded:
                render_history_analysis_body(
                    row["analysis"],
                    row["source_label"],
                    row_id=row_id,
                    pending=pending,
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

    tab_analyze, tab_history, tab_websites = st.tabs(["Analyze", "History", "Websites"])
    with tab_analyze:
        page_analyze()
    with tab_history:
        page_history()
    with tab_websites:
        page_websites()


main()
