"""add turn_id to messages

Revision ID: b91c4de2f7a3
Revises: aa73abbdd360
Create Date: 2026-08-23 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = 'b91c4de2f7a3'
down_revision: Union[str, Sequence[str], None] = 'aa73abbdd360'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('messages', sa.Column('turn_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('messages', 'turn_id')
