"""analytics events table

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_name", sa.Text, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("properties", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_analytics_events_user_created", "analytics_events", ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_analytics_events_name_created", "analytics_events", ["event_name", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_analytics_events_name_created", table_name="analytics_events")
    op.drop_index("ix_analytics_events_user_created", table_name="analytics_events")
    op.drop_table("analytics_events")
