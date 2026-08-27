"""Semantic retrieval service for user-supplied tactical language."""

from app.rag.embeddings import EmbeddingProvider
from app.rag.repository import KnowledgeRepository
from app.rag.schemas import KnowledgeQuery, KnowledgeQueryResponse


def query_knowledge(
    request: KnowledgeQuery,
    embedding_provider: EmbeddingProvider,
    repository: KnowledgeRepository,
) -> KnowledgeQueryResponse:
    """Embed one query and return Qdrant matches in proximity order."""
    batch = embedding_provider.embed([request.query])
    if len(batch.embeddings) != 1:
        raise ValueError("querying knowledge requires exactly one embedding")

    query_embedding = batch.embeddings[0]
    matches = repository.search(
        query_embedding,
        limit=request.limit,
        language=request.language,
        minimum_score=request.minimum_score,
    )
    return KnowledgeQueryResponse(
        query=request.query,
        matches=matches,
        embedding_model=query_embedding.model,
        token_count=batch.total_tokens,
    )
