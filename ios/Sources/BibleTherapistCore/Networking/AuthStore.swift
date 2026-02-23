/// AuthStore.swift — JWT token lifecycle.
///
/// MVP storage: UserDefaults (replace with Keychain before App Store submission).
/// Token is synced to APIClient on every update.
import Foundation

#if canImport(Combine)
import Combine

@MainActor
public final class AuthStore: ObservableObject {

    @Published public private(set) var isAuthenticated: Bool = false
    @Published public private(set) var token: String?

    private static let tokenKey = "btapp.auth.token"
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
        // Restore persisted session
        if let stored = UserDefaults.standard.string(forKey: Self.tokenKey) {
            self.token = stored
            self.isAuthenticated = true
            apiClient.setAuthToken(stored)
        }
    }

    /// Exchange an Apple ID token for a server JWT.
    public func authenticate(idToken: String) async throws {
        let response = try await apiClient.exchangeToken(idToken: idToken)
        persist(token: response.accessToken)
    }

    /// Dev convenience: inject a raw token directly (dev backend only).
    public func setTokenDirect(_ rawToken: String) {
        persist(token: rawToken)
    }

    public func signOut() {
        token = nil
        isAuthenticated = false
        apiClient.setAuthToken(nil)
        UserDefaults.standard.removeObject(forKey: Self.tokenKey)
    }

    private func persist(token newToken: String) {
        self.token = newToken
        self.isAuthenticated = true
        apiClient.setAuthToken(newToken)
        UserDefaults.standard.set(newToken, forKey: Self.tokenKey)
    }
}
#endif
