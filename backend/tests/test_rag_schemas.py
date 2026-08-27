import unittest
from pathlib import Path

from pydantic import ValidationError

from app.rag.ingestion import load_knowledge_document
from app.rag.schemas import KnowledgeDocument


OVERLAP_DOCUMENT_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "soccer_knowledge"
    / "concepts"
    / "overlap.yaml"
)


def valid_knowledge_document() -> dict:
    return {
        "id": "tactic.overlap",
        "canonical_term": "overlap",
        "display_name": "Overlapping run",
        "category": "tactical_movement",
        "definition": (
            "A supporting player runs outside the wide ball carrier to create "
            "a passing option."
        ),
        "aliases": [
            {"term": "run around the outside", "language": "en", "locale": "en-GB"},
            {"term": "overlapping fullback", "language": "en"},
        ],
        "examples": ["Have the fullback overlap the winger."],
        "related_concept_ids": ["concept.width"],
        "tags": ["attacking", "wide-play"],
        "source": {
            "title": "Internal tactical glossary",
            "reference": "glossary-v1",
            "license": "internal",
        },
    }


class RagSchemaTests(unittest.TestCase):
    def test_loads_and_validates_the_curated_overlap_yaml(self) -> None:
        document = load_knowledge_document(OVERLAP_DOCUMENT_PATH)

        self.assertEqual(document.id, "tactic.overlap")
        self.assertEqual(document.canonical_term, "OVERLAP")
        self.assertEqual(document.locale, "en-GB")
        self.assertEqual(len(document.aliases), 3)

    def test_accepts_a_curated_knowledge_document(self) -> None:
        document = KnowledgeDocument.model_validate(valid_knowledge_document())

        self.assertEqual(document.id, "tactic.overlap")
        self.assertEqual(document.canonical_term, "OVERLAP")
        self.assertEqual(document.aliases[0].locale, "en-GB")
        self.assertEqual(document.version, 1)

    def test_rejects_duplicate_localized_aliases(self) -> None:
        payload = valid_knowledge_document()
        payload["aliases"].append(
            {"term": "Run Around The Outside", "language": "en", "locale": "en-GB"}
        )

        with self.assertRaisesRegex(ValidationError, "aliases must be unique"):
            KnowledgeDocument.model_validate(payload)

    def test_rejects_unknown_fields(self) -> None:
        payload = valid_knowledge_document()
        payload["embedding"] = [0.1, 0.2]

        with self.assertRaises(ValidationError):
            KnowledgeDocument.model_validate(payload)

    def test_rejects_an_invalid_stable_id(self) -> None:
        payload = valid_knowledge_document()
        payload["id"] = "Tactic Overlap"

        with self.assertRaises(ValidationError):
            KnowledgeDocument.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
