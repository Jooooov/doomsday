"""
SQLAlchemy ORM models for persisted user profiles and checklist cache.

Design decisions:
- StoredProfile uses a JSONB `profile_data` column for the full profile (flexible),
  PLUS a set of denormalized scalar columns for efficient querying and analytics.
- Health data is stored only when health_data_consent=True (GDPR compliance).
- ChecklistCache avoids recomputing identical formula runs.
- Both tables share the same Base as the rest of the application.

All profile variables required for quantity calculations are reflected as
denormalized columns on StoredProfile for query efficiency.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

# Use the shared Base so Alembic tracks all tables in a single metadata object
from app.models.base import Base


# ---------------------------------------------------------------------------
# profiles table
# ---------------------------------------------------------------------------

class StoredProfile(Base):
    """
    Persisted user profile.

    The ``profile_data`` JSONB column holds the full sanitised UserProfile dict.
    Health conditions are EXCLUDED from that column if ``health_data_consent`` is False.

    The denormalized scalar columns (adults_count, children_count, …) exist for
    query efficiency — they mirror the values inside ``profile_data``.

    Columns map to formula-engine variables:
    ──────────────────────────────────────────────────────────────────
    household size    adults_count, children_count, seniors_count, total_people
    ages              adults_count / children_count / seniors_count (grouped)
    dietary flags     has_dietary_restrictions  (bool gate; full list in JSONB)
    location type     location_type  (urban | suburban | rural | remote)
    duration pref     duration_preference  (3_days … 6_months)
    climate zone      climate_zone   (hot | temperate | cold | tropical)
    housing type      housing_type   (apartment | house | rural | mobile)
    pets              has_pets, total_pets
    health            has_medical_needs, requires_power_dependency
    storage           storage_space_m3 (optional constraint)
    ──────────────────────────────────────────────────────────────────
    """

    __tablename__ = "profiles"
    __table_args__ = (
        Index("ix_profiles_family_slug", "family_slug"),
        Index("ix_profiles_country", "country"),
        Index("ix_profiles_created_at", "created_at"),
        CheckConstraint(
            "total_people >= 1 AND total_people <= 100",
            name="ck_profiles_total_people_range",
        ),
        CheckConstraint(
            "preparation_days >= 1 AND preparation_days <= 365",
            name="ck_profiles_preparation_days_range",
        ),
        CheckConstraint(
            "adults_count >= 0",
            name="ck_profiles_adults_non_negative",
        ),
        CheckConstraint(
            "children_count >= 0",
            name="ck_profiles_children_non_negative",
        ),
        CheckConstraint(
            "seniors_count >= 0",
            name="ck_profiles_seniors_non_negative",
        ),
        CheckConstraint(
            "location_type IN ('urban', 'suburban', 'rural', 'remote')",
            name="ck_profiles_location_type",
        ),
        CheckConstraint(
            "housing_type IN ('apartment', 'house', 'rural', 'mobile')",
            name="ck_profiles_housing_type",
        ),
        CheckConstraint(
            "climate_zone IN ('hot', 'temperate', 'cold', 'tropical')",
            name="ck_profiles_climate_zone",
        ),
        CheckConstraint(
            "duration_preference IN "
            "('3_days', '1_week', '2_weeks', '1_month', '3_months', '6_months')",
            name="ck_profiles_duration_preference",
        ),
        {"comment": "Persisted user preparation profiles"},
    )

    # ── Primary key ─────────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID primary key",
    )

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Record creation timestamp (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Record last update timestamp (UTC)",
    )

    # ── Family sharing (no user accounts in MVP) ─────────────────────────────
    family_slug: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Short slug for family checklist sharing (no auth in MVP)",
    )

    # ── Full profile JSON ────────────────────────────────────────────────────
    profile_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full sanitised UserProfile dict; health data excluded if consent=False",
    )

    # ── Household composition (denormalised for querying) ────────────────────

    country: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="PT",
        comment="ISO 3166-1 alpha-2 country code (uppercase)",
    )
    total_people: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Total household members (adults + children + seniors)",
    )
    adults_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of adults (18–64) in the household",
    )
    children_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of children (under 18) in the household",
    )
    seniors_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of seniors (65+) in the household",
    )

    # ── Pets ─────────────────────────────────────────────────────────────────
    has_pets: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if the household has any pets",
    )
    total_pets: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of pets across all types",
    )

    # ── Dietary restrictions ──────────────────────────────────────────────────
    has_dietary_restrictions: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment=(
            "True if any household member has dietary restrictions "
            "(vegetarian, vegan, gluten-free, halal, kosher, allergy, etc.)"
        ),
    )
    dietary_flags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            'Array of dietary restriction strings present in the household: '
            '["vegetarian","gluten_free",...]'
        ),
    )

    # ── Location & environment ────────────────────────────────────────────────
    location_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="urban",
        comment="Urban footprint: urban | suburban | rural | remote",
    )
    housing_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="apartment",
        comment="Dwelling type: apartment | house | rural | mobile",
    )
    climate_zone: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="temperate",
        comment="Climate zone: hot | temperate | cold | tropical",
    )
    region_city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="City or municipality name (optional)",
    )
    region_latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="WGS-84 latitude (optional, for POI lookups)",
    )
    region_longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="WGS-84 longitude (optional, for POI lookups)",
    )

    # ── Preparation parameters ────────────────────────────────────────────────
    duration_preference: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="1_week",
        comment=(
            "Target stockpile duration: "
            "3_days | 1_week | 2_weeks | 1_month | 3_months | 6_months"
        ),
    )
    preparation_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=7,
        comment="Preparation duration in calendar days (derived from duration_preference)",
    )
    storage_space_m3: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Available storage space in cubic metres (optional hard constraint)",
    )

    # ── Health / medical flags (GDPR-gated) ───────────────────────────────────
    has_medical_needs: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment=(
            "True if any household member has declared medical needs "
            "(only set when health_data_consent=True)"
        ),
    )
    requires_power_dependency: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment=(
            "True if any member depends on powered medical equipment "
            "(CPAP, insulin pump, dialysis)"
        ),
    )
    health_data_consented: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="GDPR explicit consent flag — health details stored only when True",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<StoredProfile id={self.id[:8]}… "
            f"people={self.total_people} "
            f"country={self.country!r} "
            f"duration={self.duration_preference}>"
        )


# ---------------------------------------------------------------------------
# checklist_cache table
# ---------------------------------------------------------------------------

class ChecklistCache(Base):
    """
    Cached formula-engine results keyed by a deterministic hash of the profile.

    The formula engine is pure/deterministic: identical inputs always produce
    identical outputs.  Caching avoids recomputing the same quantities for
    repeat requests (e.g. when a family member refreshes the checklist page).

    Cache TTL: 24 hours (controlled by ``expires_at``).
    """

    __tablename__ = "checklist_cache"
    __table_args__ = (
        Index("ix_checklist_cache_profile_id", "profile_id"),
        Index("ix_checklist_cache_expires_at", "expires_at"),
        {"comment": "Deterministic formula-engine output cache keyed by profile hash"},
    )

    # SHA-256 hex digest of the normalised profile JSON
    profile_hash: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="SHA-256 hex digest of the serialised, sorted profile JSON",
    )

    # Optional back-reference to the stored profile (may be NULL for anonymous sessions)
    profile_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="UUID of the associated StoredProfile (NULL for anonymous calculations)",
    )

    # Formula version for cache invalidation on formula updates
    formula_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
        comment="Formula library version; cache entries are invalidated on version change",
    )

    # Full result JSON produced by the formula engine
    result_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full ChecklistQuantities output serialised as JSON",
    )

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this cache entry was created",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Cache expiry timestamp (created_at + 24h by default)",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ChecklistCache hash={self.profile_hash[:12]}… "
            f"profile_id={self.profile_id} "
            f"expires={self.expires_at}>"
        )
