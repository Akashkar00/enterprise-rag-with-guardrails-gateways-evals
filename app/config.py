import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- GCP Core ---
    PROJECT_ID = os.getenv("PROJECT_ID", "advanced-rag-project-500909")
    LOCATION = os.getenv("LOCATION", "us-central1")
    GCP_DOC_AI_LOCATION = os.getenv("GCP_DOC_AI_LOCATION", "us")
    GCP_DOC_AI_PROCESSOR_ID = os.getenv("GCP_DOC_AI_PROCESSOR_ID")
    RAW_BUCKET = os.getenv("GCP_RAW_BUCKET", "advanced-rag-project-500909-rag-raw")
    PROCESSED_BUCKET = os.getenv("GCP_PROCESSED_BUCKET", "advanced-rag-project-500909-rag-processed")

    # --- Vector DB (Qdrant) ---
    QDRANT_URL = os.getenv("QDRANT_CLUSTER_ENDPOINT")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION = "enterprise_rag"

    # --- LLM (Groq) ---
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_FALLBACK_API_KEY = os.getenv("GROQ_FALLBACK_API_KEY")
    GROQ_MODEL = "llama-3.3-70b-versatile"

    # --- LLM Gateway (Portkey) ---
    # All LLM calls route THROUGH Portkey so they get caching, automatic
    # fallback, retries, and full dashboard observability. Without this the
    # Portkey cache can never hit because requests never reach the gateway.
    PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
    # This Portkey org enforces "saved-only" configs (block_inline_config), so
    # the app must reference a saved config by its pc- slug instead of passing
    # an inline config dict. This saved config holds cache + fallback + retry
    # + targets. Override via env if you point at a different saved config.
    PORTKEY_CONFIG_ID = os.getenv("PORTKEY_CONFIG_ID", "pc-enterp-edad02")
    # Dashboard integration slugs for the two Groq API keys.
    #   GROQ_SLUG   -> primary  (e.g. "rag")
    #   GROQ_SLUG_2 -> fallback (e.g. "fallback-rag")
    GROQ_SLUG = os.getenv("GROQ_SLUG", "rag")
    GROQ_SLUG_2 = os.getenv("GROQ_SLUG_2", "fallback-rag")
    # Fully-qualified Portkey model references: @<slug>/<model-name>
    PORTKEY_PRIMARY_MODEL = f"@{GROQ_SLUG}/llama-3.3-70b-versatile"
    PORTKEY_FALLBACK_MODEL = f"@{GROQ_SLUG_2}/llama-3.1-8b-instant"

    # --- Guardrails (NVIDIA) ---
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

    # --- Postgres Memory ---
    DB_HOST = os.getenv("DB_HOST")                # /cloudsql/... (Cloud Run) or hostname (local)
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_NAME = os.getenv("DB_NAME", "rag_memory")
    LOCAL_MODE = os.getenv("LOCAL_MODE", "true").lower() == "true"

    # --- Redis Semantic Cache ---
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    USE_SEMANTIC_CACHE = os.getenv("USE_SEMANTIC_CACHE", "false").lower() == "true"

    # --- Observability ---
    LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "true")
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "entreprise_rag")
    LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    # --- Evals ---
    JUDGE_GROQ_API = os.getenv("JUDGE_GROQ_API")


# Apply LangSmith env vars for automatic LangChain tracing
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGSMITH_TRACING", "true")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "entreprise_rag")
os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

settings = Settings()
