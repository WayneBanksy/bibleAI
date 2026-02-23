# Decisions (ADR-lite)

## D001 Streaming Protocol for Chat
- Status: Provisional
- Options: SSE vs WebSocket
- Decision: SSE (default) unless iOS needs WS for UX parity
- Rationale: simpler infra, easier scaling, enough for token streaming
- Implications: iOS uses EventSource-like client; backend exposes /events

## D002 Scripture Source of Truth
- Status: Provisional
- Decision: canonical verse table + strict citation validation
- Rationale: prevents hallucinated verses, supports audits