from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class POICache(Base):
    __tablename__ = "poi_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    zip_code: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    radius_km: Mapped[float] = mapped_column(Float, default=5.0)
    poi_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cache_expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
