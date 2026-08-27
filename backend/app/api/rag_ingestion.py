"""HTTP boundary for validated soccer-knowledge ingestion."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.rag.dependencies import (
    get_embedding_provider,
    get_knowledge_repository,
    require_ingestion_api_key,
)
from app.rag.embeddings import EmbeddingProvider
from app.rag.ingestion import ingest_knowledge_document
from app.rag.repository import KnowledgeRepository
from app.rag.schemas import KnowledgeDocument, KnowledgeIngestionReceipt


router = APIRouter(prefix="/rag/ingestion", tags=["rag ingestion"])
logger = logging.getLogger("uvicorn.error")


@router.post(
    "/documents",
    response_model=KnowledgeIngestionReceipt,
    status_code=201,
    summary="Embed and persist one soccer knowledge document",
    description=(
        "Validates one canonical soccer concept, generates its embedding, and "
        "upserts the vector and searchable payload into local Qdrant. The "
        "response contains persistence and embedding metadata, not the raw vector."
    ),
    dependencies=[Depends(require_ingestion_api_key)],
)
def ingest_document(
    document: KnowledgeDocument,
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
) -> KnowledgeIngestionReceipt:
    """Embed and upsert one validated soccer-knowledge document."""
    try:
        return ingest_knowledge_document(document, embedding_provider, repository)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("RAG document ingestion failed for %s", document.id)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "rag_ingestion_failed",
                "message": "The document could not be embedded and persisted",
            },
        ) from error
