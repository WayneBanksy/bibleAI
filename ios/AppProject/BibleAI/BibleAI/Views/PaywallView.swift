/// PaywallView.swift — In-app purchase paywall UI (P1-03).
///
/// Shows Free vs Plus comparison, subscription CTAs, credit packs, and restore.
/// Presented as a sheet when the backend returns 402 PAYWALL_REQUIRED.
import SwiftUI
import StoreKit
import BibleTherapistCore

#if canImport(Combine)

public struct PaywallView: View {

    @ObservedObject var storeKit: StoreKitManager
    @ObservedObject var entitlements: EntitlementsStore

    let reason: String?
    let onDismiss: () -> Void

    public init(
        storeKit: StoreKitManager,
        entitlements: EntitlementsStore,
        reason: String? = nil,
        onDismiss: @escaping () -> Void
    ) {
        self.storeKit = storeKit
        self.entitlements = entitlements
        self.reason = reason
        self.onDismiss = onDismiss
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    headerSection
                    featureComparison
                    subscriptionSection
                    creditSection
                    restoreSection
                }
                .padding()
            }
            .navigationTitle("Upgrade")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { onDismiss() }
                }
            }
            .task {
                await storeKit.loadProducts()
            }
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(spacing: 8) {
            if let reason {
                Text(reasonText(reason))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
        }
    }

    // MARK: - Feature Comparison

    private var featureComparison: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Free")
                .font(.headline)
            Text("3 sessions per week")
                .font(.subheadline).foregroundStyle(.secondary)

            Divider()

            Text("Plus")
                .font(.headline)
            VStack(alignment: .leading, spacing: 4) {
                Label("WWJD devotional mode", systemImage: "book.fill")
                Label("More daily sessions", systemImage: "message.fill")
                Label("Priority support", systemImage: "star.fill")
            }
            .font(.subheadline)
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Subscriptions

    private var subscriptionSection: some View {
        VStack(spacing: 12) {
            Text("Subscribe to Plus")
                .font(.headline)

            if storeKit.subscriptionProducts.isEmpty {
                ProgressView()
            } else {
                ForEach(storeKit.subscriptionProducts, id: \.id) { product in
                    Button {
                        Task {
                            let success = await storeKit.purchase(product)
                            if success {
                                await entitlements.refresh()
                                onDismiss()
                            }
                        }
                    } label: {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(product.displayName)
                                    .font(.body.bold())
                                Text(product.description)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(product.displayPrice)
                                .font(.body.bold())
                        }
                        .padding()
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain)
                    .disabled(storeKit.isPurchasing)
                }
            }
        }
    }

    // MARK: - Credits

    private var creditSection: some View {
        VStack(spacing: 12) {
            Text("Or Buy Credits")
                .font(.headline)
            Text("Use credits for individual sessions")
                .font(.caption)
                .foregroundStyle(.secondary)

            if storeKit.creditProducts.isEmpty {
                ProgressView()
            } else {
                ForEach(storeKit.creditProducts, id: \.id) { product in
                    Button {
                        Task {
                            let success = await storeKit.purchase(product)
                            if success {
                                await entitlements.refresh()
                                onDismiss()
                            }
                        }
                    } label: {
                        HStack {
                            Text(product.displayName)
                                .font(.body)
                            Spacer()
                            Text(product.displayPrice)
                                .font(.body.bold())
                        }
                        .padding()
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain)
                    .disabled(storeKit.isPurchasing)
                }
            }
        }
    }

    // MARK: - Restore

    private var restoreSection: some View {
        VStack(spacing: 8) {
            Button("Restore Purchases") {
                Task {
                    await storeKit.restorePurchases()
                    await entitlements.refresh()
                }
            }
            .font(.footnote)
            .foregroundStyle(.secondary)

            if let err = storeKit.purchaseError {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    // MARK: - Helpers

    private func reasonText(_ reason: String) -> String {
        switch reason {
        case "FREE_QUOTA_EXCEEDED":
            return "You've used all your free sessions this week."
        case "PLUS_DAILY_QUOTA_EXCEEDED":
            return "You've reached your daily session limit."
        case "PLUS_WEEKLY_QUOTA_EXCEEDED":
            return "You've reached your weekly session limit."
        default:
            return "Upgrade to continue."
        }
    }
}
#endif
