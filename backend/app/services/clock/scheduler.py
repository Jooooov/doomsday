"""
Doomsday Clock scheduler — APScheduler jobs:
  - News scan 4x/day (every 6h) → keyword match → LLM scoring
  - Country relations graph recalculation 1x/day
  - Cloudflare Pages static fallback deploy 1x/hour
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def start_clock_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler()

    # News scan every 6 hours: 00:00, 06:00, 12:00, 18:00
    _scheduler.add_job(
        run_news_scan,
        CronTrigger(hour="0,6,12,18", minute=0),
        id="news_scan",
        name="Doomsday Clock news scan",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Country relations graph — recalculate once per day at 03:00
    _scheduler.add_job(
        run_relations_update,
        CronTrigger(hour=3, minute=0),
        id="relations_update",
        name="Country relations graph update",
        replace_existing=True,
    )

    # Cloudflare Pages fallback — deploy every hour
    _scheduler.add_job(
        run_cf_pages_deploy,
        IntervalTrigger(hours=1),
        id="cf_pages_deploy",
        name="Cloudflare Pages static fallback",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Clock scheduler started (4x/day scan, 1x/day relations, 1x/hour CF deploy)")


async def run_news_scan():
    """Fetch news, keyword-match, call LLM only on matches, update scores."""
    logger.info("Starting news scan...")
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.clock.scoring_engine import process_news_scan
        async with AsyncSessionLocal() as db:
            await process_news_scan(db)
    except Exception as e:
        logger.error(f"News scan failed: {e}", exc_info=True)


async def run_relations_update():
    """Recalculate country relations graph via LLM."""
    logger.info("Updating country relations graph...")
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.clock.scoring_engine import update_relations_graph
        async with AsyncSessionLocal() as db:
            await update_relations_graph(db)
    except Exception as e:
        logger.error(f"Relations update failed: {e}", exc_info=True)


async def run_cf_pages_deploy():
    """Deploy static fallback to Cloudflare Pages with latest clock scores."""
    try:
        from app.services.clock.cf_fallback import deploy_static_fallback
        await deploy_static_fallback()
    except Exception as e:
        logger.error(f"CF Pages deploy failed: {e}", exc_info=True)
