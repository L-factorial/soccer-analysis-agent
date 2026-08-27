import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.rag.embeddings import (
    EmbeddingResponseError,
    OpenAIEmbeddingProvider,
    RagEmbeddingConfig,
    build_embedding_text,
)
from app.rag.ingestion import load_knowledge_document


OVERLAP_DOCUMENT_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "soccer_knowledge"
    / "concepts"
    / "overlap.yaml"
)


class RagEmbeddingTextTests(unittest.TestCase):
    def test_builds_semantic_text_from_the_curated_document(self) -> None:
        document = load_knowledge_document(OVERLAP_DOCUMENT_PATH)

        text = build_embedding_text(document)

        self.assertIn("Canonical term: OVERLAP", text)
        self.assertIn("Name: Overlapping run", text)
        self.assertIn("Category: tactical_movement", text)
        self.assertIn("run around the outside [en-GB]", text)
        self.assertIn("- Have the fullback overlap the winger.", text)
        self.assertIn("Tags: attacking, off-ball-movement, wide-play", text)

    def test_excludes_nonsemantic_storage_and_provenance_fields(self) -> None:
        document = load_knowledge_document(OVERLAP_DOCUMENT_PATH)

        text = build_embedding_text(document)

        self.assertNotIn(document.id, text)
        self.assertNotIn(document.source.reference, text)
        self.assertNotIn(document.source.license, text)
        self.assertNotIn("version", text.casefold())

    def test_building_embedding_text_is_deterministic(self) -> None:
        document = load_knowledge_document(OVERLAP_DOCUMENT_PATH)

        self.assertEqual(
            build_embedding_text(document),
            build_embedding_text(document),
        )


class OpenAIEmbeddingProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.provider = OpenAIEmbeddingProvider(
            config=RagEmbeddingConfig(
                model="text-embedding-3-small",
                dimensions=3,
                timeout_seconds=5,
            ),
            client=self.client,
        )

    def test_embeds_multiple_texts_and_restores_input_order(self) -> None:
        self.client.embeddings.create.return_value = SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.4, 0.5, 0.6]),
                SimpleNamespace(index=0, embedding=[0.1, 0.2, 0.3]),
            ],
            model="text-embedding-3-small",
            usage=SimpleNamespace(total_tokens=14),
        )

        result = self.provider.embed(["overlap", "underlap"])

        self.client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["overlap", "underlap"],
            dimensions=3,
            encoding_format="float",
        )
        self.assertEqual(result.embeddings[0].vector, (0.1, 0.2, 0.3))
        self.assertEqual(result.embeddings[1].vector, (0.4, 0.5, 0.6))
        self.assertEqual(result.total_tokens, 14)

    def test_rejects_empty_input_without_calling_openai(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one text"):
            self.provider.embed([])

        self.client.embeddings.create.assert_not_called()

    def test_rejects_blank_text_without_calling_openai(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            self.provider.embed(["overlap", "  "])

        self.client.embeddings.create.assert_not_called()

    def test_rejects_a_vector_with_the_wrong_dimensions(self) -> None:
        self.client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])],
            model="text-embedding-3-small",
            usage=SimpleNamespace(total_tokens=2),
        )

        with self.assertRaisesRegex(ValueError, "vector length must match"):
            self.provider.embed(["overlap"])

    def test_rejects_response_indices_that_do_not_match_inputs(self) -> None:
        self.client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(index=1, embedding=[0.1, 0.2, 0.3])],
            model="text-embedding-3-small",
            usage=SimpleNamespace(total_tokens=2),
        )

        with self.assertRaises(EmbeddingResponseError):
            self.provider.embed(["overlap"])


if __name__ == "__main__":
    unittest.main()
