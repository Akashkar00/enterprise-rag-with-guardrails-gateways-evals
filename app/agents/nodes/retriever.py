import logfire
from app.agents.state import AgentState
from app.services.retrieval.qdrant_service import search_enterprise_knowledge, RetrievalError
from app.services.retrieval.ranking_service import rerank_documents


def retrieve_node(state: AgentState):
    """
    Performs vector search and semantic reranking for technical queries.

    Distinguishes two outcomes:
      - Success (including a legitimately EMPTY result set) -> retrieval_failed=False,
        flows to grade_documents (which decides rewrite / web search / generate).
      - Failure (DB error, timeout, embedding failure) -> retrieval_failed=True,
        so the graph can route to an honest failure handler instead of trying to
        grade/generate on garbage.
    """
    query = state["current_query"]

    with logfire.span("🔍 Knowledge Retrieval"):
        try:
            logfire.info(f"Searching Qdrant for: {query}")
            raw_results = search_enterprise_knowledge(query, limit=15)
            logfire.info(f"Retrieved {len(raw_results)} candidates from Vector DB")

            doc_contents = [doc["content"] for doc in raw_results]

            reranked_contents = []
            if doc_contents:
                with logfire.span("⚖️ Semantic Reranking"):
                    reranked_contents = rerank_documents(query, doc_contents, top_n=5)
                    logfire.info("Reranking complete. Kept top 5 most relevant chunks.")

            formatted_docs = [f"CONTENT: {doc}" for doc in reranked_contents]

        except (RetrievalError, Exception) as e:
            # Hard failure — do NOT fabricate context. Signal the graph to handle it.
            logfire.error(f"❌ Retrieval failed (routing to failure handler): {e}")
            return {
                "documents": [],
                "retrieval_failed": True,
                "status": "Knowledge base retrieval failed.",
                "plan": state["plan"] + ["Retrieval: ❌ FAILED (DB error/timeout)"],
            }

    return {
        "documents": formatted_docs,
        "retrieval_failed": False,
        "status": "Found technical context.",
        "plan": state["plan"] + ["Context Retrieved"],
    }
