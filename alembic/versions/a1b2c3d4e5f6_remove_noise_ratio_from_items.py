"""remove_noise_ratio_from_items

Revision ID: a1b2c3d4e5f6
Revises: 7f32ffbc0eeb
Create Date: 2026-03-29 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = '7f32ffbc0eeb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop noise_ratio column from items table
    op.drop_column('items', 'noise_ratio')


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add noise_ratio column if needed to rollback
    op.add_column('items', sa.Column('noise_ratio', sa.Float(), nullable=True))
