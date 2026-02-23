/// RiskInterruptView.swift — Full-screen crisis escalation modal.
///
/// Triggered when the SSE stream emits a `risk.interrupt` event with
/// requiresAcknowledgment=true. Blocks all chat input until acknowledged.
///
/// Copy is from the server payload (pre-approved template per SAFETY_POLICY.md §2.3).
/// The acknowledgment button re-enables the input bar.
import SwiftUI
import BibleTherapistCore

// RiskInterruptPayload must conform to Identifiable for .fullScreenCover(item:)
extension RiskInterruptPayload: Identifiable {
    public var id: String { message + categories.joined() }
}

struct RiskInterruptView: View {
    let payload: RiskInterruptPayload
    let onAcknowledge: () -> Void

    var body: some View {
        ZStack {
            // Background
            Color(.systemBackground).ignoresSafeArea()

            VStack(spacing: 0) {
                // Header band
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.white)
                    Text("Crisis Support")
                        .font(.headline)
                        .foregroundColor(.white)
                }
                .frame(maxWidth: .infinity)
                .padding(16)
                .background(Color.red)

                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        // Server-provided message (pre-approved template)
                        Text(payload.message)
                            .font(.body)
                            .padding()
                            .background(Color.red.opacity(0.07))
                            .cornerRadius(12)

                        // Crisis resources
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Immediate Resources")
                                .font(.headline)
                            ForEach(payload.resources, id: \.label) { resource in
                                ResourceRow(resource: resource)
                            }
                        }

                        // Acknowledgement
                        VStack(spacing: 12) {
                            Text("Please reach out to one of the resources above if you need immediate support.")
                                .font(.footnote)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)

                            Button(action: onAcknowledge) {
                                Text("I've noted the resources — Continue")
                                    .font(.subheadline.bold())
                                    .frame(maxWidth: .infinity)
                                    .padding(14)
                                    .background(Color.accentColor)
                                    .foregroundColor(.white)
                                    .cornerRadius(12)
                            }
                        }
                        .padding(.top, 8)
                    }
                    .padding(20)
                }
            }
        }
        // Prevent accidental dismiss by swipe
        .interactiveDismissDisabled(true)
    }
}

private struct ResourceRow: View {
    let resource: CrisisResource

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "phone.fill")
                .foregroundColor(.red)
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(resource.label).font(.subheadline.bold())
                Text(resource.contact).font(.subheadline).foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 6)
    }
}
