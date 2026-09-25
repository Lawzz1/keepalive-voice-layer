"""Deterministic check on every sentence the Voice Agent wants to say.

Mirror of docs/agent-spec.md, section 4. The system prompt asks the agent to
behave; this enforces it before anything reaches the speaker. A replaced answer
is not an error — it is the agent's mistake caught, so log it and fix the prompt.
"""

import re
from dataclasses import dataclass

CLOSING = "Keep pushing to the beat."
FALLBACK_ACTIVE = "Keep pushing to the beat. Emergency services will guide you."
FALLBACK_AFTER = "The paramedics are in charge now. Take a slow, deep breath."
MAX_WORDS_ACTIVE = 18   # including the closing
MAX_SENTENCES_AFTER = 3

# Never, in any state.
FORBIDDEN_ALWAYS = [
    (r"\b\d+(\.\d+)?\s?(mg|milligrams?|ml|milliliters?|mcg|micrograms?|units?)\b", "dose"),
    (r"\b(he|she|they)('s| is| are)? (dead|gone)\b|\bcan'?t be saved\b", "death"),
    (r"\b(don'?t|do not|no need to)( need to| have to)? (call|contact)\b", "dont_call"),
]
# While CPR is running: the engine alone decides about compressions.
FORBIDDEN_ACTIVE = [
    (r"\b(stop|pause|rest|slow)\b.*\b(compress\w*|push\w*|cpr|pump\w*)", "stop_compressions"),
    (r"\bcheck\b.*\bpulse\b", "pulse_check"),
    (r"\b(water|drink|aspirin|pills?)\b", "by_mouth"),
]
# "Don't stop pushing" is exactly what we want to hear; take it out before the stop rule.
ALLOWED_STOP = r"\b(do not|don'?t|never) stop\b"


@dataclass
class GateResult:
    text: str
    action: str      # passed | closing_added | trimmed | replaced
    reason: str = ""


def gate(text: str, protocol_state: str = "active") -> GateResult:
    # "briefing" is the EMS handover report read to the paramedics: machine-built
    # from the incident log, not conversation. The forbidden phrases still apply,
    # but the three-sentence cap does not — trimming it drops clinical facts.
    if protocol_state == "briefing":
        clean = " ".join(text.split())
        if not clean:
            return GateResult(FALLBACK_AFTER, "replaced", "empty")
        for pattern, reason in FORBIDDEN_ALWAYS:
            if re.search(pattern, clean, re.I):
                return GateResult(FALLBACK_AFTER, "replaced", reason)
        return GateResult(clean, "passed")

    active = protocol_state == "active"
    fallback = FALLBACK_ACTIVE if active else FALLBACK_AFTER
    clean = " ".join(text.split())
    if not clean:
        return GateResult(fallback, "replaced", "empty")

    rules = FORBIDDEN_ALWAYS + (FORBIDDEN_ACTIVE if active else [])
    probe = re.sub(ALLOWED_STOP, "", clean, flags=re.I)
    for pattern, reason in rules:
        if re.search(pattern, probe, re.I):
            return GateResult(fallback, "replaced", reason)

    if not active:
        sentences = re.findall(r"[^.!?]+[.!?]*", clean)
        if len(sentences) > MAX_SENTENCES_AFTER:
            return GateResult(" ".join(s.strip() for s in sentences[:MAX_SENTENCES_AFTER]), "trimmed", "too_many_sentences")
        return GateResult(clean, "passed")

    action = "passed"
    if not clean.endswith(CLOSING):
        clean = f"{clean} {CLOSING}"
        action = "closing_added"
    if len(clean.split()) > MAX_WORDS_ACTIVE:
        return GateResult(FALLBACK_ACTIVE, "replaced", "too_long")
    return GateResult(clean, action)
