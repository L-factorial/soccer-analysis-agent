import unittest

from app.analysis import (
    ActionType,
    MovementType,
    analyze_movement_to_zone,
    generate_action_candidates,
    movement_to_candidate,
    resolve_initial_possession,
)
from app.builders import build_initial_game_state
from app.models.field_submission import FieldSubmission
from app.validation import validate_field_submission
from test_field_submission_validation import valid_payload


def player(player_id: str, team_id: str, number: int, x: float, y: float) -> dict:
    return {
        "id": player_id,
        "name": player_id,
        "number": number,
        "teamId": team_id,
        "position": {"x": x, "y": y},
        "orientation": 0,
        "velocity": {"x": 0, "y": 0},
    }


def build_state(
    *,
    resolve: bool = True,
    controller_number: int = 2,
    receiver_number: int = 3,
):
    payload = valid_payload()
    field = payload["fieldConfiguration"]
    field["players"] = [
        player("team1-1", "team1", controller_number, 2000, 4500),
        player("team1-2", "team1", receiver_number, 4000, 4500),
        player("team2-1", "team2", 4, 8000, 7000),
    ]
    field["ball"]["position"] = {"x": 2000, "y": 4500}
    field["openSpaces"] = [
        {
            "id": "OpenSpace1",
            "name": "OpenSpace1",
            "type": "circular",
            "center": {"x": 5000, "y": 4500},
            "radius": 500,
        },
        {
            "id": "OpenSpace2",
            "name": "OpenSpace2",
            "type": "rectangular",
            "bottomLeft": {"x": 5000, "y": 6000},
            "topRight": {"x": 6000, "y": 7000},
        },
    ]
    submission = FieldSubmission.model_validate(payload)
    validate_field_submission(submission)
    state = build_initial_game_state(submission)
    if resolve:
        state, _ = resolve_initial_possession(state)
    return state


class ActionCandidateTests(unittest.TestCase):
    def test_goalkeeper_can_pass_but_does_not_run_dribble_or_shoot(self) -> None:
        result = generate_action_candidates(build_state(controller_number=1))
        goalkeeper_actions = tuple(
            candidate
            for candidate in result.all
            if candidate.actor_id == "team1-1"
        )

        self.assertTrue(
            any(
                candidate.action_type == ActionType.PASS_TO_PLAYER
                for candidate in goalkeeper_actions
            )
        )
        self.assertFalse(
            {
                ActionType.RUN,
                ActionType.MOVE_WITH_BALL,
                ActionType.SHOT,
            }
            & {candidate.action_type for candidate in goalkeeper_actions}
        )

    def test_goalkeeper_can_receive_direct_pass_but_not_space_run(self) -> None:
        result = generate_action_candidates(build_state(receiver_number=1))
        passes_to_goalkeeper = tuple(
            candidate
            for candidate in result.all
            if candidate.receiver_id == "team1-2"
        )

        self.assertTrue(
            any(
                candidate.action_type == ActionType.PASS_TO_PLAYER
                for candidate in passes_to_goalkeeper
            )
        )
        self.assertFalse(
            any(
                candidate.action_type == ActionType.PASS_TO_SPACE
                for candidate in passes_to_goalkeeper
            )
        )

    def test_converts_movement_to_common_metrics(self) -> None:
        state = build_state()
        analysis = analyze_movement_to_zone(
            state,
            "team1-1",
            MovementType.RUN,
            "OpenSpace1",
        )
        candidate = movement_to_candidate(state, analysis, "candidate-test")

        self.assertEqual(candidate.id, "candidate-test")
        self.assertEqual(candidate.action_type, ActionType.RUN)
        self.assertEqual(candidate.metrics.forward_progress_cm, 2500)
        self.assertGreater(candidate.metrics.goal_proximity_improvement_cm, 0)
        self.assertIs(candidate.source_analysis, analysis)

    def test_generates_stable_movement_and_pass_candidates(self) -> None:
        state = build_state()
        result = generate_action_candidates(state)

        self.assertGreater(len(result.all), 17)
        self.assertEqual(result.all[0].id, "candidate-0001")
        self.assertEqual(
            tuple(candidate.id for candidate in result.all),
            tuple(
                f"candidate-{index:04d}"
                for index in range(1, len(result.all) + 1)
            ),
        )
        self.assertEqual(
            result.all[0].action_type,
            ActionType.MOVE,
        )
        self.assertEqual(result.all[0].actor_id, "team1-1")
        self.assertEqual(result.all[0].target_zone_id, "OpenSpace1")
        self.assertIn(ActionType.PASS_TO_PLAYER, {candidate.action_type for candidate in result.all})
        self.assertIn(ActionType.PASS_TO_SPACE, {candidate.action_type for candidate in result.all})

    def test_only_controller_gets_ball_actions(self) -> None:
        result = generate_action_candidates(build_state())
        ball_actions = tuple(
            candidate
            for candidate in result.all
            if candidate.action_type
            in {
                ActionType.MOVE_WITH_BALL,
                ActionType.PASS_TO_PLAYER,
                ActionType.PASS_TO_SPACE,
            }
        )

        self.assertTrue(ball_actions)
        self.assertEqual(
            {candidate.actor_id for candidate in ball_actions},
            {"team1-1"},
        )
        dribbles = tuple(
            candidate
            for candidate in ball_actions
            if candidate.action_type == ActionType.MOVE_WITH_BALL
        )
        short_dribbles = tuple(
            candidate
            for candidate in dribbles
            if candidate.source_analysis.dribble_direction is not None
        )
        self.assertEqual(len(short_dribbles), 18)
        self.assertEqual(
            {candidate.source_analysis.pace.value for candidate in short_dribbles},
            {"SLOW", "REGULAR", "SPRINT"},
        )
        self.assertEqual(
            {
                candidate.source_analysis.travel_duration_seconds
                for candidate in short_dribbles
            },
            {1.5, 3.0},
        )

    def test_unresolved_possession_generates_only_off_ball_movements(self) -> None:
        result = generate_action_candidates(build_state(resolve=False))

        self.assertGreater(len(result.all), 12)
        self.assertTrue(
            all(
                candidate.action_type in {ActionType.MOVE, ActionType.RUN}
                for candidate in result.all
            )
        )

    def test_partitions_candidates_without_mutating_state(self) -> None:
        state = build_state()
        original_ball = state.ball.position
        result = generate_action_candidates(state)

        self.assertEqual(
            result.feasible,
            tuple(candidate for candidate in result.all if candidate.feasible),
        )
        self.assertEqual(
            result.rejected,
            tuple(candidate for candidate in result.all if not candidate.feasible),
        )
        self.assertEqual(
            len(result.all),
            len(result.feasible) + len(result.rejected),
        )
        self.assertEqual(state.ball.position, original_ball)


if __name__ == "__main__":
    unittest.main()
