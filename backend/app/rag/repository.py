"""Persistence boundary and Qdrant implementation for prepared knowledge."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.rag.schemas import EmbeddingVector, KnowledgeMatch, PreparedKnowledgeRecord


class KnowledgeRepository(Protocol):
    """Storage contract consumed by the ingestion service."""

    def upsert(self, prepared: PreparedKnowledgeRecord) -> str:
        """Persist a prepared record and return its stable point ID."""

    def search(
        self,
        embedding: EmbeddingVector,
        limit: int,
        language: str | None = None,
        minimum_score: float | None = None,
    ) -> tuple[KnowledgeMatch, ...]:
        """Return nearest concepts ordered by vector similarity."""


@dataclass(frozen=True, slots=True)
class QdrantConfig:
    path: Path
    collection_name: str = "soccer_knowledge"


class QdrantKnowledgeRepository:
    """Persist soccer concepts in a local Qdrant collection."""

    def __init__(
        self,
        config: QdrantConfig,
        client: QdrantClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or QdrantClient(path=str(config.path))

    def upsert(self, prepared: PreparedKnowledgeRecord) -> str:
        self._ensure_collection(prepared.embedding.dimensions)
        point_id = str(uuid5(NAMESPACE_URL, prepared.document.id))
        payload = {
            "document": prepared.document.model_dump(mode="json"),
            "document_id": prepared.document.id,
            "canonical_term": prepared.document.canonical_term,
            "category": prepared.document.category.value,
            "language": prepared.document.language,
            "locale": prepared.document.locale,
            "embedding_text": prepared.embedding_text,
            "content_hash": prepared.content_hash,
            "embedding_model": prepared.embedding.model,
            "dimensions": prepared.embedding.dimensions,
        }
        self._client.upsert(
            collection_name=self._config.collection_name,
            wait=True,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=list(prepared.embedding.vector),
                    payload=payload,
                )
            ],
        )
        return point_id

    def search(
        self,
        embedding: EmbeddingVector,
        limit: int,
        language: str | None = None,
        minimum_score: float | None = None,
    ) -> tuple[KnowledgeMatch, ...]:
        """Search by cosine proximity and expose Qdrant's score unchanged."""
        if not self._client.collection_exists(self._config.collection_name):
            return ()

        query_filter = None
        if language is not None:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="language",
                        match=models.MatchValue(value=language),
                    )
                ]
            )

        points = self._client.query_points(
            collection_name=self._config.collection_name,
            query=list(embedding.vector),
            query_filter=query_filter,
            limit=limit,
            score_threshold=minimum_score,
            with_payload=True,
            with_vectors=False,
        ).points
        return tuple(self._match_from_point(point) for point in points)

    @staticmethod
    def _match_from_point(point: models.ScoredPoint) -> KnowledgeMatch:
        payload = point.payload or {}
        document = payload.get("document", {})
        aliases = tuple(
            alias["term"]
            for alias in document.get("aliases", ())
            if isinstance(alias, dict) and isinstance(alias.get("term"), str)
        )
        return KnowledgeMatch(
            document_id=payload["document_id"],
            canonical_term=payload["canonical_term"],
            display_name=document["display_name"],
            category=payload["category"],
            definition=document["definition"],
            aliases=aliases,
            language=payload["language"],
            locale=payload.get("locale"),
            score=point.score,
            content_hash=payload["content_hash"],
        )

    def _ensure_collection(self, dimensions: int) -> None:
        if self._client.collection_exists(self._config.collection_name):
            collection = self._client.get_collection(self._config.collection_name)
            vectors = collection.config.params.vectors
            existing_size = getattr(vectors, "size", None)
            if existing_size != dimensions:
                raise ValueError(
                    "Qdrant collection dimensions do not match the embedding provider"
                )
            return

        self._client.create_collection(
            collection_name=self._config.collection_name,
            vectors_config=models.VectorParams(
                size=dimensions,
                distance=models.Distance.COSINE,
            ),
        )
