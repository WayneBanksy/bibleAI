/// SSEEvent.swift — Typed SSE events matching INTERFACES.md §5.
import Foundation

// MARK: - Typed SSE Event

public enum SSEEvent: Sendable {
    /// Keepalive — sent every 15s. No data to display.
    case heartbeat
    /// A single streaming text chunk (sequence is monotonically increasing).
    case tokenDelta(TokenDeltaPayload)
    /// Final committed message after all token.delta events.
    case messageFinal(MessageFinalPayload)
    /// Crisis escalation. Blocks further input when requiresAcknowledgment=true.
    case riskInterrupt(RiskInterruptPayload)
    /// Server-side processing failure after 202 was already returned.
    case streamError(StreamErrorPayload)
    /// Unrecognised event type — logged, not surfaced to UI.
    case unknown(type: String, data: String)
}

// MARK: - Raw SSE Frame (intermediate parsing step)

/// Holds the raw fields from a single SSE frame (between blank-line delimiters).
public struct RawSSEFrame: Sendable {
    public var id: String?
    public var event: String?
    /// Multi-line data is joined with "\n" as per SSE spec.
    public var data: String = ""

    public var isEmpty: Bool {
        data.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && event == nil
            && id == nil
    }

    public mutating func reset() {
        id = nil
        event = nil
        data = ""
    }
}

// MARK: - SSE Frame → Typed Event

/// Pure stateless parser. Maps a RawSSEFrame to a typed SSEEvent.
/// Tests call this directly via @testable import.
public enum SSEEventParser {

    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    public static func parse(frame: RawSSEFrame) -> SSEEvent? {
        guard !frame.isEmpty else { return nil }

        let eventType = frame.event ?? ""
        let rawData = frame.data
        let dataBytes = rawData.data(using: .utf8) ?? Data()

        switch eventType {
        case "heartbeat":
            return .heartbeat
        case "" where rawData == "{}" || rawData.isEmpty:
            return .heartbeat

        case "token.delta":
            if let payload = try? decoder.decode(TokenDeltaPayload.self, from: dataBytes) {
                return .tokenDelta(payload)
            }
            return .unknown(type: eventType, data: rawData)

        case "message.final":
            if let payload = try? decoder.decode(MessageFinalPayload.self, from: dataBytes) {
                return .messageFinal(payload)
            }
            return .unknown(type: eventType, data: rawData)

        case "risk.interrupt":
            if let payload = try? decoder.decode(RiskInterruptPayload.self, from: dataBytes) {
                return .riskInterrupt(payload)
            }
            return .unknown(type: eventType, data: rawData)

        case "stream.error":
            if let payload = try? decoder.decode(StreamErrorPayload.self, from: dataBytes) {
                return .streamError(payload)
            }
            return .unknown(type: eventType, data: rawData)

        default:
            return .unknown(type: eventType, data: rawData)
        }
    }
}
