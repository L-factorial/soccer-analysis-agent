import unittest

from app.analysis import (
    InvalidMovementPolicyError,
    MovementIssueCode,
    MovementPolicy,
    MovementPace,
    MovementType,
    analyze_short_dribble_movements,
    analyze_movement_to_position,
    analyze_movement_to_zone,
    analyze_player_zone_movements,
    resolve_initial_possession,
)
from app.builders import build_initial_game_state
from app.domain import Vector2
from app.models.field_submission import FieldSubmission
from app.spatial import UnknownPlayerError
from app.validation import validate_field_submission
from test_field_submission_validation import valid_payload


def build_state(*, ball_x: float = 2000, speed_category: str = "BASELINE"):
    payload = valid_payload()
    field = payload["fieldConfiguration"]
    field["ball"]["position"] = {"x": ball_x, "y": 4500}
    field["players"][0]["speedCategory"] = speed_category
    field["openSpaces"] = [
        {
            "id": "OpenSpace1",
            "name": "OpenSpace1",
            "type": "circular",
            "center": {"x": 4000, "y": 4500},
            "radius": 500,
        },
        {
            "id": "OpenSpace2",
            "name": "OpenSpace2",
            "type": "rectangular",
            "bottomLeft": {"x": 5000, "y": 4000},
            "topRight": {"x": 6000, "y": 5000},
        },
    ]
    submission = FieldSubmission.model_validate(payload)
    validate_field_submission(submission)
    return build_initial_game_state(submission)


class MovementPolicyTests(unittest.TestCase):
    def test_rejects_nonpositive_limits(self) -> None:
        with self.assertRaises(InvalidMovementPolicyError):
            MovementPolicy(slow_run_speed_cm_per_second=0)
        with self.assertRaises(InvalidMovementPolicyError):
            MovementPolicy(maximum_duration_seconds=-1)
        with self.assertRaises(InvalidMovementPolicyError):
            MovementPolicy(turning_speed_degrees_per_second=0)


class MovementAnalysisTests(unittest.TestCase):
    def test_player_speed_category_changes_planner_movement_duration(self) -> None:
        destination = Vector2(3300, 4500)
        baseline = analyze_movement_to_position(
            build_state(speed_category="BASELINE"),
            "team1-1",
            MovementType.RUN,
            destination,
        )
        fast = analyze_movement_to_position(
            build_state(speed_category="FAST"),
            "team1-1",
            MovementType.RUN,
            destination,
        )
        super_fast = analyze_movement_to_position(
            build_state(speed_category="SUPER_FAST"),
            "team1-1",
            MovementType.RUN,
            destination,
        )

        self.assertAlmostEqual(fast.duration_seconds, baseline.duration_seconds / 1.20)
        self.assertAlmostEqual(
            super_fast.duration_seconds,
            baseline.duration_seconds / 1.56,
        )
        self.assertLess(super_fast.duration_seconds, fast.duration_seconds)

    def test_generates_short_straight_and_cut_dribbles(self) -> None:
        state, _ = resolve_initial_possession(build_state())

        dribbles = analyze_short_dribble_movements(state, "team1-1")

        self.assertEqual(len(dribbles), 18)
        self.assertEqual(
            tuple(dribble.dribble_direction.value for dribble in dribbles[:3]),
            (
                "STRAIGHT",
                "CUT_LEFT",
                "CUT_RIGHT",
            ),
        )
        self.assertEqual(
            {dribble.pace for dribble in dribbles},
            {MovementPace.SLOW, MovementPace.REGULAR, MovementPace.SPRINT},
        )
        self.assertEqual(
            {dribble.travel_duration_seconds for dribble in dribbles},
            {1.5, 3.0},
        )
        self.assertTrue(all(dribble.feasible for dribble in dribbles))
        straight, left, right = dribbles[:3]
        self.assertEqual(straight.destination.y, straight.start.y)
        self.assertLess(left.destination.y, left.start.y)
        self.assertGreater(right.destination.y, right.start.y)

    def test_turning_angle_is_reported_without_adding_time(self) -> None:
        state = build_state()

        result = analyze_movement_to_position(
            state,
            "team1-1",
            MovementType.RUN,
            Vector2(2000, 5500),
            requested_duration_seconds=2,
        )

        self.assertEqual(result.turn_angle_degrees, 90)
        # Orientation is still calculated, but turn time is temporarily disabled
        # until facing data becomes a reliable physical simulation input.
        self.assertEqual(result.turn_duration_seconds, 0)
        self.assertEqual(result.travel_duration_seconds, 2)
        self.assertEqual(result.duration_seconds, 2)

    def test_move_and_run_compute_duration_from_distance(self) -> None:
        state = build_state()
        destination = Vector2(3400, 4500)

        move = analyze_movement_to_position(
            state, "team1-1", MovementType.MOVE, destination
        )
        run = analyze_movement_to_position(
            state, "team1-1", MovementType.RUN, destination
        )

        self.assertTrue(move.feasible)
        self.assertEqual(move.distance_cm, 1400)
        self.assertEqual(move.duration_seconds, 3.5)
        self.assertEqual(move.turn_duration_seconds, 0)
        self.assertEqual(move.velocity, Vector2(400, 0))
        self.assertEqual(move.orientation_degrees, 0)
        self.assertAlmostEqual(run.duration_seconds, 1400 / 600)

    def test_requested_window_is_checked_against_speed_and_duration(self) -> None:
        state = build_state()
        destination = Vector2(3400, 4500)

        feasible = analyze_movement_to_position(
            state, "team1-1", MovementType.RUN, destination, 4
        )
        too_fast = analyze_movement_to_position(
            state, "team1-1", MovementType.MOVE, destination, 1
        )
        too_long = analyze_movement_to_position(
            state,
            "team1-1",
            MovementType.RUN,
            destination,
            31,
        )

        self.assertTrue(feasible.feasible)
        self.assertEqual(feasible.required_speed_cm_per_second, 350)
        self.assertEqual(
            too_fast.issues[0].code,
            MovementIssueCode.REQUIRED_SPEED_EXCEEDS_LIMIT,
        )
        self.assertEqual(
            too_long.issues[0].code,
            MovementIssueCode.MAXIMUM_DURATION_EXCEEDED,
        )

    def test_move_with_ball_requires_control_and_moves_ball_on_success(self) -> None:
        resolved, _ = resolve_initial_possession(build_state())
        destination = Vector2(2600, 4500)
        result = analyze_movement_to_position(
            resolved, "team1-1", MovementType.MOVE_WITH_BALL, destination
        )
        unresolved = analyze_movement_to_position(
            build_state(ball_x=6000),
            "team1-1",
            MovementType.MOVE_WITH_BALL,
            destination,
        )

        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.duration_seconds, 600 / 420)
        self.assertEqual(result.arrival_ball_position, destination)
        self.assertFalse(unresolved.feasible)
        self.assertEqual(
            unresolved.issues[0].code,
            MovementIssueCode.POSSESSION_UNRESOLVED,
        )

    def test_zone_movement_targets_nearest_boundary(self) -> None:
        state = build_state()
        result = analyze_movement_to_zone(
            state, "team1-1", MovementType.RUN, "OpenSpace1"
        )

        self.assertEqual(result.target_zone_id, "OpenSpace1")
        self.assertEqual(result.destination, Vector2(3500, 4500))
        self.assertEqual(result.distance_cm, 1500)

    def test_invalid_destination_and_duration_return_structured_issues(self) -> None:
        state = build_state()
        result = analyze_movement_to_position(
            state, "team1-1", MovementType.RUN, Vector2(13000, 4500), 0
        )

        self.assertFalse(result.feasible)
        self.assertEqual(
            {issue.code for issue in result.issues},
            {
                MovementIssueCode.DESTINATION_OUTSIDE_FIELD,
                MovementIssueCode.INVALID_DURATION,
            },
        )

    def test_batch_returns_independent_ordered_branches_without_mutation(self) -> None:
        state = build_state()
        original_position = state.players_by_id["team1-1"].position
        branches = analyze_player_zone_movements(
            state,
            "team1-1",
            movement_types=(MovementType.MOVE, MovementType.RUN),
        )

        self.assertGreater(len(branches), 4)
        self.assertEqual(
            tuple((branch.target_zone_id, branch.movement_type) for branch in branches[:2]),
            (("OpenSpace1", MovementType.MOVE), ("OpenSpace1", MovementType.RUN)),
        )
        self.assertIn("OpenSpace2", {branch.target_zone_id for branch in branches})
        self.assertEqual(state.players_by_id["team1-1"].position, original_position)

    def test_unknown_player_is_rejected(self) -> None:
        with self.assertRaises(UnknownPlayerError):
            analyze_movement_to_position(
                build_state(), "missing", MovementType.RUN, Vector2(3000, 4500)
            )


if __name__ == "__main__":
    unittest.main()
