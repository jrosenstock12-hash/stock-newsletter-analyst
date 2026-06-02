import streamlit as st

from analyze.llm import analyze_content, test_openai_connection
from config import apply_streamlit_secrets, get_openai_api_key
from db.database import delete_analyses, get_analysis, init_db, list_analyses
from ingest.email import parse_eml_file, parse_pasted_content
from ingest.markdown import parse_markdown_file
from ingest.url import fetch_url, normalize_url

st.set_page_config(
    page_title="Stock Newsletter Analyst",
    page_icon="📈",
    layout="wide",
)

RATING_COLORS = {
    "buy": "#16a34a",
    "hold": "#ca8a04",
    "sell": "#dc2626",
    "avoid": "#6b7280",
}


def render_opinion_card(analysis: dict) -> None:
    opinion = analysis["ai_opinion"]
    rating = opinion["rating"]
    color = RATING_COLORS.get(rating, "#6b7280")

    st.markdown(
        f"""
        <div style="
            border: 2px solid {color};
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
            background: {color}15;
        ">
            <div style="font-size: 1.5rem; font-weight: 700; color: {color}; text-transform: uppercase;">
                {rating}
            </div>
            <div style="margin-top: 0.5rem;">
                <strong>Confidence:</strong> {opinion["confidence"]} &nbsp;|&nbsp;
                <strong>Horizon:</strong> {opinion["time_horizon"]}
            </div>
            <div style="margin-top: 0.75rem;">{opinion["rationale"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Catalysts**")
        for item in opinion.get("catalysts", []):
            st.markdown(f"- {item}")
    with col2:
        st.markdown("**Risks**")
        for item in opinion.get("risks", []):
            st.markdown(f"- {item}")


def render_analysis(analysis: dict, tickers: list[str], source_label: str) -> None:
    st.subheader(analysis.get("title", "Analysis"))
    st.caption(f"Source: {source_label}")

    if tickers:
        st.markdown("**Public tickers:** " + ", ".join(f"`{t}`" for t in tickers))

    render_opinion_card(analysis)

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

    company_opinions = analysis.get("company_opinions", [])
    if company_opinions:
        st.markdown("### Stock opinions by company")
        for co in company_opinions:
            rating = co.get("rating", "hold").upper()
            color = RATING_COLORS.get(co.get("rating", "hold"), "#6b7280")
            st.markdown(
                f"**{co.get('ticker', '?')} — {co.get('company_name', '')}** "
                f": <span style='color:{color};font-weight:700'>{rating}</span> "
                f"({co.get('confidence', 'medium')} confidence)",
                unsafe_allow_html=True,
            )
            if co.get("article_says"):
                st.markdown(f"*Article:* {co['article_says']}")
            st.markdown(f"*Opinion:* {co.get('rationale', '')}")
            st.markdown("")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Article sentiment", analysis["sentiment_from_article"].title())
    with col2:
        st.metric("Article bias", analysis["article_bias"].title())
    with col3:
        st.metric(
            "Public companies",
            len([c for c in analysis.get("mentioned_companies", []) if c.get("is_public", True)])
            or len(company_opinions),
        )

    st.markdown("### Key claims from the article")
    for claim in analysis.get("key_claims", []):
        st.markdown(f"- {claim}")

    col_bull, col_bear = st.columns(2)
    with col_bull:
        st.markdown("### Bull case")
        st.write(analysis["bull_case"])
    with col_bear:
        st.markdown("### Bear case")
        st.write(analysis["bear_case"])

    companies = analysis.get("mentioned_companies", [])
    if companies:
        st.markdown("### All companies mentioned")
        for co in companies:
            pub = "public" if co.get("is_public", True) else "private"
            ticker = co.get("ticker") or "—"
            st.markdown(
                f"- **{ticker}** — {co['company_name']} "
                f"({co['relevance']}, {pub})"
            )
            if co.get("how_article_mentions_it"):
                st.caption(co["how_article_mentions_it"])

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
            with st.spinner("Reading content and running analysis..."):
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
            )
        except Exception as exc:
            st.error(str(exc))


def page_history() -> None:
    st.header("Saved analyses")
    rows = list_analyses(limit=100)

    if not rows:
        st.info("No saved analyses yet. Run your first analysis on the Analyze tab.")
        return

    for row in rows:
        opinion = row["analysis"]["ai_opinion"]
        rating = opinion["rating"].upper()
        tickers = ", ".join(row["detected_tickers"]) or "—"

        with st.expander(
            f"#{row['id']} · {rating} · {row['title'][:80]} · {tickers}"
        ):
            st.caption(
                f"{row['created_at'][:19]} · {row['source_type']} · "
                f"{row['source_label'][:120]}"
            )
            render_analysis(
                row["analysis"],
                row["detected_tickers"],
                row["source_label"],
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

    st.title("📈 Stock Newsletter Analyst")
    st.caption(
        "Paste a newsletter, upload an email, or drop in a link — get a stock-focused "
        "summary with a buy/hold/sell opinion. Personal use only; not financial advice."
    )

    tab_analyze, tab_history = st.tabs(["Analyze", "History"])
    with tab_analyze:
        page_analyze()
    with tab_history:
        page_history()


main()
