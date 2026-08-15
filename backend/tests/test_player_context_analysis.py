import unittest

from app.analysis import (
    InvalidPressurePolicyError,
    PossessionRole,
    PressureLevel,
    PressurePolicy,
    analyze_all_players,
    analyze_player_context,
    resolve_initial_possession,
)
from app.builders import build_initial_game_state
from app.models.field_submission import FieldSubmission
from app.spatial import UnknownPlayerError
from app.validation import validate_field_submission
from test_field_submission_validation import valid_payload


def submitted_player(
    player_id: str,
    team_id: str,
    number: int,
    x: float,
    y: float,
) -> dict:
    return {
        "id": player_id,
        "name": player_id,
        "number": number,
        "teamId": team_id,
        "position": {"x": x, "y": y},
        "orientation": 0,
        "velocity": {"x": 0, "y": 0},
    }


def build_state(players: list[dict], resolve_possession: bool = True):
    payload = valid_payload()
    payload["fieldConfiguration"]["players"] = players
    submission = FieldSubmission.model_validate(payload)
    validate_field_submission(submission)
    state = build_initial_game_state(submission)
    return resolve_initial_possession(state)[0] if resolve_possession else state


class PressurePolicyTests(unittest.TestCase):
    def test_rejects_invalid_radii(self) -> None:
        with self.assertRaises(InvalidPressurePolicyError):
            PressurePolicy(immediate_pressure_radius_cm=-1)
        with self.assertRaises(InvalidPressurePolicyError):
            PressurePolicy(
                immediate_pressure_radius_cm=200,
                nearby_pressure_radius_cm=100,
            )
        with self.assertRaises(InvalidPressurePolicyError):
            PressurePolicy(support_radius_cm=-1)


class PlayerContextAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = build_state(
            [
                submitted_player("team1-1", "team1", 1, 6000, 4500),
                submitted_player("team1-2", "team1", 2, 6500, 4500),
                submitted_player("team2-1", "team2", 1, 6100, 4500),
                submitted_player("team2-2", "team2", 2, 6300, 4500),
            ]
        )

    def test_analyzes_neighbors_support_and_high_pressure(self) -> None:
        context = analyze_player_context(self.state, "team1-1")

        self.assertEqual(context.nearest_teammate_id, "team1-2")
        self.assertEqual(context.nearest_teammate_distance_cm, 500)
        self.assertEqual(context.nearest_opponent_id, "team2-1")
        self.assertEqual(context.nearest_opponent_distance_cm, 100)
        self.assertEqual(context.supporting_teammate_ids, ("team1-2",))
        self.assertEqual(context.nearby_opponent_ids, ("team2-1", "team2-2"))
        self.assertEqual(context.immediate_pressure_opponent_ids, ("team2-1",))
        self.assertEqual(context.pressure_level, PressureLevel.HIGH)
        self.assertAlmostEqual(context.pressure_score, 0.75)

    def test_assigns_possession_roles(self) -> None:
        self.assertEqual(
            analyze_player_context(self.state, "team1-1").possession_role,
            PossessionRole.BALL_HOLDER,
        )
        self.assertEqual(
            analyze_player_context(self.state, "team1-2").possession_role,
            PossessionRole.TEAM_IN_POSSESSION,
        )
        self.assertEqual(
            analyze_player_context(self.state, "team2-1").possession_role,
            PossessionRole.OPPOSING_TEAM,
        )

    def test_normalizes_forward_position_for_both_directions(self) -> None:
        team1 = analyze_player_context(self.state, "team1-1")
        team2 = analyze_player_context(self.state, "team2-1")

        self.assertEqual(team1.normalized_forward_position, 0.5)
        self.assertAlmostEqual(
            team2.normalized_forward_position,
            (12000 - 6100) / 12000,
        )
        self.assertGreater(team1.distance_to_attacking_goal_cm, 0)
        self.assertGreater(team1.distance_to_defended_goal_cm, 0)

    def test_pressure_levels_are_explainable_from_counts(self) -> None:
        no_pressure = build_state(
            [
                submitted_player("team1-1", "team1", 1, 6000, 4500),
                submitted_player("team2-1", "team2", 1, 7000, 4500),
            ]
        )
        low_pressure = build_state(
            [
                submitted_player("team1-1", "team1", 1, 6000, 4500),
                submitted_player("team2-1", "team2", 1, 6250, 4500),
            ]
        )
        medium_pressure = build_state(
            [
                submitted_player("team1-1", "team1", 1, 6000, 4500),
                submitted_player("team2-1", "team2", 1, 6250, 4500),
                submitted_player("team2-2", "team2", 2, 6350, 4500),
            ]
        )

        self.assertEqual(
            analyze_player_context(no_pressure, "team1-1").pressure_level,
            PressureLevel.NONE,
        )
        self.assertEqual(
            analyze_player_context(low_pressure, "team1-1").pressure_level,
            PressureLevel.LOW,
        )
        self.assertEqual(
            analyze_player_context(medium_pressure, "team1-1").pressure_level,
            PressureLevel.MEDIUM,
        )

    def test_contested_and_unresolved_players_have_correct_roles(self) -> None:
        contested = build_state(
            [
                submitted_player("team1-1", "team1", 1, 5950, 4500),
                submitted_player("team2-1", "team2", 1, 6050, 4500),
            ]
        )
        unresolved = build_state(
            [submitted_player("team1-1", "team1", 1, 6000, 4500)],
            resolve_possession=False,
        )

        self.assertEqual(
            analyze_player_context(contested, "team1-1").possession_role,
            PossessionRole.CONTESTING,
        )
        self.assertEqual(
            analyze_player_context(unresolved, "team1-1").possession_role,
            PossessionRole.NEUTRAL,
        )

    def test_all_player_results_are_ordered_and_immutable(self) -> None:
        contexts = analyze_all_players(self.state)

        self.assertEqual(tuple(contexts), tuple(sorted(contexts)))
        with self.assertRaises(TypeError):
            contexts["new"] = contexts["team1-1"]

    def test_unknown_player_is_rejected(self) -> None:
        with self.assertRaises(UnknownPlayerError):
            analyze_player_context(self.state, "missing")


if __name__ == "__main__":
    unittest.main()
