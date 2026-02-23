/// APIClient.swift — REST networking layer matching INTERFACES.md v0.
///
/// All methods are async throws. Error types map 1:1 to INTERFACES.md §1.4 error codes.
import Foundation

// MARK: - Client Errors

public enum APIClientError: Error, Sendable, LocalizedError {
    case unauthenticated
    case forbidden
    case notFound
    case conflict(originalMessageId: UUID?)
    case validationError
    case rateLimited
    case serverError(String)
    case decodingError(Error)
    case networkError(Error)

    public var errorDescription: String? {
        switch self {
        case .unauthenticated:            return "Authentication required. Please sign in."
        case .forbidden:                  return "Access denied."
        case .notFound:                   return "Resource not found."
        case .conflict:                   return "Duplicate message — already processing."
        case .validationError:            return "Invalid request."
        case .rateLimited:                return "Too many requests. Please wait a moment."
        case .serverError(let msg):       return msg
        case .decodingError(let e):       return "Response parse error: \(e.localizedDescription)"
        case .networkError(let e):        return e.localizedDescription
        }
    }
}

// MARK: - Protocol (for testability)

/// Subset of APIClient used by ChatViewModel.
/// Allows MockAPIClient injection in unit tests.
public protocol SessionServiceProtocol: Sendable {
    func createSession(
        mode: SessionMode,
        translationPreference: TranslationID,
        tonePreference: TonePreference
    ) async throws -> SessionResponse

    func sendMessage(
        sessionId: UUID,
        text: String,
        clientMessageId: UUID
    ) async throws -> MessageAccepted

    func submitReport(
        sessionId: UUID,
        messageId: UUID,
        reason: ReportReason,
        details: String?
    ) async throws -> ReportResponse

    func sseURL(sessionId: UUID, lastEventId: String?) -> URL
    func authHeaders() -> [String: String]
}

// MARK: - APIClient

/// Thread-safe REST client. Auth token is updated via `setAuthToken` from the calling context.
/// This class is not an actor — callers must not share mutable state across threads.
public final class APIClient: SessionServiceProtocol, @unchecked Sendable {

    private let baseURL: URL
    private let urlSession: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    // Guarded by the @MainActor calling context (AuthStore / ChatViewModel)
    private var authToken: String?

    public init(baseURL: URL, urlSession: URLSession = .shared) {
        self.baseURL = baseURL
        self.urlSession = urlSession

        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601

        self.encoder = JSONEncoder()
        self.encoder.dateEncodingStrategy = .iso8601
        self.encoder.keyEncodingStrategy = .useDefaultKeys
    }

    public func setAuthToken(_ token: String?) {
        authToken = token
    }

    // MARK: - Auth

    public func exchangeToken(idToken: String) async throws -> TokenResponse {
        struct Body: Encodable {
            let grant_type = "apple_id_token"
            let id_token: String
        }
        return try await post(path: "/v1/auth/token", body: Body(id_token: idToken), requiresAuth: false)
    }

    // MARK: - Sessions

    public func createSession(
        mode: SessionMode,
        translationPreference: TranslationID = .niv,
        tonePreference: TonePreference = .reflective
    ) async throws -> SessionResponse {
        struct Body: Encodable {
            let mode: SessionMode
            let translation_preference: TranslationID
            let tone_preference: TonePreference
        }
        return try await post(
            path: "/v1/sessions",
            body: Body(mode: mode, translation_preference: translationPreference, tone_preference: tonePreference),
            expectedStatus: 201
        )
    }

    // MARK: - Messages

    public func sendMessage(
        sessionId: UUID,
        text: String,
        clientMessageId: UUID
    ) async throws -> MessageAccepted {
        struct Body: Encodable {
            let text: String
            let client_message_id: UUID
            let input_mode = "text"
        }
        let path = "/v1/sessions/\(sessionId.uuidString.lowercased())/messages"
        return try await post(path: path, body: Body(text: text, client_message_id: clientMessageId), expectedStatus: 202)
    }

    // MARK: - Safety Report

    public func submitReport(
        sessionId: UUID,
        messageId: UUID,
        reason: ReportReason,
        details: String? = nil
    ) async throws -> ReportResponse {
        struct Body: Encodable {
            let session_id: UUID
            let message_id: UUID
            let reason: ReportReason
            let details: String?
        }
        return try await post(
            path: "/v1/safety/report",
            body: Body(session_id: sessionId, message_id: messageId, reason: reason, details: details)
        )
    }

    // MARK: - SSE Helpers

    public func sseURL(sessionId: UUID, lastEventId: String? = nil) -> URL {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
        components.path = "/v1/sessions/\(sessionId.uuidString.lowercased())/events"
        if let lastEventId {
            components.queryItems = [URLQueryItem(name: "last_event_id", value: lastEventId)]
        }
        return components.url!
    }

    public func authHeaders() -> [String: String] {
        guard let token = authToken else { return [:] }
        return ["Authorization": "Bearer \(token)"]
    }

    // MARK: - Generic POST

    private func post<RequestBody: Encodable, ResponseBody: Decodable>(
        path: String,
        body: RequestBody,
        requiresAuth: Bool = true,
        expectedStatus: Int = 200
    ) async throws -> ResponseBody {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIClientError.networkError(URLError(.badURL))
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(UUID().uuidString, forHTTPHeaderField: "X-Request-ID")

        if requiresAuth, let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        do {
            request.httpBody = try encoder.encode(body)
        } catch {
            throw APIClientError.networkError(error)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await urlSession.data(for: request)
        } catch {
            throw APIClientError.networkError(error)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIClientError.networkError(URLError(.badServerResponse))
        }

        try throwIfHTTPError(statusCode: http.statusCode, data: data)

        do {
            return try decoder.decode(ResponseBody.self, from: data)
        } catch {
            throw APIClientError.decodingError(error)
        }
    }

    // MARK: - HTTP Error Mapping (INTERFACES.md §1.4)

    private func throwIfHTTPError(statusCode: Int, data: Data) throws {
        guard statusCode >= 400 else { return }

        switch statusCode {
        case 401:
            throw APIClientError.unauthenticated
        case 403:
            throw APIClientError.forbidden
        case 404:
            throw APIClientError.notFound
        case 409:
            // Extract original_message_id from the conflict detail
            struct ConflictDetail: Codable { let original_message_id: UUID? }
            struct ConflictWrapper: Codable { let detail: ConflictDetail? }
            let originalId = try? decoder.decode(ConflictWrapper.self, from: data).detail?.original_message_id
            throw APIClientError.conflict(originalMessageId: originalId)
        case 422:
            throw APIClientError.validationError
        case 429:
            throw APIClientError.rateLimited
        default:
            struct ErrorWrapper: Codable { let detail: APIErrorBody? }
            let message = (try? decoder.decode(ErrorWrapper.self, from: data))?.detail?.message
                ?? "Server error \(statusCode)"
            throw APIClientError.serverError(message)
        }
    }
}
