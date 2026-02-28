"""
Pydantic schemas matching INTERFACES.md v0 (locked).
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TokenRequest(BaseModel):
    grant_type: Literal["apple_id_token"]
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

TranslationID = Literal["ESV", "NIV", "KJV", "NKJV", "NLT", "CSB"]
TonePreference = Literal["reflective", "encouraging", "neutral"]
SessionMode = Literal["support_session", "guided_program", "bible_reference", "prayer_builder"]


class CreateSessionRequest(BaseModel):
    mode: SessionMode
    translation_preference: TranslationID | None = None
    tone_preference: TonePreference | None = None


class SessionResponse(BaseModel):
    session_id: uuid.UUID
    mode: str
    translation_preference: str | None
    tone_preference: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionDetailResponse(BaseModel):
    session_id: uuid.UUID
    mode: str
    status: str
    message_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class SendMessageRequest(BaseModel):
    text: str = Field(..., max_length=2000)
    client_message_id: uuid.UUID
    input_mode: Literal["text", "voice_transcript"] = "text"


class SendMessageAccepted(BaseModel):
    message_id: uuid.UUID
    client_message_id: uuid.UUID
    session_id: uuid.UUID
    status: Literal["processing"] = "processing"


# ---------------------------------------------------------------------------
# SSE event payloads (serialised to JSON strings in the stream generator)
# ---------------------------------------------------------------------------

class TokenDeltaPayload(BaseModel):
    message_id: uuid.UUID
    delta: str
    sequence: int


class CitationPayload(BaseModel):
    translation_id: str
    book: str
    chapter: int
    verse_start: int
    verse_end: int
    verse_id_list: list[uuid.UUID]
    quote: str


class StructuredPayload(BaseModel):
    reflection: str
    prayer: str | None = None
    next_step: str | None = None
    reflection_question: str | None = None


class RiskPayload(BaseModel):
    risk_level: str
    categories: list[str]
    action: str


class MessageFinalPayload(BaseModel):
    message_id: uuid.UUID
    session_id: uuid.UUID
    text: str
    structured: StructuredPayload
    citations: list[CitationPayload]
    risk: RiskPayload
    model_version: str
    created_at: datetime


class ResourceItem(BaseModel):
    label: str
    contact: str


class RiskInterruptPayload(BaseModel):
    risk_level: str = "high"
    action: str = "escalate"
    categories: list[str]
    message: str
    resources: list[ResourceItem]
    requires_acknowledgment: bool = True


class StreamErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool


# ---------------------------------------------------------------------------
# Safety report
# ---------------------------------------------------------------------------

class ReportReason(str):
    pass


class SafetyReportRequest(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID
    reason: Literal["inappropriate", "incorrect_scripture", "harmful", "other"]
    details: str | None = Field(None, max_length=500)


class SafetyReportResponse(BaseModel):
    ok: bool = True
    report_id: uuid.UUID


# ---------------------------------------------------------------------------
# Error envelope (matches INTERFACES.md §1.4)
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Entitlements (P1-01)
# ---------------------------------------------------------------------------

class EntitlementsSnapshot(BaseModel):
    subscription_tier: str
    subscription_status: str
    subscription_expires_at: str | None = None
    wwjd_enabled: bool
    credits_balance: int
    free_sessions_remaining: int | None = None
    plus_sessions_remaining_today: int | None = None
    plus_sessions_remaining_week: int | None = None
    can_start_session_now: bool
    next_reset_at: str | None = None
    blocking_reason: str | None = None


class EntitlementsResponse(BaseModel):
    entitlements: EntitlementsSnapshot


# ---------------------------------------------------------------------------
# Credits (P1-02)
# ---------------------------------------------------------------------------

class RedeemCreditsRequest(BaseModel):
    idempotency_key: str
    product_id: str
    purchase_token: str
    purchased_at: str


class RedeemCreditsResponse(BaseModel):
    credits_balance: int
    added: int


# ---------------------------------------------------------------------------
# Analytics (P1-05)
# ---------------------------------------------------------------------------

class AnalyticsEventRequest(BaseModel):
    event_name: str
    timestamp: str
    session_id: str | None = None
    properties: dict = {}


class AnalyticsEventAccepted(BaseModel):
    accepted: bool = True


class AnalyticsSummaryResponse(BaseModel):
    window_days: int
    counts: dict[str, int]


# ---------------------------------------------------------------------------
# IAP Verification (P1-04)
# ---------------------------------------------------------------------------

class IAPVerifyRequest(BaseModel):
    platform: Literal["appstore"] = "appstore"
    product_type: Literal["subscription", "consumable"]
    product_id: str
    transaction_id: str
    original_transaction_id: str | None = None
    environment: Literal["Sandbox", "Production"] = "Sandbox"
    signed_transaction_jws: str | None = None
    signed_renewal_info_jws: str | None = None


class IAPVerifyResponse(BaseModel):
    entitlements: EntitlementsSnapshot
    verified: bool
