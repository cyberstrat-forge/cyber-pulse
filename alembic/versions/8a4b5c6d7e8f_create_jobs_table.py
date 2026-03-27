"""create_jobs_table

Revision ID: 8a4b5c6d7e8f
Revises: 7f3c8e2a9b1d
Create Date: 2026-03-27 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8a4b5c6d7e8f'
down_revision: Union[str, Sequence[str], None] = '7f3c8e2a9b1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create jobs table for tracking async task execution."""
    # Create enum types
    op.execute("CREATE TYPE jobtype AS ENUM ('ingest', 'import')")
    op.execute("CREATE TYPE jobstatus AS ENUM ('pending', 'running', 'completed', 'failed')")

    # Create jobs table
    op.create_table(
        'jobs',
        sa.Column('job_id', sa.String(64), primary_key=True),
        sa.Column('type', sa.Enum('ingest', 'import', name='jobtype'), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='jobstatus'), nullable=False, server_default='pending'),
        sa.Column('source_id', sa.String(64), sa.ForeignKey('sources.source_id'), nullable=True),
        sa.Column('file_name', sa.String(255), nullable=True),
        sa.Column('result', postgresql.JSONB, nullable=True),
        sa.Column('error_type', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('retry_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create indexes
    op.create_index('ix_jobs_job_id', 'jobs', ['job_id'])
    op.create_index('ix_jobs_source_id', 'jobs', ['source_id'])


def downgrade() -> None:
    """Drop jobs table."""
    op.drop_index('ix_jobs_source_id', table_name='jobs')
    op.drop_index('ix_jobs_job_id', table_name='jobs')
    op.drop_table('jobs')

    # Drop enum types
    op.execute("DROP TYPE jobstatus")
    op.execute("DROP TYPE jobtype")