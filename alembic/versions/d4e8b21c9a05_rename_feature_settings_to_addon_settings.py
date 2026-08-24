"""rename feature_settings to addon_settings

Revision ID: d4e8b21c9a05
Revises: b91c4de2f7a3
Create Date: 2026-08-23

Renames the per-session toggle table (and its addon_name column) as part of
the feature→addon terminology cleanup. Pure rename: existing rows and their
disabled-state overrides are preserved.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e8b21c9a05"
down_revision: Union[str, Sequence[str], None] = "b91c4de2f7a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("feature_settings", "addon_settings")
    op.alter_column("addon_settings", "feature_name", new_column_name="addon_name")


def downgrade() -> None:
    op.alter_column("addon_settings", "addon_name", new_column_name="feature_name")
    op.rename_table("addon_settings", "feature_settings")
