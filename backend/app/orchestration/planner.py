from dataclasses import dataclass
import logging
from typing import Callable

from app.agent import (
    AgentConfig,
    AgentPlanningMetadata,
    AgentPlanningRun,
    PlanningMode,
)
from app.phases import PhaseSearchPolicy
from app.tactical_instruction import interpret_tactical_instruction


@dataclass(frozen=True, slots=True)
class PlannerDependencies:
    deterministic_search: Callable
    tactical_agent_factory: Callable
    tool_agent_factory: Callable


def run_tactical_planner(
    analyzed,
    instruction: str | None,
    base_search_policy: PhaseSearchPolicy,
    config: AgentConfig,
    dependencies: PlannerDependencies,
    logger: logging.Logger,
) -> AgentPlanningRun:
    """Choose orchestration mode while keeping the tactical engine deterministic."""
    fallback_reason = None
    if config.enabled and instruction and instruction.strip():
        try:
            # Tool mode lets the model request bounded complete searches. Intent
            # mode lets it choose one bounded policy and the backend searches.
            if config.planning_mode == PlanningMode.LLM_TOOL_AGENT:
                return dependencies.tool_agent_factory(config).plan(
                    analyzed, instruction, base_search_policy
                )
            return dependencies.tactical_agent_factory(config).plan(
                analyzed, instruction, base_search_policy
            )
        except Exception as error:
            # Instruction-compliance failures are API concerns and must remain
            # distinguishable from external LLM failures.
            if type(error).__name__ == "ToolAgentNoCompliantPlanError":
                raise
            logger.exception("Agentic planning failed; using deterministic fallback")
            fallback_reason = type(error).__name__

    # Empty prompts, disabled agentic mode, and external failures all converge
    # here, preserving a reliable deterministic product path.
    instruction_policy = interpret_tactical_instruction(
        instruction,
        base_search_policy,
    )
    result = dependencies.deterministic_search(
        analyzed,
        instruction_policy.search,
        scoring_policy=instruction_policy.scoring,
    )
    return AgentPlanningRun(
        result=result,
        metadata=AgentPlanningMetadata(
            mode="AGENTIC_FALLBACK" if fallback_reason else "DETERMINISTIC",
            fallbackReason=fallback_reason,
        ),
        applied_directives=instruction_policy.applied_directives,
    )
