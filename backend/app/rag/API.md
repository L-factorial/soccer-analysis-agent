# RAG ingestion and query API

This document describes the two RAG HTTP paths, how their responses are built,
and how vector proximity scores should be interpreted. Both routes are exposed
under the backend's `/api/v1` prefix.

## Architecture and provider independence

The RAG layer uses an `EmbeddingProvider` interface rather than calling a
generative model from its service or repository code:

```text
text
  -> EmbeddingProvider.embed
  -> EmbeddingBatch
  -> QdrantKnowledgeRepository
```

The current provider uses the OpenAI embeddings SDK, but neither endpoint asks
an LLM to compose its response. Response objects are assembled deterministically
from validated input, embedding metadata, and Qdrant results. A different
embedding provider can be introduced without changing the HTTP contracts as long
as it returns the same internal `EmbeddingBatch` structure.

An embedding model is not interchangeable with a chat or reasoning model. It
must return a fixed-size numerical vector. Ingestion and querying must use the
same embedding model and vector dimensions. Vectors produced by different models
must not be mixed in one Qdrant collection because they do not share a comparable
semantic space. Changing either `RAG_EMBEDDING_MODEL` or
`RAG_EMBEDDING_DIMENSIONS` requires rebuilding the collection.

Current configuration:

```dotenv
OPENAI_API_KEY=your-key
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_DIMENSIONS=1536
RAG_EMBEDDING_TIMEOUT_SECONDS=15
RAG_INGESTION_API_KEY=your-ingestion-secret
QDRANT_PATH=./data/qdrant
QDRANT_COLLECTION=soccer_knowledge
```

## Ingest one knowledge document

```http
POST /api/v1/rag/ingestion/documents
Content-Type: application/json
X-RAG-Admin-Key: <RAG_INGESTION_API_KEY>
```

The administration key is required because ingestion changes persistent state
and consumes embedding-provider credits.

### Request

The body is one `KnowledgeDocument`. One document represents one canonical
soccer concept; alternate expressions belong in `aliases` rather than separate
documents.

```json
{
  "id": "tactic.overlap",
  "canonical_term": "OVERLAP",
  "display_name": "Overlapping run",
  "category": "tactical_movement",
  "definition": "A supporting player runs outside the wide ball carrier to create a passing option.",
  "language": "en",
  "locale": "en-GB",
  "aliases": [
    {"term": "overlapping run", "language": "en"},
    {"term": "run around the outside", "language": "en", "locale": "en-GB"}
  ],
  "examples": [
    "Have the fullback overlap the winger."
  ],
  "related_concept_ids": ["concept.width"],
  "tags": ["attacking", "wide-play"],
  "source": {
    "title": "Internal tactical glossary",
    "reference": "glossary-v1",
    "license": "internal"
  },
  "version": 1
}
```

Unknown fields and invalid IDs, categories, language codes, locales, aliases,
or versions are rejected before an embedding request is made.

### Processing

```text
request JSON
  -> KnowledgeDocument validation
  -> deterministic semantic-text construction
  -> embedding provider call
  -> vector-dimension validation
  -> SHA-256 hash of the exact semantic text
  -> Qdrant collection creation or compatibility check
  -> vector and payload upsert
  -> KnowledgeIngestionReceipt
```

The Qdrant point ID is a stable UUID derived from `document.id`. Submitting
`tactic.overlap` again updates the same point. The content hash is derived from
the semantic text represented by the vector, not the original JSON or YAML
formatting.

Qdrant stores the vector together with:

- the validated document;
- the exact embedding text;
- canonical term, category, language, and locale;
- content hash; and
- embedding model and dimensions.

The raw vector is deliberately not returned by the API. Callers receive the
identity and metadata required to verify the write without transferring a large
array of floats.

### Successful response

Status: `201 Created`

```json
{
  "status": "upserted",
  "document_id": "tactic.overlap",
  "point_id": "d20e7020-a4ff-541f-b4a2-2fe71b790c47",
  "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "embedding_model": "text-embedding-3-small",
  "dimensions": 1536,
  "token_count": 82
}
```

The response is produced as follows:

| Field | Source |
| --- | --- |
| `status` | Deterministic API value after a successful Qdrant upsert. |
| `document_id` | Validated request document. |
| `point_id` | Stable UUID returned by the repository. |
| `content_hash` | SHA-256 of the deterministic embedding text. |
| `embedding_model` | Model identifier returned by the embedding provider. |
| `dimensions` | Validated vector length. |
| `token_count` | Aggregate usage returned by the embedding provider. |

### Errors

| Status | Meaning |
| --- | --- |
| `401` | `X-RAG-Admin-Key` is absent or incorrect. |
| `422` | The knowledge document failed request validation. |
| `502` | Embedding generation or Qdrant persistence failed. |
| `503` | `RAG_INGESTION_API_KEY` is not configured. |

## Query stored knowledge

```http
POST /api/v1/rag/query
Content-Type: application/json
```

This route is read-only with respect to Qdrant, although creating the query
embedding still consumes embedding-provider tokens.

### Request

```json
{
  "query": "Send the fullback around the outside",
  "limit": 5,
  "language": "en",
  "minimum_score": 0.5
}
```

| Field | Required | Behavior |
| --- | --- | --- |
| `query` | Yes | Non-empty text, at most 500 characters. |
| `limit` | No | Number of matches, from 1 through 20; default is 5. |
| `language` | No | Exact payload filter such as `en`; it is applied before result selection. |
| `minimum_score` | No | Discards results below this cosine-proximity threshold. |

### Processing

```text
query text
  -> embedding provider using the ingestion model and dimensions
  -> query vector
  -> Qdrant cosine-proximity search
  -> optional language and minimum-score filtering
  -> descending ranked matches
  -> KnowledgeQueryResponse
```

Qdrant compares the query vector with the stored concept vectors. The repository
does not ask an LLM to judge, reorder, or rewrite the matches. The score and
ordering returned by Qdrant are preserved.

### Successful response

Status: `200 OK`

```json
{
  "query": "Send the fullback around the outside",
  "matches": [
    {
      "document_id": "tactic.overlap",
      "canonical_term": "OVERLAP",
      "display_name": "Overlapping run",
      "category": "tactical_movement",
      "definition": "A supporting player runs outside the wide ball carrier to create a passing option.",
      "aliases": ["overlapping run", "run around the outside"],
      "language": "en",
      "locale": "en-GB",
      "score": 0.934,
      "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ],
  "embedding_model": "text-embedding-3-small",
  "token_count": 8
}
```

`matches` is empty when the collection does not exist or no stored point passes
the supplied filters. An empty result is a successful query, not an error.

### Proximity score

The collection uses cosine distance, and Qdrant returns a similarity score for
each match. In this configuration:

- larger values indicate closer vector direction and stronger semantic
  proximity;
- `1.0` represents identical vector direction;
- unrelated or opposing vectors can have scores near zero or below zero; and
- the score is not a probability, confidence percentage, or factuality measure.

Scores should only be compared within the same collection and embedding-model
version. A score of `0.80` does not universally mean “80% relevant.” Vocabulary,
document construction, model choice, and the query distribution all influence
the observed values.

Choose `minimum_score` empirically using an evaluation set. For example, record
expected matches for coaching prompts, inspect the score distributions of
correct and incorrect results, and select a threshold that balances missed
concepts against irrelevant matches. Do not copy an arbitrary threshold into
production without this evaluation.

### Response fields

| Field | Source |
| --- | --- |
| `query` | Validated request text. |
| `matches` | Qdrant results in descending proximity order. |
| `matches[].score` | Unmodified Qdrant vector-search score. |
| Concept fields | Payload stored during ingestion. |
| `embedding_model` | Model identifier returned for the query vector. |
| `token_count` | Usage for creating the query embedding. |

### Errors

| Status | Meaning |
| --- | --- |
| `422` | Query text, limit, language, or minimum score failed validation. |
| `502` | Query embedding or Qdrant search failed. |

## Current boundary

The query endpoint performs retrieval only. It does not generate prose, create
a tactical intent, or alter beam-search weights. Connecting retrieved concepts
to bounded planner preferences belongs to the future inference layer.
