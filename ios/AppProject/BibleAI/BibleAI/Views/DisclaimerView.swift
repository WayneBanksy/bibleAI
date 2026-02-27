/// DisclaimerView.swift — Onboarding disclaimer gate.
///
/// Must be accepted before any chat begins. Copy placeholder — final wording requires
/// Mental Health Advisor + Theology Advisor signoff (TASKS.md T012–T014).
import SwiftUI

struct DisclaimerView: View {
    let onAccept: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "book.closed.fill")
                .font(.system(size: 56))
                .foregroundColor(.accentColor)

            Text("Before You Begin")
                .font(.title.bold())

            VStack(alignment: .leading, spacing: 12) {
                DisclaimerPoint(
                    icon: "heart.text.square",
                    text: "This app offers scripture-based reflection, not professional therapy."
                )
                DisclaimerPoint(
                    icon: "cross.circle",
                    text: "It does not provide medical, psychiatric, or clinical advice."
                )
                DisclaimerPoint(
                    icon: "exclamationmark.triangle",
                    text: "If you are in crisis, please contact 988 (Suicide & Crisis Lifeline) or call 911."
                )
                DisclaimerPoint(
                    icon: "lock.shield",
                    text: "Your conversations are private and not used for training."
                )
            }
            .padding(.horizontal, 24)

            Spacer()

            // MARK: Get Help Now — persistent access per agent requirements
            GetHelpNowButton()
                .padding(.horizontal, 24)

            Button(action: onAccept) {
                Text("I Understand — Continue")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.accentColor)
                    .foregroundColor(.white)
                    .cornerRadius(12)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
        }
    }
}

// MARK: - Sub-components

private struct DisclaimerPoint: View {
    let icon: String
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .foregroundColor(.accentColor)
                .frame(width: 24)
            Text(text)
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
    }
}

struct GetHelpNowButton: View {
    @State private var showingResources = false

    var body: some View {
        Button(action: { showingResources = true }) {
            Label("Get Help Now", systemImage: "phone.circle.fill")
                .font(.subheadline.bold())
                .frame(maxWidth: .infinity)
                .padding(12)
                .background(Color.red.opacity(0.12))
                .foregroundColor(.red)
                .cornerRadius(10)
        }
        .sheet(isPresented: $showingResources) {
            CrisisResourcesSheet()
        }
    }
}

struct CrisisResourcesSheet: View {
    @Environment(\.dismiss) private var dismiss

    private let resources: [(label: String, contact: String)] = [
        ("988 Suicide & Crisis Lifeline", "Call or text 988"),
        ("Crisis Text Line", "Text HOME to 741741"),
        ("Emergency Services", "Call 911"),
    ]

    var body: some View {
        NavigationStack {
            List(resources, id: \.label) { resource in
                VStack(alignment: .leading, spacing: 4) {
                    Text(resource.label).font(.headline)
                    Text(resource.contact).font(.subheadline).foregroundColor(.secondary)
                }
                .padding(.vertical, 4)
            }
            .navigationTitle("Crisis Resources")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
