import os
import logfire
from app.agents.state import AgentState

# Backends tried in order — free scraping search is flaky/rate-limited per-backend,
# so we fall through until one returns results. If a Tavily API key is present we
# prefer it (reliable, key-based) over scraping.
_DDGS_BACKENDS = ["mojeek", "duckduckgo", "brave", "google", "yahoo", "bing"]
MAX_RESULTS = 5


def _search_tavily(query: str):
    """Reliable, key-based search. Used only if TAVILY_API_KEY is set."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return None
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(query, max_results=MAX_RESULTS)
        return [
            f"[WEB] {r.get('title','')}\n{r.get('content','')}\nSource: {r.get('url','')}"
            for r in resp.get("results", [])
        ]
    except Exception as e:
        logfire.warning(f"⚠️ Tavily search failed: {e}")
        return None


def _search_ddgs(query: str):
    """Best-effort, no-key scraping search. Tries multiple backends."""
    try:
        from ddgs import DDGS
    except Exception as e:
        logfire.warning(f"⚠️ ddgs not available: {e}")
        return []

    for backend in _DDGS_BACKENDS:
        try:
            results = list(DDGS().text(query, backend=backend, max_results=MAX_RESULTS))
            if results:
                logfire.info(f"🌐 Web search hit via backend '{backend}': {len(results)} results")
                return [
                    f"[WEB] {r.get('title','')}\n{r.get('body','')}\nSource: {r.get('href','')}"
                    for r in results
                ]
        except Exception as e:
            logfire.warning(f"⚠️ ddgs backend '{backend}' failed: {e}")
            continue
    return []


def web_search_node(state: AgentState):
    """
    External web-search fallback for the KNOWLEDGE-GAP case: reached only when
    the vector DB has no relevant documents even after query rewrites. Rewriting
    can fix bad phrasing, but not missing corpus data — so here we go outside the
    corpus to a secondary source.

    Prefers Tavily (if TAVILY_API_KEY is set), else falls back to key-free
    scraping search. Degrades gracefully to an empty result set (responder then
    answers honestly that nothing was found).
    """
    question = state["messages"][-1]["content"] if state["messages"] else state["current_query"]

    with logfire.span("🌐 External Web Search (knowledge-gap fallback)"):
        logfire.info(f"Searching the web for: {question}")

        results = _search_tavily(question)
        if results is None:
            results = _search_ddgs(question)

        if results:
            plan_update = state["plan"] + [f"Web Search: {len(results)} external result(s) found"]
            status = "Answering from external web search (not in knowledge base)."
        else:
            logfire.warning("⚠️ Web search returned no usable results.")
            plan_update = state["plan"] + ["Web Search: no external results"]
            status = "No relevant information found in knowledge base or web search."

    return {
        "documents": results,
        "plan": plan_update,
        "status": status,
    }
