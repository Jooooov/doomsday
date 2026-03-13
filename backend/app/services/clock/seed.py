"""
Database Seeder — Initial Doomsday Clock Country Scores.

Called once on first deployment (or via CLI `doomsday seed-scores`) to populate
the `country_risk_scores` table with analytically-derived starting scores.

Starting scores come from CountryConfig.initial_score_seconds in the region
registry, which were set based on the 2026 geopolitical situation.

Idempotent: existing rows are skipped (upsert by country_code).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doomsday import CountryRiskScore
from app.services.clock.region_registry import REGION_REGISTRY, GLOBAL_BASELINE_SECONDS

logger = logging.getLogger(__name__)


async def seed_initial_scores(db: AsyncSession) -> dict[str, str]:
    """
    Seed the `country_risk_scores` table with initial country scores.

    Returns a summary dict: {"PT": "created", "US": "created", "RU": "skipped", ...}
    """
    summary: dict[str, str] = {}

    for country_code, cfg in sorted(REGION_REGISTRY.items()):
        # Check if this country already has a score row
        result = await db.execute(
            select(CountryRiskScore).where(
                CountryRiskScore.country_code == country_code
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            summary[country_code] = "skipped"
            logger.debug("Seed: %s already exists (score=%.2f), skipping.", country_code, existing.score_seconds)
            continue

        # Create a new row
        score_row = CountryRiskScore(
            country_code=country_code,
            country_name=cfg.country_name,
            region=cfg.continent,
            score_seconds=cfg.initial_score_seconds,
            baseline_seconds=GLOBAL_BASELINE_SECONDS,
            cumulative_delta=0.0,
        )
        db.add(score_row)
        summary[country_code] = "created"
        logger.info(
            "Seed: created score for %s (%s) = %.2fs",
            country_code,
            cfg.country_name,
            cfg.initial_score_seconds,
        )

    await db.flush()
    return summary


async def reset_country_to_baseline(
    db: AsyncSession,
    country_code: str,
) -> bool:
    """
    Reset a single country's score to its calibrated initial value.
    Used by the CLI rollback command when full history rollback isn't needed.

    Returns True if the reset was performed, False if country not found.
    """
    cfg = REGION_REGISTRY.get(country_code.upper())
    if cfg is None:
        logger.error("reset_country_to_baseline: unknown country %s", country_code)
        return False

    result = await db.execute(
        select(CountryRiskScore).where(
            CountryRiskScore.country_code == country_code.upper()
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        logger.warning("reset_country_to_baseline: no DB row for %s", country_code)
        return False

    row.score_seconds = cfg.initial_score_seconds
    row.cumulative_delta = 0.0
    row.last_updated_at = datetime.now(timezone.utc)

    await db.flush()
    logger.info(
        "Reset %s score to initial value %.2fs",
        country_code,
        cfg.initial_score_seconds,
    )
    return True
