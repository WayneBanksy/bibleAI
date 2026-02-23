/// ChatViewModelTests.swift — State transition tests for ChatViewModel.
///
/// Uses MockSessionService (no network) and injects SSE events directly
/// via the internal handler methods exposed via @testable import.
///
/// Run with: swift test (from ios/)
import XCTest
@testable import BibleTherapistCore

// MARK: - Mock

/// Minimal mock service. All methods succeed with fixture data by default.
actor MockSessionService: SessionServiceProtocol {

    // Configurable return values
    var sessionResult: Result<SessionResponse, Error> = .success(.fixture())
    var sendResult: Result<MessageAccepted, Error> = .success(.fixture())
    var reportResult: Result<ReportResponse, Error> = .success(.fixture())

    nonisolated func sseURL(sessionId: UUID, lastEventId: String?) -> URL {
        URL(string: "http://localhost:8000/v1/sessions/\(sessionId)/events")!
    }

    nonisolated func authHeaders() -> [String: String] {
        ["Authorization": "Bearer test-token"]
    }

    func createSession(mode: SessionMode, translationPreference: TranslationID, tonePreference: TonePreference) async throws -> SessionResponse {
        try sessionResult.get()
    }

    func sendMessage(sessionId: UUID, text: String, clientMessageId: UUID) async throws -> MessageAccepted {
        try sendResult.get()
    }

    func submitReport(sessionId: UUID, messageId: UUID, reason: ReportReason, details: String?) async throws -> ReportResponse {
        try reportResult.get()
    }
}

// MARK: - Fixtures

extension SessionResponse {
    static func fixture(id: UUID = UUID()) -> SessionResponse {
        SessionResponse(
            sessionId: id,
            mode: .supportSession,
            translationPreference: .niv,
            tonePreference: .reflective,
            createdAt: Date()
        )
    }
}

extension MessageAccepted {
    static func fixture(messageId: UUID = UUID(), clientId: UUID = UUID(), sessionId: UUID = UUID()) -> MessageAccepted {
        MessageAccepted(
            messageId: messageId,
            clientMessageId: clientId,
            sessionId: sessionId,
            status: "processing"
        )
    }
}

extension ReportResponse {
    static func fixture() -> ReportResponse {
        ReportResponse(ok: true, reportId: UUID())
    }
}

// MARK: - Tests

@MainActor
final class ChatViewModelTests: XCTestCase {

    // MARK: - token.delta accumulation

    func test_tokenDelta_accumulates_into_draft() async {
        let vm = ChatViewModel(service: MockSessionService())

        // Inject a streaming assistant draft manually
        let msgId = UUID()
        let draft = ChatMessage(serverId: msgId, role: .assistant, text: "", isStreaming: true)
        vm.messages.append(draft)
        vm.currentDraftIndex = 0

        let deltas = ["Hello", " ", "world", "!"]
        for (seq, delta) in deltas.enumerated() {
            let payload = TokenDeltaPayload(messageId: msgId, delta: delta, sequence: seq + 1)
            vm.handleTokenDelta(payload)
        }

        XCTAssertEqual(vm.messages[0].text, "Hello world!")
        XCTAssertTrue(vm.messages[0].isStreaming, "Draft should still be streaming until message.final")
    }

    func test_tokenDelta_creates_draft_when_none_exists() async {
        let vm = ChatViewModel(service: MockSessionService())
        XCTAssertNil(vm.currentDraftIndex)

        let msgId = UUID()
        let payload = TokenDeltaPayload(messageId: msgId, delta: "Hi", sequence: 1)
        vm.handleTokenDelta(payload)

        XCTAssertEqual(vm.messages.count, 1)
        XCTAssertEqual(vm.messages[0].text, "Hi")
        XCTAssertTrue(vm.messages[0].isStreaming)
        XCTAssertNotNil(vm.currentDraftIndex)
    }

    // MARK: - message.final commit

    func test_messageFinal_commits_draft() async {
        let vm = ChatViewModel(service: MockSessionService())
        let sessionId = UUID()
        let msgId = UUID()

        // Establish draft via token
        let draft = ChatMessage(serverId: msgId, role: .assistant, text: "Hello", isStreaming: true)
        vm.messages.append(draft)
        vm.currentDraftIndex = 0
        vm.isStreaming = true // set directly for test

        let payload = makeMessageFinalPayload(msgId: msgId, sessionId: sessionId, text: "Hello world")
        vm.handleMessageFinal(payload)

        let committed = vm.messages[0]
        XCTAssertEqual(committed.text, "Hello world", "Final text should replace draft text")
        XCTAssertFalse(committed.isStreaming, "isStreaming should be false after message.final")
        XCTAssertEqual(committed.serverId, msgId)
        XCTAssertFalse(vm.isStreaming)
        XCTAssertNil(vm.currentDraftIndex)
    }

    func test_messageFinal_appends_when_no_draft() async {
        let vm = ChatViewModel(service: MockSessionService())
        let sessionId = UUID()
        let msgId = UUID()

        let payload = makeMessageFinalPayload(msgId: msgId, sessionId: sessionId, text: "Final")
        vm.handleMessageFinal(payload)

        XCTAssertEqual(vm.messages.count, 1)
        XCTAssertEqual(vm.messages[0].text, "Final")
        XCTAssertFalse(vm.messages[0].isStreaming)
    }

    func test_messageFinal_attaches_citations() async {
        let vm = ChatViewModel(service: MockSessionService())
        let msgId = UUID()
        let sessionId = UUID()
        let verseId = UUID()

        let citation = CitationPayload(
            translationId: .esv,
            book: "Psalm",
            chapter: 23,
            verseStart: 1,
            verseEnd: 1,
            verseIdList: [verseId],
            quote: "The Lord is my shepherd"
        )

        let payload = MessageFinalPayload(
            messageId: msgId,
            sessionId: sessionId,
            text: "God guides you.",
            structured: StructuredPayload(reflection: "God guides you.", prayer: nil, nextStep: nil, reflectionQuestion: nil),
            citations: [citation],
            risk: RiskPayload(riskLevel: .none, categories: [], action: .allow),
            modelVersion: "demo-v0",
            createdAt: Date()
        )

        vm.handleMessageFinal(payload)

        XCTAssertEqual(vm.messages[0].citations.count, 1)
        XCTAssertEqual(vm.messages[0].citations[0].book, "Psalm")
        XCTAssertEqual(vm.messages[0].citations[0].quote, "The Lord is my shepherd")
    }

    // MARK: - risk.interrupt

    func test_riskInterrupt_blocks_input_and_removes_draft() async {
        let vm = ChatViewModel(service: MockSessionService())

        // Add a user message + streaming draft
        let userMsg = ChatMessage(role: .user, text: "I feel hopeless")
        let draft = ChatMessage(role: .assistant, text: "", isStreaming: true)
        vm.messages = [userMsg, draft]
        vm.currentDraftIndex = 1
        vm.isStreaming = true

        let payload = RiskInterruptPayload(
            riskLevel: .high,
            action: .escalate,
            categories: ["self_harm"],
            message: "We hear that you are struggling.",
            resources: [CrisisResource(label: "988", contact: "Call or text 988")],
            requiresAcknowledgment: true
        )

        vm.handleRiskInterrupt(payload)

        XCTAssertTrue(vm.inputBlocked, "Input must be blocked after risk.interrupt")
        XCTAssertNotNil(vm.riskInterrupt, "riskInterrupt payload must be set")
        XCTAssertFalse(vm.isStreaming)
        XCTAssertNil(vm.currentDraftIndex)
        // Draft removed; only user message remains
        XCTAssertEqual(vm.messages.count, 1)
        XCTAssertEqual(vm.messages[0].role, .user)
    }

    func test_acknowledgeRiskInterrupt_unblocks_input() async {
        let vm = ChatViewModel(service: MockSessionService())
        vm.inputBlocked = true
        let payload = RiskInterruptPayload(
            riskLevel: .high,
            action: .escalate,
            categories: ["self_harm"],
            message: "We hear that you are struggling.",
            resources: [],
            requiresAcknowledgment: true
        )
        vm.riskInterrupt = payload

        vm.acknowledgeRiskInterrupt()

        XCTAssertFalse(vm.inputBlocked, "Input must be unblocked after acknowledgement")
        XCTAssertNil(vm.riskInterrupt, "riskInterrupt must be cleared")
    }

    func test_riskInterrupt_without_acknowledgment_does_not_block() async {
        let vm = ChatViewModel(service: MockSessionService())

        let payload = RiskInterruptPayload(
            riskLevel: .medium,
            action: .refuse,
            categories: ["medical_advice"],
            message: "I can't help with that.",
            resources: [],
            requiresAcknowledgment: false
        )

        vm.handleRiskInterrupt(payload)

        XCTAssertFalse(vm.inputBlocked)
        XCTAssertNil(vm.riskInterrupt)
    }

    // MARK: - stream.error

    func test_streamError_removes_draft_and_sets_error() async {
        let vm = ChatViewModel(service: MockSessionService())
        let draft = ChatMessage(role: .assistant, text: "partial", isStreaming: true)
        vm.messages = [draft]
        vm.currentDraftIndex = 0
        vm.isStreaming = true

        let payload = StreamErrorPayload(code: "internal_error", message: "Something went wrong.", retryable: false)
        vm.handleStreamError(payload)

        XCTAssertEqual(vm.messages.count, 0)
        XCTAssertFalse(vm.isStreaming)
        XCTAssertEqual(vm.errorMessage, "Something went wrong.")
        XCTAssertNil(vm.currentDraftIndex)
    }

    // MARK: - End-to-end token accumulation + commit

    func test_full_streaming_flow() async {
        let vm = ChatViewModel(service: MockSessionService())
        let msgId = UUID()
        let sessionId = UUID()

        // Sequence: 3 token.delta events → message.final
        vm.handleTokenDelta(TokenDeltaPayload(messageId: msgId, delta: "Peace ", sequence: 1))
        vm.handleTokenDelta(TokenDeltaPayload(messageId: msgId, delta: "be ", sequence: 2))
        vm.handleTokenDelta(TokenDeltaPayload(messageId: msgId, delta: "with you.", sequence: 3))

        // Draft should have accumulated text
        guard let idx = vm.currentDraftIndex else {
            XCTFail("Expected currentDraftIndex to be set")
            return
        }
        XCTAssertEqual(vm.messages[idx].text, "Peace be with you.")
        XCTAssertTrue(vm.messages[idx].isStreaming)

        // Commit
        let final = makeMessageFinalPayload(msgId: msgId, sessionId: sessionId, text: "Peace be with you.")
        vm.handleMessageFinal(final)

        XCTAssertEqual(vm.messages.count, 1)
        XCTAssertEqual(vm.messages[0].text, "Peace be with you.")
        XCTAssertFalse(vm.messages[0].isStreaming)
        XCTAssertFalse(vm.isStreaming)
    }
}

// MARK: - Helpers

private func makeMessageFinalPayload(msgId: UUID, sessionId: UUID, text: String) -> MessageFinalPayload {
    MessageFinalPayload(
        messageId: msgId,
        sessionId: sessionId,
        text: text,
        structured: StructuredPayload(reflection: text, prayer: nil, nextStep: nil, reflectionQuestion: nil),
        citations: [],
        risk: RiskPayload(riskLevel: .none, categories: [], action: .allow),
        modelVersion: "demo-v0",
        createdAt: Date()
    )
}
