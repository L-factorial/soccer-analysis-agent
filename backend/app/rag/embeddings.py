"""Prepare validated soccer knowledge for an embedding provider."""

from dataclasses import dataclass
import os
from typing import Protocol, Sequence

from openai import OpenAI

from app.rag.schemas import EmbeddingBatch, EmbeddingVector, KnowledgeDocument


class EmbeddingProvider(Protocol):
    """Provider-independent boundary used by ingestion and query workflows."""

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed non-empty texts while preserving their input order."""


@dataclass(frozen=True, slots=True)
class RagEmbeddingConfig:
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    timeout_seconds: float = 15

    @classmethod
    def from_environment(cls) -> "RagEmbeddingConfig":
        return cls(
            model=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small"),
            dimensions=int(os.getenv("RAG_EMBEDDING_DIMENSIONS", "1536")),
            timeout_seconds=float(os.getenv("RAG_EMBEDDING_TIMEOUT_SECONDS", "15")),
        )


class EmbeddingResponseError(RuntimeError):
    """Raised when a provider response cannot be mapped to the request."""


class OpenAIEmbeddingProvider:
    """Create embeddings through the OpenAI embeddings endpoint."""

    def __init__(
        self,
        config: RagEmbeddingConfig,
        client: OpenAI | None = None,
    ) -> None:
        if config.dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        if config.timeout_seconds <= 0:
            raise ValueError("embedding timeout must be positive")
        self._config = config
        self._client = client or OpenAI(timeout=config.timeout_seconds)

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        inputs = list(texts)
        if not inputs:
            raise ValueError("at least one text is required")
        if any(not text.strip() for text in inputs):
            raise ValueError("embedding texts must not be empty")

        response = self._client.embeddings.create(
            model=self._config.model,
            input=inputs,
            dimensions=self._config.dimensions,
            encoding_format="float",
        )
        indexed = {item.index: item for item in response.data}
        if set(indexed) != set(range(len(inputs))):
            raise EmbeddingResponseError(
                "embedding response indices do not match request inputs"
            )

        embeddings = tuple(
            EmbeddingVector(
                vector=tuple(indexed[index].embedding),
                model=response.model,
                dimensions=self._config.dimensions,
            )
            for index in range(len(inputs))
        )
        return EmbeddingBatch(
            embeddings=embeddings,
            total_tokens=response.usage.total_tokens,
        )


def build_embedding_text(document: KnowledgeDocument) -> str:
    """Create a stable semantic representation of one knowledge document."""
    lines = [
        f"Canonical term: {document.canonical_term}",
        f"Name: {document.display_name}",
        f"Category: {document.category.value}",
        f"Definition: {document.definition}",
    ]

    if document.aliases:
        aliases = "; ".join(
            _localized_text(alias.term, alias.language, alias.locale)
            for alias in document.aliases
        )
        lines.append(f"Aliases: {aliases}")

    if document.examples:
        lines.append("Examples:")
        lines.extend(f"- {example}" for example in document.examples)

    if document.tags:
        lines.append(f"Tags: {', '.join(document.tags)}")

    return "\n".join(lines)


def _localized_text(text: str, language: str, locale: str | None) -> str:
    location = locale or language
    return f"{text} [{location}]"
