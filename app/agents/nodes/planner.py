from app.agents.state import AgentState
from app.gateway import get_langchain_llm
import logfire

# Groq LLM via OpenAI-compatible client (ChatOpenAI): primary + retry, with an
# explicit fallback to a smaller model. Exposes the same .invoke() interface.
llm = get_langchain_llm(feature="planner")

def planner_node(state: AgentState):
    """
    The Planner determines if a search is needed based on the ENTIRE conversation.
    """
    # Get the conversation history (excluding the latest message)
    history = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history += f"{role}: {msg['content']}\n"
    
    user_message = state["messages"][-1]["content"] if state["messages"] else ""
    
    prompt = f"""
    You are an intelligent Assistant Planner. Analyze the conversation history and the
    latest user message, then classify how to handle it.

    CONVERSATION HISTORY:
    {history}

    LATEST MESSAGE:
    "{user_message}"

    Choose EXACTLY ONE of these outputs (respond with the label only, nothing else):

    1. CONVERSATIONAL
       - Use for greetings, thanks, or questions answerable using ONLY the conversation
         history above (e.g. "what is my name").

    2. CLARIFY
       - Use when the request is ambiguous, too vague, underspecified, or you are NOT
         confident what the user actually wants (e.g. "how do I fix it?", "tell me about
         that", "it doesn't work"). Prefer CLARIFY over guessing when intent is unclear.

    3. SEARCH: <refined search query>
       - Use for a clear technical or academic question (Kubernetes, hardware, networking,
         computer science, machine learning, algorithms, systems, or any technical/research
         topic) that needs fresh documentation. Put a concise refined query after "SEARCH:".

    Output ONLY one of: "CONVERSATIONAL", "CLARIFY", or "SEARCH: <query>".
    """

    with logfire.span("🧠 Planner Decision"):
        raw = llm.invoke(prompt).content.strip()
        logfire.info(f"Planner raw output: {raw[:160]}")

    # Robust parsing — tolerate verbose model output instead of exact-matching.
    normalized = raw.upper()

    # CLARIFY takes priority: if the model is unsure, don't barrel ahead.
    if "CLARIFY" in normalized:
        logfire.info("Intent: CLARIFY (ambiguous / low confidence)")
        return {
            "current_query": "CLARIFY",
            "status": "Intent unclear — asking the user to clarify.",
            "plan": ["Intent: Ambiguous", "Action: Ask user to clarify"],
        }

    if "CONVERSATIONAL" in normalized:
        logfire.info("Intent: CONVERSATIONAL")
        return {
            "current_query": "CONVERSATIONAL",
            "status": "Handling conversationally (using memory)...",
            "plan": ["Intent: Conversational/Memory", "Retrieval: Skipped"],
        }

    # Technical: strip an optional "SEARCH:" prefix and use the remainder as the query.
    query = raw
    if ":" in raw and normalized.lstrip().startswith("SEARCH"):
        query = raw.split(":", 1)[1].strip()
    query = query.strip().strip('"').strip()

    logfire.info(f"Intent: Technical | search='{query}'")
    return {
        "current_query": query,
        "status": f"Technical research needed. Searching for: {query}",
        "plan": ["Intent: Technical", f"Search Term: {query}"],
    }
