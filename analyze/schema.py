from typing import Literal

from pydantic import BaseModel, Field


class MentionedCompany(BaseModel):
    ticker: str
    company_name: str
    relevance: Literal["primary", "secondary", "mentioned"]
    how_article_mentions_it: str = ""
    is_public: bool = True


class CompanyOpinion(BaseModel):
    ticker: str
    company_name: str
    rating: Literal["buy", "hold", "sell", "avoid"]
    confidence: Literal["low", "medium", "high"]
    rationale: str
    article_says: str = Field(
        description="What the article claims about this company, if anything"
    )


class AiOpinion(BaseModel):
    rating: Literal["buy", "hold", "sell", "avoid"]
    confidence: Literal["low", "medium", "high"]
    rationale: str
    time_horizon: Literal["short", "medium", "long"]
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class StockAnalysis(BaseModel):
    title: str
    executive_summary: str = Field(
        description="2-4 sentence high-level takeaway"
    )
    detailed_summary: str = Field(
        description="Long-form narrative summary, 3-5 minute read"
    )
    mentioned_companies: list[MentionedCompany] = Field(default_factory=list)
    company_opinions: list[CompanyOpinion] = Field(
        default_factory=list,
        description="Per publicly traded company: buy/hold/sell based on article",
    )
    key_claims: list[str] = Field(default_factory=list)
    bull_case: str
    bear_case: str
    sentiment_from_article: Literal["bullish", "bearish", "neutral", "mixed"]
    ai_opinion: AiOpinion
    article_bias: Literal[
        "analytical", "promotional", "news", "opinion", "rumor", "mixed", "unknown"
    ]
    no_actionable_stocks: bool = False
    disclaimer: str = (
        "Not financial advice. This analysis is based solely on the provided "
        "article content and does not incorporate external market data."
    )
