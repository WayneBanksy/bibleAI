/// MockSSEProvider.swift — Canned assistant responses for DEV_PREVIEW mode.
///
/// Provides contextual mock responses with scripture citations
/// that simulate real pipeline output.
/// Guarded by `#if DEBUG` — stripped entirely from Release builds.
#if DEBUG
import Foundation

public enum MockSSEProvider {

    public struct MockResponse: Sendable {
        public let text: String
        public let citations: [CitationPayload]
        public let structured: StructuredPayload
    }

    /// Returns a contextual mock response based on user input keywords.
    public static func response(for userText: String) -> MockResponse {
        let lower = userText.lowercased()

        if lower.contains("anxious") || lower.contains("anxiety") || lower.contains("worried") {
            return anxietyResponse
        } else if lower.contains("grateful") || lower.contains("thankful") || lower.contains("thank") {
            return gratitudeResponse
        } else if lower.contains("sad") || lower.contains("hurt") || lower.contains("pain") {
            return comfortResponse
        } else {
            return defaultResponse
        }
    }

    // MARK: - Canned Responses

    private static let verseId = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!

    private static let defaultResponse = MockResponse(
        text: """
        Thank you for sharing that with me. It takes courage to bring what's on \
        your heart into the open. Scripture reminds us that God is near to all who \
        call on Him.

        "Cast all your anxiety on him because he cares for you." — 1 Peter 5:7 (NIV)

        You might consider sitting with that verse for a moment and noticing what \
        comes up. What feels most alive in your heart right now?
        """,
        citations: [
            CitationPayload(
                translationId: .niv,
                book: "1 Peter",
                chapter: 5,
                verseStart: 7,
                verseEnd: 7,
                verseIdList: [verseId],
                quote: "Cast all your anxiety on him because he cares for you."
            )
        ],
        structured: StructuredPayload(
            reflection: "Thank you for sharing that with me. It takes courage to bring what's on your heart into the open. Scripture reminds us that God is near to all who call on Him.",
            prayer: "Lord, meet this person right where they are. Grant them peace and clarity as they seek Your presence. Amen.",
            nextStep: "Consider journaling about what you're feeling and bringing it before God in prayer tonight.",
            reflectionQuestion: "What feels most alive in your heart right now?"
        )
    )

    private static let anxietyResponse = MockResponse(
        text: """
        I hear that you're carrying some anxiety right now, and I want you to know \
        that's a very human experience. The psalmist knew it too.

        "When anxiety was great within me, your consolation brought me joy." \
        — Psalm 94:19 (NIV)

        You might consider taking a few slow breaths and reading that verse aloud. \
        Sometimes letting God's words fill the room changes how we feel in it.
        """,
        citations: [
            CitationPayload(
                translationId: .niv,
                book: "Psalms",
                chapter: 94,
                verseStart: 19,
                verseEnd: 19,
                verseIdList: [verseId],
                quote: "When anxiety was great within me, your consolation brought me joy."
            )
        ],
        structured: StructuredPayload(
            reflection: "I hear that you're carrying some anxiety right now, and I want you to know that's a very human experience. The psalmist knew it too.",
            prayer: "Father, calm the storm inside. Replace worry with Your peace that passes understanding. Amen.",
            nextStep: "Try a breathing prayer: inhale 'You are,' exhale 'with me.' Repeat for two minutes.",
            reflectionQuestion: "What is the anxiety trying to protect you from?"
        )
    )

    private static let gratitudeResponse = MockResponse(
        text: """
        What a beautiful place to be — noticing gratitude is itself a gift. \
        Scripture celebrates this posture of the heart.

        "Give thanks to the Lord, for he is good; his love endures forever." \
        — Psalm 107:1 (NIV)

        You might consider writing down three specific things you're thankful for \
        today. Naming them makes the gratitude more concrete and lasting.
        """,
        citations: [
            CitationPayload(
                translationId: .niv,
                book: "Psalms",
                chapter: 107,
                verseStart: 1,
                verseEnd: 1,
                verseIdList: [verseId],
                quote: "Give thanks to the Lord, for he is good; his love endures forever."
            )
        ],
        structured: StructuredPayload(
            reflection: "What a beautiful place to be — noticing gratitude is itself a gift. Scripture celebrates this posture of the heart.",
            prayer: "Thank You, Lord, for opening eyes to see Your goodness in the everyday. Amen.",
            nextStep: "Write down three specific things you're thankful for today.",
            reflectionQuestion: "What surprised you most about what you're grateful for?"
        )
    )

    private static let comfortResponse = MockResponse(
        text: """
        I'm sorry you're going through this. Pain is real, and God doesn't ask us \
        to pretend otherwise. The psalms of lament teach us that honest grief is \
        sacred ground.

        "The Lord is close to the brokenhearted and saves those who are crushed \
        in spirit." — Psalm 34:18 (NIV)

        You might consider letting yourself feel what you feel without judgment. \
        God is closer than you think, especially now.
        """,
        citations: [
            CitationPayload(
                translationId: .niv,
                book: "Psalms",
                chapter: 34,
                verseStart: 18,
                verseEnd: 18,
                verseIdList: [verseId],
                quote: "The Lord is close to the brokenhearted and saves those who are crushed in spirit."
            )
        ],
        structured: StructuredPayload(
            reflection: "I'm sorry you're going through this. Pain is real, and God doesn't ask us to pretend otherwise. The psalms of lament teach us that honest grief is sacred ground.",
            prayer: "Lord, be near to this hurting heart. Let them feel Your closeness in the midst of their pain. Amen.",
            nextStep: "Consider reading Psalm 34 in full tonight as a prayer of your own.",
            reflectionQuestion: "What would it look like to let God hold this pain with you?"
        )
    )
}
#endif
