"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Extensions
    # -----------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # -----------------------------------------------------------------------
    # users
    # -----------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("external_id", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # -----------------------------------------------------------------------
    # consents
    # -----------------------------------------------------------------------
    op.create_table(
        "consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("disclaimer_version", sa.Text, nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("privacy_prefs", postgresql.JSONB, nullable=True),
    )

    # -----------------------------------------------------------------------
    # sessions
    # -----------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("translation_preference", sa.Text, nullable=True),
        sa.Column("tone_preference", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('support_session','guided_program','bible_reference','prayer_builder')",
            name="ck_sessions_mode",
        ),
        sa.CheckConstraint("status IN ('active','ended')", name="ck_sessions_status"),
        sa.CheckConstraint(
            "translation_preference IS NULL OR translation_preference IN ('ESV','NIV','KJV','NKJV','NLT','CSB')",
            name="ck_sessions_translation",
        ),
        sa.CheckConstraint(
            "tone_preference IS NULL OR tone_preference IN ('reflective','encouraging','neutral')",
            name="ck_sessions_tone",
        ),
    )
    op.create_index("ix_sessions_user_started", "sessions", ["user_id", "started_at"])

    # -----------------------------------------------------------------------
    # messages
    # -----------------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("text_hash", sa.Text, nullable=True),
        sa.Column("content_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("client_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_version", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),
    )
    op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])
    # Partial unique index for idempotency (INTERFACES.md §4, D004)
    op.create_index(
        "ix_messages_session_client_msg_id",
        "messages",
        ["session_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )

    # -----------------------------------------------------------------------
    # bible_verses
    # -----------------------------------------------------------------------
    op.create_table(
        "bible_verses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("translation_id", sa.Text, nullable=False),
        sa.Column("book", sa.Text, nullable=False),
        sa.Column("chapter", sa.Integer, nullable=False),
        sa.Column("verse", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_hash", sa.Text, nullable=False),
        sa.CheckConstraint(
            "translation_id IN ('ESV','NIV','KJV','NKJV','NLT','CSB')",
            name="ck_bible_verses_translation",
        ),
        sa.UniqueConstraint("translation_id", "book", "chapter", "verse", name="uq_bible_verses"),
    )
    op.create_index(
        "ix_bible_verses_lookup",
        "bible_verses",
        ["translation_id", "book", "chapter", "verse"],
        unique=True,
    )

    # -----------------------------------------------------------------------
    # verse_citations
    # -----------------------------------------------------------------------
    op.create_table(
        "verse_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("translation_id", sa.Text, nullable=False),
        sa.Column("book", sa.Text, nullable=False),
        sa.Column("chapter", sa.Integer, nullable=False),
        sa.Column("verse_start", sa.Integer, nullable=False),
        sa.Column("verse_end", sa.Integer, nullable=False),
        sa.Column("verse_id_list", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("validated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_verse_citations_message", "verse_citations", ["message_id"])

    # -----------------------------------------------------------------------
    # verse_embeddings  (pgvector — D010 spec: HNSW, 1536 dim, cosine)
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TABLE verse_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            verse_id UUID NOT NULL REFERENCES bible_verses(id),
            embedding_model TEXT NOT NULL,
            embedding vector(1536) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (verse_id, embedding_model)
        )
    """)
    op.execute("""
        CREATE INDEX verse_embeddings_hnsw_idx
            ON verse_embeddings
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
    """)

    # -----------------------------------------------------------------------
    # safety_events
    # -----------------------------------------------------------------------
    op.create_table(
        "safety_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("check_stage", sa.Text, nullable=False),
        sa.Column("risk_level", sa.Text, nullable=False),
        sa.Column("categories", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("rationale_codes", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("model_version", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("check_stage IN ('pre','post')", name="ck_safety_events_stage"),
    )
    op.create_index("ix_safety_events_message", "safety_events", ["message_id"])

    # -----------------------------------------------------------------------
    # reports
    # -----------------------------------------------------------------------
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("details_hash", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('open','reviewed','closed')", name="ck_reports_status"),
    )


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("safety_events")
    op.execute("DROP TABLE IF EXISTS verse_embeddings")
    op.drop_table("verse_citations")
    op.drop_table("bible_verses")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("consents")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
