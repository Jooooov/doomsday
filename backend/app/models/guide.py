from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class Guide(Base):
    __tablename__ = "guides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    cluster_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="current")  # current / updating / pending_regional
    language: Mapped[str] = mapped_column(String(5), default="pt")

    # Snapshot of profile at generation time
    profile_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    risk_level_at_generation: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    current_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("guide_versions.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="guides")
    versions: Mapped[list["GuideVersion"]] = relationship("GuideVersion", foreign_keys="GuideVersion.guide_id", back_populates="guide", cascade="all, delete-orphan")


class GuideVersion(Base):
    __tablename__ = "guide_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guide_id: Mapped[str] = mapped_column(String(36), ForeignKey("guides.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(default=1)

    # Content stored as JSON (12 categories)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Rollback metadata
    region_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rollback_available: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    guide: Mapped["Guide"] = relationship("Guide", foreign_keys=[guide_id], back_populates="versions")
