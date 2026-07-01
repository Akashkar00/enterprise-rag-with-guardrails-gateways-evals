import os
import logfire
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agents.state import AgentState
from app.agents.nodes.planner import planner_node
from app.agents.nodes.retriever import retrieve_node
from app.agents.nodes.grade_documents import grade_documents_node
from app.agents.nodes.rewriter import rewrite_node
from app.agents.nodes.web_search import web_search_node
from app.agents.nodes.clarify import clarify_node
from app.agents.nodes.retrieval_failure import retrieval_failure_node
from app.agents.nodes.responder import generate_node


# --- Graph definition ---
workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_node)
workflow.add_node("retriever", retrieve_node)
workflow.add_node("grade_documents", grade_documents_node)
workflow.add_node("rewriter", rewrite_node)
workflow.add_node("web_search", web_search_node)
workflow.add_node("clarify_user", clarify_node)
workflow.add_node("handle_retrieval_failure", retrieval_failure_node)
workflow.add_node("responder", generate_node)


def route_planner(state: AgentState):
    # Three-way intent routing, with a human-in-the-loop escape for ambiguity.
    intent = state["current_query"]
    if intent == "CLARIFY":
        return "clarify_user"
    if intent == "CONVERSATIONAL":
        return "responder"
    return "retriever"


workflow.set_entry_point("planner")
workflow.add_conditional_edges(
    "planner",
    route_planner,
    {
        "clarify_user": "clarify_user",
        "responder": "responder",
        "retriever": "retriever",
    },
)
workflow.add_edge("clarify_user", END)

# Retriever can fail (DB error / timeout) — route to an honest failure handler
# instead of forcing grading/generation on empty context.
def route_after_retrieval(state: AgentState):
    if state.get("retrieval_failed"):
        return "handle_retrieval_failure"
    return "grade_documents"


workflow.add_conditional_edges(
    "retriever",
    route_after_retrieval,
    {"handle_retrieval_failure": "handle_retrieval_failure", "grade_documents": "grade_documents"},
)
workflow.add_edge("handle_retrieval_failure", END)


def route_grade_documents(state: AgentState):
    # Three-way routing based on the grader's failure-type assessment:
    #   rewrite   -> phrasing issue, re-query the same corpus
    #   websearch -> knowledge gap, go to an external source
    #   generate  -> relevant docs found
    action = state.get("next_action", "generate")
    if action == "rewrite":
        return "rewriter"
    if action == "websearch":
        return "web_search"
    return "responder"


workflow.add_conditional_edges(
    "grade_documents",
    route_grade_documents,
    {"rewriter": "rewriter", "web_search": "web_search", "responder": "responder"},
)
workflow.add_edge("rewriter", "retriever")
workflow.add_edge("web_search", "responder")
workflow.add_edge("responder", END)


# --- Checkpointer: Postgres in cloud, MemorySaver locally ---
def _build_checkpointer():
    """
    LOCAL_MODE=true  → MemorySaver (default, no DB needed)
    LOCAL_MODE=false → PostgresSaver backed by Cloud SQL
                       Falls back to MemorySaver if connection fails.
    """
    local_mode = os.getenv("LOCAL_MODE", "true").lower() == "true"

    if local_mode:
        logfire.info("🧠 Checkpointer: MemorySaver (LOCAL_MODE=true)")
        return MemorySaver()

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from app.services.gcp.database_service import get_db_pool

        pool = get_db_pool()
        if pool is None:
            logfire.warning("⚠️ Postgres pool unavailable — falling back to MemorySaver")
            return MemorySaver()

        checkpointer = PostgresSaver(pool)
        checkpointer.setup()  # creates checkpoint tables on first run
        logfire.info("✅ Checkpointer: PostgresSaver (persistent memory)")
        return checkpointer

    except Exception as e:
        logfire.error(f"❌ PostgresSaver init failed, using MemorySaver: {e}")
        return MemorySaver()


checkpointer = _build_checkpointer()
rag_agent = workflow.compile(checkpointer=checkpointer)
