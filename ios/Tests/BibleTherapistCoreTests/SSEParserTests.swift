/// SSEParserTests.swift — Unit tests for SSEEventParser.
///
/// Tests parse(frame:) with well-formed and malformed SSE frames.
/// No URLSession or networking required.
///
/// Run with: swift test (from ios/)
import XCTest
@testable import BibleTherapistCore

final class SSEParserTests: XCTestCase {

    // MARK: - heartbeat

    func test_heartbeat_explicit_event_type() {
        var frame = RawSSEFrame()
        frame.event = "heartbeat"
        frame.data = "{}"

        let event = SSEEventParser.parse(frame: frame)
        guard case .heartbeat = event else {
            XCTFail("Expected .heartbeat, got \(String(describing: event))")
            return
        }
    }

    func test_heartbeat_empty_data_no_event() {
        // Bare frame with empty data and no event type → heartbeat
        var frame = RawSSEFrame()
        frame.data = ""  // isEmpty → nil parse result
        let event = SSEEventParser.parse(frame: frame)
        XCTAssertNil(event, "Empty frame should return nil")
    }

    func test_heartbeat_empty_json_no_event() {
        var frame = RawSSEFrame()
        frame.event = nil
        frame.data = "{}"
        let event = SSEEventParser.parse(frame: frame)
        guard case .heartbeat = event else {
            XCTFail("Expected .heartbeat for bare {} data, got \(String(describing: event))")
            return
        }
    }

    // MARK: - token.delta

    func test_tokenDelta_valid() {
        let msgId = UUID()
        let json = """
        {"message_id":"\(msgId.uuidString.lowercased())","delta":"Hello ","sequence":1}
        """
        var frame = RawSSEFrame()
        frame.event = "token.delta"
        frame.data = json

        let event = SSEEventParser.parse(frame: frame)
        guard case .tokenDelta(let payload) = event else {
            XCTFail("Expected .tokenDelta, got \(String(describing: event))")
            return
        }
        XCTAssertEqual(payload.messageId, msgId)
        XCTAssertEqual(payload.delta, "Hello ")
        XCTAssertEqual(payload.sequence, 1)
    }

    func test_tokenDelta_sequence_increments() {
        let msgId = UUID()
        var deltas: [TokenDeltaPayload] = []

        for seq in 1...5 {
            let json = """
            {"message_id":"\(msgId.uuidString.lowercased())","delta":"chunk\(seq)","sequence":\(seq)}
            """
            var frame = RawSSEFrame()
            frame.event = "token.delta"
            frame.data = json
            if case .tokenDelta(let p) = SSEEventParser.parse(frame: frame) {
                deltas.append(p)
            }
        }

        XCTAssertEqual(deltas.count, 5)
        XCTAssertEqual(deltas.map(\.sequence), [1, 2, 3, 4, 5])
        let assembled = deltas.map(\.delta).joined()
        XCTAssertEqual(assembled, "chunk1chunk2chunk3chunk4chunk5")
    }

    func test_tokenDelta_malformed_json_falls_back_to_unknown() {
        var frame = RawSSEFrame()
        frame.event = "token.delta"
        frame.data = "{not valid json}"

        let event = SSEEventParser.parse(frame: frame)
        guard case .unknown(let type, _) = event else {
            XCTFail("Malformed JSON should yield .unknown, got \(String(describing: event))")
            return
        }
        XCTAssertEqual(type, "token.delta")
    }

    // MARK: - message.final

    func test_messageFinal_valid() throws {
        let msgId = UUID()
        let sessionId = UUID()
        let now = ISO8601DateFormatter().string(from: Date())

        let json = """
        {
          "message_id": "\(msgId.uuidString.lowercased())",
          "session_id": "\(sessionId.uuidString.lowercased())",
          "text": "Here is a reflection.",
          "structured": {
            "reflection": "You are not alone.",
            "prayer": null,
            "next_step": null,
            "reflection_question": null
          },
          "citations": [],
          "risk": { "risk_level": "none", "categories": [], "action": "allow" },
          "model_version": "demo-v0",
          "created_at": "\(now)"
        }
        """
        var frame = RawSSEFrame()
        frame.event = "message.final"
        frame.data = json

        let event = SSEEventParser.parse(frame: frame)
        guard case .messageFinal(let payload) = event else {
            XCTFail("Expected .messageFinal, got \(String(describing: event))")
            return
        }
        XCTAssertEqual(payload.messageId, msgId)
        XCTAssertEqual(payload.sessionId, sessionId)
        XCTAssertEqual(payload.text, "Here is a reflection.")
        XCTAssertEqual(payload.structured.reflection, "You are not alone.")
        XCTAssertEqual(payload.risk.riskLevel, .none)
        XCTAssertEqual(payload.risk.action, .allow)
        XCTAssertTrue(payload.citations.isEmpty)
    }

    func test_messageFinal_with_citations() throws {
        let msgId = UUID()
        let verseId = UUID()
        let sessionId = UUID()
        let now = ISO8601DateFormatter().string(from: Date())

        let json = """
        {
          "message_id": "\(msgId.uuidString.lowercased())",
          "session_id": "\(sessionId.uuidString.lowercased())",
          "text": "Cast your anxiety on him.",
          "structured": { "reflection": "Trust in God.", "prayer": null, "next_step": null, "reflection_question": null },
          "citations": [
            {
              "translation_id": "NIV",
              "book": "1 Peter",
              "chapter": 5,
              "verse_start": 7,
              "verse_end": 7,
              "verse_id_list": ["\(verseId.uuidString.lowercased())"],
              "quote": "Cast all your anxiety on him because he cares for you."
            }
          ],
          "risk": { "risk_level": "low", "categories": [], "action": "caution" },
          "model_version": "demo-v0",
          "created_at": "\(now)"
        }
        """
        var frame = RawSSEFrame()
        frame.event = "message.final"
        frame.data = json

        let event = SSEEventParser.parse(frame: frame)
        guard case .messageFinal(let payload) = event else {
            XCTFail("Expected .messageFinal")
            return
        }
        XCTAssertEqual(payload.citations.count, 1)
        let citation = payload.citations[0]
        XCTAssertEqual(citation.translationId, .niv)
        XCTAssertEqual(citation.book, "1 Peter")
        XCTAssertEqual(citation.chapter, 5)
        XCTAssertEqual(citation.verseStart, 7)
        XCTAssertEqual(citation.verseEnd, 7)
        XCTAssertEqual(citation.verseIdList[0], verseId)
        XCTAssertEqual(citation.quote, "Cast all your anxiety on him because he cares for you.")
    }

    // MARK: - risk.interrupt

    func test_riskInterrupt_valid() {
        let json = """
        {
          "risk_level": "high",
          "action": "escalate",
          "categories": ["self_harm"],
          "message": "We hear that you are struggling.",
          "resources": [
            { "label": "988 Suicide & Crisis Lifeline", "contact": "Call or text 988" },
            { "label": "Crisis Text Line", "contact": "Text HOME to 741741" },
            { "label": "Emergency Services", "contact": "Call 911" }
          ],
          "requires_acknowledgment": true
        }
        """
        var frame = RawSSEFrame()
        frame.event = "risk.interrupt"
        frame.data = json

        let event = SSEEventParser.parse(frame: frame)
        guard case .riskInterrupt(let payload) = event else {
            XCTFail("Expected .riskInterrupt, got \(String(describing: event))")
            return
        }
        XCTAssertEqual(payload.riskLevel, .high)
        XCTAssertEqual(payload.action, .escalate)
        XCTAssertEqual(payload.categories, ["self_harm"])
        XCTAssertTrue(payload.requiresAcknowledgment)
        XCTAssertEqual(payload.resources.count, 3)
        XCTAssertEqual(payload.resources[0].label, "988 Suicide & Crisis Lifeline")
    }

    func test_riskInterrupt_without_acknowledgment_flag() {
        let json = """
        {
          "risk_level": "medium",
          "action": "caution",
          "categories": ["self_harm"],
          "message": "It sounds like you may be going through a difficult time.",
          "resources": [],
          "requires_acknowledgment": false
        }
        """
        var frame = RawSSEFrame()
        frame.event = "risk.interrupt"
        frame.data = json

        let event = SSEEventParser.parse(frame: frame)
        guard case .riskInterrupt(let payload) = event else {
            XCTFail("Expected .riskInterrupt")
            return
        }
        XCTAssertFalse(payload.requiresAcknowledgment)
        XCTAssertEqual(payload.riskLevel, .medium)
    }

    // MARK: - stream.error

    func test_streamError_retryable() {
        let json = """
        { "code": "llm_timeout", "message": "LLM call timed out.", "retryable": true }
        """
        var frame = RawSSEFrame()
        frame.event = "stream.error"
        frame.data = json

        let event = SSEEventParser.parse(frame: frame)
        guard case .streamError(let payload) = event else {
            XCTFail("Expected .streamError, got \(String(describing: event))")
            return
        }
        XCTAssertEqual(payload.code, "llm_timeout")
        XCTAssertTrue(payload.retryable)
    }

    func test_streamError_non_retryable() {
        let json = """
        { "code": "citation_integrity", "message": "Citation validation failed.", "retryable": false }
        """
        var frame = RawSSEFrame()
        frame.event = "stream.error"
        frame.data = json

        let event = SSEEventParser.parse(frame: frame)
        guard case .streamError(let payload) = event else {
            XCTFail("Expected .streamError")
            return
        }
        XCTAssertFalse(payload.retryable)
    }

    // MARK: - unknown event type

    func test_unknown_event_type_preserved() {
        var frame = RawSSEFrame()
        frame.event = "session.ended"
        frame.data = "{\"reason\":\"timeout\"}"

        let event = SSEEventParser.parse(frame: frame)
        guard case .unknown(let type, let data) = event else {
            XCTFail("Expected .unknown, got \(String(describing: event))")
            return
        }
        XCTAssertEqual(type, "session.ended")
        XCTAssertEqual(data, "{\"reason\":\"timeout\"}")
    }

    // MARK: - Empty / nil frame

    func test_nil_returns_nil_for_empty_frame() {
        let frame = RawSSEFrame()
        XCTAssertNil(SSEEventParser.parse(frame: frame))
    }
}
