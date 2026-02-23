# Governance Lock Policy

The following files are architecturally locked and may only be modified by the Orchestrator role:

- governance/INTERFACES.md
- governance/DECISIONS.md

Specialists (Backend, iOS, ML, QA, Advisors) must not directly modify these files in feature branches.

If a specialist requires a contract or decision change:
1. Open a PR comment or issue referencing the required change.
2. Add an entry to governance/DEPENDENCIES.md.
3. Orchestrator will evaluate and merge governance changes separately.

Violations of this policy may result in PR rejection.