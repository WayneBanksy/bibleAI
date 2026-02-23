# AI Team Governance (MVP)

## Purpose
Prevent chaos and rework by enforcing:
- clear ownership
- stable interfaces
- safe-by-design behavior
- traceable decisions

## Single Source of Truth Files
- TASKS.md → what work exists and status
- INTERFACES.md → API + schemas + event contracts
- SAFETY_POLICY.md → safety rules and crisis handling
- DECISIONS.md → architecture decisions (ADR-lite)
- DEPENDENCIES.md → blockers and owners

## Ownership Map
- iOS Engineer: client UX, streaming UI, local persistence, iOS tests
- Backend Engineer: FastAPI, DB schema, streaming endpoint, auth, logging
- ML Engineer: routing, safety classification, RAG retrieval, prompt contracts, eval harness
- QA: test plan, integration tests, release gate
- Theology Advisor: scripture accuracy, doctrinal neutrality, tone red flags
- Mental Health Advisor: crisis flow language, boundary compliance

## Work Intake Rules
- No implementation begins without:
  1) a TASK entry with acceptance criteria
  2) interface contract if it crosses boundaries

## Interface Discipline
- Any change to request/response shapes requires:
  - updating INTERFACES.md
  - notifying iOS + backend owners (comment in TASK)
  - adding a migration note if breaking

## Safety Discipline
- Crisis/self-harm path is deterministic (template-based), no LLM improvisation.
- Verse citations must be validated against the scripture corpus before returning.
- Output must avoid medical advice and spiritual coercion.

## Logging & Privacy
- Avoid storing raw user text by default.
- Never log sensitive user content in plaintext.
- Store model version, risk decision, and citation IDs for audits.

## Release Gate
Ship-ready requires:
- QA pass on P0 flows
- Safety policy checks pass
- Citation validation tests pass