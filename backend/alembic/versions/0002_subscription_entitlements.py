"""subscription & entitlements columns on users

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("subscription_tier", sa.Text, nullable=False, server_default="free"))
    op.add_column("users", sa.Column("subscription_source", sa.Text, nullable=True))
    op.add_column("users", sa.Column("subscription_status", sa.Text, nullable=False, server_default="inactive"))
    op.add_column("users", sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("free_quota_window_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("users", sa.Column("free_sessions_used", sa.Integer, nullable=False, server_default="0"))
    op.add_column("users", sa.Column("credits_balance", sa.Integer, nullable=False, server_default="0"))

    op.create_check_constraint("ck_users_subscription_tier", "users", "subscription_tier IN ('free', 'plus')")
    op.create_check_constraint("ck_users_subscription_status", "users", "subscription_status IN ('inactive', 'active', 'grace', 'billing_retry')")


def downgrade() -> None:
    op.drop_constraint("ck_users_subscription_status", "users", type_="check")
    op.drop_constraint("ck_users_subscription_tier", "users", type_="check")
    op.drop_column("users", "credits_balance")
    op.drop_column("users", "free_sessions_used")
    op.drop_column("users", "free_quota_window_start")
    op.drop_column("users", "subscription_expires_at")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "subscription_source")
    op.drop_column("users", "subscription_tier")
