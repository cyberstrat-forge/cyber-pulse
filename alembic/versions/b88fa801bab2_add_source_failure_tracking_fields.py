"""add source failure tracking fields

Revision ID: b88fa801bab2
Revises: 56c2ab9b309c
Create Date: 2026-03-26 06:25:15.045056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b88fa801bab2'
down_revision: Union[str, Sequence[str], None] = '56c2ab9b309c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add failure tracking fields to sources table
    op.add_column('sources', sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('sources', sa.Column('last_error_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sources', 'last_error_at')
    op.drop_column('sources', 'consecutive_failures')
