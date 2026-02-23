/// MessageBubble.swift — Renders a single chat message.
///
/// - User messages: right-aligned, accent tinted.
/// - Assistant messages: left-aligned, system secondary background.
/// - Streaming indicator: animated ellipsis while isStreaming = true.
/// - Citations: tappable chip row beneath assistant body.
/// - Report action: long-press context menu on assistant messages.
import SwiftUI
import BibleTherapistCore

struct MessageBubble: View {
    let message: ChatMessage

    @EnvironmentObject private var vm: ChatViewModel
    @State private var showingReport = false

    private var isUser: Bool { message.role == .user }

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if isUser { Spacer(minLength: 48) }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 6) {
                // Message body
                bubbleBody
                    .contextMenu {
                        if !isUser, let serverId = message.serverId {
                            Button(role: .destructive) {
                                showingReport = true
                            } label: {
                                Label("Report this message", systemImage: "flag")
                            }
                            // Copy text
                            Button {
                                UIPasteboard.general.string = message.text
                            } label: {
                                Label("Copy", systemImage: "doc.on.doc")
                            }
                        }
                    }

                // Citation chips
                if !message.citations.isEmpty {
                    citationChips
                }
            }

            if !isUser { Spacer(minLength: 48) }
        }
        .sheet(isPresented: $showingReport) {
            if let serverId = message.serverId, let sessionId = vm.sessionId {
                ReportSheet(sessionId: sessionId, messageId: serverId, service: vm.service)
            }
        }
    }

    @ViewBuilder
    private var bubbleBody: some View {
        VStack(alignment: .leading, spacing: 4) {
            if message.text.isEmpty && message.isStreaming {
                TypingIndicator()
            } else {
                Text(message.text)
                    .font(.body)
                    .foregroundColor(isUser ? .white : .primary)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(isUser ? Color.accentColor : Color(.secondarySystemBackground))
        .cornerRadius(18)
    }

    @ViewBuilder
    private var citationChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(message.citations, id: \.quote) { citation in
                    Text("\(citation.book) \(citation.chapter):\(citation.verseStart)–\(citation.verseEnd) (\(citation.translationId.rawValue))")
                        .font(.caption2.bold())
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.accentColor.opacity(0.12))
                        .cornerRadius(8)
                        .foregroundColor(.accentColor)
                }
            }
        }
    }
}

// MARK: - Typing Indicator

private struct TypingIndicator: View {
    @State private var dotOpacities: [Double] = [0.3, 0.3, 0.3]
    private let timer = Timer.publish(every: 0.4, on: .main, in: .common).autoconnect()
    @State private var step = 0

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .frame(width: 6, height: 6)
                    .opacity(dotOpacities[i])
            }
        }
        .onReceive(timer) { _ in
            step = (step + 1) % 3
            withAnimation(.easeInOut(duration: 0.3)) {
                dotOpacities = (0..<3).map { i in i == step ? 1.0 : 0.3 }
            }
        }
    }
}

// MARK: - Report Sheet

private struct ReportSheet: View {
    let sessionId: UUID
    let messageId: UUID
    let service: SessionServiceProtocol

    @Environment(\.dismiss) private var dismiss
    @State private var reason: ReportReason = .inappropriate
    @State private var details: String = ""
    @State private var isSubmitting = false
    @State private var submitted = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Reason") {
                    Picker("Reason", selection: $reason) {
                        Text("Inappropriate").tag(ReportReason.inappropriate)
                        Text("Incorrect Scripture").tag(ReportReason.incorrectScripture)
                        Text("Harmful Content").tag(ReportReason.harmful)
                        Text("Other").tag(ReportReason.other)
                    }
                    .pickerStyle(.menu)
                }
                Section("Additional Details (optional)") {
                    TextEditor(text: $details)
                        .frame(minHeight: 80)
                }
            }
            .navigationTitle("Report Message")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Submit") {
                        Task { await submit() }
                    }
                    .disabled(isSubmitting)
                }
            }
            .overlay {
                if submitted {
                    VStack(spacing: 12) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.largeTitle)
                            .foregroundColor(.green)
                        Text("Thank you for your report.")
                            .font(.headline)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(.regularMaterial)
                }
            }
        }
    }

    private func submit() async {
        isSubmitting = true
        _ = try? await service.submitReport(
            sessionId: sessionId,
            messageId: messageId,
            reason: reason,
            details: details.isEmpty ? nil : details
        )
        submitted = true
        try? await Task.sleep(nanoseconds: 1_200_000_000)
        dismiss()
    }
}
