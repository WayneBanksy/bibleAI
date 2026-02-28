/// ChatView.swift — Main chat screen.
///
/// Layout: ScrollView of messages + InputBar at bottom.
/// Overlays RiskInterruptView as a full-screen modal when inputBlocked = true.
import SwiftUI
import BibleTherapistCore

struct ChatView: View {
    @EnvironmentObject private var vm: ChatViewModel
    @State private var showingGetHelp = false

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottom) {
                // Message list
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(vm.messages) { message in
                                MessageBubble(message: message)
                                    .id(message.id)
                            }
                            // Anchor for auto-scroll
                            Color.clear
                                .frame(height: 1)
                                .id("bottom")
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                        .padding(.bottom, 80) // space for InputBar
                    }
                    .onChange(of: vm.messages.count) { _, _ in
                        withAnimation(.easeOut(duration: 0.2)) {
                            proxy.scrollTo("bottom")
                        }
                    }
                    .onChange(of: vm.messages.last?.text) { _, _ in
                        // Scroll on every token append during streaming
                        proxy.scrollTo("bottom")
                    }
                }

                // Input bar pinned to bottom
                VStack(spacing: 0) {
                    Divider()
                    InputBar(isDisabled: vm.inputBlocked || vm.isStreaming) { text in
                        #if DEV_PREVIEW
                        Task { await vm.simulateStreamingResponse(for: text) }
                        #else
                        Task { await vm.sendMessage(text) }
                        #endif
                    }
                    .padding(.bottom, 4)
                }
                .background(.ultraThinMaterial)
            }
            .navigationTitle("Reflection")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Button(action: { showingGetHelp = true }) {
                            Label("Get Help Now", systemImage: "phone.circle.fill")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            // Risk interrupt overlay (blocks all interaction)
            .fullScreenCover(item: $vm.riskInterrupt) { interrupt in
                RiskInterruptView(payload: interrupt) {
                    vm.acknowledgeRiskInterrupt()
                }
            }
            // Error banner
            .alert("Something went wrong", isPresented: Binding(
                get: { vm.errorMessage != nil },
                set: { if !$0 { vm.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: {
                Text(vm.errorMessage ?? "")
            }
            // Get Help Now sheet from overflow menu
            .sheet(isPresented: $showingGetHelp) {
                CrisisResourcesSheet()
            }
        }
        .task {
            guard vm.sessionId == nil else { return }
            await vm.createSession()

            #if DEV_PREVIEW
            // Inject a welcome message so the user sees the app is alive.
            if vm.messages.isEmpty {
                let welcome = ChatMessage(
                    role: .assistant,
                    text: "Welcome to BibleAI (Dev Preview). Share what's on your heart, and I'll offer a scripture-grounded reflection.",
                    isStreaming: false
                )
                vm.messages.append(welcome)
            }
            #endif
        }
    }
}

// MARK: - Preview

/// Stub service for SwiftUI previews. Methods are never called because
/// the preview sets sessionId, so ChatView's .task guard exits early.
private struct PreviewService: SessionServiceProtocol {
    func createSession(mode: SessionMode, translationPreference: TranslationID, tonePreference: TonePreference) async throws -> SessionResponse {
        fatalError("Preview only")
    }
    func sendMessage(sessionId: UUID, text: String, clientMessageId: UUID) async throws -> MessageAccepted {
        fatalError("Preview only")
    }
    func submitReport(sessionId: UUID, messageId: UUID, reason: ReportReason, details: String?) async throws -> ReportResponse {
        fatalError("Preview only")
    }
    func sseURL(sessionId: UUID, lastEventId: String?) -> URL {
        URL(string: "http://localhost:8000/v1/sessions/\(sessionId)/events")!
    }
    func authHeaders() -> [String: String] { [:] }
}

#Preview {
    let vm = ChatViewModel(
        service: PreviewService(),
        previewMessages: [
            ChatMessage(role: .user, text: "I've been feeling anxious about the future."),
            ChatMessage(role: .assistant, text: "It's understandable to feel that way. Many people find comfort in reflecting on scripture during uncertain times. One verse that speaks to this is about not worrying about tomorrow, for tomorrow will worry about itself."),
            ChatMessage(role: .user, text: "That helps. Can you share a prayer?"),
        ],
        sessionId: UUID()
    )
    ChatView()
        .environmentObject(vm)
}
