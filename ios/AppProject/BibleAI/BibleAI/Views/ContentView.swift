/// ContentView.swift — Root navigation: disclaimer → auth → chat.
import SwiftUI
import BibleTherapistCore

struct ContentView: View {
    @EnvironmentObject private var authStore: AuthStore
    @AppStorage("btapp.disclaimer.accepted") private var disclaimerAccepted = false

    /// Injected by the App so the ViewModel is scoped to the session lifecycle.
    @StateObject private var chatViewModel: ChatViewModel

    init(chatViewModel: ChatViewModel) {
        _chatViewModel = StateObject(wrappedValue: chatViewModel)
    }

    var body: some View {
        Group {
            if !disclaimerAccepted {
                DisclaimerView {
                    disclaimerAccepted = true
                }
            } else if !authStore.isAuthenticated {
                ProgressView("Connecting…")
                    .padding()
            } else {
                ChatView()
                    .environmentObject(chatViewModel)
            }
        }
        .animation(.easeInOut, value: disclaimerAccepted)
        .animation(.easeInOut, value: authStore.isAuthenticated)
    }
}
