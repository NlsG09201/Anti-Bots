"""Persist and deduplicate verified Kick webhook deliveries.

Revision ID: 003_kick_webhook_events
Revises: 002_add_alerts_table
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "003_kick_webhook_events"
down_revision = "002_add_alerts_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kick_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("subscription_id", sa.String(length=64), nullable=True),
        sa.Column("stream_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("broadcaster_user_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_version", sa.String(length=16), nullable=False),
        sa.Column("message_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["stream_id"], ["streams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "stream_id", name="uq_kick_webhook_message_stream"),
    )
    op.create_index(
        "ix_kick_webhook_events_status_received",
        "kick_webhook_events",
        ["processing_status", "received_at"],
    )
    op.create_index(
        "ix_kick_webhook_events_stream_received",
        "kick_webhook_events",
        ["stream_id", "received_at"],
    )
    op.create_index(
        "uq_kick_webhook_untracked_message",
        "kick_webhook_events",
        ["message_id"],
        unique=True,
        postgresql_where=sa.text("stream_id IS NULL"),
    )
    # Older Kick OAuth setup enabled auto-mitigation by default without an
    # explicit channel-owner action. New webhook findings are alert-only.
    op.execute(
        """
        UPDATE streams
        SET settings = jsonb_set(
            jsonb_set(COALESCE(settings, '{}'::jsonb), '{auto_mitigate}', 'false'::jsonb, true),
            '{kick_mitigation_default_reviewed}', 'true'::jsonb, true
        )
        WHERE platform::text IN ('KICK', 'kick')
          AND settings->>'kick_mitigation_default_reviewed' IS DISTINCT FROM 'true'
        """
    )


def downgrade() -> None:
    op.drop_index("uq_kick_webhook_untracked_message", table_name="kick_webhook_events")
    op.drop_index("ix_kick_webhook_events_stream_received", table_name="kick_webhook_events")
    op.drop_index("ix_kick_webhook_events_status_received", table_name="kick_webhook_events")
    op.drop_table("kick_webhook_events")
