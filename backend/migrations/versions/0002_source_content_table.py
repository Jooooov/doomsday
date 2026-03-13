"""Add source_content table for crawled authoritative source content

Creates the `source_content` table which stores indexed content from
crawled authoritative emergency-preparedness sources (Red Cross, FEMA, etc.)
This table serves as the LLM knowledge base for guide generation.

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
    # 1. source_content — indexed crawled pages from authoritative sources
    # ------------------------------------------------------------------
    op.create_table(
        "source_content",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),

        # Source identity
        sa.Column(
            "url",
            sa.String(length=2000),
            nullable=False,
            comment="Canonical URL that was crawled (unique per source run)",
        ),
        sa.Column(
            "source",
            sa.String(length=30),
            nullable=False,
            server_default="red_cross",
            comment="Authoritative source identifier (red_cross, fema, cdc, etc.)",
        ),
        sa.Column(
            "section_path",
            sa.String(length=500),
            nullable=True,
            comment="URL path relative to source root — used for topic inference",
        ),

        # Content
        sa.Column(
            "title",
            sa.String(length=500),
            nullable=True,
            comment="Page title extracted from <title> or <h1>",
        ),
        sa.Column(
            "summary",
            sa.String(length=1000),
            nullable=True,
            comment="First ~500 chars of extracted plain text (for display/preview)",
        ),
        sa.Column(
            "body_text",
            sa.Text(),
            nullable=True,
            comment="Full cleaned plain-text body (HTML/JS/CSS stripped)",
        ),

        # Metadata
        sa.Column(
            "topics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Topic tags: ["nuclear", "evacuation", "first-aid", ...]',
        ),
        sa.Column(
            "applicable_regions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default='["*"]',
            comment='ISO 3166-1 codes this content applies to; ["*"] = global',
        ),
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=False,
            server_default="en",
            comment="BCP-47 language code",
        ),
        sa.Column(
            "word_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Word count of body_text",
        ),

        # Crawl lifecycle
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="Crawl lifecycle state: pending/fetched/parsed/indexed/failed/skipped",
        ),
        sa.Column(
            "error_message",
            sa.String(length=1000),
            nullable=True,
            comment="Error detail when status=failed",
        ),
        sa.Column(
            "http_status_code",
            sa.Integer(),
            nullable=True,
            comment="HTTP response code from the crawl attempt",
        ),
        sa.Column(
            "crawled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of the successful crawl (UTC)",
        ),

        # Dedup / refresh
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hex of body_text — used to detect unchanged pages on re-crawl",
        ),

        # Control
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="False = soft-deleted / excluded from LLM context windows",
        ),

        # Timestamps
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
            "status IN ('pending', 'fetched', 'parsed', 'indexed', 'failed', 'skipped')",
            name="ck_source_content_status",
        ),
        sa.CheckConstraint(
            "source IN ('red_cross', 'fema', 'cdc', 'who', 'nato', 'protecao_civil_pt', 'custom')",
            name="ck_source_content_source",
        ),
        sa.CheckConstraint(
            "word_count >= 0",
            name="ck_source_content_word_count_positive",
        ),

        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_source_content_url"),
        comment="Indexed content from crawled authoritative emergency-preparedness sources",
    )

    # ------------------------------------------------------------------
    # 2. Indexes for fast lookups
    # ------------------------------------------------------------------
    op.create_index("ix_source_content_source", "source_content", ["source"], unique=False)
    op.create_index("ix_source_content_status", "source_content", ["status"], unique=False)
    op.create_index("ix_source_content_language", "source_content", ["language"], unique=False)
    op.create_index("ix_source_content_crawled_at", "source_content", ["crawled_at"], unique=False)
    op.create_index(
        "ix_source_content_source_status",
        "source_content",
        ["source", "status"],
        unique=False,
    )
    op.create_index(
        "ix_source_content_content_hash",
        "source_content",
        ["content_hash"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 3. auto-update trigger for updated_at
    # ------------------------------------------------------------------
    # Note: update_updated_at_column() function was created in migration 0001
    op.execute("""
        CREATE TRIGGER source_content_updated_at
        BEFORE UPDATE ON source_content
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # 4. GIN index on topics JSONB for fast tag-based lookups
    # ------------------------------------------------------------------
    op.execute("""
        CREATE INDEX ix_source_content_topics_gin
        ON source_content USING GIN (topics);
    """)

    # ------------------------------------------------------------------
    # 5. GIN index on applicable_regions JSONB
    # ------------------------------------------------------------------
    op.execute("""
        CREATE INDEX ix_source_content_regions_gin
        ON source_content USING GIN (applicable_regions);
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS source_content_updated_at ON source_content;")
    op.execute("DROP INDEX IF EXISTS ix_source_content_topics_gin;")
    op.execute("DROP INDEX IF EXISTS ix_source_content_regions_gin;")
    op.drop_index("ix_source_content_source_status", table_name="source_content")
    op.drop_index("ix_source_content_crawled_at", table_name="source_content")
    op.drop_index("ix_source_content_language", table_name="source_content")
    op.drop_index("ix_source_content_status", table_name="source_content")
    op.drop_index("ix_source_content_source", table_name="source_content")
    op.drop_index("ix_source_content_content_hash", table_name="source_content")
    op.drop_table("source_content")
