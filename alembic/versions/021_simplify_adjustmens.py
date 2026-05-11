import sqlalchemy as sa
from alembic import op

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.drop_table('adjustment_attachments')
    op.drop_table('adjustment_requests')

    op.create_table('adjustment_requests',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('adjustment_type', sa.String(), nullable=False),
        sa.Column('record_type', sa.String(), nullable=True),
        sa.Column('target_date', sa.Date(), nullable=False),
        sa.Column('time', sa.Time(), nullable=True),
        sa.Column('amount_hours', sa.Float(), nullable=True),
        sa.Column('reason_text', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('manager_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('manager_comment', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table('adjustment_attachments',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('adjustment_request_id', sa.Integer(), sa.ForeignKey('adjustment_requests.id'), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('file_type', sa.String(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'))
    )

def downgrade() -> None:
    pass