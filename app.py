import streamlit as st

from analyze.llm import analyze_content, test_openai_connection
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


def yahoo_quote_url(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker.upper()}/"


def ticker_links(tickers: list[str]) -> str:
    if not tickers:
        return ""
    links = [
        f"[{t.upper()}]({yahoo_quote_url(t)})" for t in tickers if t and t.strip()
    ]
    return ", ".join(links)


def render_source_tag(source_name: str) -> None:
    if not source_name:
        return
    st.markdown(
        f'<span style="display:inline-block;background:#1e3a5f;color:#93c5fd;'
        f"border:1px solid #3b82f6;border-radius:999px;padding:0.15rem 0.65rem;"
        f'font-size:0.85rem;font-weight:600;margin-right:0.35rem;">'
        f"{source_name}</span>",
        unsafe_allow_html=True,
    )


def render_ticker_tags(tickers: list[str]) -> None:
    if not tickers:
        return
    tags = []
    for t in tickers:
        sym = t.upper()
        yahoo = yahoo_quote_url(sym)
        tags.append(
            f'<a href="{yahoo}" target="_blank" style="display:inline-block;'
            f"background:#14532d;color:#86efac;border:1px solid #22c55e;"
            f'border-radius:999px;padding:0.15rem 0.55rem;font-size:0.8rem;'
            f'font-weight:600;margin:0.15rem 0.25rem 0.15rem 0;text-decoration:none;">'
            f"{sym}</a>"
        )
    st.markdown("".join(tags), unsafe_allow_html=True)


def display_title(analysis: dict, fallback_title: str = "Analysis") -> str:
    title = analysis.get("title") or fallback_title
    article_date = analysis.get("article_date", "")
    return format_display_title(title, article_date)


def history_expander_label(row: dict) -> str:
    analysis = row["analysis"]
    title = row["title"][:55]
    source = row.get("source_name") or "Unknown"
    ratings = []
    for co in analysis.get("company_opinions", []):
        ratings.append(f"{co.get('ticker', '?')}:{co.get('rating', 'hold').upper()}")
    rating_part = ", ".join(ratings[:4]) if ratings else "—"
    if len(ratings) > 4:
        rating_part += "…"
    return f"#{row['id']} · {source} · {title} · {rating_part}"


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
            st.write(co["article_says"])
        if co.get("rationale"):
            st.markdown("**Opinion**")
            st.write(co["rationale"])
        st.markdown("")


def render_analysis(
    analysis: dict,
    tickers: list[str],
    source_label: str,
    source_name: str = "",
) -> None:
    st.subheader(display_title(analysis))
    tag_col1, tag_col2 = st.columns([1, 3])
    with tag_col1:
        if source_name:
            render_source_tag(source_name)
    with tag_col2:
        render_ticker_tags(tickers)
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
            render_analysis(
                analysis.model_dump(),
                tickers,
                ingest.source_label,
                ingest.source_name,
            )
        except Exception as exc:
            st.error(str(exc))


def page_history() -> None:
    st.header("Saved analyses")

    sources = list_source_names()
    tickers_all = list_tickers()

    col1, col2 = st.columns(2)
    with col1:
        source_options = ["All sources"] + sources
        source_pick = st.selectbox("Filter by source", source_options, key="hist_source")
    with col2:
        ticker_options = ["All tickers"] + tickers_all
        ticker_pick = st.selectbox("Filter by ticker", ticker_options, key="hist_ticker")

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
        with st.expander(history_expander_label(row)):
            tag_row1, tag_row2 = st.columns([1, 3])
            with tag_row1:
                render_source_tag(row.get("source_name", ""))
            with tag_row2:
                render_ticker_tags(row.get("detected_tickers", []))
            st.caption(
                f"{row['created_at'][:19]} · {row['source_type']} · "
                f"{row['source_label'][:120]}"
            )
            render_analysis(
                row["analysis"],
                row["detected_tickers"],
                row["source_label"],
                row.get("source_name", ""),
            )

            if st.button("Delete", key=f"delete_{row['id']}"):
                delete_analyses([row["id"]])
                st.rerun()

            full = get_analysis(row["id"])
            if full:
                with st.expander("Extracted text (for debugging)"):
                    st.text(full["clean_text"][:8000])


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
