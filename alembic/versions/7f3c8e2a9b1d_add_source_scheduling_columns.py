"""add_source_scheduling_columns

Revision ID: 7f3c8e2a9b1d
Revises: 66ade19bda6e
Create Date: 2026-03-27 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f3c8e2a9b1d'
down_revision: Union[str, Sequence[str], None] = '66ade19bda6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing scheduling and tracking columns to sources table."""
    # Scheduling fields
    op.add_column('sources', sa.Column('schedule_interval', sa.Integer(), nullable=True))
    op.add_column('sources', sa.Column('next_ingest_at', sa.DateTime(), nullable=True))
    op.add_column('sources', sa.Column('last_ingested_at', sa.DateTime(), nullable=True))

    # Error tracking fields
    op.add_column('sources', sa.Column('last_error_message', sa.String(255), nullable=True))
    op.add_column('sources', sa.Column('last_job_id', sa.String(64), nullable=True))

    # Collection statistics
    op.add_column('sources', sa.Column('items_last_7d', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('sources', sa.Column('last_ingest_result', sa.String(20), nullable=True))


def downgrade() -> None:
    """Remove scheduling and tracking columns from sources table."""
    op.drop_column('sources', 'last_ingest_result')
    op.drop_column('sources', 'items_last_7d')
    op.drop_column('sources', 'last_job_id')
    op.drop_column('sources', 'last_error_message')
    op.drop_column('sources', 'last_ingested_at')
    op.drop_column('sources', 'next_ingest_at')
    op.drop_column('sources', 'schedule_interval')