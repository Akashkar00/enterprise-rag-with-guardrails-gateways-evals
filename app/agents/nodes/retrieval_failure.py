import logfire
from app.agents.state import AgentState

FAILURE_MESSAGE = (
    "I'm currently unable to access the knowledge base (the search service may be "
    "timing out or unavailable). Rather than guess and risk giving you an incorrect "
    "answer, I'd rather be upfront: I don't have the information to answer this right now. "
    "Please try again in a moment."
)


def retrieval_failure_node(state: AgentState):
    """
    Honest terminal handler for retrieval failures (DB error / timeout).

    Reached only when the retriever signals `retrieval_failed`. Returns a clear
    "insufficient info" message instead of forcing the pipeline to grade/generate
    on empty context — which would otherwise risk a confidently hallucinated answer.
    """
    logfire.warning("🛑 Handling retrieval failure — returning honest 'insufficient info' response.")
    return {
        "final_answer": FAILURE_MESSAGE,
        "status": "Retrieval failure — returned honest fallback (no hallucination).",
        "plan": state["plan"] + ["Handled retrieval failure: insufficient info"],
        "messages": [{"role": "assistant", "content": FAILURE_MESSAGE}],
    }
