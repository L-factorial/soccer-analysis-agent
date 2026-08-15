import unittest

from app.builders import build_initial_game_state
from app.domain import Vector2
from app.models.field_submission import FieldSubmission
from app.spatial import (
    UnknownPlayerError,
    direction_to_goal,
    distance_to_goal,
    goal_mouth_segment,
    nearest_opponent,
    nearest_player,
    nearest_teammate,
    players_within_radius,
)
from app.validation import validate_field_submission
from test_field_submission_validation import valid_payload


class GoalAndPlayerQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = valid_payload()
        payload["fieldConfiguration"]["players"] = [
            {
                "id": "team1-1",
                "name": "team1-1",
                "number": 1,
                "teamId": "team1",
                "position": {"x": 2000, "y": 4500},
                "orientation": 0,
                "velocity": {"x": 0, "y": 0},
            },
            {
                "id": "team1-2",
                "name": "team1-2",
                "number": 2,
                "teamId": "team1",
                "position": {"x": 3000, "y": 4500},
                "orientation": 0,
                "velocity": {"x": 0, "y": 0},
            },
            {
                "id": "team2-1",
                "name": "team2-1",
                "number": 1,
                "teamId": "team2",
                "position": {"x": 2500, "y": 4500},
                "orientation": 180,
                "velocity": {"x": 0, "y": 0},
            },
        ]
        submission = FieldSubmission.model_validate(payload)
        validate_field_submission(submission)
        self.state = build_initial_game_state(submission)

    def test_goal_geometry(self) -> None:
        left_goal = self.state.goals_by_id["goal-left"]
        mouth = goal_mouth_segment(left_goal)

        self.assertEqual(mouth[0], Vector2(200, 3300))
        self.assertEqual(mouth[1], Vector2(200, 5700))
        self.assertEqual(distance_to_goal(Vector2(100, 4500), left_goal), 0)
        self.assertEqual(direction_to_goal(Vector2(1100, 4500), left_goal), Vector2(-1, 0))

    def test_nearest_queries_and_stable_order(self) -> None:
        self.assertEqual(nearest_player(self.state, Vector2(2400, 4500)).id, "team2-1")
        self.assertEqual(nearest_teammate(self.state, "team1-1").id, "team1-2")
        self.assertEqual(nearest_opponent(self.state, "team1-1").id, "team2-1")
        nearby = players_within_radius(self.state, Vector2(2500, 4500), 500)
        self.assertEqual(tuple(player.id for player in nearby), ("team2-1", "team1-1", "team1-2"))

    def test_unknown_player_is_rejected(self) -> None:
        with self.assertRaises(UnknownPlayerError):
            nearest_opponent(self.state, "missing")


if __name__ == "__main__":
    unittest.main()
