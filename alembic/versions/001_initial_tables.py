"""initial tables

Revision ID: 001
Revises:
Create Date: 2023-10-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Users Table ---
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', sa.Enum('EMPLOYEE', 'MANAGER', name='userrole'), nullable=False),
        sa.Column('weekly_workload_hours', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # --- Time Records Table ---
    op.create_table('time_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('record_type', sa.Enum('ENTRY', 'EXIT', name='recordtype'), nullable=False),
        sa.Column('record_datetime', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_time_records_id'), 'time_records', ['id'], unique=False)

    # --- Manual Adjustments Table ---
    op.create_table('manual_adjustments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('time_record_id', sa.Integer(), nullable=False),
        sa.Column('previous_type', sa.Enum('ENTRY', 'EXIT', name='recordtype'), nullable=False),
        sa.Column('new_type', sa.Enum('ENTRY', 'EXIT', name='recordtype'), nullable=False),
        sa.Column('adjusted_by_user_id', sa.Integer(), nullable=False),
        sa.Column('adjusted_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['adjusted_by_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['time_record_id'], ['time_records.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_manual_adjustments_id'), 'manual_adjustments', ['id'], unique=False)

    # --- Adjustment Requests Table ---
    op.create_table('adjustment_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('adjustment_type', sa.Enum('MISSING_ENTRY', 'MISSING_EXIT', 'BOTH', name='adjustmenttype'), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=False),
        sa.Column('entry_time', sa.Time(), nullable=True),
        sa.Column('exit_time', sa.Time(), nullable=True),
        sa.Column('reason_text', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='adjustmentstatus'), nullable=False),
        sa.Column('manager_id', sa.Integer(), nullable=True),
        sa.Column('manager_comment', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['manager_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_adjustment_requests_id'), 'adjustment_requests', ['id'], unique=False)

    # --- Adjustment Attachments Table ---
    op.create_table('adjustment_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('adjustment_request_id', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('file_type', sa.String(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['adjustment_request_id'], ['adjustment_requests.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_adjustment_attachments_id'), 'adjustment_attachments', ['id'], unique=False)

    # --- Audit Logs Table ---
    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity', sa.String(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_adjustment_attachments_id'), table_name='adjustment_attachments')
    op.drop_table('adjustment_attachments')
    op.drop_index(op.f('ix_adjustment_requests_id'), table_name='adjustment_requests')
    op.drop_table('adjustment_requests')
    op.drop_index(op.f('ix_manual_adjustments_id'), table_name='manual_adjustments')
    op.drop_table('manual_adjustments')
    op.drop_index(op.f('ix_time_records_id'), table_name='time_records')
    op.drop_table('time_records')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')