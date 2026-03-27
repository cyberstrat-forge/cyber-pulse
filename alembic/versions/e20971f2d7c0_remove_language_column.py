"""remove_language_column

Revision ID: e20971f2d7c0
Revises: 8a4b5c6d7e8f
Create Date: 2026-03-27 12:50:52.634647

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e20971f2d7c0'
down_revision: Union[str, Sequence[str], None] = '8a4b5c6d7e8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop language column from items table
    op.drop_column('items', 'language')


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add language column if needed to rollback
    op.add_column('items', sa.Column('language', sa.String(10), nullable=True))
