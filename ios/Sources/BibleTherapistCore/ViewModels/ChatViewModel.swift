/// ChatViewModel.swift — State machine for a single chat session.
///
/// Implements T004 + T008:
///   - Session creation
///   - Message send with client_message_id (idempotency)
///   - SSE stream subscription
///   - token.delta accumulation into a streaming assistant draft
///   - message.final commit (replace draft with final payload)
///   - risk.interrupt detection → blocks input until acknowledged
///   - 409 conflict recovery (reconnect SSE, per INTERFACES.md §4)
import Foundation

#if canImport(Combine)
import Combine

@MainActor
public final class ChatViewModel: ObservableObject {

    // MARK: - Published State
    // Setters are `internal(set)` so @testable import can set state in unit tests.
    // Public getters allow SwiftUI views to observe changes.

    @Published public internal(set) var messages: [ChatMessage] = []
    @Published public internal(set) var isStreaming: Bool = false
    /// When true, the input bar and send button are disabled.
    @Published public internal(set) var inputBlocked: Bool = false
    /// Non-nil while a risk.interrupt modal should be shown.
    @Published public internal(set) var riskInterrupt: RiskInterruptPayload? = nil
    @Published public internal(set) var sessionId: UUID? = nil
    @Published public internal(set) var connectionState: ConnectionState = .disconnected
    @Published public var errorMessage: String? = nil

    public enum ConnectionState {
        case disconnected
        case connecting
        case connected
        case reconnecting
        case failed(String)
    }

    // MARK: - Private State

    /// Index into `messages` of the currently-streaming assistant draft.
    var currentDraftIndex: Int? = nil
    /// SSE event ID for reconnect (Last-Event-ID header).
    private var lastEventId: String? = nil
    /// Background task consuming the SSE stream.
    private var sseTask: Task<Void, Never>? = nil
    /// Tracks the client_message_id of the in-flight user message.
    private var pendingClientMessageId: UUID? = nil

    private let service: SessionServiceProtocol
    private let sseClient: SSEClient

    // MARK: - Init

    public init(service: SessionServiceProtocol, sseClient: SSEClient = SSEClient()) {
        self.service = service
        self.sseClient = sseClient
    }

    // MARK: - Session Lifecycle

    public func createSession(
        mode: SessionMode = .supportSession,
        translation: TranslationID = .niv,
        tone: TonePreference = .reflective
    ) async {
        do {
            let session = try await service.createSession(
                mode: mode,
                translationPreference: translation,
                tonePreference: tone
            )
            sessionId = session.sessionId
            await startSSEStream()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Send Message

    /// Sends a user message. Generates a fresh client_message_id per call.
    /// On 409 (duplicate), reconnects to SSE (message already processing).
    public func sendMessage(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let sessionId, !inputBlocked, !trimmed.isEmpty else { return }

        let clientMessageId = UUID()
        pendingClientMessageId = clientMessageId

        // Optimistically add user bubble
        let userMsg = ChatMessage(clientMessageId: clientMessageId, role: .user, text: trimmed)
        messages.append(userMsg)

        // Streaming placeholder for the assistant reply
        let draftMsg = ChatMessage(role: .assistant, text: "", isStreaming: true)
        messages.append(draftMsg)
        currentDraftIndex = messages.count - 1
        isStreaming = true

        do {
            let accepted = try await service.sendMessage(
                sessionId: sessionId,
                text: trimmed,
                clientMessageId: clientMessageId
            )
            // Tag draft with server-assigned message_id
            if let idx = currentDraftIndex {
                messages[idx].serverId = accepted.messageId
            }
        } catch APIClientError.conflict(let originalId) {
            // INTERFACES.md §4: 409 means message is already processing.
            // Update draft with the original server ID and reconnect to SSE.
            if let idx = currentDraftIndex, let originalId {
                messages[idx].serverId = originalId
            }
            await startSSEStream()
        } catch {
            // Retract the optimistic messages and surface the error.
            rollbackOptimisticMessages()
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Risk Interrupt Acknowledgement

    /// Call when the user dismisses the risk interrupt screen.
    /// Clears the blocking state and allows typing again.
    public func acknowledgeRiskInterrupt() {
        riskInterrupt = nil
        inputBlocked = false
        // Per INTERFACES.md §5: server decides if chat can continue; we allow typing.
    }

    // MARK: - SSE Stream Management

    public func startSSEStream() async {
        guard let sessionId else { return }
        sseTask?.cancel()
        connectionState = .connecting

        let url = service.sseURL(sessionId: sessionId, lastEventId: lastEventId)
        let headers = service.authHeaders()

        sseTask = Task { [weak self] in
            guard let self else { return }

            self.connectionState = .connected
            let stream = self.sseClient.stream(url: url, headers: headers, lastEventId: self.lastEventId)

            for await result in stream {
                guard !Task.isCancelled else { break }
                switch result {
                case .success(let event):
                    self.handle(event: event)
                case .failure(let error):
                    self.connectionState = .failed(error.localizedDescription)
                    // Brief back-off before reconnect
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                    if !Task.isCancelled {
                        self.connectionState = .reconnecting
                        await self.startSSEStream()
                    }
                    return
                }
            }
            self.connectionState = .disconnected
        }
    }

    public func stopSSEStream() {
        sseTask?.cancel()
        sseTask = nil
        connectionState = .disconnected
    }

    // MARK: - Event Handling (internal for @testable access in tests)

    func handle(event: SSEEvent) {
        switch event {
        case .heartbeat:
            break  // Keep-alive; no UI update needed.

        case .tokenDelta(let payload):
            handleTokenDelta(payload)

        case .messageFinal(let payload):
            handleMessageFinal(payload)

        case .riskInterrupt(let payload):
            handleRiskInterrupt(payload)

        case .streamError(let payload):
            handleStreamError(payload)

        case .unknown:
            break
        }
    }

    func handleTokenDelta(_ payload: TokenDeltaPayload) {
        if let idx = currentDraftIndex {
            messages[idx].text += payload.delta
        } else {
            // token.delta arrived before send() returned — create draft now
            let msg = ChatMessage(
                serverId: payload.messageId,
                role: .assistant,
                text: payload.delta,
                isStreaming: true
            )
            messages.append(msg)
            currentDraftIndex = messages.count - 1
            isStreaming = true
        }
    }

    func handleMessageFinal(_ payload: MessageFinalPayload) {
        if let idx = currentDraftIndex {
            // Commit draft: replace accumulated text with authoritative final text
            messages[idx].text = payload.text
            messages[idx].isStreaming = false
            messages[idx].serverId = payload.messageId
            messages[idx].citations = payload.citations
            messages[idx].risk = payload.risk
            messages[idx].structured = payload.structured
        } else {
            // No draft in progress (e.g. reconnect scenario)
            let msg = ChatMessage(
                serverId: payload.messageId,
                role: .assistant,
                text: payload.text,
                isStreaming: false,
                citations: payload.citations,
                risk: payload.risk,
                structured: payload.structured
            )
            messages.append(msg)
        }
        currentDraftIndex = nil
        isStreaming = false
        pendingClientMessageId = nil
    }

    func handleRiskInterrupt(_ payload: RiskInterruptPayload) {
        // No message.final will arrive — remove the streaming placeholder
        if let idx = currentDraftIndex {
            messages.remove(at: idx)
            currentDraftIndex = nil
        }
        isStreaming = false
        pendingClientMessageId = nil

        if payload.requiresAcknowledgment {
            inputBlocked = true
            riskInterrupt = payload
        }
    }

    func handleStreamError(_ payload: StreamErrorPayload) {
        if let idx = currentDraftIndex {
            messages.remove(at: idx)
            currentDraftIndex = nil
        }
        isStreaming = false
        errorMessage = payload.message

        if payload.retryable {
            Task { await self.startSSEStream() }
        }
    }

    // MARK: - Helpers

    private func rollbackOptimisticMessages() {
        // Remove streaming draft
        if let idx = currentDraftIndex {
            messages.remove(at: idx)
            currentDraftIndex = nil
        }
        // Remove the user message (added just before the draft)
        if !messages.isEmpty, messages.last?.role == .user {
            messages.removeLast()
        }
        isStreaming = false
        pendingClientMessageId = nil
    }
}
#endif
