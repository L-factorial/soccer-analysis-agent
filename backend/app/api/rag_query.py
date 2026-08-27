"""Read-only HTTP boundary for soccer-knowledge vector search."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.rag.dependencies import get_embedding_provider, get_knowledge_repository
from app.rag.embeddings import EmbeddingProvider
from app.rag.repository import KnowledgeRepository
from app.rag.retrieval import query_knowledge
from app.rag.schemas import KnowledgeQuery, KnowledgeQueryResponse


router = APIRouter(prefix="/rag", tags=["rag query"])
logger = logging.getLogger("uvicorn.error")


@router.post(
    "/query",
    response_model=KnowledgeQueryResponse,
    summary="Find soccer concepts by semantic proximity",
    description=(
        "Embeds the query with the configured embedding provider and returns "
        "Qdrant matches in proximity order. Each match exposes Qdrant's "
        "unmodified similarity score; the score is not a probability."
    ),
)
def query_documents(
    request: KnowledgeQuery,
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
) -> KnowledgeQueryResponse:
    """Return concepts ranked by vector proximity to the supplied query."""
    try:
        return query_knowledge(request, embedding_provider, repository)
    except Exception as error:
        logger.exception("RAG knowledge query failed")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "rag_query_failed",
                "message": "The query could not be embedded and searched",
            },
        ) from error
