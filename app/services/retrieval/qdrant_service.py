import logfire
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings
from app.services.retrieval.embedding import get_embedding_model, embed_query


class RetrievalError(Exception):
    """Raised when the knowledge-base search fails (DB error, timeout, embed failure)."""


# Initialize Qdrant Client (timeout so a hung DB errors instead of blocking forever)
client = QdrantClient(
    url=settings.QDRANT_URL,
    port=443,
    api_key=settings.QDRANT_API_KEY,
    prefer_grpc=False,
    timeout=15,
)

def search_enterprise_knowledge(query: str, limit: int = 8):
    """
    Performs a high-precision search in the enterprise knowledge base.
    Uses the modern query_points interface.

    Returns a (possibly empty) list of results on success. Raises RetrievalError
    on any failure (DB error, timeout, embedding failure) so callers can
    distinguish a genuine failure from a legitimately empty result set.
    """
    try:
        query_vector = embed_query(query)

        # Using query_points - the modern standard for Qdrant
        response = client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            limit=limit,
            with_payload=True # JSON
        )

        results = []
        for res in response.points:
            results.append({
                "content": res.payload.get("text", ""),
                "source": res.payload.get("source", "Unknown"),
                "score": res.score
            })
        
        return results
    except Exception as e:
        logfire.error(f"❌ Qdrant Search Failed: {e}")
        raise RetrievalError(str(e)) from e
