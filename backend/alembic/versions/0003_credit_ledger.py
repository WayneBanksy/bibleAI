"""credit ledger table

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("delta", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column("product_id", sa.Text, nullable=True),
        sa.Column("related_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("reason IN ('iap_redeem', 'session_consume', 'admin_adjust')", name="ck_credit_ledger_reason"),
    )
    # Partial unique index for idempotency
    op.create_index(
        "ix_credit_ledger_idempotency",
        "credit_ledger",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_idempotency", table_name="credit_ledger")
    op.drop_table("credit_ledger")
