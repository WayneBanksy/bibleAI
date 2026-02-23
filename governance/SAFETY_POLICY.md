# Safety Policy (v1)

<!-- Contributors: ML Engineer, Mental Health Advisor, Theology Advisor
     Last updated: 2026-02-22
     Status: DRAFT — requires QA + all advisor signoff before ship-ready label -->

---

## 1. Safety Taxonomy

<!-- Owner: ML Engineer | Reviewed by: Mental Health Advisor, Theology Advisor -->

### 1.1 Risk Levels

| risk_level | Definition |
|------------|------------|
| `none` | No safety concern detected; proceed normally |
| `low` | Mild sensitive topic; content may proceed with standard reflective framing |
| `medium` | Sensitive topic requiring caution; output must avoid clinical or coercive language |
| `high` | Crisis or severe harm signal; LLM MUST be bypassed; deterministic escalation required |

### 1.2 Risk Categories

| Category | Description |
|----------|-------------|
| `self_harm` | Suicidal ideation (explicit or implicit), self-injurious behavior requests or disclosures |
| `abuse` | Disclosed abuse with immediate danger; domestic violence in acute phase |
| `medical_advice` | Requests for diagnosis, treatment plans, medication or supplement guidance |
| `hate` | Content targeting a person or group with dehumanizing language |
| `sexual` | Sexual content or requests; heightened concern involving minors |
| `violence` | Intent or instructions for harm to others |
| `spiritual_coercion` | Language that applies coercive religious framing: threats, shame spirals, divine certainty claims |
| `citation_integrity` | Model attempted to return an unvalidatable or fabricated scripture citation |

### 1.3 Action Mapping Table

| risk_level | categories (any matching) | action | server behavior |
|------------|--------------------------|--------|-----------------|
| `high` | `self_harm`, `abuse`, `violence` | `escalate` | Bypass LLM entirely; emit `risk.interrupt`; block chat until user acknowledges |
| `medium` | `self_harm`, `abuse` | `caution` | Proceed with LLM; inject safety framing via system prompt; no clinical language permitted in output |
| `medium` | `medical_advice` | `refuse` | Return deterministic refusal template; do not invoke LLM for content |
| `medium` | `spiritual_coercion` | `refuse` | Block output; return safe reframe template (see §4.2) |
| `low` | any | `allow` | Proceed; log safety event |
| `none` | — | `allow` | Proceed normally; no event logged |
| any | `citation_integrity` | (log only) | Strip the invalid citation; fallback to uncited reflection; log `safety_event` |

**Non-negotiable rule:** `action=escalate` MUST bypass the LLM. No exceptions permitted in any environment including development.

### 1.4 Classifier Output Schema

The pre-check and post-check classifiers must return a `SafetyCheckResult` (full JSON schema in INTERFACES.md §8). Summary:

```json
{
  "risk_level": "none | low | medium | high",
  "categories": ["self_harm", "..."],
  "action": "allow | caution | refuse | escalate",
  "rationale_codes": ["SH_EXPLICIT", "..."]
}
```

Rationale codes are short audit strings. Raw user text must never appear in rationale codes.

---

## 2. Crisis Handling (Deterministic Bypass)

<!-- Owner: Mental Health Advisor -->

### 2.1 Crisis Definitions

A message triggers `action=escalate` if any of the following signals are detected:

| Trigger Type | Example signals |
|---|---|
| **Explicit suicidal ideation** | "I want to kill myself", "I'm thinking about ending it", "I want to die" |
| **Implicit suicidal ideation** | "Everyone would be better off without me", "I won't be here much longer", "I've said my goodbyes" |
| **Imminent self-harm intent** | "I'm going to hurt myself tonight", "I have pills in front of me", "I already cut myself and it's bad" |
| **Acute abuse / immediate danger** | "He's hitting me right now", "I'm not safe at home tonight", "I'm afraid for my life" |
| **Request for self-harm methods** | Any explicit request for methods to cause self-harm or suicide |

**Classification principle:** Err toward escalation. Near-zero false negatives required. A false positive (escalation shown unnecessarily) is always preferable to a false negative (crisis missed). When in doubt, escalate.

### 2.2 Deterministic Bypass Requirements

When `action=escalate`:

1. Do NOT invoke the LLM under any circumstance.
2. Do NOT generate a reflection, prayer, or scripture citation.
3. Emit the `risk.interrupt` SSE event immediately (see INTERFACES.md §5).
4. The `message` field in `risk.interrupt` MUST come from a pre-approved, versioned server-side template (see D009 in DECISIONS.md).
5. The iOS client MUST display a blocking acknowledgment screen. The user cannot type until they acknowledge.
6. Log a `safety_event` with `check_stage=pre`, `action=escalate`, and the crisis template version.

### 2.3 Approved Crisis Response Components

Every `risk.interrupt` message template MUST include ALL of the following:

- Acknowledgment that the user is going through something painful or difficult.
- Clear statement that this app is NOT a substitute for professional help or emergency services.
- At minimum, these three resources:
  - **988 Suicide & Crisis Lifeline:** Call or text 988 (US)
  - **Crisis Text Line:** Text HOME to 741741
  - **Emergency Services:** Call 911 (or local emergency number)
- Encouragement to reach out to a trusted person or licensed professional.
- An option for the user to indicate they are safe (to allow chat to resume if appropriate).

**Approved template (v1 — requires Mental Health Advisor written signoff before production use):**

> "It sounds like you're going through something really painful right now. I'm not a crisis counselor or emergency service — please reach out to someone who can help. You can contact the **988 Suicide & Crisis Lifeline** (call or text 988), the **Crisis Text Line** (text HOME to 741741), or call **911** if you or someone else is in immediate danger. Talking to a trusted person or licensed professional can make a real difference. Are you safe right now?"

### 2.4 Post-Crisis Chat Resumption

After the user acknowledges the crisis screen:

- Chat may resume ONLY if the user has indicated they are safe.
- The next assistant message must NOT pick up the conversation as if nothing happened.
- The next assistant message should begin with a grounding, compassionate, non-clinical check-in (from a template, not LLM-free-generated).
- Log a second `safety_event` with `check_stage=post` to mark the resumption.

---

## 3. Prohibited Clinical Language

<!-- Owner: Mental Health Advisor -->

The post-check classifier MUST flag any assistant output containing the following. If flagged, `action=refuse` and the output is blocked.

### 3.1 Prohibited Diagnoses

- Asserting the user has any mental health condition: "You have depression", "You sound like you have anxiety disorder", "This looks like PTSD", "You may be bipolar".
- Any diagnostic framing: "Based on what you're describing, you might be experiencing..."
- Armchair assessment language, even softened: "It sounds like you could be dealing with clinical anxiety."

### 3.2 Prohibited Treatment Guidance

- Recommending specific therapeutic modalities: "You should try CBT", "EMDR might help with this."
- Suggesting the user see a specialist type for their specific condition: "You should see a trauma therapist."
- Medication guidance: "You should stop taking / start taking [medication or supplement]."
- Any personalized treatment recommendation of any kind.

### 3.3 Prohibited Crisis Delay Patterns

- Using prayer, scripture, or spiritual content as the SOLE directive in response to an active crisis signal.
- Minimizing severity: "Everyone feels that way sometimes", "I'm sure things will look better tomorrow."
- Delaying help-seeking: "Let's explore this more before calling anyone", "Maybe you don't need professional help."
- Framing prayer as a substitute for crisis resources when the user has signaled acute distress.

### 3.4 Allowed Clinical-Adjacent Language

These ARE permitted:

- "Speaking with a licensed counselor or therapist can be very helpful."
- "A mental health professional can offer personalized support."
- Generic encouragement to seek professional help, without specifying type, modality, or treatment.
- Acknowledging emotional pain with compassion without diagnosing.

---

## 4. Spiritual Coercion: Prohibited Patterns and Reframes

<!-- Owner: Theology Advisor -->

### 4.1 Prohibited Patterns

The following categories of language are prohibited in any assistant output. The post-check classifier must detect and block these.

| Pattern Type | Examples |
|---|---|
| **Divine punishment threats** | "God will punish you if...", "This suffering is because of your sin", "God is angry at you" |
| **Coercive commands with divine authority** | "God is telling you to...", "You must do X or God will...", "The Bible commands you to..." (used prescriptively against user's will) |
| **Shame spirals** | "You are unworthy of God's love", "You are unclean", "You are a sinner beyond redemption" |
| **Divine certainty claims about user outcomes** | "God told me you will be healed", "God's plan for you is definitely...", "This is happening because God wants you to..." |
| **Spiritual gaslighting** | "Your doubt means you don't really believe", "If you had enough faith, you wouldn't feel this way" |
| **Proof-texting in trauma contexts** | Using scripture out of context to dismiss, minimize, or explain away grief, abuse, mental illness, or trauma |

### 4.2 Required Reframes

When output risks coercion, replace with grace-based, invitational framing:

| Instead of | Use |
|---|---|
| "God is punishing you" | "Many people find comfort in exploring what scripture says about suffering and God's presence in pain." |
| "You must have more faith" | "Doubt and struggle are part of many people's faith journeys; scripture has space for lament." |
| "God told me..." | "Scripture offers..." or "One perspective from this tradition is..." |
| Shame-based language | Compassion-centered, grace-based framing |
| Prescriptive spiritual commands | Invitational language: "Some find it helpful to...", "You might explore..." |
| "Just pray and it will get better" (as sole directive in crisis) | Combine spiritual support with concrete resources; prayer does not replace crisis help |

### 4.3 Doctrinal Neutrality Requirement

- By default, the assistant MUST NOT make denomination-specific prescriptions (no assertions about specific church practices, sacraments, or interpretations as definitive truth).
- If the user expresses a specific denominational preference, the assistant may gently reflect that tradition's perspective while noting diversity of views.
- The assistant MUST NOT endorse one denomination or tradition over another.

### 4.4 Scripture Usage Rules

- Scripture must be used contextually and appropriately for the user's stated situation.
- Do not use scripture to dismiss, gaslight, or spiritualize away mental health struggles, abuse, or trauma.
- Proof-texting (lifting a verse out of context to make a point the passage does not support) is prohibited.
- Prefer psalms of lament and grace-centered passages for users in distress over prescriptive or judgment-focused texts.

---

## 5. Citation Integrity Policy

<!-- Owner: ML Engineer + Backend Engineer | Theology Advisor reviewed -->

### 5.1 Hard Rules

- No scripture citation may appear in an assistant response unless it has been validated against the `bible_verses` table (matching `translation_id`, `book`, `chapter`, `verse`).
- The text hash of the stored verse must match what the model returned.
- If validation fails: strip the citation, return an uncited reflection, log `citation_integrity` in `safety_events`.
- The client MUST NEVER receive an unvalidated citation.

### 5.2 Paraphrase Policy

- Paraphrases may NOT be presented as direct quotes (see DECISIONS.md D006).
- If a paraphrase appears in `reflection` prose, it must be labeled inline: *"Paraphrase of [Book Chapter:Verse]"*.
- Paraphrases must NOT appear in the `verse_block` field or the `citations` array in `message.final`.
- Default behavior: if uncertain about exact verse text, omit the citation entirely and reflect without quoting.

### 5.3 Citation Fallback Copy

When a citation is stripped due to validation failure, the assistant must use this fallback:

> "I may not have the exact verse reference available; here is a reflection on this theme without a specific citation."

---

## 6. Disallowed Behaviors (Summary)

- Medical diagnosis or treatment advice of any kind
- Encouraging self-harm, violence, or abuse
- Spiritual coercion: threats, shame spirals, divine certainty claims, proof-texting in trauma contexts
- Claiming divine authority or certainty about a specific user's situation or outcome
- Fabricating or guessing scripture citations
- Presenting paraphrases as direct scripture quotes
- Using prayer/scripture as the sole response to an active crisis signal
- Delaying help-seeking in crisis situations
- Storing raw user text in plaintext logs

---

## 7. Logging Requirements

Log for every turn (raw user content must NEVER appear in logs):

- `model_name` and `model_version`
- `risk_level`, `categories`, `action` — from both pre-check and post-check stages
- `rationale_codes` from safety classifier
- `citation_ids` returned (references to `bible_verses.id`)
- `session_id`, `message_id`, `request_id`
- If escalated: crisis template version used

---

## 8. Devotional Snippet Corpus Guidelines

<!-- Owner: Theology Advisor -->

### 8.1 Topics Allowed Without Additional Review

- Encouragement, hope, peace, gratitude
- Grief, loss, loneliness
- Forgiveness, restoration
- Purpose, meaning, calling
- Prayer, faith, trust

### 8.2 Topics Requiring Additional Review Before Corpus Inclusion

The following topics require review by both the Theology Advisor and Mental Health Advisor before a devotional snippet is added to the RAG corpus:

- Suicide, self-harm, depression
- Domestic abuse, sexual abuse, trauma
- Mental illness and psychological suffering
- Sexuality and gender identity
- Death, hell, eternal judgment
- Addiction and recovery

### 8.3 Snippet Review Criteria

Before any snippet is added to the corpus, it must:

- Be sourced from a reputable devotional author or be original and reviewed content.
- Not contain coercive language, shame-based framing, or prescriptive clinical guidance.
- Use scripture contextually and accurately.
- Be doctrinal-neutral (avoid denomination-specific prescriptions).
- Be reviewed and approved by the Theology Advisor (and Mental Health Advisor for sensitive topics).

---

## 9. Open Items Requiring Signoff

| Item | Owner | Blocker for Ship? |
|------|-------|-------------------|
| Crisis template v1 written signoff | Mental Health Advisor | YES |
| Devotional snippet review for sensitive topics | Theology + Mental Health | YES |
| Post-crisis resumption template | Mental Health Advisor | YES |
| Eval harness gold set (100-200 examples) | ML Engineer | YES |
| Encryption key management strategy | Backend Engineer | YES |
