//
//  BibleAIApp.swift
//  BibleAI
//
//  Created by Wayne Banks II on 2/26/26.
//

import SwiftUI
import BibleTherapistCore

@main
struct BibleAIApp: App {
    private let apiClient: APIClient
    @StateObject private var authStore: AuthStore
    @StateObject private var chatViewModel: ChatViewModel

    init() {
        let client = APIClient(baseURL: URL(string: "http://localhost:8000")!)
        let auth = AuthStore(apiClient: client)

        #if DEV_PREVIEW
        // DEV_PREVIEW: inject MockSessionService so the app runs without a backend.
        // AuthStore still needs a real APIClient for its init, but we bypass auth below.
        let vm = ChatViewModel(service: MockSessionService())
        #else
        let vm = ChatViewModel(service: client)
        #endif

        self.apiClient = client
        _authStore = StateObject(wrappedValue: auth)
        _chatViewModel = StateObject(wrappedValue: vm)

        #if DEV_PREVIEW
        // Bypass the auth gate — sets isAuthenticated = true immediately.
        auth.setTokenDirect("dev-preview-token")
        #endif
    }

    var body: some Scene {
        WindowGroup {
            ContentView(chatViewModel: chatViewModel)
                .environmentObject(authStore)
        }
    }
}
