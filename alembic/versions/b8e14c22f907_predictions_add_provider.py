"""predictions: add provider

Records which model wrote each Predict read, so accuracy can be compared per
provider (committee plan Phase 3). Existing rows are backfilled to 'openai',
which is what produced all of them.

Revision ID: b8e14c22f907
Revises: a7c31b904e55
Create Date: 2026-08-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e14c22f907'
down_revision: Union[str, Sequence[str], None] = 'a7c31b904e55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider', sa.String(length=32), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_predictions_provider'), ['provider'], unique=False
        )

    # Every Predict read recorded before this migration came from OpenAI. News
    # rows have no provider and stay null.
    op.execute("UPDATE predictions SET provider = 'openai' WHERE source = 'predict'")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_predictions_provider'))
        batch_op.drop_column('provider')
