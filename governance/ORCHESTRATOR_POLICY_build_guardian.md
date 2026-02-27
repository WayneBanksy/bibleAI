# Orchestrator Policy: iOS Build Guardian & Pre-Merge Gate

**Priority:** PERMANENT POLICY — applies to all current and future sprints  
**Issued by:** Project Owner  
**Date:** 2026-02-27  
**Scope:** Merge workflow, iOS build integrity, agent accountability

---

## 1. Build Guardian Role

The **iOS Engineer (Lead)** agent is hereby assigned the permanent role of **Build Guardian** for the iOS app target.

### 1.1 Responsibilities

- **Every PR that touches any file under `ios/`** must result in a passing build before merge.
- The iOS Engineer is responsible for verifying that PRs from OTHER agents (Backend, ML, QA) that modify files under `ios/Sources/BibleTherapistCore/` do not break the app build.
- If a non-iOS agent's PR breaks the build, the iOS Engineer must:
  1. Identify the root cause and the responsible agent.
  2. File a **blocking issue** in `governance/TASKS.md` assigned to that agent.
  3. Provide a clear description of what broke and what the fix requires.
  4. Optionally provide a patch if the fix is trivial.
- The iOS Engineer may **reject any PR** that breaks the build until the owning agent fixes it.

### 1.2 Scope of Guardianship

The Build Guardian is accountable for:

| Area | Guardian Action |
|------|----------------|
| New views added | Verify placed in `ios/AppProject/BibleAI/BibleAI/Views/` only |
| New models/networking/store changes in package | Verify no compile errors in app target |
| `Package.swift` changes | Verify dependency resolution and build pass |
| Any `@main` or entry point changes | Verify exactly ONE `@main` exists |
| Xcode project file (`project.pbxproj`) changes | Verify no stale references or duplicate targets |

---

## 2. Automated Pre-Merge Gate

### 2.1 Gate Script

The file `scripts/verify_ios_build.sh` is the **canonical build verification gate**. It performs:

1. **Project file existence check** — confirms `.xcodeproj` exists
2. **Prohibited path check** — ensures `ios/App/` and `ios/Sources/BibleTherapistCore/Views/` have not been recreated (per D014)
3. **Single `@main` check** — ensures exactly one entry point
4. **Duplicate filename check** — catches symbol collisions before compile
5. **`xcodebuild clean build`** — full compile against iOS Simulator

### 2.2 Gate Enforcement Rules

**MANDATORY:** The orchestrator must enforce the following before ANY merge to `main`:

```
┌─────────────────────────────────────────────────────────┐
│                  PR MERGE CHECKLIST                      │
│                                                         │
│  For PRs touching ios/ (any file):                      │
│                                                         │
│  □ 1. Agent ran: ./scripts/verify_ios_build.sh          │
│  □ 2. Script exited with code 0 (BUILD SUCCEEDED)       │
│  □ 3. Build log reviewed — 0 errors, 0 warnings*        │
│  □ 4. iOS Engineer (Build Guardian) approved             │
│                                                         │
│  * Warnings may be acceptable if pre-existing;          │
│    new warnings require justification.                  │
│                                                         │
│  If ANY box is unchecked → PR is BLOCKED.               │
└─────────────────────────────────────────────────────────┘
```

**For PRs NOT touching `ios/`:** The gate script is not required, but the orchestrator should use judgment — if a backend schema change could affect iOS models via shared contract, request a build verification anyway.

### 2.3 Gate Integration in Merge Sequencing

The orchestrator's existing merge sequencing must incorporate the gate:

```
1. Orchestrator receives PR from agent
2. Orchestrator reviews scope (files changed)
3. IF any file under ios/ is changed:
   a. Orchestrator assigns iOS Engineer to run verify_ios_build.sh
   b. iOS Engineer runs script and reports result
   c. IF exit code 0 → proceed to merge
   d. IF exit code 1 → PR blocked, escalation protocol triggered
4. Orchestrator merges in dependency order (governance → backend → package → ios)
5. After merge, orchestrator runs verify_ios_build.sh once more as post-merge smoke test
```

---

## 3. Escalation Protocol

When the build breaks, the following escalation protocol applies:

### Level 1: Self-Fix (iOS Engineer)
- If the failure is in view code, app entry point, or Xcode project config → iOS Engineer fixes directly.
- Turnaround: immediate (same work session).

### Level 2: Cross-Agent Escalation
- If the failure is caused by a package change (model, networking, store, viewmodel) committed by another agent:
  1. iOS Engineer identifies the breaking commit and owning agent.
  2. iOS Engineer adds a blocking task to `governance/TASKS.md`:
     ```
     ### T-BUILD-BREAK-<date>: Build broken by <agent> in <file>
     - **Status:** BLOCKING
     - **Owner:** <responsible agent>
     - **Filed by:** iOS Engineer (Build Guardian)
     - **Error:** <compiler error message>
     - **Fix required:** <description>
     - **Blocked PRs:** <list of PRs waiting on fix>
     ```
  3. Orchestrator halts all ios/ merges until the blocking task is resolved.

### Level 3: Project Owner Escalation
- If the responsible agent cannot fix within one work session, or if there's a disagreement about ownership → Project Owner decides.

---

## 4. Required Updates to Orchestrator Merge Workflow

Add the following to `orchestrator.md` (or equivalent orchestrator instructions):

```markdown
## Pre-Merge Gate (iOS)

Before merging any PR that modifies files under `ios/`:

1. Ensure the branch is rebased on latest `main`.
2. Run `./scripts/verify_ios_build.sh` from the repo root.
3. Require exit code 0.
4. If the script fails, do NOT merge. Trigger escalation protocol.
5. After merge to main, run the script again as a post-merge smoke test.

The iOS Engineer (Lead) is the Build Guardian and has authority to
block any PR that fails the gate, regardless of which agent authored it.
```

---

## 5. Required Updates to All iOS Work Packets

All current and future work packets that touch `ios/` must include:

```markdown
## Build Verification (MANDATORY)

Before marking this work packet as complete:
1. Run `./scripts/verify_ios_build.sh` from repo root
2. Confirm exit code 0
3. Paste build result summary in PR description

If the build fails and the cause is outside this work packet's scope,
file a blocking issue per the escalation protocol and notify the orchestrator.
```

---

## 6. Governance Artifact Updates

### 6.1 `governance/DECISIONS.md` — Append:

```markdown
### D015: iOS Build Guardian Role & Automated Pre-Merge Gate

- **Date:** 2026-02-27
- **Decision:** The iOS Engineer (Lead) is permanently assigned as Build
  Guardian. All PRs touching ios/ must pass `scripts/verify_ios_build.sh`
  (exit code 0) before merge. Failures trigger a defined escalation protocol.
- **Rationale:** Repeated build failures from directory duplication and
  cross-agent changes demonstrated the need for automated enforcement
  and clear ownership of build integrity.
- **Status:** LOCKED
```

### 6.2 `governance/TASKS.md` — Append:

```markdown
### T-BUILD-GUARDIAN: iOS Build Guardian Standing Assignment
- **Status:** ACTIVE (permanent)
- **Owner:** iOS Engineer (Lead)
- **Summary:** Ongoing responsibility to verify iOS build integrity
  on every PR touching ios/. Includes running pre-merge gate script,
  approving ios/ merges, and escalating cross-agent build breaks.
```