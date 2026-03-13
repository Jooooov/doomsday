"""Doomsday Clock API — world map + country detail + top5 for anonymous users"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.models.clock import CountryRiskScore
from app.schemas.clock import CountryRiskScoreOut, WorldMapOut, CountryDetailOut

router = APIRouter()


@router.get("/world", response_model=WorldMapOut)
async def get_world_map(db: AsyncSession = Depends(get_db)):
    """All country risk scores for choropleth map. No auth required."""
    result = await db.execute(select(CountryRiskScore))
    scores = result.scalars().all()
    return WorldMapOut(
        countries=[CountryRiskScoreOut.model_validate(s) for s in scores],
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/country/{country_iso}", response_model=CountryDetailOut)
async def get_country_detail(country_iso: str, db: AsyncSession = Depends(get_db)):
    """Country clock detail with news context. No auth required."""
    result = await db.execute(
        select(CountryRiskScore).where(CountryRiskScore.country_iso == country_iso.upper())
    )
    score = result.scalar_one_or_none()
    if not score:
        return CountryDetailOut(
            country_iso=country_iso.upper(),
            seconds_to_midnight=settings.CLOCK_ANCHOR_SECONDS,
            risk_level="green",
            llm_context_paragraph=None,
            top_news_items=[],
            last_updated=datetime.now(timezone.utc),
            is_propagated=True,
        )
    return CountryDetailOut.model_validate(score)


@router.get("/top5/{country_iso}")
async def get_top5(country_iso: str, db: AsyncSession = Depends(get_db)):
    """Pre-generated top 5 items for anonymous users (IP geolocation → country)."""
    from app.services.content.top5 import get_top5_for_country
    return await get_top5_for_country(country_iso.upper(), db)
