"""Initial Doomsday Clock schema

Creates the core tables for the per-country Doomsday Clock scoring system:
- doomsday_scores     : current state per country (one row per country)
- score_history       : append-only audit log of score snapshots
- global_clock_state  : singleton global aggregated clock state
- news_events         : news articles processed during recalculations
- region_configs      : per-country calibration and normalization config

Baseline anchor: 85.0 seconds (Bulletin of the Atomic Scientists, 2026 reference)
Delta cap: ±5 seconds per recalculation
Recalculation schedule: every 6 hours (4x per day)

Revision ID: 0001
Revises: (none — initial migration)
Create Date: 2026-03-11
"""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

# Constants (kept in sync with app/models/doomsday_clock.py)
GLOBAL_BASELINE_SECONDS = Decimal("85.0")
MAX_DELTA_PER_RECALC = Decimal("5.0")
SCORE_MIN_SECONDS = Decimal("10.0")
SCORE_MAX_SECONDS = Decimal("3600.0")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. region_configs — calibration config per country
    # ------------------------------------------------------------------
    op.create_table(
        "region_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "region_code",
            sa.String(length=2),
            nullable=False,
            comment="ISO 3166-1 alpha-2 country code",
        ),
        sa.Column(
            "region_name",
            sa.String(length=100),
            nullable=False,
            comment="Human-readable region name",
        ),
        sa.Column(
            "regional_multiplier",
            sa.Numeric(precision=6, scale=4),
            nullable=False,
            server_default="1.0",
            comment="Multiplier applied to baseline_anchor during normalization",
        ),
        sa.Column(
            "baseline_override",
            sa.Numeric(precision=8, scale=3),
            nullable=True,
            comment="If set, overrides global baseline_anchor for this region",
        ),
        sa.Column(
            "max_delta_override",
            sa.Numeric(precision=5, scale=2),
            nullable=True,
            comment="If set, overrides global MAX_DELTA_PER_RECALC for this region",
        ),
        sa.Column(
            "neighboring_countries",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Array of neighboring country codes: ["ES","FR","MA"]',
        ),
        sa.Column(
            "alliance_memberships",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Array of alliances: ["NATO","EU","UN"]',
        ),
        sa.Column(
            "conflict_proximity_km",
            sa.Integer(),
            nullable=True,
            comment="Distance in km to nearest active conflict zone",
        ),
        sa.Column(
            "primary_news_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Preferred news API sources for this country",
        ),
        sa.Column(
            "news_languages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Array of language codes: ["pt","en"]',
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether this region is active in the live map",
        ),
        sa.Column(
            "is_mvp_region",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True for MVP-supported regions (PT, US)",
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_code", name="uq_region_configs_code"),
        comment="Per-country/region calibration configuration for score normalization",
    )
    op.create_index(
        "ix_region_configs_region_code", "region_configs", ["region_code"], unique=False
    )

    # Trigger: auto-update updated_at on region_configs
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    op.execute("""
        CREATE TRIGGER region_configs_updated_at
        BEFORE UPDATE ON region_configs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # 2. doomsday_scores — current per-country scores
    # ------------------------------------------------------------------
    op.create_table(
        "doomsday_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Geographic identity
        sa.Column(
            "country_code",
            sa.String(length=2),
            nullable=False,
            comment="ISO 3166-1 alpha-2 country code (uppercase)",
        ),
        sa.Column(
            "country_name",
            sa.String(length=100),
            nullable=False,
            comment="English country name",
        ),
        # Scoring fields
        sa.Column(
            "raw_score",
            sa.Numeric(precision=6, scale=3),
            nullable=False,
            comment="LLM-produced risk index 0–100 before normalization",
        ),
        sa.Column(
            "normalized_score",
            sa.Numeric(precision=8, scale=3),
            nullable=False,
            comment="Seconds to midnight (lower = more dangerous)",
        ),
        sa.Column(
            "baseline_anchor",
            sa.Numeric(precision=8, scale=3),
            nullable=False,
            server_default=str(float(GLOBAL_BASELINE_SECONDS)),
            comment="Global baseline reference in seconds (~85.0 per BAS 2026)",
        ),
        sa.Column(
            "regional_multiplier",
            sa.Numeric(precision=6, scale=4),
            nullable=False,
            server_default="1.0",
            comment="Regional geopolitical adjustment factor",
        ),
        # Change tracking
        sa.Column(
            "previous_score",
            sa.Numeric(precision=8, scale=3),
            nullable=True,
            comment="Normalized score from the previous recalculation",
        ),
        sa.Column(
            "score_delta",
            sa.Numeric(precision=6, scale=3),
            nullable=False,
            server_default="0.0",
            comment="Change vs previous_score, capped at ±5s",
        ),
        # LLM metadata
        sa.Column(
            "confidence_level",
            sa.String(length=10),
            nullable=False,
            server_default="medium",
            comment="LLM confidence: high / medium / low",
        ),
        sa.Column(
            "llm_model",
            sa.String(length=100),
            nullable=True,
            comment="LLM model identifier used for this analysis",
        ),
        sa.Column(
            "news_articles_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of news articles fed to the LLM",
        ),
        sa.Column(
            "analysis_summary",
            sa.String(length=500),
            nullable=True,
            comment="Short LLM-generated human-readable summary",
        ),
        sa.Column(
            "analysis_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Full LLM response metadata (model, tokens, latency, sources)",
        ),
        # Scheduling
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="When this score was last recalculated (UTC)",
        ),
        sa.Column(
            "next_update_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Scheduled timestamp for next recalculation (UTC)",
        ),
        # Control flags
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether this country is shown on the live risk map",
        ),
        sa.Column(
            "is_fallback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if score was generated from regional baseline (LLM failed)",
        ),
        # Timestamps (from TimestampMixin)
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
        # Constraints
        sa.CheckConstraint(
            "char_length(country_code) = 2",
            name="ck_doomsday_scores_country_code_len",
        ),
        sa.CheckConstraint(
            "raw_score >= 0 AND raw_score <= 100",
            name="ck_doomsday_scores_raw_score_range",
        ),
        sa.CheckConstraint(
            f"normalized_score >= {SCORE_MIN_SECONDS} AND normalized_score <= {SCORE_MAX_SECONDS}",
            name="ck_doomsday_scores_normalized_range",
        ),
        sa.CheckConstraint(
            f"score_delta >= -{MAX_DELTA_PER_RECALC} AND score_delta <= {MAX_DELTA_PER_RECALC}",
            name="ck_doomsday_scores_delta_cap",
        ),
        sa.CheckConstraint(
            "baseline_anchor > 0",
            name="ck_doomsday_scores_baseline_positive",
        ),
        sa.CheckConstraint(
            "confidence_level IN ('high', 'medium', 'low')",
            name="ck_doomsday_scores_confidence_level",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_code", name="uq_doomsday_scores_country_code"),
        comment="Current per-country Doomsday Clock scores",
    )
    op.create_index(
        "ix_doomsday_scores_country_code", "doomsday_scores", ["country_code"], unique=False
    )
    op.create_index(
        "ix_doomsday_scores_normalized_score",
        "doomsday_scores",
        ["normalized_score"],
        unique=False,
    )
    op.create_index(
        "ix_doomsday_scores_last_updated", "doomsday_scores", ["last_updated"], unique=False
    )
    # Trigger: auto-update updated_at
    op.execute("""
        CREATE TRIGGER doomsday_scores_updated_at
        BEFORE UPDATE ON doomsday_scores
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # 3. score_history — append-only audit log
    # ------------------------------------------------------------------
    op.create_table(
        "score_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "country_code",
            sa.String(length=2),
            nullable=False,
            comment="ISO 3166-1 alpha-2 country code",
        ),
        sa.Column(
            "country_name",
            sa.String(length=100),
            nullable=False,
            comment="English country name at time of snapshot",
        ),
        # Score snapshot
        sa.Column(
            "raw_score",
            sa.Numeric(precision=6, scale=3),
            nullable=False,
            comment="Raw LLM risk index at time of snapshot",
        ),
        sa.Column(
            "normalized_score",
            sa.Numeric(precision=8, scale=3),
            nullable=False,
            comment="Normalized seconds-to-midnight at time of snapshot",
        ),
        sa.Column(
            "baseline_anchor",
            sa.Numeric(precision=8, scale=3),
            nullable=False,
            comment="Baseline anchor used in this calculation",
        ),
        sa.Column(
            "regional_multiplier",
            sa.Numeric(precision=6, scale=4),
            nullable=False,
            server_default="1.0",
            comment="Regional multiplier used in this calculation",
        ),
        sa.Column(
            "score_delta",
            sa.Numeric(precision=6, scale=3),
            nullable=False,
            server_default="0.0",
            comment="Delta from previous snapshot, capped at ±5s",
        ),
        # Analysis context
        sa.Column(
            "confidence_level",
            sa.String(length=10),
            nullable=False,
            server_default="medium",
            comment="LLM confidence level",
        ),
        sa.Column(
            "trigger",
            sa.String(length=20),
            nullable=False,
            server_default="scheduled",
            comment="What triggered this recalculation",
        ),
        sa.Column(
            "llm_model",
            sa.String(length=100),
            nullable=True,
            comment="LLM model used",
        ),
        sa.Column(
            "news_articles_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of news articles analysed",
        ),
        sa.Column(
            "analysis_summary",
            sa.String(length=500),
            nullable=True,
            comment="Short LLM-generated summary",
        ),
        sa.Column(
            "analysis_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Full LLM metadata blob",
        ),
        sa.Column(
            "is_fallback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if generated from regional baseline (LLM failed)",
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="When this snapshot was recorded (UTC)",
        ),
        # Constraints
        sa.CheckConstraint(
            "trigger IN ('scheduled', 'manual', 'news_event', 'initial', 'rollback')",
            name="ck_score_history_trigger",
        ),
        sa.CheckConstraint(
            "confidence_level IN ('high', 'medium', 'low')",
            name="ck_score_history_confidence_level",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Append-only audit log of per-country Doomsday Clock score history",
    )
    op.create_index(
        "ix_score_history_country_code", "score_history", ["country_code"], unique=False
    )
    op.create_index(
        "ix_score_history_recorded_at", "score_history", ["recorded_at"], unique=False
    )
    op.create_index(
        "ix_score_history_country_recorded",
        "score_history",
        ["country_code", "recorded_at"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 4. global_clock_state — singleton global state
    # ------------------------------------------------------------------
    op.create_table(
        "global_clock_state",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
            comment="Always 1 — singleton row",
        ),
        sa.Column(
            "global_score",
            sa.Numeric(precision=8, scale=3),
            nullable=False,
            comment="Globally aggregated seconds-to-midnight",
        ),
        sa.Column(
            "baseline_anchor",
            sa.Numeric(precision=8, scale=3),
            nullable=False,
            server_default=str(float(GLOBAL_BASELINE_SECONDS)),
            comment="BAS reference baseline in seconds (~85.0 for 2026)",
        ),
        sa.Column(
            "previous_global_score",
            sa.Numeric(precision=8, scale=3),
            nullable=True,
            comment="Previous global score for delta tracking",
        ),
        sa.Column(
            "global_delta",
            sa.Numeric(precision=6, scale=3),
            nullable=False,
            server_default="0.0",
            comment="Change in global_score since last recalculation, capped at ±5s",
        ),
        sa.Column(
            "active_countries_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of countries contributing to the global score",
        ),
        sa.Column(
            "countries_in_critical",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Countries with normalized_score <= 30s (critical tier)",
        ),
        sa.Column(
            "countries_in_high",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Countries with normalized_score 31–60s (high tier)",
        ),
        sa.Column(
            "last_recalculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="When the global score was last recalculated (UTC)",
        ),
        sa.Column(
            "next_recalculation_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Next scheduled global recalculation (UTC)",
        ),
        sa.Column(
            "fallback_static_built_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the last hourly Cloudflare Pages fallback was built",
        ),
        sa.Column(
            "calculation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Metadata about the last global aggregation calculation",
        ),
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
        sa.CheckConstraint("global_score > 0", name="ck_global_clock_score_positive"),
        sa.CheckConstraint("baseline_anchor > 0", name="ck_global_clock_baseline_positive"),
        sa.PrimaryKeyConstraint("id"),
        comment="Singleton row holding global aggregated Doomsday Clock state",
    )
    op.execute("""
        CREATE TRIGGER global_clock_state_updated_at
        BEFORE UPDATE ON global_clock_state
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # 5. news_events — news articles processed during recalculations
    # ------------------------------------------------------------------
    op.create_table(
        "news_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "score_history_id",
            sa.Integer(),
            sa.ForeignKey("score_history.id", ondelete="SET NULL"),
            nullable=True,
            comment="FK to score_history snapshot that consumed this article",
        ),
        sa.Column(
            "country_code",
            sa.String(length=2),
            nullable=False,
            comment="Country code this news event relates to",
        ),
        sa.Column(
            "title",
            sa.String(length=500),
            nullable=False,
            comment="Article headline",
        ),
        sa.Column(
            "url",
            sa.String(length=2000),
            nullable=True,
            comment="Source URL",
        ),
        sa.Column(
            "source_name",
            sa.String(length=200),
            nullable=True,
            comment="News source name",
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Article publication timestamp",
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="When this article was fetched by the news service",
        ),
        sa.Column(
            "relevance_score",
            sa.Numeric(precision=5, scale=3),
            nullable=True,
            comment="LLM-assigned relevance score 0–1",
        ),
        sa.Column(
            "sentiment_score",
            sa.Numeric(precision=5, scale=3),
            nullable=True,
            comment="Sentiment -1 (very negative) to +1 (very positive)",
        ),
        sa.Column(
            "risk_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Risk-relevant keywords extracted from the article",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="News articles processed during Doomsday Clock recalculations",
    )
    op.create_index(
        "ix_news_events_country_code", "news_events", ["country_code"], unique=False
    )
    op.create_index(
        "ix_news_events_published_at", "news_events", ["published_at"], unique=False
    )
    op.create_index(
        "ix_news_events_score_history_id",
        "news_events",
        ["score_history_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 6. Seed data: Initial global clock state (singleton row)
    # ------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO global_clock_state (
            id,
            global_score,
            baseline_anchor,
            previous_global_score,
            global_delta,
            active_countries_count,
            countries_in_critical,
            countries_in_high,
            last_recalculated_at,
            calculation_metadata
        ) VALUES (
            1,
            {float(GLOBAL_BASELINE_SECONDS)},
            {float(GLOBAL_BASELINE_SECONDS)},
            NULL,
            0.0,
            0,
            0,
            0,
            NOW(),
            '{{"seeded": true, "version": "0001", "note": "Initial seed — BAS 2026 anchor"}}'
        );
    """)

    # ------------------------------------------------------------------
    # 7. Seed data: MVP Region Configs (Portugal + USA)
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO region_configs (
            region_code, region_name, regional_multiplier, baseline_override,
            neighboring_countries, alliance_memberships, conflict_proximity_km,
            primary_news_sources, news_languages, is_active, is_mvp_region
        ) VALUES
        (
            'PT', 'Portugal', 1.05, NULL,
            '["ES"]',
            '["NATO", "EU", "UN", "OSCE"]',
            2500,
            '["the-next-web", "reuters", "associated-press", "bbc-news"]',
            '["pt", "en"]',
            true, true
        ),
        (
            'US', 'United States', 1.0, NULL,
            '["CA", "MX"]',
            '["NATO", "UN", "G7", "G20", "FIVE_EYES"]',
            9000,
            '["the-washington-post", "the-new-york-times", "cnn", "fox-news", "reuters"]',
            '["en"]',
            true, true
        );
    """)

    # ------------------------------------------------------------------
    # 8. Seed data: Initial DoomsdayScore rows for MVP regions
    # ------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO doomsday_scores (
            country_code, country_name,
            raw_score, normalized_score, baseline_anchor, regional_multiplier,
            previous_score, score_delta,
            confidence_level, llm_model, news_articles_used,
            analysis_summary, analysis_metadata,
            last_updated, is_active, is_fallback
        ) VALUES
        (
            'PT', 'Portugal',
            42.0,
            {float(GLOBAL_BASELINE_SECONDS) * 1.05 * (1 - 42.0 / 200):.3f},
            {float(GLOBAL_BASELINE_SECONDS)},
            1.05,
            NULL, 0.0,
            'medium', 'seed', 0,
            'Initial seeded score for Portugal based on 2026 BAS baseline. No LLM analysis performed yet.',
            '{{"seeded": true, "trigger": "initial"}}',
            NOW(), true, true
        ),
        (
            'US', 'United States',
            45.0,
            {float(GLOBAL_BASELINE_SECONDS) * 1.0 * (1 - 45.0 / 200):.3f},
            {float(GLOBAL_BASELINE_SECONDS)},
            1.0,
            NULL, 0.0,
            'medium', 'seed', 0,
            'Initial seeded score for United States based on 2026 BAS baseline. No LLM analysis performed yet.',
            '{{"seeded": true, "trigger": "initial"}}',
            NOW(), true, true
        );
    """)

    # ------------------------------------------------------------------
    # 9. Seed initial score_history entries for MVP regions
    # ------------------------------------------------------------------
    op.execute(f"""
        INSERT INTO score_history (
            country_code, country_name,
            raw_score, normalized_score, baseline_anchor, regional_multiplier,
            score_delta, confidence_level, trigger, llm_model, news_articles_used,
            analysis_summary, is_fallback, recorded_at
        ) VALUES
        (
            'PT', 'Portugal',
            42.0,
            {float(GLOBAL_BASELINE_SECONDS) * 1.05 * (1 - 42.0 / 200):.3f},
            {float(GLOBAL_BASELINE_SECONDS)},
            1.05, 0.0,
            'medium', 'initial', 'seed', 0,
            'Initial seeded score for Portugal.',
            true, NOW()
        ),
        (
            'US', 'United States',
            45.0,
            {float(GLOBAL_BASELINE_SECONDS) * 1.0 * (1 - 45.0 / 200):.3f},
            {float(GLOBAL_BASELINE_SECONDS)},
            1.0, 0.0,
            'medium', 'initial', 'seed', 0,
            'Initial seeded score for United States.',
            true, NOW()
        );
    """)


def downgrade() -> None:
    """Drops all tables in reverse dependency order."""
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS doomsday_scores_updated_at ON doomsday_scores;")
    op.execute("DROP TRIGGER IF EXISTS region_configs_updated_at ON region_configs;")
    op.execute("DROP TRIGGER IF EXISTS global_clock_state_updated_at ON global_clock_state;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")

    # Drop tables (FK-safe order)
    op.drop_table("news_events")
    op.drop_index("ix_score_history_country_recorded", table_name="score_history")
    op.drop_index("ix_score_history_recorded_at", table_name="score_history")
    op.drop_index("ix_score_history_country_code", table_name="score_history")
    op.drop_table("score_history")
    op.drop_index("ix_doomsday_scores_last_updated", table_name="doomsday_scores")
    op.drop_index("ix_doomsday_scores_normalized_score", table_name="doomsday_scores")
    op.drop_index("ix_doomsday_scores_country_code", table_name="doomsday_scores")
    op.drop_table("doomsday_scores")
    op.drop_table("global_clock_state")
    op.drop_index("ix_region_configs_region_code", table_name="region_configs")
    op.drop_table("region_configs")
