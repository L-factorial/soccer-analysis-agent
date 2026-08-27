"""Validated source records accepted by the RAG ingestion boundary."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KnowledgeCategory(StrEnum):
    """Top-level classifications for curated soccer knowledge."""

    FIELD_ZONE = "field_zone"
    FORMATION = "formation"
    PLAYER_ROLE = "player_role"
    TACTICAL_CONCEPT = "tactical_concept"
    TACTICAL_MOVEMENT = "tactical_movement"


class KnowledgeAlias(BaseModel):
    """One localized expression that refers to a canonical concept."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    term: str = Field(min_length=1, max_length=120)
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}$")
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")


class KnowledgeSource(BaseModel):
    """Provenance retained with an ingested knowledge record."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=500)
    license: str | None = Field(default=None, max_length=120)


class KnowledgeDocument(BaseModel):
    """A single, human-curated soccer concept before chunking or embedding."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
    )
    canonical_term: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)
    category: KnowledgeCategory
    definition: str = Field(min_length=10, max_length=4000)
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}$")
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    aliases: tuple[KnowledgeAlias, ...] = ()
    examples: tuple[str, ...] = ()
    related_concept_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    source: KnowledgeSource
    version: int = Field(default=1, ge=1)

    @field_validator("canonical_term")
    @classmethod
    def canonical_term_must_be_an_enum_style_name(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.replace("_", "").isalnum():
            raise ValueError("canonical_term must contain only letters, numbers, and underscores")
        return normalized

    @field_validator("examples", "related_concept_ids", "tags")
    @classmethod
    def string_collections_must_be_nonempty_and_unique(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("collection values must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("collection values must be unique")
        return normalized

    @model_validator(mode="after")
    def aliases_must_be_unique(self) -> "KnowledgeDocument":
        identities = tuple(
            (alias.term.casefold(), alias.language, alias.locale)
            for alias in self.aliases
        )
        if len(set(identities)) != len(identities):
            raise ValueError("aliases must be unique within a language and locale")
        return self


class EmbeddingVector(BaseModel):
    """One validated vector returned by an embedding provider."""

    model_config = ConfigDict(extra="forbid")

    vector: tuple[float, ...]
    model: str = Field(min_length=1)
    dimensions: int = Field(gt=0)

    @model_validator(mode="after")
    def vector_must_match_dimensions(self) -> "EmbeddingVector":
        if len(self.vector) != self.dimensions:
            raise ValueError("vector length must match dimensions")
        return self


class EmbeddingBatch(BaseModel):
    """Ordered vectors and aggregate API usage for one embedding request."""

    model_config = ConfigDict(extra="forbid")

    embeddings: tuple[EmbeddingVector, ...]
    total_tokens: int = Field(ge=0)


class PreparedKnowledgeRecord(BaseModel):
    """Validated document plus the vector-ready projection derived from it.

    This is an in-memory handoff between preparation and persistence. It does
    not imply that the record has been stored in a vector database.
    """

    model_config = ConfigDict(extra="forbid")

    document: KnowledgeDocument
    embedding_text: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding: EmbeddingVector
    token_count: int = Field(ge=0)


class KnowledgeIngestionReceipt(BaseModel):
    """Public result returned after a prepared vector is persisted."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["upserted"] = "upserted"
    document_id: str
    point_id: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_model: str
    dimensions: int = Field(gt=0)
    token_count: int = Field(ge=0)


class KnowledgeQuery(BaseModel):
    """Validated semantic-search request from an API consumer."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    minimum_score: float | None = Field(default=None, ge=-1, le=1)


class KnowledgeMatch(BaseModel):
    """One ranked Qdrant match, including its cosine-similarity score."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    canonical_term: str
    display_name: str
    category: KnowledgeCategory
    definition: str
    aliases: tuple[str, ...] = ()
    language: str
    locale: str | None = None
    score: float
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class KnowledgeQueryResponse(BaseModel):
    """Ordered semantic matches and query-embedding usage metadata."""

    model_config = ConfigDict(extra="forbid")

    query: str
    matches: tuple[KnowledgeMatch, ...]
    embedding_model: str
    token_count: int = Field(ge=0)
