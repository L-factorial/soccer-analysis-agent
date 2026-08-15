import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent import AgentConfig, PlanningMode, TacticalAgent, TacticalIntent
from app.agent.models import PlanEvaluation
from app.agent.evaluator import evaluate_plan
from app.agent.observation import build_tactical_observation
from app.agent.tool_service import ToolPlanningAgent
from app.phases import PhaseSearchPolicy
from app.api.field_configurations import (
    _run_planner,
    _sequence_uses_preferred_space,
)
from test_tactical_phases import phase_state


def intent(objective: str = "CREATE_SPACE") -> TacticalIntent:
    return TacticalIntent.model_validate(
        {
            "objective": objective,
            "tempo": "FAST",
            "riskLevel": 0.5,
            "preferredActionTypes": ["PASS_TO_SPACE"],
            "preferredPlayerIds": ["team1-3", "invented-player"],
            "preferredSpaceIds": ["OpenSpace1", "invented-space"],
            "offBallPriorities": ["DECOY_RUN"],
            "reasoningSummary": "Create space before progressing.",
        }
    )


class FakeIntentClient:
    def __init__(self) -> None:
        self.calls = 0

    def choose_intent(self, observation, previous_intent=None, evaluation=None):
        self.calls += 1
        return intent("CREATE_SPACE" if self.calls == 1 else "FAST_ATTACK")


class FakeToolResponses:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            output = [SimpleNamespace(
                type="function_call",
                name="search_tactical_sequences",
                call_id="call-search",
                arguments='{"requiredSpaceIds":[],"preferredSpaceIds":[],'
                '"forbiddenSpaceIds":[],"preferredPlayerIds":[],'
                '"requiredLateralChannels":[],"preferredLateralChannels":[],'
                '"forbiddenLateralChannels":[],'
                '"preferredActionTypes":[],"maximumDepth":8,"beamWidth":10,'
                '"purpose":"requested plan"}',
            )]
        else:
            tool_output = next(
                json.loads(item["output"])
                for item in reversed(kwargs["input"])
                if isinstance(item, dict)
                and item.get("type") == "function_call_output"
            )
            sequence_id = tool_output["sequences"][0]["sequenceId"]
            output = [SimpleNamespace(
                type="function_call",
                name="select_plans",
                call_id="call-select",
                arguments=json.dumps({
                    "primarySequenceId": sequence_id,
                    "alternativeSequenceIds": [],
                    "alternativeReasons": [],
                }),
            )]
        return SimpleNamespace(output=output)


class TacticalAgentTests(unittest.TestCase):
    @patch("openai.OpenAI")
    def test_tool_agent_runs_search_and_select_loop(self, openai_client) -> None:
        responses = FakeToolResponses()
        openai_client.return_value.responses = responses

        run = ToolPlanningAgent(
            AgentConfig(
                enabled=True,
                planning_mode=PlanningMode.LLM_TOOL_AGENT,
                maximum_agent_iterations=3,
            )
        ).plan(phase_state(), "Score a goal", PhaseSearchPolicy())

        self.assertEqual(run.metadata.mode, "TOOL_AGENT")
        self.assertEqual(run.metadata.tool_calls, 2)
        self.assertEqual(run.metadata.agent_iterations, 2)
        self.assertTrue(run.result.best_sequences)

    def test_explicit_planning_mode_takes_precedence_over_legacy_flag(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SOCCER_PLANNING_MODE": "DETERMINISTIC",
                "SOCCER_AGENTIC_PLANNING_ENABLED": "true",
            },
            clear=False,
        ):
            config = AgentConfig.from_environment()

        self.assertEqual(config.planning_mode, PlanningMode.DETERMINISTIC)
        self.assertFalse(config.enabled)

    @patch("app.api.field_configurations.ToolPlanningAgent")
    def test_tool_agent_mode_routes_to_tool_planner(self, tool_agent) -> None:
        expected = object()
        tool_agent.return_value.plan.return_value = expected
        with patch.dict(
            "os.environ",
            {"SOCCER_PLANNING_MODE": "LLM_TOOL_AGENT"},
            clear=False,
        ):
            run = _run_planner(object(), "Attack through OpenSpace2")

        self.assertIs(run, expected)
        tool_agent.return_value.plan.assert_called_once()

    def test_preferred_space_is_a_required_plan_alignment(self) -> None:
        analyzed = phase_state()
        action = SimpleNamespace(
            action_type=SimpleNamespace(value="PASS_TO_SPACE"),
            actor_id="team1-3",
            receiver_id="team1-5",
            target_zone_id="OpenSpace1",
        )
        sequence = SimpleNamespace(
            analyzed_state=SimpleNamespace(
                game_state=SimpleNamespace(scoring_team_id="team1")
            ),
            steps=(
                SimpleNamespace(
                    phase=SimpleNamespace(
                        primary_action=action,
                        attacking_intentions=(),
                    )
                ),
            ),
        )
        result = SimpleNamespace(
            root=analyzed,
            best_sequences=(sequence,),
        )
        requested = intent().model_copy(
            update={"preferred_space_ids": ["OpenSpace2"]}
        )

        evaluation = evaluate_plan(result, requested)

        self.assertTrue(evaluation.goal_scored)
        self.assertEqual(evaluation.instruction_alignment, 0)
        self.assertIn("OpenSpace2", evaluation.reasons[0])
        self.assertFalse(
            _sequence_uses_preferred_space(sequence, ("OpenSpace2",))
        )

    def test_observation_exposes_labeled_ui_and_computed_spaces(self) -> None:
        analyzed = phase_state()
        observation = build_tactical_observation(
            analyzed,
            "Use the labeled opening",
        )

        ui_space = next(
            space for space in observation.spaces
            if space["id"] == "OpenSpace1"
        )
        self.assertEqual(ui_space["name"], "OpenSpace1")
        self.assertEqual(ui_space["source"], "USER_DEFINED")
        self.assertIn(ui_space["lateralChannel"], {"LEFT", "CENTER", "RIGHT"})
        self.assertIn(ui_space["fieldThird"], {"DEFENSIVE", "MIDDLE", "ATTACKING"})
        self.assertIn("nearestDefenderDistanceCm", ui_space)
        self.assertTrue(
            any(space["source"] == "DYNAMIC" for space in observation.spaces)
        )

    @patch("app.api.field_configurations.TacticalAgent")
    @patch("app.api.field_configurations.search_tactical_phases")
    def test_disabled_feature_flag_uses_deterministic_path(
        self,
        search,
        agent_class,
    ) -> None:
        search.return_value = object()
        with patch.dict(
            "os.environ",
            {"SOCCER_AGENTIC_PLANNING_ENABLED": "false"},
            clear=False,
        ):
            run = _run_planner(object(), "Attack quickly")

        agent_class.assert_not_called()
        self.assertEqual(run.metadata.mode, "DETERMINISTIC")
        self.assertIn("FAST_TEMPO", run.applied_directives)

    @patch("app.api.field_configurations.TacticalAgent")
    @patch("app.api.field_configurations.search_tactical_phases")
    def test_agent_failure_falls_back_to_deterministic_path(
        self,
        search,
        agent_class,
    ) -> None:
        search.return_value = object()
        agent_class.return_value.plan.side_effect = RuntimeError("unavailable")
        with patch.dict(
            "os.environ",
            {"SOCCER_AGENTIC_PLANNING_ENABLED": "true"},
            clear=False,
        ):
            run = _run_planner(object(), "Attack quickly")

        self.assertEqual(run.metadata.mode, "AGENTIC_FALLBACK")
        self.assertEqual(run.metadata.fallback_reason, "RuntimeError")
        search.assert_called_once()

    @patch("app.agent.service.search_tactical_phases")
    @patch("app.agent.service.evaluate_plan")
    def test_revises_once_and_filters_hallucinated_references(
        self,
        evaluate,
        search,
    ) -> None:
        analyzed = phase_state(include_shape_attacker=True)
        client = FakeIntentClient()
        search.return_value = object()
        evaluate.side_effect = (
            PlanEvaluation(
                goalScored=False,
                instructionAlignment=0,
                reasons=["No goal"],
            ),
            PlanEvaluation(
                goalScored=True,
                instructionAlignment=1,
                reasons=[],
            ),
        )
        agent = TacticalAgent(
            AgentConfig(enabled=True, maximum_revisions=1),
            client,
        )

        run = agent.plan(
            analyzed,
            "Create space and attack quickly",
            PhaseSearchPolicy(),
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(search.call_count, 2)
        self.assertEqual(run.metadata.mode, "AGENTIC")
        self.assertEqual(run.metadata.attempts, 2)
        self.assertEqual(run.metadata.intent.preferred_player_ids, ["team1-3"])
        self.assertEqual(run.metadata.intent.preferred_space_ids, ["OpenSpace1"])
        first_scoring_policy = search.call_args_list[0].kwargs["scoring_policy"]
        self.assertEqual(
            first_scoring_policy.preferred_action_types,
            ("PASS_TO_SPACE",),
        )
        self.assertEqual(first_scoring_policy.preferred_player_ids, ("team1-3",))
        self.assertEqual(
            first_scoring_policy.preferred_off_ball_intentions,
            ("DECOY_RUN",),
        )

    @patch("app.agent.service.search_tactical_phases")
    @patch("app.agent.service.evaluate_plan")
    def test_stops_after_first_satisfactory_plan(self, evaluate, search) -> None:
        analyzed = phase_state()
        client = FakeIntentClient()
        search.return_value = object()
        evaluate.return_value = PlanEvaluation(
            goalScored=True,
            instructionAlignment=1,
            reasons=[],
        )

        run = TacticalAgent(
            AgentConfig(enabled=True, maximum_revisions=1),
            client,
        ).plan(analyzed, "Attack", PhaseSearchPolicy())

        self.assertEqual(client.calls, 1)
        self.assertEqual(run.metadata.attempts, 1)


if __name__ == "__main__":
    unittest.main()
