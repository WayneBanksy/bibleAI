# Work Packet: P2-01 — WWJD Mode (ML)

## Goal
Implement WWJD mode as a premium response mode that produces:
- scripture-grounded reflection
- 2–3 concrete "Christlike action steps"
- 1 supporting verse with valid citation
Must respect safety taxonomy and crisis bypass rules.

## Owner
ML Engineer

## Branch / Worktree Name
agent/ml/P2-01-wwjd-mode

## Dependencies
- Safety taxonomy & citation rules already exist in SAFETY_POLICY.md.
- Citation validation gate exists (T010).
- Backend supports "mode" field on message request OR this WP defines the spec and requests Orchestrator update INTERFACES.md.

## Scope (files allowed to change)
- backend/app/prompting/wwjd_prompt.py (new) OR wherever prompts live
- backend/app/prompting/default_prompt.py (modify if needed)
- backend/app/schemas/assistant_output.py (update schema)
- backend/tests/test_wwjd_prompting.py (new)
- governance/TASKS.md (status line update only)

## Do Not Touch
- governance/INTERFACES.md, governance/DECISIONS.md (Orchestrator-only)
- backend/app/routers/* (unless explicitly coordinated with backend owner)
- Crisis templates content (B002 signoff pending)

## Input contract
Message request must support:
- mode: "default" | "wwjd"

If not present yet, add an "INTERFACES CHANGE REQUEST" note at end of this WP for Orchestrator.

## Output contract (structured)
WWJD mode must emit JSON with:
```json
{
  "mode": "wwjd",
  "devotional": {
    "title": "string",
    "reflection": "string (<= 1200 chars)",
    "action_steps": ["string (2..3 items, each <= 160 chars)"],
    "prayer": "string (<= 500 chars)"
  },
  "verse_block": {
    "translation": "NIV | ESV | KJV | NKJV | NLT | CSB",
    "reference": "string",
    "text": "string",
    "citations": [{ "verse_id": "string", "start": 1, "end": 3 }]
  }
}
```

Rules:
- Action steps must be phrased as suggestions, not commands.
- No moral condemnation language.
- No clinical diagnosis or treatment guidance.
- If safety classifier returns crisis/high risk → WWJD mode must be overridden to crisis interrupt behavior (no WWJD output).

## Prompt requirements
Add a WWJD system prompt that:
- explicitly defines WWJD as "how to respond in a way consistent with Jesus' character"
- requires scriptural support and verified verse citation
- forbids inventing verses
- enforces tone: warm, calm, non-judgmental, action-oriented

## Tests
- validate prompt renders with correct constraints
- sample outputs pass JSON schema validation
- citations required and non-empty for verse_block
- action_steps count and length constraints

Command:
```
uv run pytest tests/test_wwjd_prompting.py -v
```

## Acceptance Criteria
- [ ] WWJD schema is deterministic and validated.
- [ ] Safety override disables WWJD during crisis/high-risk paths.
- [ ] Output consistently includes actionable suggestions + valid verse citations.

## PR Title
feat(ml): P2-01 WWJD mode prompt + structured output schema + safety override

## INTERFACES CHANGE REQUEST (if needed)
If message request/response schemas do not currently include "mode", request Orchestrator update INTERFACES.md:
- request: add `mode` field to POST /v1/sessions/{id}/messages
- response: include `mode` echoed in message.final payload

## Notes / Risks
- WWJD mode must never bypass crisis detection. Safety pre-check runs before mode-specific prompting.
- Verse citations must pass through the existing citation validation gate (T010) — no special exemption for WWJD.
- Action steps must be suggestions ("Consider..."), never imperatives ("You must...").
- If the LLM cannot find a relevant verse, it should omit verse_block rather than hallucinate.
