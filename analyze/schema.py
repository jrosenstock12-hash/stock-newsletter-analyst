from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompanyOpinion(BaseModel):
    ticker: str
    company_name: str
    rating: Literal["buy", "hold", "sell", "avoid"]
    confidence: Literal["low", "medium", "high"]
    article_says: str = Field(
        description=(
            "Primary field: 8-12 sentences on what the author explicitly said about "
            "this company — metrics, products, peer comparisons, quotes. Only if the "
            "company is named/discussed in the article; never speculate on indirect "
            "beneficiaries or write that a company was not mentioned"
        )
    )
    rationale: str = Field(
        description=(
            "Brief 2-3 sentence buy/hold/sell/avoid opinion tied to article_says"
        )
    )


class AiOpinion(BaseModel):
    """Legacy field — not shown in UI; optional for API compatibility."""

    rating: Literal["buy", "hold", "sell", "avoid"] = "hold"
    confidence: Literal["low", "medium", "high"] = "medium"
    rationale: str = ""
    time_horizon: Literal["short", "medium", "long"] = "medium"
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class StockAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    article_date: str = Field(
        default="",
        description="Article publish date as YYYY-MM-DD when known from the text",
    )
    executive_summary: str = Field(
        description="2-4 sentence high-level takeaway"
    )
    detailed_summary: str = Field(
        description="Long-form narrative summary, 3-5 minute read"
    )
    company_opinions: list[CompanyOpinion] = Field(
        default_factory=list,
        description="Per publicly traded company discussed in the article",
    )
    disclaimer: str = (
        "Not financial advice. This analysis is based solely on the provided "
        "article content and does not incorporate external market data."
    )
    # Legacy optional fields (not displayed; prevent validation errors on deploy)
    key_claims: list[str] = Field(default_factory=list)
    bull_case: str = ""
    bear_case: str = ""
    sentiment_from_article: Literal["bullish", "bearish", "neutral", "mixed"] = (
        "neutral"
    )
    ai_opinion: AiOpinion = Field(default_factory=AiOpinion)
    article_bias: Literal[
        "analytical", "promotional", "news", "opinion", "rumor", "mixed", "unknown"
    ] = "unknown"
    no_actionable_stocks: bool = False
