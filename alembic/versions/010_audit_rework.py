import sqlalchemy as sa
from alembic import op

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('actor_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('old_data', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('new_data', sa.JSON(), nullable=True))
        batch_op.create_foreign_key('fk_audit_actor', 'users', ['actor_id'], ['id'])
        batch_op.create_foreign_key('fk_audit_target', 'users', ['target_user_id'], ['id'])

        batch_op.drop_column('user_id')
        batch_op.drop_column('details')
        batch_op.drop_column('actor_name')
        batch_op.drop_column('target_user_name')
        batch_op.drop_column('justification')
        batch_op.drop_column('reason')
        batch_op.drop_column('record_time')
        batch_op.drop_column('record_type')


def downgrade() -> None:
    pass