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
        let vm = ChatViewModel(service: client)
        self.apiClient = client
        _authStore = StateObject(wrappedValue: auth)
        _chatViewModel = StateObject(wrappedValue: vm)
    }

    var body: some Scene {
        WindowGroup {
            ContentView(chatViewModel: chatViewModel)
                .environmentObject(authStore)
        }
    }
}
