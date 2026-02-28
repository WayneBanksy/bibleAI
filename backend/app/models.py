"""
SQLAlchemy 2.0 ORM models.
All tables match INTERFACES.md §9 (locked).
"""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    external_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    consent_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Subscription & monetization (P1-01, P1-02)
    subscription_tier: Mapped[str] = mapped_column(Text, nullable=False, default="free")
    subscription_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscription_status: Mapped[str] = mapped_column(Text, nullable=False, default="inactive")
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    free_quota_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    free_sessions_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")
    reports: Mapped[list["Report"]] = relationship(back_populates="user")
    credit_ledger_entries: Mapped[list["CreditLedger"]] = relationship(back_populates="user")
    iap_transactions: Mapped[list["IAPTransaction"]] = relationship(back_populates="user")


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    disclaimer_version: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    privacy_prefs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('support_session','guided_program','bible_reference','prayer_builder')",
            name="ck_sessions_mode",
        ),
        CheckConstraint("status IN ('active','ended')", name="ck_sessions_status"),
        CheckConstraint(
            "translation_preference IS NULL OR translation_preference IN ('ESV','NIV','KJV','NKJV','NLT','CSB')",
            name="ck_sessions_translation",
        ),
        CheckConstraint(
            "tone_preference IS NULL OR tone_preference IN ('reflective','encouraging','neutral')",
            name="ck_sessions_tone",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    translation_preference: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone_preference: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session",
        order_by="Message.created_at",
    )
    reports: Mapped[list["Report"]] = relationship(back_populates="session")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),
        # Partial unique index: idempotency key (session_id, client_message_id)
        # Only enforced when client_message_id is not NULL.
        Index(
            "ix_messages_session_client_msg_id",
            "session_id",
            "client_message_id",
            unique=True,
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_encrypted: Mapped[bytes | None] = mapped_column(nullable=True)  # BYTEA; AES-256-GCM future
    msg_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    client_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    session: Mapped["Session"] = relationship(back_populates="messages")
    safety_events: Mapped[list["SafetyEvent"]] = relationship(back_populates="message")
    citations: Mapped[list["VerseCitation"]] = relationship(back_populates="message")


class BibleVerse(Base):
    __tablename__ = "bible_verses"
    __table_args__ = (
        CheckConstraint(
            "translation_id IN ('ESV','NIV','KJV','NKJV','NLT','CSB')",
            name="ck_bible_verses_translation",
        ),
        UniqueConstraint("translation_id", "book", "chapter", "verse", name="uq_bible_verses"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    translation_id: Mapped[str] = mapped_column(Text, nullable=False)
    book: Mapped[str] = mapped_column(Text, nullable=False)
    chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    verse: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(Text, nullable=False)

    citations: Mapped[list["VerseCitation"]] = relationship(
        back_populates="bible_verse",
        primaryjoin="foreign(VerseCitation.verse_id_list).any() == BibleVerse.id",
        viewonly=True,
    )
    embeddings: Mapped[list["VerseEmbedding"]] = relationship(back_populates="bible_verse")


class VerseCitation(Base):
    __tablename__ = "verse_citations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False)
    translation_id: Mapped[str] = mapped_column(Text, nullable=False)
    book: Mapped[str] = mapped_column(Text, nullable=False)
    chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    verse_start: Mapped[int] = mapped_column(Integer, nullable=False)
    verse_end: Mapped[int] = mapped_column(Integer, nullable=False)
    verse_id_list: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    message: Mapped["Message"] = relationship(back_populates="citations")
    bible_verse: Mapped["BibleVerse | None"] = relationship(
        back_populates="citations",
        primaryjoin="BibleVerse.id == any_(foreign(VerseCitation.verse_id_list))",
        viewonly=True,
    )


class VerseEmbedding(Base):
    __tablename__ = "verse_embeddings"
    __table_args__ = (
        UniqueConstraint("verse_id", "embedding_model", name="uq_verse_embeddings"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    verse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bible_verses.id"), nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    bible_verse: Mapped["BibleVerse"] = relationship(back_populates="embeddings")


class SafetyEvent(Base):
    __tablename__ = "safety_events"
    __table_args__ = (
        CheckConstraint("check_stage IN ('pre','post')", name="ck_safety_events_stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False)
    check_stage: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    rationale_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    message: Mapped["Message"] = relationship(back_populates="safety_events")


class CreditLedger(Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('iap_redeem', 'session_consume', 'admin_adjust')",
            name="ck_credit_ledger_reason",
        ),
        Index(
            "ix_credit_ledger_idempotency",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    user: Mapped["User"] = relationship(back_populates="credit_ledger_entries")


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("status IN ('open','reviewed','closed')", name="ck_reports_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    details_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    session: Mapped["Session"] = relationship(back_populates="reports")
    user: Mapped["User"] = relationship(back_populates="reports")


class IAPTransaction(Base):
    __tablename__ = "iap_transactions"
    __table_args__ = (
        CheckConstraint(
            "product_type IN ('subscription', 'consumable')",
            name="ck_iap_transactions_product_type",
        ),
        CheckConstraint(
            "environment IN ('Sandbox', 'Production')",
            name="ck_iap_transactions_environment",
        ),
        UniqueConstraint("platform", "transaction_id", name="uq_iap_transactions_platform_txn"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False, default="appstore")
    transaction_id: Mapped[str] = mapped_column(Text, nullable=False)
    original_transaction_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[str] = mapped_column(Text, nullable=False)
    product_type: Mapped[str] = mapped_column(Text, nullable=False)
    signed_transaction_jws: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_renewal_info_jws: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    environment: Mapped[str] = mapped_column(Text, nullable=False, default="Sandbox")
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship(back_populates="iap_transactions")
