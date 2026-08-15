import unittest
from dataclasses import replace

from app.analysis import (
    InvalidPossessionPolicyError,
    PossessionPolicy,
    PossessionReason,
    analyze_initial_possession,
    resolve_initial_possession,
)
from app.builders import build_initial_game_state
from app.domain import PossessionStatus
from app.models.field_submission import FieldSubmission
from app.validation import validate_field_submission
from test_field_submission_validation import valid_payload


def build_state(players: list[dict], ball_position: dict | None = None):
    payload = valid_payload()
    field = payload["fieldConfiguration"]
    field["players"] = players
    field["ball"]["position"] = ball_position or {"x": 6000, "y": 4500}
    submission = FieldSubmission.model_validate(payload)
    validate_field_submission(submission)
    return build_initial_game_state(submission)


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


class PossessionPolicyTests(unittest.TestCase):
    def test_rejects_invalid_thresholds(self) -> None:
        with self.assertRaises(InvalidPossessionPolicyError):
            PossessionPolicy(control_radius_cm=-1)
        with self.assertRaises(InvalidPossessionPolicyError):
            PossessionPolicy(control_radius_cm=100, contested_radius_cm=99)
        with self.assertRaises(InvalidPossessionPolicyError):
            PossessionPolicy(ambiguity_distance_cm=-1)
        with self.assertRaises(InvalidPossessionPolicyError):
            PossessionPolicy(stationary_ball_speed_threshold=-1)


class InitialPossessionAnalysisTests(unittest.TestCase):
    def test_no_players_means_loose_ball(self) -> None:
        analysis = analyze_initial_possession(build_state([]))

        self.assertEqual(analysis.possession.status, PossessionStatus.LOOSE)
        self.assertEqual(analysis.reason, PossessionReason.NO_PLAYERS)

    def test_player_inside_control_radius_has_clear_control(self) -> None:
        state = build_state(
            [
                player("team1-1", "team1", 1, 5960, 4500),
                player("team2-1", "team2", 1, 6300, 4500),
            ]
        )
        analysis = analyze_initial_possession(state)

        self.assertEqual(analysis.possession.status, PossessionStatus.CONTROLLED)
        self.assertEqual(analysis.possession.player_id, "team1-1")
        self.assertEqual(analysis.possession.team_id, "team1")
        self.assertEqual(analysis.reason, PossessionReason.CLEAR_CONTROL)
        self.assertEqual(analysis.nearest_opponent_id, "team2-1")

    def test_nearest_player_outside_control_radius_means_loose(self) -> None:
        analysis = analyze_initial_possession(
            build_state([player("team1-1", "team1", 1, 6200, 4500)])
        )

        self.assertEqual(analysis.possession.status, PossessionStatus.LOOSE)
        self.assertEqual(analysis.reason, PossessionReason.OUTSIDE_CONTROL_RADIUS)
        self.assertEqual(analysis.nearest_player_distance_cm, 200)

    def test_equal_opposing_distances_are_contested(self) -> None:
        state = build_state(
            [
                player("team1-1", "team1", 1, 5950, 4500),
                player("team2-1", "team2", 1, 6050, 4500),
            ]
        )
        analysis = analyze_initial_possession(state)

        self.assertEqual(analysis.possession.status, PossessionStatus.CONTESTED)
        self.assertEqual(
            analysis.possession.contesting_player_ids,
            ("team1-1", "team2-1"),
        )

    def test_multiple_ambiguous_opponents_are_included_in_stable_order(self) -> None:
        state = build_state(
            [
                player("team1-1", "team1", 1, 5960, 4500),
                player("team2-2", "team2", 2, 6050, 4500),
                player("team2-1", "team2", 1, 5950, 4500),
            ]
        )
        analysis = analyze_initial_possession(state)

        self.assertEqual(
            analysis.possession.contesting_player_ids,
            ("team1-1", "team2-1", "team2-2"),
        )

    def test_nearby_opponent_with_clear_distance_disadvantage_does_not_contest(self) -> None:
        state = build_state(
            [
                player("team1-1", "team1", 1, 5990, 4500),
                player("team2-1", "team2", 1, 6090, 4500),
            ]
        )
        analysis = analyze_initial_possession(state)

        self.assertEqual(analysis.possession.status, PossessionStatus.CONTROLLED)
        self.assertEqual(analysis.possession.player_id, "team1-1")

    def test_equal_distance_teammates_use_stable_player_id_order(self) -> None:
        state = build_state(
            [
                player("team1-2", "team1", 2, 5950, 4500),
                player("team1-1", "team1", 1, 6050, 4500),
            ]
        )
        analysis = analyze_initial_possession(state)

        self.assertEqual(analysis.possession.player_id, "team1-1")

    def test_moving_ball_is_not_assigned_by_proximity(self) -> None:
        state = build_state([player("team1-1", "team1", 1, 6000, 4500)])
        moving_state = replace(state, ball=replace(state.ball, speed=20))
        analysis = analyze_initial_possession(moving_state)

        self.assertEqual(analysis.possession.status, PossessionStatus.LOOSE)
        self.assertEqual(analysis.reason, PossessionReason.BALL_IN_MOTION)

    def test_resolve_returns_new_state_without_mutating_original(self) -> None:
        state = build_state([player("team1-1", "team1", 1, 6000, 4500)])
        resolved, analysis = resolve_initial_possession(state)

        self.assertEqual(state.possession.status, PossessionStatus.UNRESOLVED)
        self.assertEqual(resolved.possession.status, PossessionStatus.CONTROLLED)
        self.assertIsNot(state, resolved)
        self.assertEqual(resolved.possession, analysis.possession)


if __name__ == "__main__":
    unittest.main()
