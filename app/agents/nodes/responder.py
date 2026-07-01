import logfire
from app.agents.state import AgentState
from app.gateway import get_langchain_llm

llm = get_langchain_llm(feature="responder")


def generate_node(state: AgentState):
    """
    Synthesizes a response using both Documentation Context AND Conversation History.
    Uses a direct ChatGroq client (Portkey gateway removed) with a manual
    fallback model configured in app.gateway.client.
    """
    query = state["current_query"]

    history_str = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    user_msg = state["messages"][-1]["content"] if state["messages"] else ""

    if query == "CONVERSATIONAL":
        logfire.info("Generating conversational response using memory.")
        prompt = f"""
        You are a friendly and helpful Enterprise AI Assistant.
        Answer the user's latest message using the CONVERSATION HISTORY below.

        CONVERSATION HISTORY:
        {history_str}

        LATEST MESSAGE:
        "{user_msg}"
        """
    else:
        logfire.info("Generating technical RAG response.")
        max_context_chars = 25000
        full_context = ""

        for doc in state["documents"]:
            if len(full_context) + len(doc) < max_context_chars:
                full_context += doc + "\n\n"
            else:
                logfire.warning("Context truncated to fit Groq TPM limits.")
                break

        if not full_context.strip():
            # grade_documents found no relevant context (after retries) — answer honestly.
            logfire.info("No relevant context available — generating a graceful fallback answer.")
            prompt = f"""
            You are a Senior Technical Research Assistant with expertise across computer science,
            machine learning, systems, networking, and hardware.

            No relevant documents were found in the knowledge base for this question.
            Tell the user you don't have specific documentation on this topic. You may offer
            general knowledge only if clearly caveated as not sourced from the knowledge base.

            CONVERSATION HISTORY:
            {history_str}

            USER QUESTION:
            "{user_msg}"
            """
        else:
            prompt = f"""
            You are a Senior Technical Research Assistant with expertise across computer science,
            machine learning, systems, networking, and hardware.
            Answer the question using the TECHNICAL CONTEXT provided.

            TECHNICAL CONTEXT:
            {full_context}

            CONVERSATION HISTORY:
            {history_str}

            USER QUESTION:
            "{user_msg}"
            """

    with logfire.span("✍️ LLM Synthesis"):
        try:
            response = llm.invoke(prompt)
            content = response.content

            logfire.info("✅ Response synthesised via LLM.")
            plan_update = state["plan"]
            status = "Response generated."

            return {
                "final_answer": content,
                "status": status,
                "plan": plan_update,
                "messages": [{"role": "assistant", "content": content}]
            }

        except Exception as e:
            logfire.error(f"LLM Generation failed: {e}")
            raise e
