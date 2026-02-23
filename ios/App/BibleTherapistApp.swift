/// BibleTherapistApp.swift — App entry point.
///
/// NOTE: This file belongs in an Xcode project app target that depends on
/// BibleTherapistCore (Swift Package). It is NOT part of the Package.swift manifest.
///
/// Dev bootstrap: exchanges a dev token on first launch so the chat is immediately usable
/// against the local docker-compose backend (http://localhost:8000).
import SwiftUI
import BibleTherapistCore

@main
struct BibleTherapistApp: App {

    @StateObject private var authStore: AuthStore
    private let apiClient: APIClient
    private let sseClient: SSEClient

    init() {
        let baseURL = URL(string: ProcessInfo.processInfo.environment["API_BASE_URL"]
            ?? "http://localhost:8000")!
        let client = APIClient(baseURL: baseURL)
        self.apiClient = client
        self.sseClient = SSEClient()
        self._authStore = StateObject(wrappedValue: AuthStore(apiClient: client))
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authStore)
                .task { await bootstrapDevAuth() }
        }
    }

    /// In development, authenticates with a stable dev token so no real Apple Sign-In is needed.
    private func bootstrapDevAuth() async {
        guard !authStore.isAuthenticated else { return }
        #if DEBUG
        let devId = "dev-user-ios-\(UIDevice.current.identifierForVendor?.uuidString ?? "unknown")"
        do {
            try await authStore.authenticate(idToken: devId)
        } catch {
            // Backend might not be running — continue; ContentView handles unauthenticated state
        }
        #endif
    }

    var chatViewModel: ChatViewModel {
        ChatViewModel(service: apiClient, sseClient: sseClient)
    }
}
