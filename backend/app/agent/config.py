from dataclasses import dataclass
from enum import StrEnum
import os


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


class PlanningMode(StrEnum):
    """Mutually exclusive orchestration modes selected from environment config."""
    DETERMINISTIC = "DETERMINISTIC"
    LLM_INTENT = "LLM_INTENT"
    LLM_TOOL_AGENT = "LLM_TOOL_AGENT"


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Validated environment-backed limits for LLM orchestration.

    Search and simulation rules do not live here; this config only bounds model
    calls, revisions, tool iterations, timeouts, and tool-requested search size.
    """
    """Runtime settings; disabled is the safe default."""

    enabled: bool = False
    model: str = "gpt-5-mini"
    timeout_seconds: float = 8
    maximum_revisions: int = 1
    planning_mode: PlanningMode = PlanningMode.DETERMINISTIC
    maximum_tool_calls: int = 8
    maximum_agent_iterations: int = 6
    maximum_tool_beam_width: int = 30

    @classmethod
    def from_environment(cls) -> "AgentConfig":
        configured_mode = os.getenv("SOCCER_PLANNING_MODE", "").strip().upper()
        if configured_mode:
            mode = PlanningMode(configured_mode)
        elif _enabled(os.getenv("SOCCER_AGENTIC_PLANNING_ENABLED")):
            mode = PlanningMode.LLM_INTENT
        else:
            mode = PlanningMode.DETERMINISTIC
        return cls(
            enabled=mode != PlanningMode.DETERMINISTIC,
            model=os.getenv("SOCCER_AGENT_MODEL", "gpt-5-mini"),
            timeout_seconds=float(os.getenv("SOCCER_AGENT_TIMEOUT_SECONDS", "8")),
            maximum_revisions=min(
                1,
                max(0, int(os.getenv("SOCCER_AGENT_MAXIMUM_REVISIONS", "1"))),
            ),
            planning_mode=mode,
            maximum_tool_calls=max(
                1, int(os.getenv("SOCCER_TOOL_AGENT_MAX_TOOL_CALLS", "8"))
            ),
            maximum_agent_iterations=max(
                1, int(os.getenv("SOCCER_TOOL_AGENT_MAX_ITERATIONS", "6"))
            ),
            maximum_tool_beam_width=min(
                30,
                max(1, int(os.getenv("SOCCER_TOOL_MAX_BEAM_WIDTH", "30"))),
            ),
        )
