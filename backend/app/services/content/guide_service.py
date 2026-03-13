"""Guide generation service — streaming + cluster cache + version rollback"""
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.guide import Guide, GuideVersion
from app.models.user import User
from app.services.llm.factory import get_llm

logger = logging.getLogger(__name__)

CATEGORIES = [
    "water", "food", "shelter", "health",
    "communication", "evacuation", "energy",
    "security", "documentation", "mental_health",
    "armed_conflict", "family_coordination",
]

GUIDE_SYSTEM_PROMPT = """You are a civil preparedness expert writing practical survival guides.
Be specific about quantities using the user's household profile.
Use metric units. Always include a brief legal disclaimer per section.
Content is informational only — not a substitute for official civil protection guidance.
Return valid JSON only."""


def compute_cluster_hash(user: User) -> str:
    """hash(region + household_size + housing_type + language) for cache clustering."""
    key = f"{user.country_code}|{user.zip_code or ''}|{user.household_size or 1}|{user.housing_type or 'unknown'}|{user.language}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


async def get_guide_content(guide: Guide) -> dict:
    """Load current guide content from latest version."""
    result_versions = guide.versions if hasattr(guide, 'versions') and guide.versions else []
    if not result_versions:
        return {}
    latest = max(result_versions, key=lambda v: v.version_number)
    return latest.content


async def generate_guide_streaming(user: User, db: AsyncSession) -> AsyncIterator[str]:
    """Generate personalized guide section by section (streaming SSE chunks)."""
    llm = get_llm()
    cluster_hash = compute_cluster_hash(user)

    # 1. Cluster cache hit → return instantly
    cache_path = Path(settings.DATA_DIR) / "clusters" / f"{cluster_hash}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            cached = json.load(f)
        yield json.dumps({"type": "cached", "content": cached})
        return

    # 2. Load base regional content (pre-generated batch)
    region_path = (
        Path(settings.REGIONS_DIR)
        / user.country_code.lower()
        / f"{user.zip_code or 'general'}.json"
    )
    base_content = {}
    if region_path.exists():
        with open(region_path) as f:
            base_content = json.load(f)

    content = {}

    for category in CATEGORIES:
        yield json.dumps({"type": "category_start", "category": category})
        try:
            prompt = f"""Generate preparation guide section for: {category}
User: country={user.country_code}, household_size={user.household_size or 1},
housing={user.housing_type or 'unknown'}, vehicle={user.has_vehicle}, language={user.language}
Base regional content: {json.dumps(base_content.get(category, {}))}

Return JSON: {{
  "title": str,
  "items": [{{"text": str, "quantity": float|null, "unit": str|null, "priority": int, "formula": str|null}}],
  "tips": [str],
  "disclaimer": str
}}"""
            section = await llm.generate_json(prompt, GUIDE_SYSTEM_PROMPT)
            content[category] = section
            yield json.dumps({"type": "category_done", "category": category, "data": section})
        except Exception as e:
            logger.error(f"Guide generation failed for {category}: {e}")
            # Fallback to base content
            content[category] = base_content.get(category, {
                "title": category.replace("_", " ").title(),
                "items": [],
                "error": "Content temporarily unavailable",
            })
            yield json.dumps({"type": "category_error", "category": category})

    # 3. Persist to cluster cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    # 4. Save guide version to DB
    result = await db.execute(select(Guide).where(Guide.user_id == user.id))
    guide = result.scalar_one_or_none()

    if not guide:
        guide = Guide(
            id=str(uuid.uuid4()),
            user_id=user.id,
            cluster_hash=cluster_hash,
            language=user.language,
            profile_snapshot={
                "country_code": user.country_code,
                "household_size": user.household_size,
                "housing_type": user.housing_type,
                "has_vehicle": user.has_vehicle,
            },
        )
        db.add(guide)
        await db.flush()

    # Get next version number
    existing_versions = [v for v in guide.versions] if guide.versions else []
    next_version = len(existing_versions) + 1

    version = GuideVersion(
        id=str(uuid.uuid4()),
        guide_id=guide.id,
        version_number=next_version,
        content=content,
        region_id=user.country_code,
    )
    db.add(version)
    guide.current_version_id = version.id
    guide.status = "current"
    await db.commit()

    yield json.dumps({"type": "complete"})


async def rollback_guide_version(user: User, region: str, db: AsyncSession) -> dict:
    """Rollback to previous guide version. CLI: rollback --region=PT --to=previous"""
    result = await db.execute(select(Guide).where(Guide.user_id == user.id))
    guide = result.scalar_one_or_none()

    if not guide:
        return {"error": "No guide found"}
    if not guide.versions or len(guide.versions) < 2:
        return {"error": "No previous version available for rollback"}

    sorted_versions = sorted(guide.versions, key=lambda v: v.version_number)
    previous = sorted_versions[-2]
    guide.current_version_id = previous.id
    await db.commit()

    return {
        "rolled_back_to_version": previous.version_number,
        "region": region,
        "content_date": previous.created_at.isoformat(),
    }
