import re
import logfire
from app.agents.state import AgentState


# ---------------------------------------------------------------------------
# Output Guardrails
#
# Final safety pass on the LLM's answer BEFORE it is returned to the user:
#   1. PII DETECTION   — redact emails, phone numbers, SSNs, credit cards, IPs
#                        that may have leaked from context or memory.
#   2. POLICY/TOXICITY — scan for disallowed / toxic content; if found, replace
#                        the answer with a safe refusal instead of leaking it.
#
# Rule-based on purpose: deterministic, zero added latency, no new dependencies.
# (Hallucination is already mitigated upstream by the grounding + rewrite loop
#  in grade_documents, so it is intentionally not re-checked here.)
# ---------------------------------------------------------------------------

# --- PII patterns --------------------------------------------------------------
PII_PATTERNS = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "PHONE": re.compile(
        r"(?<!\d)(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\d)"
    ),
    "IP_ADDRESS": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
}

# --- Toxicity / policy wordlist (minimal, illustrative; tune for your policy) --
TOXIC_TERMS = [
    r"\bkill\s+yourself\b",
    r"\bi\s+hate\s+you\b",
    r"\bslur\b",  # placeholder for a real slur list managed out-of-band
]
_TOXIC = [re.compile(p, re.IGNORECASE) for p in TOXIC_TERMS]

SAFE_REFUSAL = (
    "I'm sorry, but I can't provide that response as it may violate content policy. "
    "Please rephrase your request and I'll be glad to help."
)


def _redact_pii(text: str) -> tuple[str, list[str]]:
    """Replaces detected PII with typed placeholders. Returns (text, kinds_found)."""
    found = []
    for label, pattern in PII_PATTERNS.items():
        # CREDIT_CARD is greedy; require it to actually look card-like (>=13 digits).
        if label == "CREDIT_CARD":
            def _repl(m):
                digits = re.sub(r"\D", "", m.group(0))
                if 13 <= len(digits) <= 16:
                    found.append(label)
                    return f"[REDACTED_{label}]"
                return m.group(0)
            text = pattern.sub(_repl, text)
        else:
            if pattern.search(text):
                found.append(label)
                text = pattern.sub(f"[REDACTED_{label}]", text)
    return text, sorted(set(found))


def output_guard_node(state: AgentState):
    """
    Output Guardrails: PII redaction + policy/toxicity validation on the final
    answer. Runs after the responder, right before the graph ends.
    """
    answer = state.get("final_answer", "") or ""

    if not answer.strip():
        return {"plan": state["plan"] + ["Output Guardrails ✅ (empty answer, skipped)"]}

    with logfire.span("🛡️ Output Guardrails"):
        # 1. Policy / toxicity — block outright if violated.
        if any(rx.search(answer) for rx in _TOXIC):
            logfire.warning("🛡️ Output guard: policy/toxicity violation — replacing answer with safe refusal.")
            return {
                "final_answer": SAFE_REFUSAL,
                "messages": [{"role": "assistant", "content": SAFE_REFUSAL}],
                "plan": state["plan"] + ["Output Guardrails ✅ (policy violation → safe refusal)"],
                "status": "Output blocked by policy check.",
            }

        # 2. PII redaction.
        redacted, kinds = _redact_pii(answer)

    if kinds:
        logfire.warning(f"🛡️ Output guard: redacted PII types {kinds}.")
        return {
            "final_answer": redacted,
            # Overwrite the assistant message so persisted memory is also clean.
            "messages": [{"role": "assistant", "content": redacted}],
            "plan": state["plan"] + [f"Output Guardrails ✅ (redacted PII: {', '.join(kinds)})"],
            "status": "Output sanitized (PII redacted).",
        }

    logfire.info("🛡️ Output guard: clean — no PII or policy issues.")
    return {"plan": state["plan"] + ["Output Guardrails ✅ (clean)"]}
