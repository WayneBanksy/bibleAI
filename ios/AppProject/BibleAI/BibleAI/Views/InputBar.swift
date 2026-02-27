/// InputBar.swift — Text input + send button.
///
/// Disabled when isDisabled=true (streaming in progress or risk interrupt active).
/// Submits on tap or return key. Clears field after submit.
import SwiftUI

struct InputBar: View {
    let isDisabled: Bool
    let onSend: (String) -> Void

    @State private var text: String = ""
    @FocusState private var isFocused: Bool

    private var canSend: Bool {
        !isDisabled && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField("Type a message…", text: $text, axis: .vertical)
                .lineLimit(1...5)
                .padding(10)
                .background(Color(.secondarySystemBackground))
                .cornerRadius(20)
                .focused($isFocused)
                .disabled(isDisabled)
                .submitLabel(.send)
                .onSubmit {
                    if canSend { submit() }
                }

            Button(action: submit) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 32))
                    .foregroundColor(canSend ? .accentColor : .gray)
            }
            .disabled(!canSend)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .animation(.easeInOut(duration: 0.15), value: isDisabled)
    }

    private func submit() {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        text = ""
        isFocused = false
        onSend(trimmed)
    }
}
