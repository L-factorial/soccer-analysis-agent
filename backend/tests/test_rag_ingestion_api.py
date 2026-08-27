import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.rag.dependencies import (
    get_embedding_provider,
    get_knowledge_repository,
)
from app.rag.schemas import EmbeddingBatch, EmbeddingVector
from tests.test_rag_schemas import valid_knowledge_document


class StubEmbeddingProvider:
    def embed(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            embeddings=(
                EmbeddingVector(
                    vector=(0.1, 0.2, 0.3),
                    model="test-embedding-model",
                    dimensions=3,
                ),
            ),
            total_tokens=12,
        )


class RecordingRepository:
    def __init__(self) -> None:
        self.prepared = None

    def upsert(self, prepared) -> str:
        self.prepared = prepared
        return "d20e7020-a4ff-541f-b4a2-2fe71b790c47"


class RagIngestionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = RecordingRepository()
        app.dependency_overrides[get_embedding_provider] = StubEmbeddingProvider
        app.dependency_overrides[get_knowledge_repository] = lambda: self.repository
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    @patch.dict(
        "os.environ",
        {"RAG_INGESTION_API_KEY": "test-admin-key"},
        clear=False,
    )
    def test_embeds_and_persists_a_valid_document(self) -> None:
        response = self.client.post(
            "/api/v1/rag/ingestion/documents",
            headers={"X-RAG-Admin-Key": "test-admin-key"},
            json=valid_knowledge_document(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "upserted")
        self.assertEqual(response.json()["document_id"], "tactic.overlap")
        self.assertEqual(response.json()["embedding_model"], "test-embedding-model")
        self.assertEqual(response.json()["dimensions"], 3)
        self.assertEqual(response.json()["token_count"], 12)
        self.assertEqual(self.repository.prepared.document.id, "tactic.overlap")

    @patch.dict(
        "os.environ",
        {"RAG_INGESTION_API_KEY": "test-admin-key"},
        clear=False,
    )
    def test_rejects_an_invalid_admin_key_before_ingestion(self) -> None:
        response = self.client.post(
            "/api/v1/rag/ingestion/documents",
            headers={"X-RAG-Admin-Key": "wrong-key"},
            json=valid_knowledge_document(),
        )

        self.assertEqual(response.status_code, 401)
        self.assertIsNone(self.repository.prepared)

    @patch.dict(
        "os.environ",
        {"RAG_INGESTION_API_KEY": "test-admin-key"},
        clear=False,
    )
    def test_validates_the_document_before_calling_dependencies(self) -> None:
        payload = valid_knowledge_document()
        payload["id"] = "Invalid Document ID"

        response = self.client.post(
            "/api/v1/rag/ingestion/documents",
            headers={"X-RAG-Admin-Key": "test-admin-key"},
            json=payload,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIsNone(self.repository.prepared)


if __name__ == "__main__":
    unittest.main()
