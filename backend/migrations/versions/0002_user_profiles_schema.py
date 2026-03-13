"""User profiles and checklist cache schema

Creates the user profile tables for the survival preparedness guide platform:
- profiles        : persisted user profiles with all variables for quantity calculations
- checklist_cache : deterministic formula-engine output cache (TTL 24h)

All variables required by the formula engine for quantity calculations are
stored both in the JSONB ``profile_data`` blob (full fidelity) and as
denormalised scalar columns (query efficiency):

  household_size   → adults_count, children_count, seniors_count, total_people
  ages (grouped)   → adults_count / children_count / seniors_count
  dietary flags    → has_dietary_restrictions (bool) + dietary_flags (JSONB array)
  location type    → location_type  (urban | suburban | rural | remote)
  duration pref    → duration_preference (3_days … 6_months) + preparation_days (int)
  climate zone     → climate_zone  (hot | temperate | cold | tropical)
  housing type     → housing_type  (apartment | house | rural | mobile)
  pets             → has_pets, total_pets
  health (GDPR)    → has_medical_needs, requires_power_dependency, health_data_consented
  storage          → storage_space_m3 (nullable)

GDPR compliance:
  - health_data_consented must be True before any medical data is persisted
  - profile_data JSONB excludes health details when consent is False
  - explicit CHECK constraints enforce valid enum values at DB level

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. profiles — core user profile table
    # ------------------------------------------------------------------
    op.create_table(
        "profiles",
        # ── Primary key ────────────────────────────────────────────────
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            comment="UUID primary key (client-generated or server-default)",
        ),

        # ── Timestamps ─────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Record creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Record last update timestamp (UTC)",
        ),

        # ── Family sharing ──────────────────────────────────────────────
        sa.Column(
            "family_slug",
            sa.String(length=64),
            nullable=True,
            comment="Short slug for family checklist sharing (no auth in MVP)",
        ),

        # ── Full profile JSON ───────────────────────────────────────────
        sa.Column(
            "profile_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment=(
                "Full sanitised UserProfile dict; "
                "health data excluded when health_data_consent=False"
            ),
        ),

        # ── Household composition (denormalised) ────────────────────────

        sa.Column(
            "country",
            sa.String(length=3),
            nullable=False,
            server_default="PT",
            comment="ISO 3166-1 alpha-2 country code (uppercase)",
        ),
        sa.Column(
            "total_people",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Total household members (adults + children + seniors)",
        ),
        sa.Column(
            "adults_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Number of adults (18–64)",
        ),
        sa.Column(
            "children_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of children (under 18)",
        ),
        sa.Column(
            "seniors_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of seniors (65+)",
        ),

        # ── Pets ────────────────────────────────────────────────────────
        sa.Column(
            "has_pets",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if household has any pets",
        ),
        sa.Column(
            "total_pets",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total number of pets across all types",
        ),

        # ── Dietary restrictions ─────────────────────────────────────────
        sa.Column(
            "has_dietary_restrictions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if any member has dietary restrictions",
        ),
        sa.Column(
            "dietary_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                'Array of dietary restriction strings present in household: '
                '["vegetarian","gluten_free","halal",...]'
            ),
        ),

        # ── Location & environment ────────────────────────────────────────
        sa.Column(
            "location_type",
            sa.String(length=16),
            nullable=False,
            server_default="urban",
            comment="Urban footprint: urban | suburban | rural | remote",
        ),
        sa.Column(
            "housing_type",
            sa.String(length=16),
            nullable=False,
            server_default="apartment",
            comment="Dwelling type: apartment | house | rural | mobile",
        ),
        sa.Column(
            "climate_zone",
            sa.String(length=16),
            nullable=False,
            server_default="temperate",
            comment="Climate zone affecting water/food calculations: hot | temperate | cold | tropical",
        ),
        sa.Column(
            "region_city",
            sa.String(length=100),
            nullable=True,
            comment="City or municipality name (optional)",
        ),
        sa.Column(
            "region_latitude",
            sa.Float(),
            nullable=True,
            comment="WGS-84 latitude — enables local POI lookups via Overpass API",
        ),
        sa.Column(
            "region_longitude",
            sa.Float(),
            nullable=True,
            comment="WGS-84 longitude — enables local POI lookups via Overpass API",
        ),

        # ── Preparation parameters ────────────────────────────────────────
        sa.Column(
            "duration_preference",
            sa.String(length=16),
            nullable=False,
            server_default="1_week",
            comment=(
                "Target stockpile duration enum: "
                "3_days | 1_week | 2_weeks | 1_month | 3_months | 6_months"
            ),
        ),
        sa.Column(
            "preparation_days",
            sa.Integer(),
            nullable=False,
            server_default="7",
            comment="Planning horizon in calendar days (derived from duration_preference)",
        ),
        sa.Column(
            "storage_space_m3",
            sa.Float(),
            nullable=True,
            comment="Available storage space in cubic metres — optional volume constraint",
        ),

        # ── Health / medical (GDPR-gated) ─────────────────────────────────
        sa.Column(
            "has_medical_needs",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=(
                "True if any household member has declared medical needs. "
                "Only populated when health_data_consent=True."
            ),
        ),
        sa.Column(
            "requires_power_dependency",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=(
                "True if any member depends on powered medical equipment "
                "(CPAP, insulin pump, dialysis). Only set when consented."
            ),
        ),
        sa.Column(
            "health_data_consented",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="GDPR explicit consent — health details persisted only when True",
        ),

        # ── CHECK constraints ─────────────────────────────────────────────
        sa.CheckConstraint(
            "total_people >= 1 AND total_people <= 100",
            name="ck_profiles_total_people_range",
        ),
        sa.CheckConstraint(
            "preparation_days >= 1 AND preparation_days <= 365",
            name="ck_profiles_preparation_days_range",
        ),
        sa.CheckConstraint(
            "adults_count >= 0",
            name="ck_profiles_adults_non_negative",
        ),
        sa.CheckConstraint(
            "children_count >= 0",
            name="ck_profiles_children_non_negative",
        ),
        sa.CheckConstraint(
            "seniors_count >= 0",
            name="ck_profiles_seniors_non_negative",
        ),
        sa.CheckConstraint(
            "location_type IN ('urban', 'suburban', 'rural', 'remote')",
            name="ck_profiles_location_type",
        ),
        sa.CheckConstraint(
            "housing_type IN ('apartment', 'house', 'rural', 'mobile')",
            name="ck_profiles_housing_type",
        ),
        sa.CheckConstraint(
            "climate_zone IN ('hot', 'temperate', 'cold', 'tropical')",
            name="ck_profiles_climate_zone",
        ),
        sa.CheckConstraint(
            "duration_preference IN "
            "('3_days', '1_week', '2_weeks', '1_month', '3_months', '6_months')",
            name="ck_profiles_duration_preference",
        ),

        sa.PrimaryKeyConstraint("id"),
        comment="User preparation profiles — persisted with GDPR consent, session-scoped otherwise",
    )

    # Indexes
    op.create_index("ix_profiles_family_slug", "profiles", ["family_slug"], unique=False)
    op.create_index("ix_profiles_country", "profiles", ["country"], unique=False)
    op.create_index("ix_profiles_created_at", "profiles", ["created_at"], unique=False)
    op.create_index("ix_profiles_location_type", "profiles", ["location_type"], unique=False)
    op.create_index(
        "ix_profiles_duration_preference", "profiles", ["duration_preference"], unique=False
    )

    # Trigger: auto-update updated_at
    op.execute("""
        CREATE TRIGGER profiles_updated_at
        BEFORE UPDATE ON profiles
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # 2. checklist_cache — formula-engine output cache
    # ------------------------------------------------------------------
    op.create_table(
        "checklist_cache",
        sa.Column(
            "profile_hash",
            sa.String(length=64),
            primary_key=True,
            nullable=False,
            comment="SHA-256 hex digest of the serialised, canonically sorted profile JSON",
        ),
        sa.Column(
            "profile_id",
            sa.String(length=36),
            nullable=True,
            comment="UUID of the associated profiles row (NULL for anonymous calculations)",
        ),
        sa.Column(
            "formula_version",
            sa.String(length=20),
            nullable=False,
            server_default="1.0.0",
            comment="Formula library version — cache entries are invalid after a formula update",
        ),
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Full ChecklistQuantities output serialised as JSON",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Cache entry creation timestamp (UTC)",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Cache expiry timestamp — default created_at + 24h",
        ),
        sa.PrimaryKeyConstraint("profile_hash"),
        comment="Deterministic formula-engine output cache keyed by profile hash (TTL 24h)",
    )

    op.create_index(
        "ix_checklist_cache_profile_id", "checklist_cache", ["profile_id"], unique=False
    )
    op.create_index(
        "ix_checklist_cache_expires_at", "checklist_cache", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_checklist_cache_formula_version",
        "checklist_cache",
        ["formula_version"],
        unique=False,
    )


def downgrade() -> None:
    """Drop profile-related tables in reverse dependency order."""

    # Indexes
    op.drop_index("ix_checklist_cache_formula_version", table_name="checklist_cache")
    op.drop_index("ix_checklist_cache_expires_at", table_name="checklist_cache")
    op.drop_index("ix_checklist_cache_profile_id", table_name="checklist_cache")
    op.drop_table("checklist_cache")

    # Trigger
    op.execute("DROP TRIGGER IF EXISTS profiles_updated_at ON profiles;")

    op.drop_index("ix_profiles_duration_preference", table_name="profiles")
    op.drop_index("ix_profiles_location_type", table_name="profiles")
    op.drop_index("ix_profiles_created_at", table_name="profiles")
    op.drop_index("ix_profiles_country", table_name="profiles")
    op.drop_index("ix_profiles_family_slug", table_name="profiles")
    op.drop_table("profiles")
