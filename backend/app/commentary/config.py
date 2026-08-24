"""Environment-backed configuration for the removable commentary prototype."""

from dataclasses import dataclass
import os
from pathlib import Path


def _load_backend_environment() -> None:
    """Load this prototype's simple KEY=VALUE file without a new dependency."""
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


# Load only the backend-local file and never override variables supplied by the
# process or deployment environment.
_load_backend_environment()


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CommentaryConfig:
    enabled: bool
    model: str
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "CommentaryConfig":
        return cls(
            enabled=_enabled(os.getenv("SOCCER_COMMENTARY_ENABLED")),
            model=os.getenv("SOCCER_COMMENTARY_MODEL", "gpt-5.6-luna"),
            timeout_seconds=float(
                os.getenv("SOCCER_COMMENTARY_TIMEOUT_SECONDS", "15")
            ),
        )
