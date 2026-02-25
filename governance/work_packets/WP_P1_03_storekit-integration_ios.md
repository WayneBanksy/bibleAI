# Work Packet: P1-03 — StoreKit Integration (iOS)

## Goal
Implement iOS in-app purchases via StoreKit 2:
- Plus subscription product (auto-renewable)
- Credit packs (consumable)
Sync purchase state with backend via redeem/entitlements endpoints.

## Owner
iOS Engineer (Lead)

## Branch / Worktree Name
agent/ios/P1-03-storekit

## Dependencies
- Backend endpoints exist:
  - GET /v1/entitlements (P1-01)
  - POST /v1/credits/redeem (P1-02)
- Product IDs are defined and configured in App Store Connect (for local dev you can stub UI; purchase flows require StoreKit config file).

## Scope (files allowed to change)
- ios/Sources/** (or ios/App/** depending on your layout)
- Create StoreKit modules:
  - StoreKitManager.swift (new)
  - PaywallView.swift (new)
  - CreditsStoreView.swift (optional)
- Update Chat UI to show paywall/credits CTA based on entitlements
- Update APIClient to call /v1/entitlements and /v1/credits/redeem
- ios/Tests/** for unit tests (lightweight)
- governance/TASKS.md (status line update only)

## Do Not Touch
- governance/INTERFACES.md, governance/DECISIONS.md
- Any backend files

## Product IDs (must be centralized)
Define constants:
- SUB_PLUS_MONTHLY = "plus_monthly"
- SUB_PLUS_ANNUAL  = "plus_annual"
- CREDITS_5  = "credits_5"
- CREDITS_10 = "credits_10"
- CREDITS_30 = "credits_30"
- CREDITS_50 = "credits_50"

## Behavior requirements

### Entitlements refresh
- On app launch, after auth, call GET /v1/entitlements and store in an EntitlementsStore ObservableObject.
- After any successful purchase, refresh entitlements.

### Subscription purchase
- Use StoreKit 2 `Product.purchase()`
- On success, send transaction info to backend via a new call:
  - For MVP, subscription is handled by entitlements endpoint refresh (backend may not verify receipt yet).
  - Still implement local UI unlock after purchase, but always confirm with backend refresh.

### Credits purchase
- After purchasing a credit product, call POST /v1/credits/redeem with:
  - idempotency_key = transaction.id (string)
  - product_id = product.id
  - purchase_token = signedTransactionInfo or transaction.jwsRepresentation (if available)
  - purchased_at = transaction.purchaseDate

### Restore purchases
- Implement "Restore Purchases" action:
  - call `Transaction.currentEntitlements`
  - refresh backend entitlements
  - For credits, only redeem on actual purchase events; do not double-redeem restores.

### UI
- PaywallView:
  - show Free vs Plus features
  - CTA: Subscribe
  - Secondary CTA: Buy Credits
  - Restore button
- Chat:
  - When backend returns 402 PAYWALL_REQUIRED, show paywall modal with reason
  - When user selects WWJD and not entitled, route to WWJD lock overlay (P2-03)

## Testing
- Use StoreKit Test Configuration file for local testing if available.
- Add unit tests for EntitlementsStore state transitions and API calls (mock SessionServiceProtocol).

## Acceptance Criteria
- [ ] User can purchase Plus and app reflects unlocked status after backend refresh.
- [ ] User can purchase credits; credits_balance increases on backend and UI updates.
- [ ] Restore purchases refreshes entitlements.
- [ ] All network calls are resilient (error states with retry).

## PR Title
feat(ios): P1-03 StoreKit2 purchases + paywall + credits redeem + entitlements sync

## Notes / Risks
- StoreKit 2 requires iOS 15+. Confirm minimum deployment target.
- Local testing requires a StoreKit Configuration file in the Xcode project.
- Credit restores must NOT re-redeem — only fresh purchase transactions trigger /v1/credits/redeem.
- Backend receipt verification (P1-04) is not yet live; MVP relies on client-side transaction trust + backend idempotency.
