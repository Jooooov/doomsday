from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(50), default="email_password")
    google_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)

    # Profile
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    household_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    housing_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    has_vehicle: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="pt")

    # GDPR
    health_data_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    health_conditions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Family group
    family_group_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("family_groups.id", ondelete="SET NULL"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    guides: Mapped[List["Guide"]] = relationship("Guide", back_populates="user", cascade="all, delete-orphan")
    family_group: Mapped[Optional["FamilyGroup"]] = relationship("FamilyGroup", foreign_keys=[family_group_id], back_populates="members")
    push_subscriptions: Mapped[List["PushSubscription"]] = relationship("PushSubscription", back_populates="user", cascade="all, delete-orphan")
