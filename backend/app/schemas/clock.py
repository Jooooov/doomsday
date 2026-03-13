from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class CountryRiskScoreOut(BaseModel):
    country_iso: str
    seconds_to_midnight: float
    risk_level: str
    llm_context_paragraph: Optional[str]
    top_news_items: Optional[list]
    last_updated: datetime
    is_propagated: bool

    model_config = {"from_attributes": True}


class WorldMapOut(BaseModel):
    countries: List[CountryRiskScoreOut]
    generated_at: datetime


class CountryDetailOut(BaseModel):
    country_iso: str
    seconds_to_midnight: float
    risk_level: str
    llm_context_paragraph: Optional[str]
    top_news_items: Optional[list]
    last_updated: datetime
    is_propagated: bool = False

    model_config = {"from_attributes": True}
