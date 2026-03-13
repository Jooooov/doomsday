"""POI service — Overpass API + server-side weekly cache per ZIP code"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.poi_cache import POICache

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


async def get_pois_for_location(
    zip_code: str,
    country_code: str,
    radius_km: float,
    category: str,
    db: AsyncSession,
) -> dict:
    """Return POIs from cache (weekly) or fetch from Overpass (1 query covers all categories)."""
    result = await db.execute(
        select(POICache).where(
            POICache.zip_code == zip_code,
            POICache.country_code == country_code,
            POICache.cache_expires > datetime.now(timezone.utc),
        )
    )
    cached = result.scalar_one_or_none()

    if cached:
        data = cached.poi_data
        if category != "all" and isinstance(data, dict) and category in data:
            return {"pois": data[category], "category": category, "cached": True}
        return {"pois": data, "cached": True}

    poi_data = await _fetch_all_pois(zip_code, country_code, radius_km)

    cache_entry = POICache(
        id=str(uuid.uuid4()),
        zip_code=zip_code,
        country_code=country_code,
        radius_km=radius_km,
        poi_data=poi_data,
        cache_expires=datetime.now(timezone.utc) + timedelta(weeks=1),
    )
    db.add(cache_entry)
    await db.commit()

    if category != "all" and isinstance(poi_data, dict) and category in poi_data:
        return {"pois": poi_data[category], "category": category, "cached": False}
    return {"pois": poi_data, "cached": False}


async def _fetch_all_pois(zip_code: str, country_code: str, radius_km: float) -> dict:
    """One Overpass query covering all preparedness categories."""
    radius_m = int(radius_km * 1000)

    # Geocode ZIP → lat/lon via Nominatim
    # Strategy: multiple fallbacks because Nominatim is inconsistent with postal codes
    lat, lon = None, None
    country_lower = country_code.lower()
    # Many countries use XXXX-YYY format — strip suffix for structured lookup
    zip_prefix = zip_code.split("-")[0].split(" ")[0]

    queries = [
        # 1) structured prefix + countrycodes (works for PT, DE, FR...)
        {"postalcode": zip_prefix, "countrycodes": country_lower, "format": "json", "limit": 1},
        # 2) full code + countrycodes
        {"postalcode": zip_code, "countrycodes": country_lower, "format": "json", "limit": 1},
        # 3) free-form with country name (avoid ISO codes — Nominatim misinterprets them)
        {"q": f"{zip_prefix} {country_code}", "countrycodes": country_lower, "format": "json", "limit": 1},
    ]

    async with httpx.AsyncClient(timeout=10) as client:
        for params in queries:
            try:
                geo_resp = await client.get(
                    NOMINATIM_URL, params=params,
                    headers={"User-Agent": "DoomsdayPlatform/1.0 (preparedness)"},
                )
                geo_resp.raise_for_status()
                results = geo_resp.json()
                if results:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    logger.info(f"Geocoded {zip_code}/{country_code} → {lat},{lon}")
                    break
            except Exception as e:
                logger.warning(f"Geocoding attempt failed ({params}): {e}")

    if lat is None:
        logger.error(f"Geocoding failed for {zip_code}/{country_code} — all strategies exhausted")
        return {}

    # Single comprehensive Overpass query
    query = f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[amenity~"drinking_water|water_point|hospital|clinic|pharmacy|doctors|school|community_centre|police|fire_station|fuel"];
  node(around:{radius_m},{lat},{lon})[shop~"supermarket|convenience|marketplace"];
  node(around:{radius_m},{lat},{lon})[amenity="shelter"][name];
);
out body;
"""
    elements = []
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(OVERPASS_URL, data=query)
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                break  # success
        except Exception as e:
            logger.warning(f"Overpass attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                import asyncio
                await asyncio.sleep(2 ** attempt)  # 1s, 2s backoff
    if not elements:
        logger.error(f"Overpass failed after 3 attempts for {zip_code}/{country_code}")
        return {}

    result: dict = {
        "water": [], "health": [], "food": [],
        "shelter": [], "evacuation": [], "security": [],
    }

    for el in elements:
        tags = el.get("tags", {})
        amenity = tags.get("amenity", "")
        shop = tags.get("shop", "")
        poi = {
            "id": el["id"],
            "lat": el.get("lat"),
            "lon": el.get("lon"),
            "name": tags.get("name") or amenity or shop or "Unknown",
            "type": amenity or shop,
        }
        if amenity in ("drinking_water", "water_point"):
            result["water"].append(poi)
        elif amenity in ("hospital", "clinic", "pharmacy", "doctors"):
            result["health"].append(poi)
        elif amenity in ("school", "community_centre", "shelter"):
            result["shelter"].append(poi)
        elif amenity in ("police", "fire_station"):
            result["security"].append(poi)
        elif amenity == "fuel":
            result["evacuation"].append(poi)
        elif shop in ("supermarket", "convenience", "marketplace"):
            result["food"].append(poi)

    return result
