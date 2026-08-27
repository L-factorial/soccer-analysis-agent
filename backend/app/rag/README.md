# RAG knowledge ingestion

The RAG package prepares curated soccer concepts for semantic retrieval while
keeping the source content, embedding provider, and future vector database
separate.

For full HTTP contracts, examples, error behavior, provider independence, and
proximity-score interpretation, see [RAG ingestion and query API](API.md).

## Current preparation pipeline

```text
YAML concept
    -> load_knowledge_document
    -> KnowledgeDocument validation
    -> build_embedding_text
    -> EmbeddingProvider.embed
    -> PreparedKnowledgeRecord
    -> QdrantKnowledgeRepository.upsert
    -> KnowledgeIngestionReceipt
```

`prepare_knowledge_file` coordinates these steps for one concept. Its result is
an in-memory record containing the validated document, the exact text represented
by the vector, a SHA-256 content hash, embedding metadata, and aggregate token
usage.

The content hash is calculated from the embedding text, not the YAML file bytes.
Changing YAML formatting alone therefore leaves the searchable content identity
unchanged.

## Boundaries

- YAML files under `backend/data/soccer_knowledge` are the current source of
  truth.
- `KnowledgeDocument` is the validation boundary for source data.
- `EmbeddingProvider` keeps preparation independent of OpenAI in tests and from
  any future alternative embedding provider.
- `PreparedKnowledgeRecord` is the handoff to the repository layer.
- `QdrantKnowledgeRepository` stores the vector and its payload in the local
  `soccer_knowledge` collection using a stable UUID derived from the document ID.
- `POST /api/v1/rag/ingestion/documents` accepts a JSON `KnowledgeDocument`,
  embeds it, and upserts it. The endpoint requires `X-RAG-Admin-Key` matching
  `RAG_INGESTION_API_KEY` because it mutates data and consumes API credits.
- `POST /api/v1/rag/query` embeds a prompt and returns concepts ordered by
  Qdrant cosine proximity. Every match includes the unmodified vector-search
  score; optional language and minimum-score filters can narrow the results.
- Prompt-to-planner policy mapping and bulk ingestion are not yet implemented.
