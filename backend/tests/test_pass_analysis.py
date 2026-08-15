import unittest

from app.analysis import (
    InvalidPassPolicyError,
    PassIssueCode,
    PassPolicy,
    PassType,
    analyze_all_passes,
    analyze_pass_to_player,
    analyze_pass_to_space,
    resolve_initial_possession,
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


def build_state(*, defender: tuple[float, float] | None = None):
    payload = valid_payload()
    field = payload["fieldConfiguration"]
    field["players"] = [
        player("team1-1", "team1", 1, 2000, 4500),
        player("team1-2", "team1", 2, 4000, 4500),
    ]
    if defender is not None:
        field["players"].append(
            player("team2-1", "team2", 1, defender[0], defender[1])
        )
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
    resolved, _ = resolve_initial_possession(state)
    return resolved


class PassPolicyTests(unittest.TestCase):
    def test_rejects_invalid_policy(self) -> None:
        with self.assertRaises(InvalidPassPolicyError):
            PassPolicy(ball_speed_cm_per_second=0)
        with self.assertRaises(InvalidPassPolicyError):
            PassPolicy(
                ball_speed_cm_per_second=2000,
                maximum_ball_speed_cm_per_second=1000,
            )
        with self.assertRaises(InvalidPassPolicyError):
            PassPolicy(lane_clearance_cm=-1)
        with self.assertRaises(InvalidPassPolicyError):
            PassPolicy(maximum_ball_carrier_hold_seconds=-1)


class PassAnalysisTests(unittest.TestCase):
    def test_safe_direct_pass_computes_ball_motion(self) -> None:
        result = analyze_pass_to_player(
            build_state(), "team1-1", "team1-2"
        )

        self.assertTrue(result.feasible)
        self.assertEqual(result.pass_type, PassType.PASS_TO_PLAYER)
        self.assertEqual(result.distance_cm, 2000)
        self.assertAlmostEqual(result.duration_seconds, 2000 / 1800)
        self.assertEqual(result.ball_velocity, Vector2(1800, 0))
        self.assertEqual(result.expected_possession_player_id, "team1-2")

    def test_defender_on_lane_blocks_and_can_intercept(self) -> None:
        result = analyze_pass_to_player(
            build_state(defender=(3000, 4500)),
            "team1-1",
            "team1-2",
        )

        self.assertFalse(result.feasible)
        self.assertEqual(
            {issue.code for issue in result.issues},
            {
                PassIssueCode.BLOCKED_PASSING_LANE,
                PassIssueCode.INTERCEPTION_RISK,
            },
        )
        self.assertEqual(
            result.nearest_defender_interception.interception_point,
            Vector2(3000, 4500),
        )

    def test_space_pass_checks_receiver_arrival(self) -> None:
        state = build_state()
        reachable = analyze_pass_to_space(
            state, "team1-1", "team1-2", "OpenSpace1"
        )
        late = analyze_pass_to_space(
            state,
            "team1-1",
            "team1-2",
            "OpenSpace2",
            policy=PassPolicy(receiver_arrival_tolerance_seconds=0),
        )

        self.assertTrue(reachable.feasible)
        self.assertEqual(reachable.destination, Vector2(4500, 4500))
        self.assertEqual(reachable.target_zone_id, "OpenSpace1")
        self.assertFalse(late.feasible)
        self.assertIn(
            PassIssueCode.RECEIVER_ARRIVES_TOO_LATE,
            {issue.code for issue in late.issues},
        )

    def test_requested_duration_enforces_ball_speed_limit(self) -> None:
        result = analyze_pass_to_player(
            build_state(), "team1-1", "team1-2", requested_duration_seconds=0.5
        )

        self.assertFalse(result.feasible)
        self.assertIn(
            PassIssueCode.REQUIRED_BALL_SPEED_EXCEEDS_LIMIT,
            {issue.code for issue in result.issues},
        )

    def test_rejects_space_pass_that_requires_long_stationary_hold(self) -> None:
        result = analyze_pass_to_space(
            build_state(),
            "team1-1",
            "team1-2",
            "OpenSpace2",
            policy=PassPolicy(maximum_ball_carrier_hold_seconds=0.5),
        )

        self.assertFalse(result.feasible)
        self.assertGreater(result.ball_carrier_hold_time_seconds, 0.5)
        self.assertIn(
            PassIssueCode.EXCESSIVE_BALL_CARRIER_HOLD,
            {issue.code for issue in result.issues},
        )

    def test_passer_must_control_ball(self) -> None:
        result = analyze_pass_to_player(
            build_state(), "team1-2", "team1-1"
        )

        self.assertFalse(result.feasible)
        self.assertEqual(
            result.issues[0].code,
            PassIssueCode.PASSER_DOES_NOT_CONTROL_BALL,
        )

    def test_receiver_must_be_teammate(self) -> None:
        result = analyze_pass_to_player(
            build_state(defender=(6000, 6000)),
            "team1-1",
            "team2-1",
        )

        self.assertIn(
            PassIssueCode.RECEIVER_IS_OPPONENT,
            {issue.code for issue in result.issues},
        )

    def test_batch_is_stably_ordered_and_does_not_mutate_state(self) -> None:
        state = build_state()
        original_ball = state.ball.position
        candidates = analyze_all_passes(state, "team1-1")

        self.assertGreater(len(candidates), 3)
        self.assertEqual(
            (candidates[0].pass_type, candidates[0].receiver_id, candidates[0].target_zone_id),
            (PassType.PASS_TO_PLAYER, "team1-2", None),
        )
        self.assertTrue(
            all(candidate.pass_type == PassType.PASS_TO_SPACE for candidate in candidates[1:])
        )
        self.assertEqual(state.ball.position, original_ball)


if __name__ == "__main__":
    unittest.main()
