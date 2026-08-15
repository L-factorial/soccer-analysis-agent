from dataclasses import dataclass

from app.agent.config import AgentConfig
from app.agent.evaluator import evaluate_plan
from app.agent.llm_client import OpenAITacticalIntentClient, TacticalIntentClient
from app.agent.models import AgentPlanningMetadata
from app.agent.observation import build_tactical_observation
from app.agent.policy_adapter import adapt_intent_to_policies
from app.agent.validation import validate_intent_references
from app.phases import (
    PhaseSearchNode,
    PhaseSearchPolicy,
    PhaseSearchResult,
    search_tactical_phases,
)
from app.planning import AnalyzedGameState


@dataclass(frozen=True, slots=True)
class AgentPlanningRun:
    result: PhaseSearchResult
    metadata: AgentPlanningMetadata
    applied_directives: tuple[str, ...] = ()
    alternative_sequences: tuple[PhaseSearchNode, ...] = ()
    alternative_reasons: tuple[str, ...] = ()


class TacticalAgent:
    """A bounded observe-decide-plan-evaluate-revise loop."""

    def __init__(
        self,
        config: AgentConfig,
        client: TacticalIntentClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or OpenAITacticalIntentClient(config)

    def plan(
        self,
        analyzed: AnalyzedGameState,
        instruction: str,
        base_search_policy: PhaseSearchPolicy,
    ) -> AgentPlanningRun:
        observation = build_tactical_observation(analyzed, instruction)
        intent = evaluation = None
        result = None
        attempts = 0
        for attempt in range(self._config.maximum_revisions + 1):
            intent = self._client.choose_intent(observation, intent, evaluation)
            intent = validate_intent_references(intent, observation)
            policies = adapt_intent_to_policies(intent, base_search_policy)
            result = search_tactical_phases(
                analyzed,
                policies.search,
                scoring_policy=policies.scoring,
            )
            evaluation = evaluate_plan(result, intent)
            attempts = attempt + 1
            if evaluation.goal_scored and evaluation.instruction_alignment >= 0.5:
                break
        assert result is not None and intent is not None and evaluation is not None
        return AgentPlanningRun(
            result=result,
            metadata=AgentPlanningMetadata(
                mode="AGENTIC",
                model=self._config.model,
                attempts=attempts,
                intent=intent,
                evaluation=evaluation,
            ),
        )
