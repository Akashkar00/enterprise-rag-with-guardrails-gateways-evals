import logfire
from app.agents.state import AgentState
from app.gateway import get_langchain_llm

llm = get_langchain_llm(feature="doc_grader")

MAX_RETRIES = 2

GRADE_PROMPT = """
You are a STRICT relevance grader for a retrieval system. Your job is to reject documents
that do not genuinely help answer the user's question. Be conservative: it is better to
return NONE than to pass through weakly-related or off-topic documents.

USER QUESTION:
"{question}"

RETRIEVED DOCUMENTS (numbered):
{numbered_docs}

A document is RELEVANT only if it contains specific, substantive information that directly
helps answer THIS question — the correct topic, entities, and concepts actually being asked
about. Mark a document NOT relevant if it:
  - is about a different subject that merely shares generic words,
  - only mentions the topic in passing without real information,
  - is vague, templated, or filler text that doesn't actually address the question.

If you are unsure whether a document is truly on-topic, treat it as NOT relevant.

Task:
Return ONLY the numbers of the genuinely relevant documents as a comma-separated list
(e.g. "1, 3"). If NONE of the documents genuinely help answer the question, return exactly
"NONE". Do not explain.
"""


def _truncate(doc: str, limit: int = 1500) -> str:
    return doc if len(doc) <= limit else doc[:limit] + " ...[truncated]"


def grade_documents_node(state: AgentState):
    """
    CRAG-style document grader: grades the RETRIEVED documents for relevance
    BEFORE generation, so irrelevant context never triggers a wasted LLM
    generation call.

    - Keeps only relevant documents and passes them to the responder.
    - If no documents are relevant and the retry budget remains, signals the
      graph to rewrite the query and retrieve again (needs_retry=True).
    - If the retry budget is exhausted with no relevant docs, lets generation
      proceed with empty context (responder produces a graceful "no info"
      answer).

    Uses a single batched LLM call to grade all documents at once (avoids the
    per-document rate-limiting seen with one-call-per-doc grading).
    """
    documents = state.get("documents", [])
    retry_count = state.get("retry_count", 0)

    # Grade against the original user question, not the (rewritten) search query.
    question = state["messages"][-1]["content"] if state["messages"] else state["current_query"]

    if not documents:
        logfire.info("No documents to grade.")
        # No docs at all: rewrite if budget remains, else escalate to web search.
        if retry_count < MAX_RETRIES:
            return {
                "documents": [],
                "plan": state["plan"] + ["Doc Grading: no documents retrieved → rewriting"],
                "status": "No documents retrieved.",
                "retry_count": retry_count + 1,
                "next_action": "rewrite",
            }
        return {
            "documents": [],
            "plan": state["plan"] + ["Doc Grading: no documents after retries → web search"],
            "status": "No documents in knowledge base — escalating to web search.",
            "next_action": "websearch",
        }

    numbered = "\n\n".join(f"[{i+1}] {_truncate(doc)}" for i, doc in enumerate(documents))

    with logfire.span("🧪 Grading Retrieved Documents (pre-generation)"):
        prompt = GRADE_PROMPT.format(question=question, numbered_docs=numbered)
        try:
            raw = llm.invoke(prompt).content.strip()
        except Exception as e:
            logfire.warning(f"⚠️ Doc grading failed — keeping all docs by default: {e}")
            raw = ", ".join(str(i + 1) for i in range(len(documents)))

        relevant_docs = []
        if raw.upper() != "NONE":
            for token in raw.replace(".", ",").split(","):
                token = token.strip()
                if token.isdigit():
                    idx = int(token) - 1
                    if 0 <= idx < len(documents):
                        relevant_docs.append(documents[idx])

        logfire.info(f"Doc grading: {len(relevant_docs)}/{len(documents)} documents relevant")

    # Relevant docs found → proceed to generation.
    if relevant_docs:
        return {
            "documents": relevant_docs,
            "plan": state["plan"] + [f"Doc Grading: {len(relevant_docs)}/{len(documents)} relevant → generating"],
            "status": f"Found {len(relevant_docs)} relevant document(s).",
            "next_action": "generate",
        }

    # No relevant docs, retry budget remains → rewrite query (assume phrasing issue).
    if retry_count < MAX_RETRIES:
        logfire.info(f"🔁 No relevant docs — rewriting query (attempt {retry_count + 1}/{MAX_RETRIES}).")
        return {
            "documents": [],
            "plan": state["plan"] + [f"Doc Grading: 0 relevant → rewriting ({retry_count + 1}/{MAX_RETRIES})"],
            "status": "No relevant documents — rewriting query...",
            "retry_count": retry_count + 1,
            "next_action": "rewrite",
        }

    # No relevant docs after retries → likely a knowledge gap, escalate to web search.
    logfire.warning(f"⚠️ No relevant docs after {retry_count} rewrites — escalating to web search.")
    return {
        "documents": [],
        "plan": state["plan"] + [f"Doc Grading: 0 relevant after {retry_count} rewrites → web search"],
        "status": "Knowledge gap — escalating to external web search.",
        "next_action": "websearch",
    }
