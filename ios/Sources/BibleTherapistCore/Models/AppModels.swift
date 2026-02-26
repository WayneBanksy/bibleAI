/// AppModels.swift — Domain types matching INTERFACES.md v0.
/// All Codable types use snake_case ↔ camelCase mapping via CodingKeys.
import Foundation

// MARK: - Primitive Enums

public enum TranslationID: String, Codable, CaseIterable, Sendable {
    case esv = "ESV"
    case niv = "NIV"
    case kjv = "KJV"
    case nkjv = "NKJV"
    case nlt = "NLT"
    case csb = "CSB"
}

public enum SessionMode: String, Codable, Sendable {
    case supportSession = "support_session"
    case guidedProgram = "guided_program"
    case bibleReference = "bible_reference"
    case prayerBuilder = "prayer_builder"
}

public enum TonePreference: String, Codable, Sendable {
    case reflective
    case encouraging
    case neutral
}

public enum RiskLevel: String, Codable, Sendable {
    case none
    case low
    case medium
    case high
}

public enum SafetyAction: String, Codable, Sendable {
    case allow
    case caution
    case refuse
    case escalate
}

public enum ReportReason: String, Codable, Sendable {
    case inappropriate
    case incorrectScripture = "incorrect_scripture"
    case harmful
    case other
}

// MARK: - Auth

public struct TokenResponse: Codable, Sendable {
    public let accessToken: String
    public let tokenType: String
    public let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
    }
}

// MARK: - Session

public struct SessionResponse: Codable, Sendable {
    public let sessionId: UUID
    public let mode: SessionMode
    public let translationPreference: TranslationID
    public let tonePreference: TonePreference
    public let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case mode
        case translationPreference = "translation_preference"
        case tonePreference = "tone_preference"
        case createdAt = "created_at"
    }
}

// MARK: - Messages

public struct MessageAccepted: Codable, Sendable {
    public let messageId: UUID
    public let clientMessageId: UUID
    public let sessionId: UUID
    public let status: String

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case clientMessageId = "client_message_id"
        case sessionId = "session_id"
        case status
    }
}

// MARK: - SSE Structured Payloads (also used in message.final)

public struct StructuredPayload: Codable, Sendable {
    public let reflection: String
    public let prayer: String?
    public let nextStep: String?
    public let reflectionQuestion: String?

    enum CodingKeys: String, CodingKey {
        case reflection
        case prayer
        case nextStep = "next_step"
        case reflectionQuestion = "reflection_question"
    }
}

public struct CitationPayload: Codable, Sendable {
    public let translationId: TranslationID
    public let book: String
    public let chapter: Int
    public let verseStart: Int
    public let verseEnd: Int
    public let verseIdList: [UUID]
    public let quote: String

    enum CodingKeys: String, CodingKey {
        case translationId = "translation_id"
        case book
        case chapter
        case verseStart = "verse_start"
        case verseEnd = "verse_end"
        case verseIdList = "verse_id_list"
        case quote
    }
}

public struct RiskPayload: Codable, Sendable {
    public let riskLevel: RiskLevel
    public let categories: [String]
    public let action: SafetyAction

    enum CodingKeys: String, CodingKey {
        case riskLevel = "risk_level"
        case categories
        case action
    }
}

public struct MessageFinalPayload: Codable, Sendable {
    public let messageId: UUID
    public let sessionId: UUID
    public let text: String
    public let structured: StructuredPayload
    public let citations: [CitationPayload]
    public let risk: RiskPayload
    public let modelVersion: String
    public let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case sessionId = "session_id"
        case text
        case structured
        case citations
        case risk
        case modelVersion = "model_version"
        case createdAt = "created_at"
    }
}

public struct TokenDeltaPayload: Codable, Sendable {
    public let messageId: UUID
    public let delta: String
    public let sequence: Int

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case delta
        case sequence
    }
}

public struct CrisisResource: Codable, Sendable {
    public let label: String
    public let contact: String
}

public struct RiskInterruptPayload: Codable, Sendable {
    public let riskLevel: RiskLevel
    public let action: SafetyAction
    public let categories: [String]
    public let message: String
    public let resources: [CrisisResource]
    public let requiresAcknowledgment: Bool

    enum CodingKeys: String, CodingKey {
        case riskLevel = "risk_level"
        case action
        case categories
        case message
        case resources
        case requiresAcknowledgment = "requires_acknowledgment"
    }
}

public struct StreamErrorPayload: Codable, Sendable {
    public let code: String
    public let message: String
    public let retryable: Bool
}

// MARK: - Safety Report

public struct ReportResponse: Codable, Sendable {
    public let ok: Bool
    public let reportId: UUID

    enum CodingKeys: String, CodingKey {
        case ok
        case reportId = "report_id"
    }
}

// MARK: - Entitlements (P1-01)

public struct EntitlementsSnapshot: Codable, Sendable {
    public let subscriptionTier: String
    public let subscriptionStatus: String
    public let subscriptionExpiresAt: String?
    public let wwjdEnabled: Bool
    public let creditsBalance: Int
    public let freeSessionsRemaining: Int?
    public let plusSessionsRemainingToday: Int?
    public let plusSessionsRemainingWeek: Int?
    public let canStartSessionNow: Bool
    public let nextResetAt: String?
    public let blockingReason: String?

    enum CodingKeys: String, CodingKey {
        case subscriptionTier = "subscription_tier"
        case subscriptionStatus = "subscription_status"
        case subscriptionExpiresAt = "subscription_expires_at"
        case wwjdEnabled = "wwjd_enabled"
        case creditsBalance = "credits_balance"
        case freeSessionsRemaining = "free_sessions_remaining"
        case plusSessionsRemainingToday = "plus_sessions_remaining_today"
        case plusSessionsRemainingWeek = "plus_sessions_remaining_week"
        case canStartSessionNow = "can_start_session_now"
        case nextResetAt = "next_reset_at"
        case blockingReason = "blocking_reason"
    }
}

public struct EntitlementsResponse: Codable, Sendable {
    public let entitlements: EntitlementsSnapshot
}

// MARK: - Credits (P1-02)

public struct RedeemCreditsResponse: Codable, Sendable {
    public let creditsBalance: Int
    public let added: Int

    enum CodingKeys: String, CodingKey {
        case creditsBalance = "credits_balance"
        case added
    }
}

// MARK: - IAP Verification (P1-04)

public struct IAPVerifyResponse: Codable, Sendable {
    public let entitlements: EntitlementsSnapshot
    public let verified: Bool
}

// MARK: - Error

public struct APIErrorBody: Codable, Sendable {
    public let code: String
    public let message: String
}

// MARK: - Local Chat Message (client-side model)

public enum MessageRole: String, Sendable {
    case user
    case assistant
}

public struct ChatMessage: Identifiable, Sendable {
    public let id: UUID                     // stable SwiftUI identity
    public var serverId: UUID?              // message_id from server
    public let clientMessageId: UUID?       // idempotency key (user messages only)
    public let role: MessageRole
    public var text: String                 // accumulates token.delta chunks
    public var isStreaming: Bool            // true while streaming tokens
    public var citations: [CitationPayload]
    public var risk: RiskPayload?
    public var structured: StructuredPayload?

    public init(
        id: UUID = UUID(),
        serverId: UUID? = nil,
        clientMessageId: UUID? = nil,
        role: MessageRole,
        text: String = "",
        isStreaming: Bool = false,
        citations: [CitationPayload] = [],
        risk: RiskPayload? = nil,
        structured: StructuredPayload? = nil
    ) {
        self.id = id
        self.serverId = serverId
        self.clientMessageId = clientMessageId
        self.role = role
        self.text = text
        self.isStreaming = isStreaming
        self.citations = citations
        self.risk = risk
        self.structured = structured
    }
}
