"""voice_consents: consent / source records for custom (clone) voices (phase 13)

Revision ID: c7d9e1f3a5b8
Revises: a1c3e5f7b9d2
Create Date: 2026-11-24 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c7d9e1f3a5b8'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'voice_consents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('voice_id', sa.String(length=64), nullable=False),
        sa.Column('source_type', sa.String(length=16), nullable=False),
        sa.Column('speaker_name', sa.String(length=150), nullable=False),
        sa.Column('consent_scope', sa.String(length=255), nullable=False),
        sa.Column('signed_document_path', sa.String(length=255), nullable=True),
        sa.Column('attestation_note', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('added_by', sa.Integer(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['added_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_voice_consents_voice_id'), 'voice_consents', ['voice_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_voice_consents_voice_id'), table_name='voice_consents')
    op.drop_table('voice_consents')
