from typing import Literal

from pydantic import BaseModel, Field


class CompanyOpinion(BaseModel):
    ticker: str
    company_name: str
    rating: Literal["buy", "hold", "sell", "avoid"]
    confidence: Literal["low", "medium", "high"]
    article_says: str = Field(
        description=(
            "Detailed explanation of what the author said about this stock "
            "(claims, data, tone, implications)"
        )
    )
    rationale: str = Field(
        description=(
            "Your buy/hold/sell/avoid opinion based on what the article said, "
            "and why"
        )
    )


class StockAnalysis(BaseModel):
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
