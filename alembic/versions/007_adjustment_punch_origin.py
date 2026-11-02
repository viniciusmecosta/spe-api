from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('time_records', sa.Column('source_adjustment_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_record_source_adjustment', 'time_records', 'adjustment_requests',
                          ['source_adjustment_id'], ['id'], ondelete='SET NULL')
    op.create_unique_constraint('uq_record_source_adjustment', 'time_records', ['source_adjustment_id'])
    op.add_column('adjustment_requests', sa.Column('applied_time_record_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_adjustment_applied_record', 'adjustment_requests', 'time_records',
                          ['applied_time_record_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_adjustment_applied_record', 'adjustment_requests', type_='foreignkey')
    op.drop_column('adjustment_requests', 'applied_time_record_id')
    op.drop_constraint('uq_record_source_adjustment', 'time_records', type_='unique')
    op.drop_constraint('fk_record_source_adjustment', 'time_records', type_='foreignkey')
    op.drop_column('time_records', 'source_adjustment_id')
