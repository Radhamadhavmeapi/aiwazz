"""speaking styles (generations.style) + pronunciation dictionary (seeded global list)

Revision ID: a1c3e5f7b9d2
Revises: f8fe972aed73
Create Date: 2026-11-24 10:30:00

"""
from datetime import datetime, UTC
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, Sequence[str], None] = 'f8fe972aed73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED = [("AiWazz", "Ai Wazz"), ("GST", "G S T"), ("UPI", "U P I"), ("API", "A P I")]


def upgrade() -> None:
    op.add_column('generations', sa.Column('style', sa.String(length=32), nullable=True))
    t = op.create_table(
        'pronunciations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('word', sa.String(length=64), nullable=False),
        sa.Column('word_key', sa.String(length=64), nullable=False),
        sa.Column('say_as', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'word_key', name='uq_pronunciations_user_word'),
    )
    op.create_index(op.f('ix_pronunciations_user_id'), 'pronunciations', ['user_id'], unique=False)
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(t, [{"user_id": None, "word": w, "word_key": w.lower(), "say_as": s, "created_at": now, "updated_at": now}
                       for w, s in SEED])


def downgrade() -> None:
    op.drop_index(op.f('ix_pronunciations_user_id'), table_name='pronunciations')
    op.drop_table('pronunciations')
    op.drop_column('generations', 'style')
