"""Persist tenant-scoped OpenAI usage and cost estimates.

Revision ID: 004_ai_usage_records
Revises: 003_kick_webhook_events
Create Date: 2026-10-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "004_ai_usage_records"
down_revision = "003_kick_webhook_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stream_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stream_id"], ["streams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_tenant_created", "ai_usage_records", ["tenant_id", "created_at"])
    op.create_index("ix_ai_usage_stream_created", "ai_usage_records", ["stream_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_stream_created", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_tenant_created", table_name="ai_usage_records")
    op.drop_table("ai_usage_records")
