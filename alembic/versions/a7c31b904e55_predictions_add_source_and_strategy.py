"""predictions: add source/strategy_id/confidence, relax article columns

Lets the Predict tab's forward-looking reads live in the same table as the
news-pipeline calls, so both feed one evaluation loop. A Predict read has no
article, hence classification_id/article_id/importance become nullable; it does
have a strategy, which is what makes per-strategy accuracy possible.

Existing rows are backfilled to source='news'.

Revision ID: a7c31b904e55
Revises: 4dcf8d53403d
Create Date: 2026-08-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c31b904e55'
down_revision: Union[str, Sequence[str], None] = '4dcf8d53403d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite cannot ALTER COLUMN, so every change goes through batch mode
    # (rebuild-and-copy). Add the columns nullable first, backfill, then tighten.
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('strategy_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('confidence', sa.String(length=16), nullable=True))

    # Everything recorded before this migration came from the news pipeline.
    op.execute("UPDATE predictions SET source = 'news' WHERE source IS NULL")

    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.alter_column(
            'source', existing_type=sa.String(length=16), nullable=False
        )
        batch_op.alter_column(
            'classification_id', existing_type=sa.Integer(), nullable=True
        )
        batch_op.alter_column('article_id', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column(
            'importance', existing_type=sa.String(length=16), nullable=True
        )
        batch_op.create_index(
            batch_op.f('ix_predictions_source'), ['source'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_predictions_strategy_id'), ['strategy_id'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Predict-tab rows have no article and cannot satisfy the old NOT NULLs.
    op.execute("DELETE FROM predictions WHERE source = 'predict'")

    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_predictions_strategy_id'))
        batch_op.drop_index(batch_op.f('ix_predictions_source'))
        batch_op.alter_column(
            'importance', existing_type=sa.String(length=16), nullable=False
        )
        batch_op.alter_column('article_id', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            'classification_id', existing_type=sa.Integer(), nullable=False
        )
        batch_op.drop_column('confidence')
        batch_op.drop_column('strategy_id')
        batch_op.drop_column('source')
