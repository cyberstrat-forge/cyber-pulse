"""fix_api_client_status_enum

Revision ID: 6664e7b0fa8a
Revises: f7a1067318b7
Create Date: 2026-03-20 19:44:04.998234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6664e7b0fa8a'
down_revision: Union[str, Sequence[str], None] = 'f7a1067318b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix API client status enum values to match model definition.

    PostgreSQL doesn't support renaming enum values directly, so we:
    1. Create a new enum type with correct values
    2. Drop the default, update the column, set new default
    3. Drop the old type
    4. Rename the new type to the original name
    """
    # Step 1: Create new enum type with uppercase values
    op.execute("""
        CREATE TYPE apiclientstatus_new AS ENUM ('ACTIVE', 'SUSPENDED', 'REVOKED')
    """)

    # Step 2: Drop default, alter column, set new default
    op.execute("ALTER TABLE api_clients ALTER COLUMN status DROP DEFAULT")
    op.execute("""
        ALTER TABLE api_clients
        ALTER COLUMN status TYPE apiclientstatus_new
        USING (
            CASE status::text
                WHEN 'active' THEN 'ACTIVE'::apiclientstatus_new
                WHEN 'suspended' THEN 'SUSPENDED'::apiclientstatus_new
                WHEN 'revoked' THEN 'REVOKED'::apiclientstatus_new
            END
        )
    """)
    op.execute("ALTER TABLE api_clients ALTER COLUMN status SET DEFAULT 'ACTIVE'::apiclientstatus_new")

    # Step 3: Drop old enum type
    op.execute("DROP TYPE apiclientstatus")

    # Step 4: Rename new type to original name
    op.execute("ALTER TYPE apiclientstatus_new RENAME TO apiclientstatus")


def downgrade() -> None:
    """Revert to lowercase enum values."""
    # Step 1: Create new enum type with lowercase values
    op.execute("""
        CREATE TYPE apiclientstatus_new AS ENUM ('active', 'suspended', 'revoked')
    """)

    # Step 2: Drop default, alter column, set new default
    op.execute("ALTER TABLE api_clients ALTER COLUMN status DROP DEFAULT")
    op.execute("""
        ALTER TABLE api_clients
        ALTER COLUMN status TYPE apiclientstatus_new
        USING (
            CASE status::text
                WHEN 'ACTIVE' THEN 'active'::apiclientstatus_new
                WHEN 'SUSPENDED' THEN 'suspended'::apiclientstatus_new
                WHEN 'REVOKED' THEN 'revoked'::apiclientstatus_new
            END
        )
    """)
    op.execute("ALTER TABLE api_clients ALTER COLUMN status SET DEFAULT 'active'::apiclientstatus_new")

    # Step 3: Drop old enum type
    op.execute("DROP TYPE apiclientstatus")

    # Step 4: Rename new type to original name
    op.execute("ALTER TYPE apiclientstatus_new RENAME TO apiclientstatus")