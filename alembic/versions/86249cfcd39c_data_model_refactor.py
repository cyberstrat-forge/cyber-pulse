"""data_model_refactor

Revision ID: 86249cfcd39c
Revises: 810a2d7751de
Create Date: 2026-03-27 06:47:38.976604

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86249cfcd39c'
down_revision: Union[str, Sequence[str], None] = '810a2d7751de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add new columns to items table
    op.add_column('items', sa.Column('normalized_title', sa.String(1024), nullable=True))
    op.add_column('items', sa.Column('normalized_body', sa.Text(), nullable=True))
    op.add_column('items', sa.Column('canonical_hash', sa.String(64), nullable=True))
    op.add_column('items', sa.Column('word_count', sa.Integer(), nullable=True))
    op.add_column('items', sa.Column('language', sa.String(10), nullable=True))

    # Create index on canonical_hash
    op.create_index('ix_items_canonical_hash', 'items', ['canonical_hash'])

    # 2. Drop obsolete columns from sources
    op.drop_column('sources', 'last_fetched_at')
    op.drop_column('sources', 'is_in_observation')
    op.drop_column('sources', 'observation_until')
    op.drop_column('sources', 'fetch_interval')
    op.drop_column('sources', 'total_contents')

    # 3. Drop obsolete columns from items
    op.drop_column('items', 'content_id')
    op.drop_column('items', 'content_hash')

    # 4. Drop contents table (if exists)
    op.drop_table('contents')


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate contents table
    op.create_table(
        'contents',
        sa.Column('content_id', sa.String(64), primary_key=True),
        sa.Column('canonical_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('normalized_title', sa.String(1024), nullable=False),
        sa.Column('normalized_body', sa.Text(), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.Column('source_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(20), nullable=False, server_default='ACTIVE'),
    )

    # Restore items columns
    op.add_column('items', sa.Column('content_id', sa.String(64), sa.ForeignKey('contents.content_id'), nullable=True))
    op.add_column('items', sa.Column('content_hash', sa.String(64), nullable=False))
    op.drop_index('ix_items_canonical_hash', 'items')
    op.drop_column('items', 'normalized_title')
    op.drop_column('items', 'normalized_body')
    op.drop_column('items', 'canonical_hash')
    op.drop_column('items', 'word_count')
    op.drop_column('items', 'language')

    # Restore sources columns
    op.add_column('sources', sa.Column('last_fetched_at', sa.DateTime(), nullable=True))
    op.add_column('sources', sa.Column('is_in_observation', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('sources', sa.Column('observation_until', sa.DateTime(), nullable=True))
    op.add_column('sources', sa.Column('fetch_interval', sa.Integer(), nullable=True))
    op.add_column('sources', sa.Column('total_contents', sa.Integer(), nullable=False, server_default='0'))