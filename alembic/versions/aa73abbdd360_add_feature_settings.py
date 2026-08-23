"""add feature_settings table

Revision ID: aa73abbdd360
Revises: 6847e7fed8ba
Create Date: 2026-08-22 19:30:12.481220

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = 'aa73abbdd360'
down_revision: Union[str, Sequence[str], None] = '6847e7fed8ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('feature_settings',
    sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('feature_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.session_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('session_id', 'feature_name')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('feature_settings')
