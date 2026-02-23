/// SSEClient.swift — URLSession-based SSE stream consumer.
///
/// Architecture:
///   stream(url:headers:lastEventId:) → AsyncStream<Result<SSEEvent, SSEClientError>>
///
/// The caller receives typed SSEEvents and reconnects on failure.
/// Single-instance MVP: no Redis; state lives in process.
import Foundation

// MARK: - Errors

public enum SSEClientError: Error, Sendable, LocalizedError {
    case httpError(statusCode: Int)
    case connectionLost
    case cancelled

    public var errorDescription: String? {
        switch self {
        case .httpError(let code): return "SSE connection failed with HTTP \(code)."
        case .connectionLost: return "SSE connection lost."
        case .cancelled: return "SSE stream cancelled."
        }
    }
}

// MARK: - Client

/// Stateless SSE client. Create one per stream session; cancel via the AsyncStream's termination.
public final class SSEClient: Sendable {

    private let urlSession: URLSession

    public init(urlSession: URLSession = .shared) {
        self.urlSession = urlSession
    }

    /// Opens an SSE connection and returns a stream of typed events.
    ///
    /// The stream ends when:
    /// - The server closes the connection
    /// - The connection errors (yields `.failure` then finishes)
    /// - The caller cancels (via `onTermination`)
    public func stream(
        url: URL,
        headers: [String: String],
        lastEventId: String? = nil
    ) -> AsyncStream<Result<SSEEvent, SSEClientError>> {

        var request = URLRequest(url: url)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        for (key, value) in headers {
            request.setValue(value, forHTTPHeaderField: key)
        }
        if let lastEventId {
            request.setValue(lastEventId, forHTTPHeaderField: "Last-Event-ID")
        }

        let session = self.urlSession

        return AsyncStream { continuation in
            let task = Task {
                do {
                    let (asyncBytes, response) = try await session.bytes(for: request)

                    guard let httpResp = response as? HTTPURLResponse else {
                        continuation.yield(.failure(.httpError(statusCode: 0)))
                        continuation.finish()
                        return
                    }
                    guard httpResp.statusCode == 200 else {
                        continuation.yield(.failure(.httpError(statusCode: httpResp.statusCode)))
                        continuation.finish()
                        return
                    }

                    var frame = RawSSEFrame()

                    for try await line in asyncBytes.lines {
                        guard !Task.isCancelled else { break }

                        if line.isEmpty {
                            // Blank line = end of frame
                            if !frame.isEmpty, let event = SSEEventParser.parse(frame: frame) {
                                continuation.yield(.success(event))
                            }
                            frame.reset()
                            continue
                        }

                        // Comment lines
                        if line.hasPrefix(":") { continue }

                        // Field dispatch
                        if let value = fieldValue(line: line, field: "id") {
                            frame.id = value
                        } else if let value = fieldValue(line: line, field: "event") {
                            frame.event = value
                        } else if let value = fieldValue(line: line, field: "data") {
                            frame.data = frame.data.isEmpty ? value : frame.data + "\n" + value
                        }
                    }

                    continuation.finish()

                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.yield(.failure(.connectionLost))
                    continuation.finish()
                }
            }

            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

// MARK: - Helpers

/// Extract the value portion of an SSE field line.
/// Handles both "field: value" (with space) and "field:value" (no space).
private func fieldValue(line: String, field: String) -> String? {
    let prefix = "\(field):"
    guard line.hasPrefix(prefix) else { return nil }
    let remainder = line.dropFirst(prefix.count)
    // Strip a single leading space per SSE spec
    if remainder.first == " " {
        return String(remainder.dropFirst())
    }
    return String(remainder)
}
