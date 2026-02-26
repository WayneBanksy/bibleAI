/// ProductIDs.swift — Centralized App Store product identifiers (P1-03).
import Foundation

public enum ProductIDs {
    // Subscriptions (auto-renewable)
    public static let plusMonthly = "plus_monthly"
    public static let plusAnnual  = "plus_annual"

    // Credit packs (consumable)
    public static let credits5  = "credits_5"
    public static let credits10 = "credits_10"
    public static let credits30 = "credits_30"
    public static let credits50 = "credits_50"

    public static let subscriptionIDs: Set<String> = [plusMonthly, plusAnnual]
    public static let creditIDs: Set<String> = [credits5, credits10, credits30, credits50]
    public static let allIDs: Set<String> = subscriptionIDs.union(creditIDs)
}
