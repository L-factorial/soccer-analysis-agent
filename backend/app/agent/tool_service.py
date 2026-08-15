from dataclasses import replace
import json
import re

from app.agent.config import AgentConfig
from app.agent.models import AgentPlanningMetadata
from app.agent.observation import build_tactical_observation
from app.agent.service import AgentPlanningRun
from app.phases import (
    PhaseScoringPolicy,
    PhaseSearchNode,
    PhaseSearchPolicy,
    PhaseSearchResult,
    search_tactical_phases,
)
from app.planning import AnalyzedGameState


TOOL_AGENT_PROMPT = """You are a bounded soccer planning agent. Use the search tool
to find one plan that follows the coach's instruction and, when useful, one or two
meaningfully different alternatives. LEFT and RIGHT are always relative to the
attacking team's direction, using the lateralChannel values in the observation.
When the coach explicitly requests a channel, pass it as requiredLateralChannels.
Soccer legality is decided only by tool results.
Never invent sequence IDs. Prefer a compliant requested plan as primary. Alternatives
may relax tactical preferences. After finding a compliant primary plan, run at least
one relaxed search without the instruction's channel/space constraints. Select an
alternative only when it is structurally different and has a higher deterministic
score or shorter duration; state that measurable advantage and any instruction
trade-off in the reason. Finish by calling select_plans exactly once."""


SEARCH_TOOL = {
    "type": "function",
    "name": "search_tactical_sequences",
    "description": "Run one complete deterministic beam search from the initial state.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "requiredSpaceIds": {"type": "array", "items": {"type": "string"}},
            "preferredSpaceIds": {"type": "array", "items": {"type": "string"}},
            "forbiddenSpaceIds": {"type": "array", "items": {"type": "string"}},
            "requiredLateralChannels": {
                "type": "array", "items": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT"]}
            },
            "preferredLateralChannels": {
                "type": "array", "items": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT"]}
            },
            "forbiddenLateralChannels": {
                "type": "array", "items": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT"]}
            },
            "preferredPlayerIds": {"type": "array", "items": {"type": "string"}},
            "preferredActionTypes": {"type": "array", "items": {"type": "string"}},
            "maximumDepth": {"type": "integer", "minimum": 1, "maximum": 10},
            "beamWidth": {"type": "integer", "minimum": 1, "maximum": 30},
            "purpose": {"type": "string"},
        },
        "required": [
            "requiredSpaceIds", "preferredSpaceIds", "forbiddenSpaceIds",
            "requiredLateralChannels", "preferredLateralChannels",
            "forbiddenLateralChannels",
            "preferredPlayerIds", "preferredActionTypes", "maximumDepth",
            "beamWidth", "purpose",
        ],
        "additionalProperties": False,
    },
}

SELECT_TOOL = {
    "type": "function",
    "name": "select_plans",
    "description": "Select the requested plan and up to two alternatives from tool results.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "primarySequenceId": {"type": "string"},
            "alternativeSequenceIds": {
                "type": "array", "items": {"type": "string"}, "maxItems": 2
            },
            "alternativeReasons": {
                "type": "array", "items": {"type": "string"}, "maxItems": 2
            },
        },
        "required": [
            "primarySequenceId", "alternativeSequenceIds", "alternativeReasons"
        ],
        "additionalProperties": False,
    },
}


def _uses_spaces(node: PhaseSearchNode) -> set[str]:
    return {
        step.phase.primary_action.target_zone_id
        for step in node.steps
        if step.phase.primary_action.target_zone_id is not None
    }


def _sequence_signature(node: PhaseSearchNode) -> tuple:
    return tuple(
        (
            step.phase.primary_action.action_type.value,
            step.phase.primary_action.actor_id,
            step.phase.primary_action.receiver_id,
            step.phase.primary_action.target_zone_id,
        )
        for step in node.steps
    )


def _objective_score(node: PhaseSearchNode, score_discount: float = 0.9) -> float:
    """Compare searches without counting instruction-specific preference bonuses."""
    return sum(
        score_discount ** (step.depth - 1)
        * (step.score.total - step.score.tactical_preference)
        for step in node.steps
    )


def _explicit_channels(instruction: str) -> set[str]:
    words = set(re.findall(r"[a-z]+", instruction.lower()))
    channels = set()
    if "left" in words:
        channels.add("LEFT")
    if "right" in words:
        channels.add("RIGHT")
    if words.intersection({"center", "central", "middle"}):
        channels.add("CENTER")
    return channels


class ToolAgentNoCompliantPlanError(ValueError):
    pass


class ToolPlanningAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def plan(
        self,
        analyzed: AnalyzedGameState,
        instruction: str,
        base_policy: PhaseSearchPolicy,
    ) -> AgentPlanningRun:
        from openai import OpenAI

        observation = build_tactical_observation(analyzed, instruction)
        space_channels = {
            space["id"]: space["lateralChannel"] for space in observation.spaces
        }
        valid_spaces = set(space_channels)
        valid_players = {player["id"] for player in observation.players}
        requested_channels = _explicit_channels(instruction)
        sequences: dict[str, tuple[PhaseSearchNode, PhaseSearchResult]] = {}
        selected: dict | None = None
        tool_calls = 0
        iterations = 0
        inputs: list = [
            {"role": "system", "content": TOOL_AGENT_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "instruction": instruction,
                        "observation": observation.model_dump(by_alias=True),
                        "limits": {
                            "maximumToolCalls": self._config.maximum_tool_calls,
                            "maximumBeamWidth": self._config.maximum_tool_beam_width,
                            "maximumAlternatives": 2,
                        },
                    }
                ),
            },
        ]
        client = OpenAI(timeout=self._config.timeout_seconds)

        for _ in range(self._config.maximum_agent_iterations):
            iterations += 1
            response = client.responses.create(
                model=self._config.model,
                input=inputs,
                tools=[SEARCH_TOOL, SELECT_TOOL],
            )
            inputs.extend(response.output)
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                break
            for call in calls:
                if tool_calls >= self._config.maximum_tool_calls:
                    break
                tool_calls += 1
                arguments = json.loads(call.arguments)
                if call.name == "search_tactical_sequences":
                    output = self._search(
                        analyzed, base_policy, arguments, valid_spaces, valid_players,
                        sequences, space_channels, requested_channels,
                    )
                elif call.name == "select_plans":
                    output = self._select(
                        arguments, sequences, requested_channels, space_channels
                    )
                    if output["accepted"]:
                        selected = arguments
                else:
                    output = {"error": "unknown_tool"}
                inputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(output),
                    }
                )
            if selected is not None:
                break

        if not sequences:
            raise ValueError("The tool agent did not run a tactical search")
        if selected is None:
            raise ToolAgentNoCompliantPlanError(
                "No plan satisfying the explicitly requested channel was selected"
            )
        primary_id = selected["primarySequenceId"]
        primary, result = sequences[primary_id]
        alternative_ids = selected.get("alternativeSequenceIds", [])
        alternatives = tuple(
            sequences[sequence_id][0]
            for sequence_id in alternative_ids[:2]
            if sequence_id in sequences and sequence_id != primary_id
        )
        reasons = tuple(
            str(reason)
            for reason in selected.get("alternativeReasons", [])
        )[:len(alternatives)]
        ordered = (primary, *(node for node in result.best_sequences if node.id != primary.id))
        result = replace(result, best_sequences=ordered)
        return AgentPlanningRun(
            result=result,
            metadata=AgentPlanningMetadata(
                mode="TOOL_AGENT",
                model=self._config.model,
                attempts=iterations,
                toolCalls=tool_calls,
                agentIterations=iterations,
            ),
            alternative_sequences=alternatives,
            alternative_reasons=reasons,
        )

    def _search(
        self, analyzed, base_policy, arguments, valid_spaces, valid_players, sequences,
        space_channels, requested_channels,
    ) -> dict:
        required = tuple(
            value for value in arguments["requiredSpaceIds"] if value in valid_spaces
        )
        preferred = tuple(dict.fromkeys((*required, *(
            value for value in arguments["preferredSpaceIds"] if value in valid_spaces
        ))))
        forbidden = {
            value for value in arguments["forbiddenSpaceIds"] if value in valid_spaces
        }
        required_channels = set(arguments["requiredLateralChannels"])
        preferred_channels = set(arguments["preferredLateralChannels"])
        forbidden_channels = set(arguments["forbiddenLateralChannels"])
        channel_preferred_spaces = tuple(
            space_id for space_id, channel in space_channels.items()
            if channel in required_channels | preferred_channels
        )
        preferred = tuple(dict.fromkeys((*preferred, *channel_preferred_spaces)))
        policy = replace(
            base_policy,
            maximum_depth=min(10, max(1, arguments["maximumDepth"])),
            beam_width=min(
                self._config.maximum_tool_beam_width,
                max(1, arguments["beamWidth"]),
            ),
            maximum_retained_nodes=max(
                base_policy.maximum_retained_nodes,
                min(600, arguments["beamWidth"] * arguments["maximumDepth"] * 3),
            ),
        )
        scoring = PhaseScoringPolicy(
            preferred_space_ids=preferred,
            preferred_player_ids=tuple(
                value for value in arguments["preferredPlayerIds"] if value in valid_players
            ),
            preferred_action_types=tuple(arguments["preferredActionTypes"]),
        )
        result = search_tactical_phases(analyzed, policy, scoring_policy=scoring)
        search_ids = {key.split(":", 1)[0] for key in sequences}
        search_id = f"search-{len(search_ids) + 1:03d}"
        attacking_team = analyzed.game_state.possession.team_id
        candidates = []
        for node in result.best_sequences:
            spaces = _uses_spaces(node)
            used_channels = {
                space_channels[space_id]
                for space_id in spaces
                if space_id in space_channels
            }
            instruction_compliant = requested_channels.issubset(used_channels)
            if node.analyzed_state.game_state.scoring_team_id != attacking_team:
                continue
            if required and not set(required).issubset(spaces):
                continue
            if spaces.intersection(forbidden):
                continue
            if required_channels and not required_channels.issubset(used_channels):
                continue
            if used_channels.intersection(forbidden_channels):
                continue
            sequence_id = f"{search_id}:{node.id}"
            sequences[sequence_id] = (node, result)
            candidates.append(
                {
                    "sequenceId": sequence_id,
                    "score": round(node.cumulative_score, 3),
                    "objectiveScore": round(
                        _objective_score(node, policy.score_discount), 3
                    ),
                    "durationSeconds": round(node.duration_seconds, 3),
                    "targetedSpaceIds": sorted(spaces),
                    "lateralChannels": sorted(used_channels),
                    "instructionCompliant": instruction_compliant,
                    "phases": [
                        {
                            "actionType": step.phase.primary_action.action_type.value,
                            "actorId": step.phase.primary_action.actor_id,
                            "receiverId": step.phase.primary_action.receiver_id,
                            "targetZoneId": step.phase.primary_action.target_zone_id,
                        }
                        for step in node.steps
                    ],
                }
            )
            if len(candidates) == 5:
                break
        return {
            "purpose": arguments["purpose"],
            "sequences": candidates,
            "reachedDepth": result.diagnostics.reached_depth,
            "rejectionReasons": dict(result.diagnostics.invalid_issue_counts),
        }

    @staticmethod
    def _select(arguments: dict, sequences: dict, requested_channels, space_channels) -> dict:
        ids = [arguments["primarySequenceId"], *arguments["alternativeSequenceIds"]]
        unknown = [sequence_id for sequence_id in ids if sequence_id not in sequences]
        primary = sequences.get(arguments["primarySequenceId"])
        primary_channels = (
            {space_channels.get(space_id) for space_id in _uses_spaces(primary[0])}
            if primary is not None else set()
        )
        missing_channels = sorted(requested_channels - primary_channels)
        known_nodes = [sequences[sequence_id][0] for sequence_id in ids if sequence_id in sequences]
        signatures = [_sequence_signature(node) for node in known_nodes]
        duplicates = len(signatures) != len(set(signatures))
        primary_node = primary[0] if primary is not None else None
        not_better = []
        if primary_node is not None:
            primary_score = _objective_score(primary_node)
            for sequence_id in arguments["alternativeSequenceIds"]:
                candidate = sequences.get(sequence_id)
                if candidate is None:
                    continue
                node = candidate[0]
                if not (
                    _objective_score(node) > primary_score + 1e-6
                    or node.duration_seconds < primary_node.duration_seconds - 0.1
                ):
                    not_better.append(sequence_id)
        return {
            "accepted": (
                not unknown and not missing_channels and not duplicates and not not_better
            ),
            "unknownSequenceIds": unknown,
            "missingRequestedChannels": missing_channels,
            "duplicatePlans": duplicates,
            "alternativesWithoutMeasuredAdvantage": not_better,
        }
