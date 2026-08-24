import math
import unittest

from app.analysis import (
    ActionType,
    ShotIssueCode,
    ShotPolicy,
    analyze_all_shots,
    analyze_shot,
    generate_action_candidates,
    tactical_target_points,
)
from app.api.field_configurations import analyze_field_configuration
from app.builders import build_animation_response, build_initial_game_state
from app.models.field_submission import FieldSubmission
from app.planning import SearchPolicy, analyze_game_state, search_tactical_sequences
from app.transitions import apply_action_candidate
from app.validation import validate_field_submission
from test_field_submission_validation import valid_payload


def shooting_state(team_id: str):
    payload = valid_payload()
    field = payload["fieldConfiguration"]
    if team_id == "team1":
        position = {"x": 11000, "y": 4500}
        player_id = "team1-1"
        number = 2
    else:
        position = {"x": 1000, "y": 4500}
        player_id = "team2-1"
        number = 2
    field["players"] = [
        {
            "id": player_id,
            "name": player_id,
            "number": number,
            "teamId": team_id,
            "position": position,
            "orientation": 0,
            "velocity": {"x": 0, "y": 0},
        }
    ]
    field["ball"]["position"] = position
    submission = FieldSubmission.model_validate(payload)
    validate_field_submission(submission)
    return submission, analyze_game_state(build_initial_game_state(submission))


class ShootingTests(unittest.TestCase):
    def test_generates_center_and_two_post_side_shot_targets(self) -> None:
        _, analyzed = shooting_state("team1")

        shots = analyze_all_shots(analyzed.game_state, "team1-1")

        self.assertEqual(len(shots), 3)
        self.assertEqual(shots[0].destination, analyzed.game_state.goals_by_id["goal-right"].center)
        self.assertEqual(
            {shot.destination.y for shot in shots},
            {3660.0, 4500.0, 5340.0},
        )

    def test_team1_and_team2_target_only_their_attacking_goals(self) -> None:
        _, team1 = shooting_state("team1")
        _, team2 = shooting_state("team2")

        team1_shot = analyze_shot(team1.game_state, "team1-1")
        team2_shot = analyze_shot(team2.game_state, "team2-1")
        self.assertTrue(team1_shot.feasible)
        self.assertEqual(team1_shot.goal_id, "goal-right")
        self.assertEqual(team1_shot.goal_space_id, "GoalSpace-team1")
        self.assertTrue(team2_shot.feasible)
        self.assertEqual(team2_shot.goal_id, "goal-left")
        self.assertEqual(team2_shot.goal_space_id, "GoalSpace-team2")

    def test_shot_is_rejected_beyond_five_yards_outside_penalty_arc(self) -> None:
        payload = valid_payload()
        field = payload["fieldConfiguration"]
        goal_center_x = 11900
        maximum_distance = ShotPolicy().maximum_shot_distance_cm
        position = {"x": goal_center_x - maximum_distance - 1, "y": 4500}
        field["players"] = [
            {
                "id": "team1-1",
                "name": "team1-1",
                "number": 2,
                "teamId": "team1",
                "position": position,
                "orientation": 0,
                "velocity": {"x": 0, "y": 0},
            }
        ]
        field["ball"]["position"] = position
        submission = FieldSubmission.model_validate(payload)
        validate_field_submission(submission)
        state = analyze_game_state(build_initial_game_state(submission)).game_state

        shot = analyze_shot(state, "team1-1")

        self.assertFalse(shot.feasible)
        self.assertIn(
            ShotIssueCode.SHOT_OUT_OF_RANGE,
            {issue.code for issue in shot.issues},
        )

    def test_shot_is_allowed_at_five_yard_boundary(self) -> None:
        payload = valid_payload()
        field = payload["fieldConfiguration"]
        maximum_distance = ShotPolicy().maximum_shot_distance_cm
        position = {"x": 11900 - maximum_distance, "y": 4500}
        field["players"] = [
            {
                "id": "team1-1",
                "name": "team1-1",
                "number": 2,
                "teamId": "team1",
                "position": position,
                "orientation": 0,
                "velocity": {"x": 0, "y": 0},
            }
        ]
        field["ball"]["position"] = position
        submission = FieldSubmission.model_validate(payload)
        validate_field_submission(submission)
        state = analyze_game_state(build_initial_game_state(submission)).game_state

        shot = analyze_shot(state, "team1-1")

        self.assertNotIn(
            ShotIssueCode.SHOT_OUT_OF_RANGE,
            {issue.code for issue in shot.issues},
        )

    def test_shot_transition_marks_terminal_scored_state(self) -> None:
        _, analyzed = shooting_state("team1")
        candidate = next(
            candidate
            for candidate in generate_action_candidates(analyzed.game_state).feasible
            if candidate.action_type == ActionType.SHOT
        )
        next_state = apply_action_candidate(
            analyzed.game_state,
            candidate,
        ).resulting_state
        terminal = analyze_game_state(next_state)

        self.assertEqual(next_state.scored_goal_id, "goal-right")
        self.assertEqual(next_state.scoring_team_id, "team1")
        self.assertEqual(next_state.ball.position, next_state.goals_by_id["goal-right"].center)
        self.assertFalse(terminal.action_candidates.all)

    def test_search_prefers_and_stops_after_goal(self) -> None:
        _, analyzed = shooting_state("team1")
        result = search_tactical_sequences(
            analyzed,
            SearchPolicy(maximum_depth=3, beam_width=5),
        )
        best = result.best_sequences[0]

        self.assertEqual(best.steps[-1].candidate.action_type, ActionType.SHOT)
        self.assertEqual(best.resulting_analysis.game_state.scored_goal_id, "goal-right")

    def test_api_emits_frontend_shot_event(self) -> None:
        submission, _ = shooting_state("team1")
        response = analyze_field_configuration(submission)
        payload = response.model_dump(by_alias=True)
        shot = next(event for event in payload["events"] if event["type"] == "SHOT")

        self.assertEqual(shot["goalId"], "goal-right")
        self.assertEqual(shot["playerId"], "team1-1")
        self.assertEqual(shot["target"], {"x": 11900.0, "y": 4500.0})
        diagnostics = payload["diagnostics"]
        self.assertEqual(diagnostics["objective"], "SCORE_GOAL")
        self.assertEqual(diagnostics["plannerType"], "TACTICAL_PHASE")
        self.assertEqual(diagnostics["attackingTeamId"], "team1")
        self.assertEqual(diagnostics["phaseCount"], 1)
        self.assertEqual(diagnostics["selectedSequenceDepth"], 1)
        self.assertTrue(diagnostics["dynamicSpaces"])

    def test_api_emits_turn_before_shot_for_misaligned_player(self) -> None:
        submission, _ = shooting_state("team1")
        payload = submission.model_dump(by_alias=True)
        payload["fieldConfiguration"]["players"][0]["orientation"] = 180

        response = analyze_field_configuration(
            FieldSubmission.model_validate(payload)
        ).model_dump(by_alias=True)
        turn = next(event for event in response["events"] if event["type"] == "TURN")
        shot = next(event for event in response["events"] if event["type"] == "SHOT")

        self.assertEqual(turn["playerId"], "team1-1")
        self.assertEqual(turn["startOrientation"], 180)
        expected_orientation = (
            math.degrees(
                math.atan2(
                    shot["target"]["y"] - 4500,
                    shot["target"]["x"] - 11000,
                )
            )
            % 360
        )
        self.assertAlmostEqual(
            turn["targetOrientation"],
            expected_orientation,
        )
        self.assertEqual(shot["startTime"], turn["duration"])

    def test_large_open_space_exposes_forward_point_within_shooting_range(self) -> None:
        payload = valid_payload()
        field = payload["fieldConfiguration"]
        position = {"x": 2678.1115879828326, "y": 4406.811150187092}
        field["players"] = [
            {
                "id": "team1-1",
                "name": "team1-1",
                "number": 2,
                "teamId": "team1",
                "position": position,
                "orientation": 0,
                "velocity": {"x": 0, "y": 0},
            }
        ]
        field["ball"]["position"] = position
        field["openSpaces"] = [
            {
                "id": "OpenSpace1",
                "name": "OpenSpace1",
                "type": "circular",
                "center": {
                    "x": 7900,
                    "y": 4500,
                },
                "radius": 1700,
            }
        ]
        submission = FieldSubmission.model_validate(payload)
        validate_field_submission(submission)
        analyzed = analyze_game_state(build_initial_game_state(submission))
        zone = analyzed.game_state.target_zones_by_id["OpenSpace1"]

        points = tactical_target_points(
            analyzed.game_state,
            zone,
            "team1",
            analyzed.game_state.ball.position,
        )
        forward_point = next(point for point in points if point.x == zone.top_right.x)
        self.assertEqual(forward_point.y, zone.center.y)

        result = search_tactical_sequences(
            analyzed,
            SearchPolicy(maximum_depth=2, beam_width=10),
        )
        scoring_sequences = [
            sequence
            for sequence in result.best_sequences
            if sequence.resulting_analysis.game_state.scored_goal_id == "goal-right"
        ]
        self.assertTrue(scoring_sequences)
        self.assertEqual(
            scoring_sequences[0].steps[-1].candidate.action_type,
            ActionType.SHOT,
        )

    def test_high_branching_layout_can_still_find_goal_after_beam_pruning(self) -> None:
        payload = valid_payload()
        field = payload["fieldConfiguration"]

        def player(player_id, team_id, number, x, y):
            return {
                "id": player_id, "name": player_id, "number": number,
                "teamId": team_id, "position": {"x": x, "y": y},
                "orientation": 0, "velocity": {"x": 0, "y": 0},
            }

        field["players"] = [
            player("team1-1", "team1", 1, 2652.36, 7450.99),
            player("team1-2", "team1", 2, 2712.45, 4431.66),
            player("team1-4", "team1", 4, 5356.22, 6096.64),
            player("team1-5", "team1", 5, 2781.12, 1213.53),
            player("team2-1", "team2", 1, 3090.13, 7227.34),
            player("team2-5", "team2", 5, 3081.55, 1176.25),
            player("team1-3", "team1", 3, 4721.03, 2729.41),
            player("team2-3", "team2", 3, 3527.90, 2716.98),
            player("team2-2", "team2", 2, 3914.16, 5773.59),
            player("team2-4", "team2", 4, 6901.29, 3313.39),
        ]
        field["ball"]["position"] = {"x": 2772.53, "y": 4419.24}
        spaces = [
            ("OpenSpace2", 7733.91, 7109.67, 1773.21),
            ("OpenSpace5", 4592.27, 4319.83, 800),
            ("OpenSpace6", 7072.96, 1052.00, 800),
            ("OpenSpace7", 9030.04, 2878.51, 800),
            ("OpenSpace8", 4377.68, 7898.30, 800),
        ]
        field["openSpaces"] = [
            {
                "id": space_id, "name": space_id, "type": "circular",
                "center": {"x": x, "y": y}, "radius": radius,
            }
            for space_id, x, y, radius in spaces
        ]
        submission = FieldSubmission.model_validate(payload)
        validate_field_submission(submission)
        analyzed = analyze_game_state(build_initial_game_state(submission))
        result = search_tactical_sequences(
            analyzed,
            SearchPolicy(
                maximum_depth=5,
                beam_width=5,
                maximum_sequence_duration_seconds=30,
                maximum_retained_nodes=75,
                require_possession_retention=True,
                maximum_consecutive_off_ball_actions=0,
            ),
        )

        scoring = [
            sequence for sequence in result.best_sequences
            if sequence.resulting_analysis.game_state.scoring_team_id == "team1"
        ]
        self.assertFalse(result.diagnostics.stopped_by_node_limit)
        self.assertTrue(scoring)
        self.assertEqual(scoring[0].steps[-1].candidate.action_type, ActionType.SHOT)
        animation = build_animation_response(scoring[0])
        received_at = {}
        for event in sorted(animation.events, key=lambda item: item.start_time):
            if event.type == "RECEIVE":
                received_at[event.player_id] = event.start_time
            if event.type == "PASS_TO_SPACE" and event.player_id in received_at:
                self.assertLessEqual(
                    event.start_time - received_at[event.player_id],
                    1.5 + 1e-6,
                )


if __name__ == "__main__":
    unittest.main()
