import copy
import unittest
from dataclasses import FrozenInstanceError

from app.builders import build_initial_game_state
from app.domain import (
    AttackingDirection,
    PossessionStatus,
    TargetZoneShape,
    TargetZoneSource,
)
from app.models.field_submission import FieldSubmission
from app.validation import validate_field_submission
from test_field_submission_validation import valid_payload


class InitialGameStateBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = valid_payload()
        self.payload["fieldConfiguration"]["players"].append(
            {
                "id": "team2-1",
                "name": "team2-1",
                "number": 1,
                "teamId": "team2",
                "position": {"x": 10000, "y": 4500},
                "orientation": 180,
                "velocity": {"x": 0, "y": 0},
            }
        )
        self.payload["fieldConfiguration"]["openSpaces"] = [
            {
                "id": "OpenSpace1",
                "name": "OpenSpace1",
                "type": "circular",
                "center": {"x": 4000, "y": 3000},
                "radius": 500,
            },
            {
                "id": "OpenSpace2",
                "name": "OpenSpace2",
                "type": "rectangular",
                "bottomLeft": {"x": 7000, "y": 5000},
                "topRight": {"x": 8000, "y": 6000},
            },
        ]

    def build(self):
        submission = FieldSubmission.model_validate(self.payload)
        validate_field_submission(submission)
        return submission, build_initial_game_state(submission)

    def test_builds_team_attacking_goals_and_directions(self) -> None:
        _, state = self.build()

        self.assertEqual(state.teams_by_id["team1"].attacking_goal_id, "goal-right")
        self.assertEqual(
            state.teams_by_id["team1"].attacking_direction,
            AttackingDirection.POSITIVE_X,
        )
        self.assertEqual(state.teams_by_id["team2"].attacking_goal_id, "goal-left")
        self.assertEqual(
            state.teams_by_id["team2"].attacking_direction,
            AttackingDirection.NEGATIVE_X,
        )

    def test_indexes_players_and_initializes_unresolved_possession(self) -> None:
        _, state = self.build()

        self.assertEqual(state.player_ids_by_team["team1"], ("team1-1",))
        self.assertEqual(state.player_ids_by_team["team2"], ("team2-1",))
        self.assertEqual(state.players_by_id["team2-1"].team_id, "team2")
        self.assertEqual(state.possession.status, PossessionStatus.UNRESOLVED)
        self.assertIsNone(state.possession.player_id)
        self.assertEqual(state.time_seconds, 0)

    def test_builds_player_speed_category_with_baseline_default(self) -> None:
        self.payload["fieldConfiguration"]["players"][0][
            "speedCategory"
        ] = "SUPER_FAST"

        _, state = self.build()

        self.assertEqual(
            state.players_by_id["team1-1"].speed_category.value,
            "SUPER_FAST",
        )
        self.assertEqual(
            state.players_by_id["team2-1"].speed_category.value,
            "BASELINE",
        )

    def test_converts_user_open_spaces_to_target_zones(self) -> None:
        _, state = self.build()
        circle = state.target_zones_by_id["OpenSpace1"]
        rectangle = state.target_zones_by_id["OpenSpace2"]

        self.assertEqual(circle.shape, TargetZoneShape.CIRCULAR)
        self.assertEqual(circle.source, TargetZoneSource.USER_DEFINED)
        self.assertEqual(circle.bottom_left.x, 3500)
        self.assertEqual(rectangle.shape, TargetZoneShape.RECTANGULAR)
        self.assertEqual(rectangle.center.x, 7500)
        self.assertEqual(rectangle.center.y, 5500)

    def test_creates_team_owned_ball_only_attacking_goal_spaces(self) -> None:
        payload = valid_payload()
        submission = FieldSubmission.model_validate(payload)
        validate_field_submission(submission)
        state = build_initial_game_state(submission)

        team1_goal = state.target_zones_by_id["GoalSpace-team1"]
        team2_goal = state.target_zones_by_id["GoalSpace-team2"]
        self.assertEqual(team1_goal.source, TargetZoneSource.ATTACKING_GOAL)
        self.assertEqual(team1_goal.attacking_team_id, "team1")
        self.assertEqual(team1_goal.center, state.goals_by_id["goal-right"].center)
        self.assertTrue(team1_goal.ball_only)
        self.assertEqual(team2_goal.attacking_team_id, "team2")
        self.assertEqual(team2_goal.center, state.goals_by_id["goal-left"].center)

    def test_build_does_not_mutate_submission_and_state_is_immutable(self) -> None:
        original_payload = copy.deepcopy(self.payload)
        submission, state = self.build()

        self.assertEqual(
            submission.model_dump(by_alias=True),
            FieldSubmission.model_validate(original_payload).model_dump(by_alias=True),
        )
        with self.assertRaises(TypeError):
            state.players_by_id["another"] = state.players_by_id["team1-1"]
        with self.assertRaises(FrozenInstanceError):
            state.ball.speed = 10


if __name__ == "__main__":
    unittest.main()
