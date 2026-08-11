"""create position_exit_analyses

One row per Position Exit Advisor analysis. Capture only — nothing scores these
yet. The snapshot (price, levels, ATR, verdict, and the full payload the user
saw) is the part that cannot be reconstructed later; the scorer is a pure
function over it plus a future price, so it can be written at any time.

Deliberately a separate table from `predictions`: that one scores a *direction*
over a horizon, and an exit action is not a direction. Mapping `partial-sell`
onto BULLISH/BEARISH would bake a lossy decision into stored data.

Revision ID: c41f7a2e9d10
Revises: b8e14c22f907
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c41f7a2e9d10'
down_revision: Union[str, Sequence[str], None] = 'b8e14c22f907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'position_exit_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('position_id', sa.String(length=32), nullable=True),
        sa.Column('ticker', sa.String(length=16), nullable=False),
        sa.Column('shares', sa.Float(), nullable=False),
        sa.Column('average_cost', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('ai_action', sa.String(length=32), nullable=True),
        sa.Column('rules_final', sa.String(length=32), nullable=True),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('support', sa.Float(), nullable=True),
        sa.Column('resistance', sa.Float(), nullable=True),
        sa.Column('invalidation', sa.Float(), nullable=True),
        sa.Column('atr14', sa.Float(), nullable=True),
        sa.Column('hold_reward_risk', sa.Float(), nullable=True),
        sa.Column('unrealized_pnl', sa.Float(), nullable=True),
        sa.Column('evidence_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_position_exit_analyses_position_id'),
        'position_exit_analyses', ['position_id'], unique=False,
    )
    op.create_index(
        op.f('ix_position_exit_analyses_ticker'),
        'position_exit_analyses', ['ticker'], unique=False,
    )
    op.create_index(
        op.f('ix_position_exit_analyses_action'),
        'position_exit_analyses', ['action'], unique=False,
    )
    op.create_index(
        op.f('ix_position_exit_analyses_provider'),
        'position_exit_analyses', ['provider'], unique=False,
    )
    op.create_index(
        op.f('ix_position_exit_analyses_created_at'),
        'position_exit_analyses', ['created_at'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_position_exit_analyses_created_at'), table_name='position_exit_analyses'
    )
    op.drop_index(
        op.f('ix_position_exit_analyses_provider'), table_name='position_exit_analyses'
    )
    op.drop_index(
        op.f('ix_position_exit_analyses_action'), table_name='position_exit_analyses'
    )
    op.drop_index(
        op.f('ix_position_exit_analyses_ticker'), table_name='position_exit_analyses'
    )
    op.drop_index(
        op.f('ix_position_exit_analyses_position_id'), table_name='position_exit_analyses'
    )
    op.drop_table('position_exit_analyses')
