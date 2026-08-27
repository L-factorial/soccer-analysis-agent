"""FastAPI dependency factories for the RAG subsystem."""

from functools import lru_cache
import os
from pathlib import Path
from secrets import compare_digest

from fastapi import Header, HTTPException, status

from app.rag.embeddings import OpenAIEmbeddingProvider, RagEmbeddingConfig
from app.rag.repository import QdrantConfig, QdrantKnowledgeRepository


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def require_ingestion_api_key(
    supplied_key: str | None = Header(default=None, alias="X-RAG-Admin-Key"),
) -> None:
    """Protect the mutating, credit-consuming ingestion endpoint."""
    expected_key = os.getenv("RAG_INGESTION_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "rag_ingestion_unconfigured",
                "message": "RAG_INGESTION_API_KEY is not configured",
            },
        )
    if supplied_key is None or not compare_digest(supplied_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_rag_admin_key",
                "message": "A valid RAG ingestion key is required",
            },
        )


@lru_cache
def get_embedding_provider() -> OpenAIEmbeddingProvider:
    """Reuse the thread-safe OpenAI client across ingestion requests."""
    return OpenAIEmbeddingProvider(RagEmbeddingConfig.from_environment())


@lru_cache
def get_knowledge_repository() -> QdrantKnowledgeRepository:
    """Reuse one persistent local Qdrant client for this process."""
    configured_path = os.getenv("QDRANT_PATH")
    path = Path(configured_path) if configured_path else Path("data/qdrant")
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return QdrantKnowledgeRepository(
        QdrantConfig(
            path=path,
            collection_name=os.getenv("QDRANT_COLLECTION", "soccer_knowledge"),
        )
    )
