import logfire
from portkey_ai import Portkey, createHeaders, PORTKEY_GATEWAY_URL
from langchain_openai import ChatOpenAI
from langchain_core.runnables import Runnable

from app.config import settings


# Groq's OpenAI-compatible endpoint. The NeMo Guardrails classifier
# (app/guardrails/rails.py) calls Groq directly through this URL — it's a fast
# gate-keeping model that doesn't need gateway caching/fallback.
GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"


# ---------------------------------------------------------------------------
# Portkey LLM Gateway
# ---------------------------------------------------------------------------
# Every LLM call routes THROUGH Portkey instead of hitting Groq directly. This
# is what gives us:
#   - Caching       (identical requests served from cache — no LLM call, ~instant)
#   - Fallback      (primary 70B → smaller 8B on non-2xx)
#   - Retries       (transient 429/503 retried before the fallback fires)
#   - Observability (every request logged in the Portkey dashboard)
#
# IMPORTANT: this Portkey org enforces saved-only configs (block_inline_config
# is enabled), so we reference a SAVED config by its `pc-...` slug rather than
# passing an inline config dict. The saved config (settings.PORTKEY_CONFIG_ID)
# holds: strategy=fallback, cache=semantic, retry, and the primary/fallback
# targets. If requests do NOT go through this config, the cache can never hit.
# ---------------------------------------------------------------------------

PORTKEY_CONFIG_ID = settings.PORTKEY_CONFIG_ID       # e.g. "pc-enterp-edad02"
PRIMARY_MODEL = settings.PORTKEY_PRIMARY_MODEL       # e.g. "@rag/llama-3.3-70b-versatile"
FALLBACK_MODEL = settings.PORTKEY_FALLBACK_MODEL     # e.g. "@fallback-rag/llama-3.1-8b-instant"


# Native Portkey client — used where we need the raw response object so we can
# read the `x-portkey-cache-status` response header (see extract_cache_status).
portkey_client = Portkey(
    api_key=settings.PORTKEY_API_KEY,
    config=PORTKEY_CONFIG_ID,
)


def extract_cache_status(response) -> str:
    """
    Read Portkey's `x-portkey-cache-status` response header ("HIT" / "MISS").

    The Portkey Python SDK (2.x) attaches the raw response headers to the
    returned object as `._headers` (an httpx.Headers, case-insensitive) and also
    exposes a `.get_headers()` accessor on some versions. We try both. If the
    header can't be read we return "MISS" — the app still works and the true
    HIT/MISS is always visible in the Portkey dashboard Logs.

    NOTE: Portkey's cache write is asynchronous, so an *immediate* repeat of a
    request may still report MISS; a moment later it reports HIT.
    """
    # Preferred: private httpx.Headers (case-insensitive lookup).
    headers = getattr(response, "_headers", None)

    # Fallback: get_headers() returns a plain dict on some SDK versions.
    if headers is None:
        getter = getattr(response, "get_headers", None)
        if callable(getter):
            try:
                headers = getter()
            except Exception:
                headers = None

    if headers is not None:
        status = ""
        try:
            status = headers.get("x-portkey-cache-status", "") or ""
            if not status and isinstance(headers, dict):
                status = next(
                    (v for k, v in headers.items()
                     if k.lower() == "x-portkey-cache-status"),
                    "",
                )
        except Exception:
            status = ""
        if status:
            return status.upper()
    return "MISS"


def get_langchain_llm(feature: str = "rag") -> Runnable:
    """
    LangChain-compatible LLM (ChatOpenAI) that routes through the Portkey
    gateway using the SAVED config. Preserves the `.invoke(prompt)` ->
    message-with-`.content` interface every node already relies on, so node
    logic is unchanged.

    Fallback + retries + caching are handled by the saved gateway config, so no
    explicit client-side fallback logic is needed here.
    """
    llm = ChatOpenAI(
        api_key=settings.PORTKEY_API_KEY,
        base_url=PORTKEY_GATEWAY_URL,
        model=PRIMARY_MODEL,
        temperature=0,
        default_headers=createHeaders(
            api_key=settings.PORTKEY_API_KEY,
            config=PORTKEY_CONFIG_ID,
            metadata={"feature": feature},
        ),
    )
    logfire.info(
        f"🧠 LLM client ready via Portkey ({feature}): config={PORTKEY_CONFIG_ID} "
        f"({PRIMARY_MODEL} -> fallback {FALLBACK_MODEL}, cache + retry enabled)"
    )
    return llm


def get_groq_client(feature: str = "rag") -> Runnable:
    """
    Backward-compatible alias of get_langchain_llm — kept so existing imports
    (`from app.gateway.client import get_groq_client`) keep working.
    """
    return get_langchain_llm(feature=feature)
