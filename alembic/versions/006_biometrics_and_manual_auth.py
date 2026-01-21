import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('user_biometrics',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('template_data', sa.String(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                              nullable=True),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_user_biometrics_id'), 'user_biometrics', ['id'], unique=False)

    op.create_table('manual_authorizations',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('authorized_by_id', sa.Integer(), nullable=False),
                    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('reason', sa.String(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                              nullable=True),
                    sa.ForeignKeyConstraint(['authorized_by_id'], ['users.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_manual_authorizations_id'), 'manual_authorizations', ['id'], unique=False)

    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('biometric_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('original_timestamp', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('is_manual', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('edited_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('edit_reason', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key('fk_time_records_biometric', 'user_biometrics', ['biometric_id'], ['id'])
        batch_op.create_foreign_key('fk_time_records_editor', 'users', ['edited_by'], ['id'])

    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'username' not in columns:
            batch_op.add_column(sa.Column('username', sa.String(), nullable=True))
            batch_op.create_unique_constraint('uq_users_username', ['username'])

        if 'can_manual_punch' not in columns:
            batch_op.add_column(sa.Column('can_manual_punch', sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('can_manual_punch')
        batch_op.drop_constraint('uq_users_username', type_='unique')
        batch_op.drop_column('username')

    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.drop_constraint('fk_time_records_editor', type_='foreignkey')
        batch_op.drop_constraint('fk_time_records_biometric', type_='foreignkey')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('edit_reason')
        batch_op.drop_column('edited_by')
        batch_op.drop_column('is_manual')
        batch_op.drop_column('original_timestamp')
        batch_op.drop_column('biometric_id')

    op.drop_index(op.f('ix_manual_authorizations_id'), table_name='manual_authorizations')
    op.drop_table('manual_authorizations')
    op.drop_index(op.f('ix_user_biometrics_id'), table_name='user_biometrics')
    op.drop_table('user_biometrics')
