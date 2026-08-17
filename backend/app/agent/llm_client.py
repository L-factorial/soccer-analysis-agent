import json
from typing import Protocol

from app.agent.config import AgentConfig
from app.agent.models import PlanEvaluation, TacticalIntent, TacticalObservation


# The intent-mode model is constrained to tactical preferences. Structured
# parsing below prevents it from emitting executable state transitions.
SYSTEM_PROMPT = """You are a soccer tactical director. Convert the coach's instruction
and analyzed field observation into one supported tactical intent. Choose strategy only.
Never invent player IDs, space IDs, action types, coordinates, or game rules. The
deterministic engine is authoritative for legality, movement, offside, and scoring."""


class TacticalIntentClient(Protocol):
    def choose_intent(
        self,
        observation: TacticalObservation,
        previous_intent: TacticalIntent | None = None,
        evaluation: PlanEvaluation | None = None,
    ) -> TacticalIntent: ...


class OpenAITacticalIntentClient:
    """Thin official-SDK adapter; deliberately contains no agent framework."""

    def __init__(self, config: AgentConfig):
        self._config = config

    def choose_intent(
        self,
        observation: TacticalObservation,
        previous_intent: TacticalIntent | None = None,
        evaluation: PlanEvaluation | None = None,
    ) -> TacticalIntent:
        from openai import OpenAI

        payload: dict = {
            "observation": observation.model_dump(by_alias=True),
            "supportedObjectives": [
                "BALANCED", "FAST_ATTACK", "RETAIN_POSSESSION",
                "CREATE_SPACE", "WIDE_OVERLOAD",
            ],
        }
        if previous_intent is not None and evaluation is not None:
            payload["previousAttempt"] = {
                "intent": previous_intent.model_dump(by_alias=True),
                "evaluation": evaluation.model_dump(by_alias=True),
                "request": "Revise the intent to address the evaluation reasons.",
            }
        response = OpenAI(timeout=self._config.timeout_seconds).responses.parse(
            model=self._config.model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            text_format=TacticalIntent,
        )
        if response.output_parsed is None:
            raise ValueError("The model did not return a tactical intent")
        return response.output_parsed
