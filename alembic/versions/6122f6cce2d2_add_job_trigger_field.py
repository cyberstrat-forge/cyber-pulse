"""add_job_trigger_field

Revision ID: 6122f6cce2d2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-31 19:54:01.813709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6122f6cce2d2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add trigger column to jobs table."""
    # Add trigger column to jobs table
    op.add_column('jobs', sa.Column('trigger', sa.String(20), nullable=True))

    # Set default value for existing records (assume manual trigger)
    op.execute("UPDATE jobs SET trigger = 'manual' WHERE trigger IS NULL")


def downgrade() -> None:
    """Remove trigger column from jobs table."""
    # Remove trigger column
    op.drop_column('jobs', 'trigger')
