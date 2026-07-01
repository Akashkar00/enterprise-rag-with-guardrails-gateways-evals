import logfire
from app.agents.state import AgentState
from app.gateway import get_langchain_llm

llm = get_langchain_llm(feature="rewriter")

REWRITE_PROMPT = """
You are a search query optimizer for a vector-database retrieval system.

The previous search query did not retrieve documents that could ground a good answer.
Rewrite it into a better search query: try different terminology, synonyms, broader or more
specific phrasing, and key technical terms that are likely to appear in relevant documents.

ORIGINAL USER QUESTION:
"{user_question}"

PREVIOUS SEARCH QUERY (did not work well):
"{previous_query}"

Output ONLY the improved search query text, nothing else.
"""


def rewrite_node(state: AgentState):
    """
    Reformulates the search query after a failed grounding check, so that the
    next retrieval attempt actually differs from the previous one (otherwise
    the corrective loop would re-fetch identical documents).

    Updates `current_query`, which the retriever reads on its next pass.
    """
    previous_query = state["current_query"]

    # Anchor rewrites to what the user actually asked.
    user_question = state["messages"][-1]["content"] if state["messages"] else previous_query

    with logfire.span("✍️ Query Rewrite"):
        prompt = REWRITE_PROMPT.format(
            user_question=user_question,
            previous_query=previous_query,
        )
        try:
            new_query = llm.invoke(prompt).content.strip().strip('"')
        except Exception as e:
            logfire.warning(f"⚠️ Query rewrite failed, keeping previous query: {e}")
            new_query = previous_query

        logfire.info(f"🔄 Rewrote query: '{previous_query}' -> '{new_query}'")

    return {
        "current_query": new_query,
        "status": f"Rewrote search query: {new_query}",
        "plan": state["plan"] + [f"Query Rewrite: {new_query}"],
    }
