# Safety Policy (v1)

## Disallowed Behaviors
- medical diagnosis/treatment advice
- encouraging self-harm or violence
- spiritual coercion ("God will punish you", fear-based threats)
- claiming divine authority or certainty about God's will for the user

## Crisis Handling (Deterministic)
If risk_level=high (self-harm, active abuse danger):
- bypass LLM generation
- return escalation template + resources
- block further chat until user acknowledges

## Citation Integrity
- No response returns scripture citations unless validated against verse corpus
- If validation fails → fallback: "I may be mistaken; here is a general reflection without citation" + log event

## Logging
Log:
- model name + version
- risk decision + categories + action
- citation IDs returned
Never log raw user content by default.