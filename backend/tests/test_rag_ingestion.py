import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from qdrant_client import QdrantClient

from app.rag.ingestion import prepare_knowledge_file
from app.rag.repository import QdrantConfig, QdrantKnowledgeRepository
from app.rag.schemas import EmbeddingBatch, EmbeddingVector


OVERLAP_DOCUMENT_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "soccer_knowledge"
    / "concepts"
    / "overlap.yaml"
)


class StubEmbeddingProvider:
    """Small deterministic provider that keeps ingestion tests offline."""

    def __init__(self) -> None:
        self.received_texts: list[str] = []

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        self.received_texts.extend(texts)
        return EmbeddingBatch(
            embeddings=(
                EmbeddingVector(
                    vector=(0.1, 0.2, 0.3),
                    model="test-embedding-model",
                    dimensions=3,
                ),
            ),
            total_tokens=42,
        )


class RagIngestionPreparationTests(unittest.TestCase):
    def test_prepares_a_validated_file_and_its_embedding(self) -> None:
        provider = StubEmbeddingProvider()

        prepared = prepare_knowledge_file(OVERLAP_DOCUMENT_PATH, provider)

        self.assertEqual(prepared.document.id, "tactic.overlap")
        self.assertEqual(provider.received_texts, [prepared.embedding_text])
        self.assertEqual(prepared.embedding.vector, (0.1, 0.2, 0.3))
        self.assertEqual(prepared.embedding.model, "test-embedding-model")
        self.assertEqual(prepared.token_count, 42)
        self.assertEqual(len(prepared.content_hash), 64)

    def test_content_hash_is_stable_for_the_same_semantic_projection(self) -> None:
        first = prepare_knowledge_file(
            OVERLAP_DOCUMENT_PATH,
            StubEmbeddingProvider(),
        )
        second = prepare_knowledge_file(
            OVERLAP_DOCUMENT_PATH,
            StubEmbeddingProvider(),
        )

        self.assertEqual(first.content_hash, second.content_hash)

    def test_invalid_yaml_stops_before_embedding(self) -> None:
        provider = StubEmbeddingProvider()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.yaml"
            path.write_text("id: invalid\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                prepare_knowledge_file(path, provider)

        self.assertEqual(provider.received_texts, [])

    def test_rejects_a_provider_result_without_exactly_one_embedding(self) -> None:
        class EmptyEmbeddingProvider:
            def embed(self, texts: list[str]) -> EmbeddingBatch:
                return EmbeddingBatch(embeddings=(), total_tokens=0)

        with self.assertRaisesRegex(ValueError, "exactly one embedding"):
            prepare_knowledge_file(
                OVERLAP_DOCUMENT_PATH,
                EmptyEmbeddingProvider(),
            )


class QdrantKnowledgeRepositoryTests(unittest.TestCase):
    def test_upserts_the_vector_and_search_payload(self) -> None:
        prepared = prepare_knowledge_file(
            OVERLAP_DOCUMENT_PATH,
            StubEmbeddingProvider(),
        )
        client = QdrantClient(":memory:")
        repository = QdrantKnowledgeRepository(
            QdrantConfig(path=Path("unused")),
            client=client,
        )

        first_point_id = repository.upsert(prepared)
        second_point_id = repository.upsert(prepared)

        self.assertEqual(first_point_id, second_point_id)
        stored = client.retrieve(
            collection_name="soccer_knowledge",
            ids=[first_point_id],
            with_payload=True,
            with_vectors=True,
        )
        self.assertEqual(len(stored), 1)
        # Cosine collections normalize stored vectors; persistence preserves
        # direction rather than the original magnitude.
        self.assertAlmostEqual(stored[0].vector[0], 0.26726124)
        self.assertAlmostEqual(stored[0].vector[1], 0.53452247)
        self.assertAlmostEqual(stored[0].vector[2], 0.80178374)
        self.assertEqual(stored[0].payload["document_id"], "tactic.overlap")
        self.assertEqual(stored[0].payload["canonical_term"], "OVERLAP")
        self.assertEqual(stored[0].payload["content_hash"], prepared.content_hash)


if __name__ == "__main__":
    unittest.main()
