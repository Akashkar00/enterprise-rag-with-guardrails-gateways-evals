# ============================================================
# CRITICAL: logfire MUST be configured before ALL other imports
# so that spans from all modules are captured from the start.
# ============================================================
import logfire
import os
from dotenv import load_dotenv

load_dotenv()
logfire.configure(token=os.getenv("LOGFIRE_TOKEN"))

# Now safe to import app modules
from fastapi import FastAPI, Response
from langgraph.errors import GraphRecursionError
from app.agents.graph import rag_agent
from app.guardrails import initialize_rails, guard

from pydantic import BaseModel
from typing import Optional

# Hard backstop against runaway loops (grader → rewriter → retriever cycle).
# The grader's MAX_RETRIES (2) is the primary, graceful cap; this recursion
# limit is a secondary safety net in case that counter logic ever fails.
# Legitimate worst case (2 retries) is ~12 super-steps; 20 leaves margin.
GRAPH_RECURSION_LIMIT = 20


app = FastAPI(title="Enterprise Agentic RAG API")


@app.on_event("startup")
def startup_event():
    initialize_rails()


class QueryRequest(BaseModel):
    q: str
    thread_id: Optional[str] = "default_user"


@app.get("/")
def home():
    return {"message": "Enterprise LangGraph RAG API is live."}


@app.get("/graph")
def get_graph_image():
    try:
        png_bytes = rag_agent.get_graph().draw_mermaid_png()
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        return {"error": f"Could not generate graph image: {e}"}


@app.post("/query")
def query(request: QueryRequest):
    q = request.q
    thread_id = request.thread_id

    initial_state = {
        "messages": [{"role": "user", "content": q}],
        "current_query": q,
        "documents": [],
        "plan": ["Start"],
        "status": "Initializing Graph...",
        "retry_count": 0,
    }
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": GRAPH_RECURSION_LIMIT,
    }

    try:
        # Gate 1: NeMo Guardrails — blocks off-topic / jailbreaks
        rail_fired, rail_response = guard(q)
        if rail_fired:
            logfire.info(f"🛡️ Request blocked by guardrails | thread={thread_id}")
            return {
                "question": q,
                "answer": rail_response,
                "thought_process": ["Intent: Guardrails Fired", "Retrieval: Skipped"],
                "status": "Blocked by guardrails.",
                "sources": [],
            }

        # Gate 2: Semantic Cache — serve instantly if a similar query was answered before
        if os.getenv("USE_SEMANTIC_CACHE", "false").lower() == "true":
            try:
                from app.services.gcp.redis_semantic_cache import check_cache
                cached = check_cache(q)
                if cached:
                    logfire.info(f"⚡ Semantic cache HIT | thread={thread_id}")
                    return {
                        "question": q,
                        "answer": cached,
                        "thought_process": ["⚡ Semantic Cache HIT — instant response"],
                        "status": "Served from cache.",
                        "sources": [],
                    }
            except Exception as e:
                logfire.warning(f"⚠️ Cache check failed (non-fatal): {e}")

        # Gate 3: LangGraph RAG pipeline
        final_output = rag_agent.invoke(initial_state, config=config)

        answer = final_output.get("final_answer", "")

        # Store successful answer in semantic cache for future hits
        if os.getenv("USE_SEMANTIC_CACHE", "false").lower() == "true" and answer:
            try:
                from app.services.gcp.redis_semantic_cache import set_cache
                set_cache(q, answer)
            except Exception:
                pass

        return {
            "question": q,
            "answer": answer,
            "thought_process": final_output.get("plan"),
            "status": final_output.get("status"),
            "sources": final_output.get("documents", []),
        }

    except GraphRecursionError as e:
        # Secondary safety net fired: the graph exceeded its recursion limit,
        # meaning the corrective loop did not terminate via MAX_RETRIES as
        # expected. Return a graceful fallback instead of a 500.
        logfire.error(f"🛑 Graph recursion limit hit — forcing fallback answer: {e}")
        return {
            "question": q,
            "answer": (
                "I wasn't able to find a well-grounded answer for this question in the "
                "knowledge base after several attempts. Please try rephrasing your question "
                "or asking about a related topic."
            ),
            "thought_process": ["Loop terminated: recursion limit reached (fallback answer)."],
            "status": "fallback",
            "sources": [],
        }

    except Exception as e:
        logfire.error(f"❌ Backend Execution Failed: {e}")
        return {
            "question": q,
            "answer": "I apologize, but I encountered an internal error. Please try again.",
            "thought_process": ["Error encountered during execution."],
            "status": "error",
            "sources": [],
        }
