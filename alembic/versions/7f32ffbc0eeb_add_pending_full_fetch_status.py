"""add_pending_full_fetch_status

Revision ID: 7f32ffbc0eeb
Revises: fbbce8790325
Create Date: 2026-03-28 16:30:03.135002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f32ffbc0eeb'
down_revision: Union[str, Sequence[str], None] = 'fbbce8790325'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new enum value to itemstatus
    # Using IF NOT EXISTS for idempotency
    op.execute("ALTER TYPE itemstatus ADD VALUE IF NOT EXISTS 'PENDING_FULL_FETCH'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL doesn't support removing enum values
    # This is a no-op for safety
    pass
