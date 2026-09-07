import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager

from app.models.animation_response import AnimationResponse, CommentaryTrack
from app.models.field_submission import FieldSubmission

# Bump when engine behavior or cached response compatibility changes.
ENGINE_CACHE_VERSION = "triangles-v1"


def configuration_hash(submission: FieldSubmission) -> str:
    """Exact normalized input identity, excluding per-request cancellation IDs."""
    data = submission.model_dump(mode="json", by_alias=True)
    data.pop("analysisId", None)
    field = data["fieldConfiguration"]
    for collection in ("players", "teams", "goals", "openSpaces"):
        field[collection] = sorted(field[collection], key=lambda item: item["id"])
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return 0 if isinstance(value, (int, float)) and value == 0 else value
    encoded = json.dumps(
        {"engine": ENGINE_CACHE_VERSION, "submission": normalize(data)},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


class SolutionCache:
    """SQLite transactions serialize LRU updates across threads and workers."""

    def __init__(self, path: Path, capacity: int = 50):
        if not 1 <= capacity <= 50:
            raise ValueError("Solution cache capacity must be between 1 and 50")
        self.path = Path(path)
        self.capacity = capacity

    @contextmanager
    def _connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS solutions (field_hash TEXT PRIMARY KEY, submission TEXT NOT NULL, response TEXT NOT NULL, accessed INTEGER NOT NULL)")
                connection.execute("BEGIN IMMEDIATE")
                yield connection
        finally:
            connection.close()

    def get(self, field_hash: str):
        with self._connection() as connection:
            row = connection.execute("SELECT submission, response FROM solutions WHERE field_hash = ?", (field_hash,)).fetchone()
            if row is None:
                return None
            connection.execute("UPDATE solutions SET accessed = ? WHERE field_hash = ?", (time.time_ns(), field_hash))
            return FieldSubmission.model_validate_json(row[0]), AnimationResponse.model_validate_json(row[1])

    def put(self, field_hash: str, submission: FieldSubmission, response: AnimationResponse) -> AnimationResponse:
        with self._connection() as connection:
            # Concurrent completions for the same input retain the first result.
            connection.execute(
                "INSERT OR IGNORE INTO solutions VALUES (?, ?, ?, ?)",
                (field_hash, submission.model_dump_json(by_alias=True), response.model_dump_json(), time.time_ns()),
            )
            connection.execute("UPDATE solutions SET accessed = ? WHERE field_hash = ?", (time.time_ns(), field_hash))
            connection.execute("DELETE FROM solutions WHERE field_hash NOT IN (SELECT field_hash FROM solutions ORDER BY accessed DESC, field_hash LIMIT ?)", (self.capacity,))
            row = connection.execute("SELECT response FROM solutions WHERE field_hash = ?", (field_hash,)).fetchone()
            return AnimationResponse.model_validate_json(row[0])

    def save_commentary(self, field_hash: str, plan_id: str, commentary: CommentaryTrack) -> CommentaryTrack:
        """Merge narration atomically, preserving concurrent updates to other plans."""
        with self._connection() as connection:
            row = connection.execute("SELECT response FROM solutions WHERE field_hash = ?", (field_hash,)).fetchone()
            # Eviction while generating narration must not resurrect an old entry.
            if row is None:
                return commentary
            response = AnimationResponse.model_validate_json(row[0])
            def merge(plan):
                nonlocal commentary
                tracks = dict(plan.commentary_by_language)
                if plan.commentary is not None:
                    tracks.setdefault(plan.commentary.language, plan.commentary)
                existing = tracks.get(commentary.language)
                if existing is not None and existing.script == commentary.script:
                    commentary = existing
                tracks[commentary.language] = commentary
                return plan.model_copy(update={
                    "commentary_by_language": tracks,
                    "commentary": tracks.get("en"),
                })
            if plan_id == "requested":
                response = merge(response)
            else:
                plan = next((plan for plan in response.alternative_plans if plan.id == plan_id), None)
                if plan is None:
                    return commentary
                response = response.model_copy(update={"alternative_plans": tuple(
                    merge(plan) if plan.id == plan_id else plan
                    for plan in response.alternative_plans
                )})
            connection.execute("UPDATE solutions SET response = ?, accessed = ? WHERE field_hash = ?",
                               (response.model_dump_json(), time.time_ns(), field_hash))
            return commentary


solution_cache = SolutionCache(Path(os.environ.get(
    "SOCCER_SOLUTION_CACHE_PATH",
    str(Path(__file__).resolve().parents[2] / "data" / "solution_cache" / "solutions.sqlite3"),
)))
