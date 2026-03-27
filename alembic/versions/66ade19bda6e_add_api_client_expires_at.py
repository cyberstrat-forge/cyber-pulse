"""add_api_client_expires_at

Revision ID: 66ade19bda6e
Revises: 86249cfcd39c
Create Date: 2026-03-27 01:18:34.832992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66ade19bda6e'
down_revision: Union[str, Sequence[str], None] = '86249cfcd39c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('api_clients', sa.Column('expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('api_clients', 'expires_at')