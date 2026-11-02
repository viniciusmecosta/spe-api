from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'background_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('deduplication_key', sa.String(), unique=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('result', JSONB(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('lease_token', sa.String()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_background_jobs_claim', 'background_jobs', ['status', 'next_attempt_at'])


def downgrade():
    raise NotImplementedError('Pendências precisam ser concluídas ou exportadas antes de remover a fila.')
