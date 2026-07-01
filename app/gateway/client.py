import logfire
from langchain_groq import ChatGroq

from app.config import settings


# Direct Groq access (no Portkey gateway).
#   - Primary:  llama-3.3-70b-versatile
#   - Fallback: llama-3.1-8b-instant (used manually on primary failure, see fallback below)
PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"


def get_langchain_llm(feature: str = "rag") -> ChatGroq:
    """
    Returns a direct ChatGroq client (Portkey gateway removed).

    Retains a manual fallback to a faster/smaller model if the primary
    model call fails (e.g. rate limit / server error), similar to what
    the Portkey gateway previously provided.
    """
    primary = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=PRIMARY_MODEL,
        temperature=0,
    )
    fallback = ChatGroq(
        api_key=settings.GROQ_FALLBACK_API_KEY or settings.GROQ_API_KEY,
        model=FALLBACK_MODEL,
        temperature=0,
    )
    logfire.info(f"🧠 LLM client ready ({feature}): {PRIMARY_MODEL} -> fallback {FALLBACK_MODEL}")
    return primary.with_fallbacks([fallback])


def get_groq_client(feature: str = "rag") -> ChatGroq:
    """
    Alias of get_langchain_llm — plain Groq client with fallback,
    for nodes that previously used the raw Portkey client.
    """
    return get_langchain_llm(feature=feature)
