"""initial schema

Revision ID: f7a1067318b7
Revises:
Create Date: 2026-03-18 18:54:48.993722

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f7a1067318b7"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sources table
    op.create_table(
        "sources",
        sa.Column("source_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("connector_type", sa.String(50), nullable=False),
        sa.Column(
            "tier",
            sa.Enum("T0", "T1", "T2", "T3", name="sourcetier"),
            nullable=False,
            server_default="T2",
        ),
        sa.Column("score", sa.Float, nullable=False, server_default="50.0"),
        sa.Column(
            "status",
            sa.Enum("active", "frozen", "removed", name="sourcestatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("is_in_observation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("observation_until", sa.DateTime, nullable=True),
        sa.Column("pending_review", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("review_reason", sa.Text, nullable=True),
        sa.Column("fetch_interval", sa.Integer, nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("last_fetched_at", sa.DateTime, nullable=True),
        sa.Column("last_scored_at", sa.DateTime, nullable=True),
        sa.Column("total_items", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_contents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_sources_source_id", "sources", ["source_id"])

    # Create items table
    op.create_table(
        "items",
        sa.Column("item_id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.source_id"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("raw_content", sa.Text, nullable=True),
        sa.Column("published_at", sa.DateTime, nullable=False),
        sa.Column("fetched_at", sa.DateTime, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="new"),
        sa.Column("raw_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("meta_completeness", sa.Float, nullable=True),
        sa.Column("content_completeness", sa.Float, nullable=True),
        sa.Column("noise_ratio", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_items_item_id", "items", ["item_id"])
    op.create_index("ix_items_source_id", "items", ["source_id"])
    op.create_index("ix_items_external_id", "items", ["external_id"])
    op.create_index("ix_items_url", "items", ["url"])
    op.create_index("ix_items_published_at", "items", ["published_at"])
    op.create_index("ix_items_fetched_at", "items", ["fetched_at"])
    op.create_index("ix_items_source_published", "items", ["source_id", "published_at"])
    op.create_index("ix_items_source_url", "items", ["source_id", "url"], unique=True)

    # Create contents table
    op.create_table(
        "contents",
        sa.Column("content_id", sa.String(64), primary_key=True),
        sa.Column("canonical_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("normalized_title", sa.String(1024), nullable=False),
        sa.Column("normalized_body", sa.Text, nullable=False),
        sa.Column("first_seen_at", sa.DateTime, nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_contents_content_id", "contents", ["content_id"])
    op.create_index("ix_contents_canonical_hash", "contents", ["canonical_hash"], unique=True)
    op.create_index("ix_contents_first_seen", "contents", ["first_seen_at"])

    # Create api_clients table
    op.create_table(
        "api_clients",
        sa.Column("client_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("api_key", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("permissions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_api_clients_client_id", "api_clients", ["client_id"])
    op.create_index("ix_api_clients_api_key", "api_clients", ["api_key"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_api_clients_api_key", table_name="api_clients")
    op.drop_index("ix_api_clients_client_id", table_name="api_clients")
    op.drop_table("api_clients")

    op.drop_index("ix_contents_first_seen", table_name="contents")
    op.drop_index("ix_contents_canonical_hash", table_name="contents")
    op.drop_index("ix_contents_content_id", table_name="contents")
    op.drop_table("contents")

    op.drop_index("ix_items_source_url", table_name="items")
    op.drop_index("ix_items_source_published", table_name="items")
    op.drop_index("ix_items_fetched_at", table_name="items")
    op.drop_index("ix_items_published_at", table_name="items")
    op.drop_index("ix_items_url", table_name="items")
    op.drop_index("ix_items_external_id", table_name="items")
    op.drop_index("ix_items_source_id", table_name="items")
    op.drop_index("ix_items_item_id", table_name="items")
    op.drop_table("items")

    op.drop_index("ix_sources_source_id", table_name="sources")
    op.drop_table("sources")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS sourcestatus")
    op.execute("DROP TYPE IF EXISTS sourcetier")