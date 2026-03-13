"""Crawled content schema

Adds the `crawled_content` table for indexing preparedness web pages
from authoritative sources (ready.gov, fema.gov).

Each row stores one crawled URL with extracted text, metadata, and a
SHA-256 content hash for change detection on subsequent crawl runs.

The content_text column is the primary source for LLM grounding when
generating personalised survival guides.

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
    # ------------------------------------------------------------------ #
    # crawled_content — one row per crawled URL                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "crawled_content",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            comment="Surrogate PK",
        ),
        # --- Identity ---
        sa.Column(
            "url",
            sa.String(length=2048),
            nullable=False,
            comment="Canonical URL crawled (unique)",
        ),
        sa.Column(
            "source_domain",
            sa.String(length=100),
            nullable=False,
            comment="Domain of the source: ready.gov, fema.gov …",
        ),
        sa.Column(
            "source_category",
            sa.String(length=100),
            nullable=False,
            comment="Logical category (e.g. emergency-kit, nuclear, hurricane)",
        ),
        # --- Content ---
        sa.Column(
            "title",
            sa.String(length=500),
            nullable=True,
            comment="Page title from <title> or first <h1>",
        ),
        sa.Column(
            "content_text",
            sa.Text(),
            nullable=True,
            comment="Body text with HTML stripped — primary LLM input",
        ),
        sa.Column(
            "content_html",
            sa.Text(),
            nullable=True,
            comment="Raw inner-HTML of the main content block (optional)",
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hex digest of content_text for change detection",
        ),
        # --- Language ---
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=False,
            server_default="en",
            comment="ISO 639-1 language code",
        ),
        # --- Crawl state ---
        sa.Column(
            "http_status",
            sa.Integer(),
            nullable=True,
            comment="HTTP response status code (200, 404, …)",
        ),
        sa.Column(
            "crawled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of the last successful crawl (UTC)",
        ),
        sa.Column(
            "next_crawl_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Scheduled next crawl timestamp; NULL = not scheduled",
        ),
        sa.Column(
            "crawl_error",
            sa.Text(),
            nullable=True,
            comment="Last crawl error message",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Consecutive failed crawl attempts since last success",
        ),
        # --- Rich metadata ---
        sa.Column(
            "meta_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Relevant <meta> tags: {description, keywords, og:title, …}",
        ),
        sa.Column(
            "headings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Ordered list: [{level: 'h2', text: '...'}, …]",
        ),
        sa.Column(
            "links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Internal links: [{href, text}, …]",
        ),
        # --- Control ---
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="False = exclude from LLM context without deleting",
        ),
        # --- Timestamps ---
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
        # --- Constraints ---
        sa.CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status < 600)",
            name="ck_crawled_content_http_status",
        ),
        sa.UniqueConstraint("url", name="uq_crawled_content_url"),
        comment="Web pages crawled from FEMA/ready.gov for LLM grounding",
    )

    # Indexes
    op.create_index(
        "ix_crawled_content_source_domain",
        "crawled_content",
        ["source_domain"],
        unique=False,
    )
    op.create_index(
        "ix_crawled_content_source_category",
        "crawled_content",
        ["source_category"],
        unique=False,
    )
    op.create_index(
        "ix_crawled_content_crawled_at",
        "crawled_content",
        ["crawled_at"],
        unique=False,
    )
    op.create_index(
        "ix_crawled_content_content_hash",
        "crawled_content",
        ["content_hash"],
        unique=False,
    )
    # Composite: most common query pattern (domain + category)
    op.create_index(
        "ix_crawled_content_domain_category",
        "crawled_content",
        ["source_domain", "source_category"],
        unique=False,
    )

    # Auto-update updated_at trigger (reuses function created in 0001)
    op.execute("""
        CREATE TRIGGER crawled_content_updated_at
        BEFORE UPDATE ON crawled_content
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS crawled_content_updated_at ON crawled_content;")
    op.drop_index("ix_crawled_content_domain_category", table_name="crawled_content")
    op.drop_index("ix_crawled_content_content_hash", table_name="crawled_content")
    op.drop_index("ix_crawled_content_crawled_at", table_name="crawled_content")
    op.drop_index("ix_crawled_content_source_category", table_name="crawled_content")
    op.drop_index("ix_crawled_content_source_domain", table_name="crawled_content")
    op.drop_table("crawled_content")
