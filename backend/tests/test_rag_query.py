import unittest

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.main import app
from app.rag.dependencies import get_embedding_provider, get_knowledge_repository
from app.rag.embeddings import build_embedding_text
from app.rag.repository import QdrantConfig, QdrantKnowledgeRepository
from app.rag.schemas import (
    EmbeddingBatch,
    EmbeddingVector,
    KnowledgeDocument,
    KnowledgeMatch,
    PreparedKnowledgeRecord,
)
from tests.test_rag_schemas import valid_knowledge_document


def prepared_record(
    document: KnowledgeDocument,
    vector: tuple[float, ...],
) -> PreparedKnowledgeRecord:
    return PreparedKnowledgeRecord(
        document=document,
        embedding_text=build_embedding_text(document),
        content_hash="a" * 64,
        embedding=EmbeddingVector(
            vector=vector,
            model="test-embedding-model",
            dimensions=len(vector),
        ),
        token_count=10,
    )


class QdrantKnowledgeQueryTests(unittest.TestCase):
    def test_returns_matches_in_score_order_with_vector_proximity(self) -> None:
        overlap = KnowledgeDocument.model_validate(valid_knowledge_document())
        underlap = overlap.model_copy(
            update={
                "id": "tactic.underlap",
                "canonical_term": "UNDERLAP",
                "display_name": "Underlapping run",
                "definition": "A supporting player runs inside the wide ball carrier.",
            }
        )
        client = QdrantClient(":memory:")
        repository = QdrantKnowledgeRepository(
            QdrantConfig(path="unused"),
            client=client,
        )
        repository.upsert(prepared_record(overlap, (1.0, 0.0, 0.0)))
        repository.upsert(prepared_record(underlap, (0.0, 1.0, 0.0)))

        matches = repository.search(
            EmbeddingVector(
                vector=(1.0, 0.0, 0.0),
                model="test-embedding-model",
                dimensions=3,
            ),
            limit=2,
        )

        self.assertEqual([match.canonical_term for match in matches], ["OVERLAP", "UNDERLAP"])
        self.assertAlmostEqual(matches[0].score, 1.0)
        self.assertAlmostEqual(matches[1].score, 0.0)

    def test_minimum_score_removes_distant_matches(self) -> None:
        overlap = KnowledgeDocument.model_validate(valid_knowledge_document())
        repository = QdrantKnowledgeRepository(
            QdrantConfig(path="unused"),
            client=QdrantClient(":memory:"),
        )
        repository.upsert(prepared_record(overlap, (1.0, 0.0, 0.0)))

        matches = repository.search(
            EmbeddingVector(
                vector=(0.0, 1.0, 0.0),
                model="test-embedding-model",
                dimensions=3,
            ),
            limit=5,
            minimum_score=0.5,
        )

        self.assertEqual(matches, ())


class StubEmbeddingProvider:
    def embed(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            embeddings=(
                EmbeddingVector(
                    vector=(1.0, 0.0, 0.0),
                    model="test-embedding-model",
                    dimensions=3,
                ),
            ),
            total_tokens=6,
        )


class RankedRepository:
    def search(self, embedding, limit, language=None, minimum_score=None):
        return (
            KnowledgeMatch(
                document_id="tactic.overlap",
                canonical_term="OVERLAP",
                display_name="Overlapping run",
                category="tactical_movement",
                definition="A supporting player runs outside the wide ball carrier.",
                aliases=("run around the outside",),
                language="en",
                score=0.934,
                content_hash="a" * 64,
            ),
            KnowledgeMatch(
                document_id="tactic.underlap",
                canonical_term="UNDERLAP",
                display_name="Underlapping run",
                category="tactical_movement",
                definition="A supporting player runs inside the wide ball carrier.",
                language="en",
                score=0.612,
                content_hash="b" * 64,
            ),
        )[:limit]


class RagQueryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides[get_embedding_provider] = StubEmbeddingProvider
        app.dependency_overrides[get_knowledge_repository] = RankedRepository
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_returns_each_match_with_its_vector_score(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={
                "query": "Send the fullback around the outside",
                "limit": 2,
                "language": "en",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["embedding_model"], "test-embedding-model")
        self.assertEqual(body["token_count"], 6)
        self.assertEqual(body["matches"][0]["canonical_term"], "OVERLAP")
        self.assertEqual(body["matches"][0]["score"], 0.934)
        self.assertEqual(body["matches"][1]["score"], 0.612)

    def test_rejects_an_empty_query(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={"query": "   "},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
