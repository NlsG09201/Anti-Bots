"""Add alerts tables to database

Revision ID: 002_add_alerts_table
Revises: 001_initial_schema
Create Date: 2026-06-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_alerts_table'
down_revision = None  # Set to previous migration ID if exists
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Create alerts table
    op.create_table(
        'alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stream_id', sa.String(255), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.String(1000), nullable=False),
        sa.Column('data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('dismissed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('acknowledged', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('dismissed_at', sa.DateTime(), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for alerts table
    op.create_index('ix_alerts_stream_id_created_at', 'alerts', ['stream_id', 'created_at'])
    op.create_index('ix_alerts_tenant_id_created_at', 'alerts', ['tenant_id', 'created_at'])
    op.create_index('ix_alerts_severity', 'alerts', ['severity'])
    op.create_index('ix_alerts_dismissed', 'alerts', ['dismissed'])
    op.create_index('ix_alerts_alert_type', 'alerts', ['alert_type'])
    op.create_index('ix_alerts_stream_id', 'alerts', ['stream_id'])
    op.create_index('ix_alerts_tenant_id', 'alerts', ['tenant_id'])

    # Create alert_history table
    op.create_table(
        'alert_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('alert_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('changed_by', sa.String(255), nullable=True),
        sa.Column('reason', sa.String(500), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for alert_history table
    op.create_index('ix_alert_history_alert_id', 'alert_history', ['alert_id'])
    op.create_index('ix_alert_history_created_at', 'alert_history', ['created_at'])

    # Create alert_rules table
    op.create_table(
        'alert_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('conditions', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('actions', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('max_alerts_per_hour', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for alert_rules table
    op.create_index('ix_alert_rules_tenant_id', 'alert_rules', ['tenant_id'])
    op.create_index('ix_alert_rules_enabled', 'alert_rules', ['enabled'])


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop alert_rules table
    op.drop_index('ix_alert_rules_enabled', table_name='alert_rules')
    op.drop_index('ix_alert_rules_tenant_id', table_name='alert_rules')
    op.drop_table('alert_rules')

    # Drop alert_history table
    op.drop_index('ix_alert_history_created_at', table_name='alert_history')
    op.drop_index('ix_alert_history_alert_id', table_name='alert_history')
    op.drop_table('alert_history')

    # Drop alerts table
    op.drop_index('ix_alerts_tenant_id', table_name='alerts')
    op.drop_index('ix_alerts_stream_id', table_name='alerts')
    op.drop_index('ix_alerts_alert_type', table_name='alerts')
    op.drop_index('ix_alerts_dismissed', table_name='alerts')
    op.drop_index('ix_alerts_severity', table_name='alerts')
    op.drop_index('ix_alerts_tenant_id_created_at', table_name='alerts')
    op.drop_index('ix_alerts_stream_id_created_at', table_name='alerts')
    op.drop_table('alerts')
