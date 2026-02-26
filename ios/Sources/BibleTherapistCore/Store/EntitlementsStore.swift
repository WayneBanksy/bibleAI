/// EntitlementsStore.swift — Observable entitlement state synced from backend (P1-03).
///
/// Fetches GET /v1/entitlements and exposes the snapshot for SwiftUI binding.
/// Refresh after auth, after purchase, and on app foreground.
import Foundation

#if canImport(Combine)
import Combine

@MainActor
public final class EntitlementsStore: ObservableObject {

    @Published public private(set) var snapshot: EntitlementsSnapshot?
    @Published public private(set) var isLoading: Bool = false
    @Published public private(set) var error: String?

    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Derived state

    public var isPlusActive: Bool {
        guard let s = snapshot else { return false }
        return s.subscriptionTier == "plus" && s.subscriptionStatus == "active"
    }

    public var wwjdEnabled: Bool {
        snapshot?.wwjdEnabled ?? false
    }

    public var creditsBalance: Int {
        snapshot?.creditsBalance ?? 0
    }

    public var canStartSession: Bool {
        snapshot?.canStartSessionNow ?? false
    }

    public var blockingReason: String? {
        snapshot?.blockingReason
    }

    // MARK: - Fetch

    public func refresh() async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let response = try await apiClient.getEntitlements()
            snapshot = response.entitlements
        } catch {
            self.error = error.localizedDescription
        }
    }
}
#endif
