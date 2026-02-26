/// EntitlementsStoreTests.swift — Unit tests for EntitlementsStore (P1-03).
import XCTest
@testable import BibleTherapistCore

@MainActor
final class EntitlementsStoreTests: XCTestCase {

    func testDerivedStateDefaultsWhenNoSnapshot() {
        let client = APIClient(baseURL: URL(string: "http://test")!)
        let store = EntitlementsStore(apiClient: client)

        XCTAssertFalse(store.isPlusActive)
        XCTAssertFalse(store.wwjdEnabled)
        XCTAssertEqual(store.creditsBalance, 0)
        XCTAssertFalse(store.canStartSession)
        XCTAssertNil(store.blockingReason)
        XCTAssertNil(store.snapshot)
    }

    func testProductIDsAreCentralized() {
        XCTAssertEqual(ProductIDs.plusMonthly, "plus_monthly")
        XCTAssertEqual(ProductIDs.plusAnnual, "plus_annual")
        XCTAssertEqual(ProductIDs.credits5, "credits_5")
        XCTAssertEqual(ProductIDs.credits10, "credits_10")
        XCTAssertEqual(ProductIDs.credits30, "credits_30")
        XCTAssertEqual(ProductIDs.credits50, "credits_50")
        XCTAssertEqual(ProductIDs.allIDs.count, 6)
        XCTAssertEqual(ProductIDs.subscriptionIDs.count, 2)
        XCTAssertEqual(ProductIDs.creditIDs.count, 4)
    }

    func testEntitlementsSnapshotDecoding() throws {
        let json = """
        {
            "subscription_tier": "plus",
            "subscription_status": "active",
            "subscription_expires_at": "2026-03-25T00:00:00Z",
            "wwjd_enabled": true,
            "credits_balance": 15,
            "free_sessions_remaining": null,
            "plus_sessions_remaining_today": 1,
            "plus_sessions_remaining_week": 8,
            "can_start_session_now": true,
            "next_reset_at": null,
            "blocking_reason": null
        }
        """.data(using: .utf8)!

        let snapshot = try JSONDecoder().decode(EntitlementsSnapshot.self, from: json)
        XCTAssertEqual(snapshot.subscriptionTier, "plus")
        XCTAssertEqual(snapshot.subscriptionStatus, "active")
        XCTAssertTrue(snapshot.wwjdEnabled)
        XCTAssertEqual(snapshot.creditsBalance, 15)
        XCTAssertTrue(snapshot.canStartSessionNow)
        XCTAssertEqual(snapshot.plusSessionsRemainingToday, 1)
        XCTAssertNil(snapshot.blockingReason)
    }

    func testRedeemCreditsResponseDecoding() throws {
        let json = """
        {"credits_balance": 20, "added": 10}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(RedeemCreditsResponse.self, from: json)
        XCTAssertEqual(response.creditsBalance, 20)
        XCTAssertEqual(response.added, 10)
    }

    func testIAPVerifyResponseDecoding() throws {
        let json = """
        {
            "entitlements": {
                "subscription_tier": "plus",
                "subscription_status": "active",
                "subscription_expires_at": null,
                "wwjd_enabled": true,
                "credits_balance": 0,
                "free_sessions_remaining": null,
                "plus_sessions_remaining_today": 2,
                "plus_sessions_remaining_week": 10,
                "can_start_session_now": true,
                "next_reset_at": null,
                "blocking_reason": null
            },
            "verified": true
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(IAPVerifyResponse.self, from: json)
        XCTAssertTrue(response.verified)
        XCTAssertEqual(response.entitlements.subscriptionTier, "plus")
        XCTAssertTrue(response.entitlements.wwjdEnabled)
    }
}
