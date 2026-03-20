"""fix_all_enum_values

Revision ID: 56c2ab9b309c
Revises: 6664e7b0fa8a
Create Date: 2026-03-20 20:01:17.223653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56c2ab9b309c'
down_revision: Union[str, Sequence[str], None] = '6664e7b0fa8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _upgrade_enum(table: str, column: str, enum_name: str, old_values: list, new_values: list) -> None:
    """Helper to upgrade an enum type.

    Args:
        table: Table name
        column: Column name
        enum_name: Enum type name
        old_values: Old enum values (lowercase)
        new_values: New enum values (uppercase)
    """
    temp_enum = f"{enum_name}_new"

    # Create new enum type
    op.execute(f"CREATE TYPE {temp_enum} AS ENUM {tuple(new_values)}")

    # Build CASE expression for conversion
    case_parts = []
    for old, new in zip(old_values, new_values):
        case_parts.append(f"WHEN '{old}' THEN '{new}'::{temp_enum}")
    case_expr = "CASE " + column + "::text " + " ".join(case_parts) + f" ELSE {column}::text::{temp_enum} END"

    # Drop default, alter column, set new default
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {temp_enum} USING {case_expr}")
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{new_values[0]}'::{temp_enum}")

    # Drop old type and rename
    op.execute(f"DROP TYPE {enum_name}")
    op.execute(f"ALTER TYPE {temp_enum} RENAME TO {enum_name}")


def _downgrade_enum(table: str, column: str, enum_name: str, old_values: list, new_values: list) -> None:
    """Helper to downgrade an enum type back to lowercase values."""
    temp_enum = f"{enum_name}_new"

    # Create new enum type with lowercase values
    op.execute(f"CREATE TYPE {temp_enum} AS ENUM {tuple(old_values)}")

    # Build CASE expression for conversion
    case_parts = []
    for old, new in zip(old_values, new_values):
        case_parts.append(f"WHEN '{new}' THEN '{old}'::{temp_enum}")
    case_expr = "CASE " + column + "::text " + " ".join(case_parts) + f" ELSE {column}::text::{temp_enum} END"

    # Drop default, alter column, set new default
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {temp_enum} USING {case_expr}")
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{old_values[0]}'::{temp_enum}")

    # Drop old type and rename
    op.execute(f"DROP TYPE {enum_name}")
    op.execute(f"ALTER TYPE {temp_enum} RENAME TO {enum_name}")


def upgrade() -> None:
    """Fix all enum values to match Python model definitions (uppercase)."""

    # Fix sourcestatus: active, frozen, removed -> ACTIVE, FROZEN, REMOVED
    _upgrade_enum(
        "sources", "status", "sourcestatus",
        ["active", "frozen", "removed"],
        ["ACTIVE", "FROZEN", "REMOVED"]
    )

    # Fix contentstatus: active, archived -> ACTIVE, ARCHIVED
    _upgrade_enum(
        "contents", "status", "contentstatus",
        ["active", "archived"],
        ["ACTIVE", "ARCHIVED"]
    )

    # Fix itemstatus: new, normalized, mapped, rejected -> NEW, NORMALIZED, MAPPED, REJECTED
    _upgrade_enum(
        "items", "status", "itemstatus",
        ["new", "normalized", "mapped", "rejected"],
        ["NEW", "NORMALIZED", "MAPPED", "REJECTED"]
    )


def downgrade() -> None:
    """Revert all enum values to lowercase."""

    # Revert sourcestatus
    _downgrade_enum(
        "sources", "status", "sourcestatus",
        ["active", "frozen", "removed"],
        ["ACTIVE", "FROZEN", "REMOVED"]
    )

    # Revert contentstatus
    _downgrade_enum(
        "contents", "status", "contentstatus",
        ["active", "archived"],
        ["ACTIVE", "ARCHIVED"]
    )

    # Revert itemstatus
    _downgrade_enum(
        "items", "status", "itemstatus",
        ["new", "normalized", "mapped", "rejected"],
        ["NEW", "NORMALIZED", "MAPPED", "REJECTED"]
    )