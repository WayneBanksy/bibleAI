/// MockSessionService.swift — Mock SessionServiceProtocol for DEV_PREVIEW mode.
///
/// Returns canned responses with simulated network delays.
/// Guarded by `#if DEBUG` — stripped entirely from Release builds.
#if DEBUG
import Foundation

public actor MockSessionService: SessionServiceProtocol {

    public init() {}

    public func createSession(
        mode: SessionMode,
        translationPreference: TranslationID,
        tonePreference: TonePreference
    ) async throws -> SessionResponse {
        try await Task.sleep(nanoseconds: 300_000_000) // 0.3s simulated latency
        return SessionResponse(
            sessionId: UUID(),
            mode: mode,
            translationPreference: translationPreference,
            tonePreference: tonePreference,
            createdAt: Date()
        )
    }

    public func sendMessage(
        sessionId: UUID,
        text: String,
        clientMessageId: UUID
    ) async throws -> MessageAccepted {
        try await Task.sleep(nanoseconds: 200_000_000) // 0.2s simulated latency
        return MessageAccepted(
            messageId: UUID(),
            clientMessageId: clientMessageId,
            sessionId: sessionId,
            status: "processing"
        )
    }

    public func submitReport(
        sessionId: UUID,
        messageId: UUID,
        reason: ReportReason,
        details: String?
    ) async throws -> ReportResponse {
        return ReportResponse(ok: true, reportId: UUID())
    }

    nonisolated public func sseURL(sessionId: UUID, lastEventId: String?) -> URL {
        URL(string: "http://localhost:0/mock-sse")!
    }

    nonisolated public func authHeaders() -> [String: String] {
        ["Authorization": "Bearer dev-preview-token"]
    }
}
#endif
