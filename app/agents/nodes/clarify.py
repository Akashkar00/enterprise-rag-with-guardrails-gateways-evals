import logfire
from app.agents.state import AgentState
from app.gateway import get_langchain_llm

llm = get_langchain_llm(feature="clarify")

CLARIFY_PROMPT = """
You are a helpful Technical Research Assistant. The user's request is ambiguous or
underspecified, so instead of guessing (which risks a confidently wrong answer), you must
ask a brief clarifying question.

CONVERSATION HISTORY:
{history}

LATEST USER MESSAGE:
"{user_msg}"

Write ONE short, friendly clarifying question that pinpoints the specific information you
need to help (e.g. which system/technology, what they're trying to achieve, or what error
they see). Do not attempt to answer the original question. Output only the clarifying question.
"""


def clarify_node(state: AgentState):
    """
    Human-in-the-loop escape hatch. Reached when the planner judges intent to be
    ambiguous / low-confidence. Instead of barreling into retrieval or a direct
    (possibly hallucinated) answer, we ask the user to clarify and end the turn.

    The clarifying question is returned as the answer and appended to history, so
    the user's next message is interpreted with this context (via the checkpointer).
    """
    user_msg = state["messages"][-1]["content"] if state["messages"] else ""

    history_str = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    with logfire.span("❓ Clarify User Intent"):
        prompt = CLARIFY_PROMPT.format(history=history_str, user_msg=user_msg)
        try:
            question = llm.invoke(prompt).content.strip()
        except Exception as e:
            logfire.warning(f"⚠️ Clarify generation failed, using generic prompt: {e}")
            question = (
                "Could you clarify what you'd like help with — which system or technology, "
                "and what you're trying to achieve?"
            )
        logfire.info("Asked user a clarifying question.")

    return {
        "final_answer": question,
        "status": "Awaiting user clarification.",
        "plan": state["plan"] + ["Clarify: asked user for more detail"],
        "messages": [{"role": "assistant", "content": question}],
    }
