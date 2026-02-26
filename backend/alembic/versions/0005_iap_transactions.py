"""iap_transactions table

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iap_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.Text, nullable=False, server_default="appstore"),
        sa.Column("transaction_id", sa.Text, nullable=False),
        sa.Column("original_transaction_id", sa.Text, nullable=True),
        sa.Column("product_id", sa.Text, nullable=False),
        sa.Column("product_type", sa.Text, nullable=False),
        sa.Column("signed_transaction_jws", sa.Text, nullable=True),
        sa.Column("signed_renewal_info_jws", sa.Text, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("environment", sa.Text, nullable=False, server_default="Sandbox"),
        sa.Column("raw_payload", postgresql.JSONB, nullable=True),
        sa.CheckConstraint("product_type IN ('subscription', 'consumable')", name="ck_iap_transactions_product_type"),
        sa.CheckConstraint("environment IN ('Sandbox', 'Production')", name="ck_iap_transactions_environment"),
        sa.UniqueConstraint("platform", "transaction_id", name="uq_iap_transactions_platform_txn"),
    )
    op.create_index("ix_iap_transactions_user_id", "iap_transactions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_iap_transactions_user_id", table_name="iap_transactions")
    op.drop_table("iap_transactions")
