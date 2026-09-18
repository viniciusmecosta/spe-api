import sqlalchemy as sa

from alembic import op

revision = '034'
down_revision = '033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('time_records') as batch_op:
        batch_op.add_column(
            sa.Column(
                'original_record_id',
                sa.Integer(),
                sa.ForeignKey('time_records.id', name='fk_time_records_original_record_id'),
                nullable=True
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('time_records') as batch_op:
        batch_op.drop_column('original_record_id')
