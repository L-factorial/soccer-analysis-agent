"""Feature-flagged tactical LLM orchestration.

The LLM chooses a typed tactical intent. The deterministic engine remains
authoritative for rules, simulation, search, and animation.
"""

from app.agent.config import AgentConfig, PlanningMode
from app.agent.models import AgentPlanningMetadata, TacticalIntent
from app.agent.service import AgentPlanningRun, TacticalAgent

__all__ = [
    "AgentConfig",
    "PlanningMode",
    "AgentPlanningMetadata",
    "AgentPlanningRun",
    "TacticalAgent",
    "TacticalIntent",
]
