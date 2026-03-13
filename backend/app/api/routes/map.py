"""Local POI map endpoints via Overpass API + server-side cache"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db

router = APIRouter()


@router.get("/pois")
async def get_pois(
    zip_code: str = Query(...),
    country_code: str = Query(...),
    radius_km: float = Query(default=5.0, le=20.0),
    category: str = Query(default="all"),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch POIs from Overpass API with weekly server-side cache.
    One comprehensive query per ZIP code covers all categories.
    """
    from app.services.content.poi_service import get_pois_for_location
    return await get_pois_for_location(zip_code, country_code, radius_km, category, db)
