# Work Packet: P2-03 — WWJD Blur Overlay (iOS)

## Goal
Implement WWJD Mode UX:
- A mode toggle (Default | WWJD)
- If WWJD requested and backend returns locked response:
  - show blurred preview block (unreadable)
  - show paywall overlay with subscription CTA
  - on successful purchase, automatically unlock and display full WWJD response

## Owner
iOS Engineer

## Branch / Worktree Name
agent/ios/P2-03-wwjd-overlay

## Dependencies
- P1-03 paywall exists (or minimal paywall view).
- Backend P2-02 implements locked response fields + /v1/locked/{id}.
- Entitlements store refresh works.

## Scope (files allowed to change)
- ios/** (SwiftUI views + view models)
- ChatViewModel.swift (modify)
- ChatView.swift (modify)
- PaywallView.swift (reuse/modify)
- APIClient.swift (add GET /v1/locked/{id})
- Tests for view model state (optional but recommended)
- governance/TASKS.md (status line update only)

## Do Not Touch
- governance/INTERFACES.md, governance/DECISIONS.md
- Backend files

## UX behavior

### Mode toggle
- On chat screen: segmented control Default | WWJD
- Default is selected by default.

### Request behavior
When sending a message:
- include mode in request

### Locked response rendering
If message.final.locked == true:
- render a "WWJD Preview" bubble using preview_text but apply blur:
  - blur radius high enough to be unreadable
  - overlay gradient or frosted glass
- show overlay card:
  - Title: "Unlock WWJD Mode"
  - Bullets: "Christlike action steps", "Guided reflection", "Prayer + verse"
  - CTA: "Start Plus"
  - Secondary: "Not now"
  - Restore purchases

### Unlock flow
After subscription purchase success OR user becomes entitled:
1. refresh entitlements
2. call GET /v1/locked/{locked_content_id}
3. replace blurred bubble with full WWJD formatted response
4. persist as a normal message in UI state

### Security requirement
- App must not attempt to reconstruct locked content from preview_text.
- Full payload only comes from unlock endpoint after entitlement.

## API requirements
Add to APIClient:
- func fetchLockedContent(id: String) async throws -> WWJDResponsePayload

## Acceptance Criteria
- [ ] Non-subscriber: WWJD request shows blurred preview + paywall overlay.
- [ ] Subscriber: WWJD request returns full response directly.
- [ ] Post-purchase: unlock happens automatically (no manual refresh required).
- [ ] UI remains stable on network errors (retry button).

## PR Title
feat(ios): P2-03 WWJD locked preview blur + paywall overlay + unlock fetch

## Notes / Risks
- Blur must be visually opaque enough that content is genuinely unreadable — not just dimmed.
- The unlock flow must handle the case where locked_content has expired (410 from backend) — show a "Generate again" option.
- Mode toggle state should not persist across sessions unless explicitly designed to.
- Full WWJD payload rendering (action steps, prayer, verse) requires a dedicated message bubble layout distinct from the default reflection bubble.
