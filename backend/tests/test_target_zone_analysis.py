import unittest

from app.analysis import (
    InvalidTargetZonePolicyError,
    TargetZonePolicy,
    TargetZoneStatus,
    UnknownTargetZoneError,
    UnknownTeamError,
    analyze_all_target_zones,
    analyze_target_zone,
)
from app.builders import build_initial_game_state
from app.domain import Vector2
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


def build_state(players: list[dict]):
    payload = valid_payload()
    field = payload["fieldConfiguration"]
    field["players"] = players
    field["openSpaces"] = [
        {
            "id": "OpenSpace1",
            "name": "OpenSpace1",
            "type": "circular",
            "center": {"x": 7000, "y": 4500},
            "radius": 500,
        },
        {
            "id": "OpenSpace2",
            "name": "OpenSpace2",
            "type": "rectangular",
            "bottomLeft": {"x": 3500, "y": 4000},
            "topRight": {"x": 4500, "y": 5000},
        },
    ]
    submission = FieldSubmission.model_validate(payload)
    validate_field_submission(submission)
    return build_initial_game_state(submission)


class TargetZonePolicyTests(unittest.TestCase):
    def test_rejects_invalid_policy_values(self) -> None:
        with self.assertRaises(InvalidTargetZonePolicyError):
            TargetZonePolicy(attacker_speed_cm_per_second=0)
        with self.assertRaises(InvalidTargetZonePolicyError):
            TargetZonePolicy(defender_speed_cm_per_second=-1)
        with self.assertRaises(InvalidTargetZonePolicyError):
            TargetZonePolicy(reachable_horizon_seconds=-1)
        with self.assertRaises(InvalidTargetZonePolicyError):
            TargetZonePolicy(contested_arrival_margin_seconds=-1)


class TargetZoneAnalysisTests(unittest.TestCase):
    def test_available_zone_uses_nearest_boundary_and_arrival_advantage(self) -> None:
        state = build_state(
            [
                player("team1-1", "team1", 1, 6000, 4500),
                player("team2-1", "team2", 1, 9000, 4500),
            ]
        )
        policy = TargetZonePolicy(
            attacker_speed_cm_per_second=500,
            defender_speed_cm_per_second=500,
        )
        analysis = analyze_target_zone(state, "OpenSpace1", "team1", policy)

        self.assertEqual(analysis.status, TargetZoneStatus.AVAILABLE)
        self.assertEqual(analysis.nearest_attacker_id, "team1-1")
        self.assertEqual(analysis.nearest_attacker_distance_cm, 500)
        self.assertEqual(analysis.nearest_attacker_entry_point, Vector2(6500, 4500))
        self.assertEqual(analysis.attacker_arrival_time_seconds, 1)
        self.assertEqual(analysis.nearest_defender_distance_cm, 1500)
        self.assertEqual(analysis.defender_arrival_time_seconds, 3)
        self.assertEqual(analysis.arrival_advantage_seconds, 2)
        self.assertEqual(analysis.reachable_attacker_ids, ("team1-1",))

    def test_zone_is_contested_when_arrivals_are_close(self) -> None:
        state = build_state(
            [
                player("team1-1", "team1", 1, 6000, 4500),
                player("team2-1", "team2", 1, 8000, 4500),
            ]
        )
        analysis = analyze_target_zone(state, "OpenSpace1", "team1")

        self.assertEqual(analysis.status, TargetZoneStatus.CONTESTED)
        self.assertEqual(analysis.arrival_advantage_seconds, 0)

    def test_zone_can_be_defender_controlled_or_unreachable(self) -> None:
        defender_first = build_state(
            [
                player("team1-1", "team1", 1, 5000, 4500),
                player("team2-1", "team2", 1, 7100, 4500),
            ]
        )
        no_attackers = build_state(
            [player("team2-1", "team2", 1, 7100, 4500)]
        )

        self.assertEqual(
            analyze_target_zone(
                defender_first,
                "OpenSpace1",
                "team1",
            ).status,
            TargetZoneStatus.DEFENDER_CONTROLLED,
        )
        self.assertEqual(
            analyze_target_zone(
                no_attackers,
                "OpenSpace1",
                "team1",
            ).status,
            TargetZoneStatus.UNREACHABLE,
        )

    def test_ball_distance_and_forward_values_respect_team_direction(self) -> None:
        state = build_state(
            [
                player("team1-1", "team1", 1, 6000, 4500),
                player("team2-1", "team2", 1, 6000, 4600),
            ]
        )
        team1 = analyze_target_zone(state, "OpenSpace1", "team1")
        team2 = analyze_target_zone(state, "OpenSpace2", "team2")

        self.assertEqual(team1.ball_distance_cm, 500)
        self.assertEqual(team1.ball_entry_point, Vector2(6500, 4500))
        self.assertEqual(team1.forward_progress_from_ball_cm, 1000)
        self.assertAlmostEqual(team1.normalized_forward_value, 7000 / 12000)
        self.assertEqual(team2.forward_progress_from_ball_cm, 2000)
        self.assertAlmostEqual(team2.normalized_forward_value, 8000 / 12000)

    def test_all_zone_results_are_ordered_and_immutable(self) -> None:
        state = build_state(
            [player("team1-1", "team1", 1, 6000, 4500)]
        )
        analyses = analyze_all_target_zones(state, "team1")

        self.assertEqual(
            tuple(analyses),
            ("GoalSpace-team1", "OpenSpace1", "OpenSpace2"),
        )
        with self.assertRaises(TypeError):
            analyses["another"] = analyses["OpenSpace1"]

    def test_unknown_team_and_zone_are_rejected(self) -> None:
        state = build_state([])
        with self.assertRaises(UnknownTargetZoneError):
            analyze_target_zone(state, "missing", "team1")
        with self.assertRaises(UnknownTeamError):
            analyze_target_zone(state, "OpenSpace1", "missing")


if __name__ == "__main__":
    unittest.main()
