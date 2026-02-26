/// StoreKitManager.swift — StoreKit 2 purchase + transaction management (P1-03).
///
/// Handles product loading, purchase flow, transaction observation, and restore.
/// Syncs verified transactions with the backend via APIClient.
import Foundation
import StoreKit

#if canImport(Combine)
import Combine

@MainActor
public final class StoreKitManager: ObservableObject {

    // MARK: - Published State

    @Published public private(set) var subscriptionProducts: [Product] = []
    @Published public private(set) var creditProducts: [Product] = []
    @Published public private(set) var isPurchasing: Bool = false
    @Published public private(set) var purchaseError: String?

    // MARK: - Private

    private let apiClient: APIClient
    private var transactionListener: Task<Void, Never>?

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
        transactionListener = listenForTransactions()
    }

    deinit {
        transactionListener?.cancel()
    }

    // MARK: - Load Products

    public func loadProducts() async {
        do {
            let products = try await Product.products(for: ProductIDs.allIDs)
            subscriptionProducts = products
                .filter { ProductIDs.subscriptionIDs.contains($0.id) }
                .sorted { $0.price < $1.price }
            creditProducts = products
                .filter { ProductIDs.creditIDs.contains($0.id) }
                .sorted { $0.price < $1.price }
        } catch {
            purchaseError = "Failed to load products: \(error.localizedDescription)"
        }
    }

    // MARK: - Purchase

    public func purchase(_ product: Product) async -> Bool {
        isPurchasing = true
        purchaseError = nil
        defer { isPurchasing = false }

        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                let transaction = try checkVerified(verification)
                await handleVerifiedTransaction(transaction, product: product)
                await transaction.finish()
                return true

            case .userCancelled:
                return false

            case .pending:
                purchaseError = "Purchase is pending approval."
                return false

            @unknown default:
                purchaseError = "Unexpected purchase result."
                return false
            }
        } catch {
            purchaseError = error.localizedDescription
            return false
        }
    }

    // MARK: - Restore Purchases

    public func restorePurchases() async {
        // Sync App Store transactions
        try? await AppStore.sync()

        // Process current entitlements (subscriptions only — credits are not re-redeemed)
        for await result in Transaction.currentEntitlements {
            guard let transaction = try? checkVerified(result) else { continue }

            if ProductIDs.subscriptionIDs.contains(transaction.productID) {
                await syncSubscriptionWithBackend(transaction)
            }
            // Note: credit consumables are NOT re-redeemed on restore (per spec)
        }
    }

    // MARK: - Transaction Listener

    private func listenForTransactions() -> Task<Void, Never> {
        Task.detached { [weak self] in
            for await result in Transaction.updates {
                guard let self else { return }
                if let transaction = try? Self.checkVerifiedStatic(result) {
                    await self.handleVerifiedTransaction(transaction, product: nil)
                    await transaction.finish()
                }
            }
        }
    }

    /// Non-isolated verification for use in detached tasks.
    private nonisolated static func checkVerifiedStatic(_ result: VerificationResult<StoreKit.Transaction>) throws -> StoreKit.Transaction {
        switch result {
        case .unverified(_, let error):
            throw error
        case .verified(let transaction):
            return transaction
        }
    }

    // MARK: - Backend Sync

    private func handleVerifiedTransaction(_ transaction: StoreKit.Transaction, product: Product?) async {
        let productId = transaction.productID

        if ProductIDs.subscriptionIDs.contains(productId) {
            await syncSubscriptionWithBackend(transaction)
        } else if ProductIDs.creditIDs.contains(productId) {
            await redeemCreditsWithBackend(transaction)
        }
    }

    private func syncSubscriptionWithBackend(_ transaction: StoreKit.Transaction) async {
        do {
            _ = try await apiClient.verifyIAP(
                productType: "subscription",
                productId: transaction.productID,
                transactionId: String(transaction.id),
                originalTransactionId: String(transaction.originalID),
                environment: transaction.environmentStringValue,
                signedTransactionJWS: nil
            )
        } catch {
            purchaseError = "Failed to sync subscription: \(error.localizedDescription)"
        }
    }

    private func redeemCreditsWithBackend(_ transaction: StoreKit.Transaction) async {
        do {
            _ = try await apiClient.redeemCredits(
                idempotencyKey: String(transaction.id),
                productId: transaction.productID,
                purchaseToken: String(transaction.id),
                purchasedAt: transaction.purchaseDate
            )
        } catch {
            purchaseError = "Failed to redeem credits: \(error.localizedDescription)"
        }
    }

    // MARK: - Verification

    private func checkVerified(_ result: VerificationResult<StoreKit.Transaction>) throws -> StoreKit.Transaction {
        switch result {
        case .unverified(_, let error):
            throw error
        case .verified(let transaction):
            return transaction
        }
    }
}

// MARK: - StoreKit.Transaction Environment Helper

private extension StoreKit.Transaction {
    var environmentStringValue: String {
        if environment == .sandbox { return "Sandbox" }
        return "Production"
    }
}
#endif
