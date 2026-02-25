# In-App Purchase Product Definitions

This file defines canonical App Store product IDs and server-side mappings.
These values MUST be used consistently across:
- iOS StoreKit configuration
- Backend verification logic (P1-04)
- Credit redemption logic (P1-02)
- Analytics events (P1-05)

Do not modify without orchestrator approval.

---

## Subscription Products

### Product: Plus Monthly
- product_id: com.bibletherapist.plus.monthly
- type: auto-renewable subscription
- duration: 1 month
- entitlement:
    subscription_tier = "plus"
    wwjd_enabled = true
- quota:
    free_sessions_per_week = 10
    free_sessions_per_day = 2
- server mapping:
    product_type = "subscription"

### Product: Plus Annual
- product_id: com.bibletherapist.plus.annual
- type: auto-renewable subscription
- duration: 1 year
- entitlement:
    subscription_tier = "plus"
    wwjd_enabled = true
- quota:
    free_sessions_per_week = 10
    free_sessions_per_day = 2
- server mapping:
    product_type = "subscription"

---

## Credit Packs (Consumables)

### Small Pack
- product_id: com.bibletherapist.credits.10
- type: consumable
- credits_granted: 10

### Medium Pack
- product_id: com.bibletherapist.credits.30
- type: consumable
- credits_granted: 30

### Large Pack
- product_id: com.bibletherapist.credits.50
- type: consumable
- credits_granted: 50

Server mapping:
- product_type = "consumable"
- quantity MUST match credits_granted
- mismatch → 400 INVALID_PURCHASE

---

## Enforcement Rules

1. Subscription ALWAYS overrides free-tier limits.
2. Credits override free-tier limits but are consumed when subscription inactive.
3. WWJD mode requires:
   subscription_tier == "plus"
4. Credits do NOT grant WWJD access.

---

## Analytics Product Properties

All analytics events must include:
- product_id
- product_type
- subscription_tier (post-transaction)