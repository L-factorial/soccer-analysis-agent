"""Load curated soccer knowledge into validated ingestion records."""

from hashlib import sha256
from pathlib import Path

import yaml

from app.rag.embeddings import EmbeddingProvider, build_embedding_text
from app.rag.repository import KnowledgeRepository
from app.rag.schemas import (
    KnowledgeDocument,
    KnowledgeIngestionReceipt,
    PreparedKnowledgeRecord,
)


def load_knowledge_document(path: Path) -> KnowledgeDocument:
    """Load and validate one YAML knowledge document from ``path``."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return KnowledgeDocument.model_validate(payload)


def prepare_knowledge_file(
    path: Path,
    embedding_provider: EmbeddingProvider,
) -> PreparedKnowledgeRecord:
    """Prepare one curated YAML file for later vector-store persistence.

    Preparation owns the deterministic pipeline before storage:

    1. Load and validate the source document.
    2. Build the semantic text used for retrieval.
    3. Generate exactly one embedding for that text.
    4. Package the source, projection, vector, and stable content identity.

    The function deliberately does not write to Qdrant or any other database.
    Keeping persistence outside this boundary lets validation and embedding be
    tested independently and prevents partially prepared records from being
    stored.
    """
    return prepare_knowledge_document(
        load_knowledge_document(path),
        embedding_provider,
    )


def prepare_knowledge_document(
    document: KnowledgeDocument,
    embedding_provider: EmbeddingProvider,
) -> PreparedKnowledgeRecord:
    """Build and embed one already-validated knowledge document."""
    embedding_text = build_embedding_text(document)
    batch = embedding_provider.embed([embedding_text])

    # A single concept currently produces one semantic document and therefore
    # must produce one vector. Chunking, if introduced later, belongs before
    # this invariant and will return a collection of prepared records instead.
    if len(batch.embeddings) != 1:
        raise ValueError("preparing one knowledge file requires exactly one embedding")

    # Hash the exact text represented by the vector, rather than the YAML bytes.
    # Formatting-only YAML changes therefore do not trigger unnecessary
    # re-embedding, while any semantic projection change receives a new hash.
    content_hash = sha256(embedding_text.encode("utf-8")).hexdigest()

    return PreparedKnowledgeRecord(
        document=document,
        embedding_text=embedding_text,
        content_hash=content_hash,
        embedding=batch.embeddings[0],
        token_count=batch.total_tokens,
    )


def ingest_knowledge_document(
    document: KnowledgeDocument,
    embedding_provider: EmbeddingProvider,
    repository: KnowledgeRepository,
) -> KnowledgeIngestionReceipt:
    """Prepare one API document and atomically hand it to the repository."""
    prepared = prepare_knowledge_document(document, embedding_provider)
    point_id = repository.upsert(prepared)
    return KnowledgeIngestionReceipt(
        document_id=document.id,
        point_id=point_id,
        content_hash=prepared.content_hash,
        embedding_model=prepared.embedding.model,
        dimensions=prepared.embedding.dimensions,
        token_count=prepared.token_count,
    )
