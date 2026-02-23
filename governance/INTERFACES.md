# Interfaces / Contracts (v0)

## Auth
- Header: Authorization: Bearer <jwt>

## Create Session
POST /v1/sessions
Response:
{
  "session_id": "uuid",
  "mode": "support_session",
  "created_at": "iso"
}

## Send Message
POST /v1/sessions/{session_id}/messages
Request:
{
  "text": "string",
  "client_message_id": "uuid",
  "input_mode": "text|voice_transcript"
}

Response (non-stream fallback):
{
  "assistant_message": {...},
  "risk": {...}
}

## Stream Events (SSE)
GET /v1/sessions/{session_id}/events

Event types:
- token.delta: { "message_id": "uuid", "delta": "string" }
- message.final: {
    "message_id": "uuid",
    "text": "string",
    "citations": [ { "book":"", "chapter":1, "verse_start":1, "verse_end":2, "translation_id":"" } ],
    "structured": { "reflection":"", "prayer":"", "next_step":"", "question":"" },
    "risk": { "risk_level":"none|low|medium|high", "categories":[], "action":"allow|caution|refuse|escalate" }
  }
- risk.interrupt: { "risk_level":"high", "action":"escalate", "resources":[...] }

## Report Assistant Message
POST /v1/safety/report
Request:
{ "session_id":"uuid", "message_id":"uuid", "reason":"string", "details":"string?" }
Response: { "ok": true }