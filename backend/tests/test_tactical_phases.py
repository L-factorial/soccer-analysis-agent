import unittest
from dataclasses import FrozenInstanceError, replace
from types import MappingProxyType
from unittest.mock import patch

from app.builders import build_initial_game_state
from app.builders import build_phase_animation_response, build_phase_planner_diagnostics
from app.models.field_submission import FieldSubmission
from app.domain import Vector2
from app.phases import (
    DefensiveIntention,
    DefensiveIntentionType,
    PhaseIssueCode,
    PhaseSearchPolicy,
    PhaseStatus,
    PhaseTemplateType,
    generate_tactical_phases,
    search_tactical_phases,
    simulate_tactical_phase,
    validate_tactical_phase,
    check_phase_offside,
)
from app.planning import analyze_game_state
from app.spatial import distance
from app.validation import validate_field_submission
from test_action_candidates import player
from test_field_submission_validation import valid_payload
from test_shooting import shooting_state


def phase_state(
    include_shape_defender: bool = False,
    include_shape_attacker: bool = False,
    include_additional_shape_players: bool = False,
    include_attacking_goalkeeper: bool = False,
    include_advanced_fast_attacker: bool = False,
    include_two_wide_fast_attackers: bool = False,
):
    payload = valid_payload()
    field = payload["fieldConfiguration"]
    field["players"] = [
        player("team1-1", "team1", 6, 2000, 4500),
        player("team1-2", "team1", 2, 4000, 4500),
        player("team1-3", "team1", 3, 3500, 6500),
        player("team2-1", "team2", 1, 6500, 4200),
        player("team2-2", "team2", 2, 7000, 6500),
    ]
    if include_shape_defender:
        field["players"].extend(
            (
                player("team2-3", "team2", 3, 8500, 3000),
                player("team2-4", "team2", 4, 8500, 7800),
            )
        )
    if include_shape_attacker:
        field["players"].append(
            player("team1-4", "team1", 4, 1500, 2000)
        )
    if include_attacking_goalkeeper:
        field["players"].append(
            player("team1-gk", "team1", 1, 600, 4500)
        )
    if include_advanced_fast_attacker:
        fast_attacker = player("team1-6", "team1", 4, 6200, 8200)
        fast_attacker["speedCategory"] = "FAST"
        field["players"].append(fast_attacker)
    if include_two_wide_fast_attackers:
        high_runner = player("team1-6", "team1", 4, 6200, 8200)
        high_runner["speedCategory"] = "FAST"
        low_runner = player("team1-7", "team1", 5, 6200, 2000)
        low_runner["speedCategory"] = "SUPER_FAST"
        field["players"].extend((high_runner, low_runner))
    if include_additional_shape_players:
        field["players"].extend(
            (
                player("team1-5", "team1", 5, 1800, 7800),
                player("team2-5", "team2", 5, 8800, 1500),
            )
        )
    field["ball"]["position"] = {"x": 2000, "y": 4500}
    field["openSpaces"] = [
        {
            "id": "OpenSpace1", "name": "OpenSpace1", "type": "circular",
            "center": {"x": 5500, "y": 4500}, "radius": 600,
        }
    ]
    submission = FieldSubmission.model_validate(payload)
    validate_field_submission(submission)
    return analyze_game_state(build_initial_game_state(submission))


class TacticalPhaseGenerationTests(unittest.TestCase):
    def test_fast_wide_runners_keep_their_natural_lanes(self) -> None:
        analyzed = phase_state(include_two_wide_fast_attackers=True)
        phases = generate_tactical_phases(
            analyzed.game_state,
            analyzed.action_candidates.feasible,
        )
        targets = {
            intention.player_id: intention.target.y
            for phase in phases
            if phase.template_type == PhaseTemplateType.DRIBBLE_WITH_SUPPORT
            and phase.primary_action.destination == Vector2(2750, 4500)
            for intention in phase.attacking_intentions
            if intention.player_id in {"team1-6", "team1-7"}
            and intention.intention_type.value == "FORWARD_RUN"
        }

        self.assertGreater(targets["team1-6"], targets["team1-7"])
        self.assertLess(
            abs(8200 - targets["team1-6"])
            + abs(2000 - targets["team1-7"]),
            abs(8200 - targets["team1-7"])
            + abs(2000 - targets["team1-6"]),
        )

    def test_advanced_fast_attacker_runs_forward_instead_of_dropping_to_support(self) -> None:
        analyzed = phase_state(include_advanced_fast_attacker=True)
        phases = generate_tactical_phases(
            analyzed.game_state,
            analyzed.action_candidates.feasible,
        )
        fast_player_intentions = tuple(
            intention
            for phase in phases
            if phase.template_type == PhaseTemplateType.DRIBBLE_WITH_SUPPORT
            for intention in phase.attacking_intentions
            if intention.player_id == "team1-6"
        )

        self.assertTrue(fast_player_intentions)
        self.assertNotIn(
            "SUPPORT_BALL",
            {intention.intention_type.value for intention in fast_player_intentions},
        )
        self.assertIn(
            "FORWARD_RUN",
            {intention.intention_type.value for intention in fast_player_intentions},
        )

    def test_generates_decoy_and_passing_lane_tactical_alternatives(self) -> None:
        analyzed = phase_state(
            include_shape_defender=True,
            include_shape_attacker=True,
        )
        phases = generate_tactical_phases(
            analyzed.game_state,
            analyzed.action_candidates.feasible,
        )

        decoy_phases = tuple(
            phase
            for phase in phases
            if any(
                intention.intention_type.value == "DECOY_RUN"
                for intention in phase.attacking_intentions
            )
        )

        self.assertTrue(decoy_phases)
        self.assertTrue(
            any(
                intention.intention_type
                == DefensiveIntentionType.COVER_PASSING_LANE
                for phase in decoy_phases
                for intention in phase.defensive_intentions
            )
        )
        self.assertTrue(
            any(
                intention.intention_type
                == DefensiveIntentionType.TRACK_RECEIVER
                and intention.target_player_id
                == next(
                    attack.player_id
                    for attack in phase.attacking_intentions
                    if attack.intention_type.value == "DECOY_RUN"
                )
                for phase in decoy_phases
                for intention in phase.defensive_intentions
            )
        )

    def test_goalkeeper_covers_goal_instead_of_pressing_or_tracking(self) -> None:
        analyzed = phase_state()
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.PASS_INTO_SPACE
        )
        goalkeeper_intention = next(
            intention
            for intention in phase.defensive_intentions
            if intention.player_id == "team2-1"
        )

        self.assertEqual(
            goalkeeper_intention.intention_type,
            DefensiveIntentionType.COVER_GOAL,
        )
        self.assertEqual(
            goalkeeper_intention.target,
            analyzed.game_state.goals_by_id["goal-right"].center,
        )

    def test_attacking_goalkeeper_does_not_join_shape_run(self) -> None:
        analyzed = phase_state(include_attacking_goalkeeper=True)
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.PASS_INTO_SPACE
        )

        self.assertNotIn(
            "team1-gk",
            {intention.player_id for intention in phase.attacking_intentions},
        )

    def test_generates_immutable_coordinated_templates(self) -> None:
        analyzed = phase_state()
        phases = generate_tactical_phases(
            analyzed.game_state,
            analyzed.action_candidates.feasible,
        )
        templates = {phase.template_type for phase in phases}

        self.assertIn(PhaseTemplateType.DIRECT_PASS, templates)
        self.assertIn(PhaseTemplateType.PASS_INTO_SPACE, templates)
        self.assertIn(PhaseTemplateType.DRIBBLE_WITH_SUPPORT, templates)
        dribble_phases = tuple(
            phase
            for phase in phases
            if phase.template_type == PhaseTemplateType.DRIBBLE_WITH_SUPPORT
        )
        for phase in dribble_phases:
            assigned_players = [
                intention.player_id for intention in phase.attacking_intentions
            ]
            self.assertEqual(len(assigned_players), len(set(assigned_players)))
        support_targets = {
            (intention.target.x, intention.target.y)
            for phase in dribble_phases
            for intention in phase.attacking_intentions
        }
        self.assertGreaterEqual(len(support_targets), 3)
        self.assertTrue(
            any(
                intention.intention_type.value == "FORWARD_RUN"
                for phase in dribble_phases
                for intention in phase.attacking_intentions
            )
        )
        space_phase = next(
            phase for phase in phases
            if phase.template_type == PhaseTemplateType.PASS_INTO_SPACE
        )
        self.assertTrue(space_phase.attacking_intentions)
        self.assertEqual(len(space_phase.defensive_intentions), 2)
        receiver_intention = next(
            intention
            for intention in space_phase.attacking_intentions
            if intention.player_id == space_phase.primary_action.receiver_id
        )
        self.assertEqual(receiver_intention.start_offset_seconds, 0)
        self.assertTrue(
            any(
                intention.start_offset_seconds > 0
                for intention in space_phase.defensive_intentions
                if intention.intention_type
                != DefensiveIntentionType.PRESS_BALL_CARRIER
            )
        )
        with self.assertRaises(FrozenInstanceError):
            space_phase.duration_seconds = 99

    def test_assigns_unmatched_defenders_to_shift_with_team_shape(self) -> None:
        analyzed = phase_state(include_shape_defender=True)
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.PASS_INTO_SPACE
        )
        intentions_by_player = {
            intention.player_id: intention
            for intention in phase.defensive_intentions
        }

        self.assertEqual(
            set(intentions_by_player),
            set(analyzed.game_state.player_ids_by_team["team2"]),
        )
        shape_intentions = tuple(
            intention
            for intention in phase.defensive_intentions
            if intention.intention_type == DefensiveIntentionType.HOLD_SHAPE
        )
        self.assertEqual(len(shape_intentions), 1)
        shape_intention = shape_intentions[0]
        start = analyzed.game_state.players_by_id[
            shape_intention.player_id
        ].position
        self.assertGreater(distance(start, shape_intention.target), 0)
        self.assertLessEqual(distance(start, shape_intention.target), 600 + 1e-6)

    def test_assigns_unmatched_attackers_to_shift_with_the_play(self) -> None:
        analyzed = phase_state(include_shape_attacker=True)
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.PASS_INTO_SPACE
        )
        assigned_ids = {
            phase.primary_action.actor_id,
            *(intention.player_id for intention in phase.attacking_intentions),
        }

        self.assertEqual(
            assigned_ids,
            set(analyzed.game_state.player_ids_by_team["team1"]),
        )
        shape_intentions = tuple(
            intention
            for intention in phase.attacking_intentions
            if intention.intention_type.value == "SHIFT_WITH_PLAY"
        )
        self.assertTrue(shape_intentions)
        for intention in shape_intentions:
            start = analyzed.game_state.players_by_id[intention.player_id].position
            self.assertGreater(distance(start, intention.target), 0)
            self.assertLessEqual(distance(start, intention.target), 700 + 1e-6)

    def test_shape_players_receive_distinct_lateral_formation_lanes(self) -> None:
        analyzed = phase_state(
            include_shape_defender=True,
            include_shape_attacker=True,
            include_additional_shape_players=True,
        )
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.PASS_INTO_SPACE
        )
        defensive_targets = [
            intention.target.y
            for intention in phase.defensive_intentions
            if intention.intention_type == DefensiveIntentionType.HOLD_SHAPE
        ]
        attacking_targets = [
            intention.target.y
            for intention in phase.attacking_intentions
            if intention.intention_type.value == "SHIFT_WITH_PLAY"
        ]

        self.assertGreaterEqual(len(defensive_targets), 2)
        self.assertGreaterEqual(len(attacking_targets), 2)
        self.assertEqual(len(defensive_targets), len(set(defensive_targets)))
        self.assertEqual(len(attacking_targets), len(set(attacking_targets)))


class OffsideRuleTests(unittest.TestCase):
    def _offside_state_and_phase(self):
        analyzed = phase_state()
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.DIRECT_PASS
        )
        receiver_id = phase.primary_action.receiver_id
        players = dict(analyzed.game_state.players_by_id)
        players[receiver_id] = replace(
            players[receiver_id],
            position=Vector2(9000, players[receiver_id].position.y),
        )
        players["team2-1"] = replace(
            players["team2-1"], position=Vector2(7600, 4200)
        )
        players["team2-2"] = replace(
            players["team2-2"], position=Vector2(7000, 6500)
        )
        state = replace(
            analyzed.game_state,
            players_by_id=MappingProxyType(players),
        )
        return analyzed, state, phase

    def test_flags_receiver_beyond_ball_and_second_last_defender(self) -> None:
        _, state, phase = self._offside_state_and_phase()

        result = check_phase_offside(state, phase)

        self.assertTrue(result.applicable)
        self.assertTrue(result.offside)
        self.assertEqual(result.receiver_id, phase.primary_action.receiver_id)
        self.assertEqual(result.offside_line_x, 7000)

    def test_ball_ahead_of_receiver_keeps_receiver_onside(self) -> None:
        _, state, phase = self._offside_state_and_phase()
        state = replace(
            state,
            ball=replace(state.ball, position=Vector2(9500, 4500)),
        )

        result = check_phase_offside(state, phase)

        self.assertFalse(result.offside)
        self.assertEqual(result.reason, "receiver_onside")

    def test_phase_search_prunes_offside_phase_before_simulation(self) -> None:
        analyzed, state, phase = self._offside_state_and_phase()
        root = replace(analyzed, game_state=state)

        with patch(
            "app.phases.search.generate_tactical_phases",
            return_value=(phase,),
        ):
            result = search_tactical_phases(root)

        self.assertEqual(result.diagnostics.generated_phase_count, 1)
        self.assertEqual(result.diagnostics.pruned_by_offside_count, 1)
        self.assertEqual(result.diagnostics.simulated_phase_count, 0)

    def test_validates_conflicting_player_assignments(self) -> None:
        analyzed = phase_state()
        phase = generate_tactical_phases(
            analyzed.game_state,
            analyzed.action_candidates.feasible,
        )[0]
        defender = phase.defensive_intentions[0]
        conflict = replace(
            phase,
            defensive_intentions=(
                defender,
                DefensiveIntention(
                    player_id=defender.player_id,
                    intention_type=DefensiveIntentionType.HOLD_SHAPE,
                    target=defender.target,
                    target_player_id=None,
                ),
            ),
        )
        validation = validate_tactical_phase(analyzed.game_state, conflict)

        self.assertFalse(validation.valid)
        self.assertIn(
            PhaseIssueCode.PLAYER_ACTION_CONFLICT,
            {issue.code for issue in validation.issues},
        )


class TacticalPhaseSimulationTests(unittest.TestCase):
    def test_simulates_attackers_and_two_defenders_concurrently(self) -> None:
        analyzed = phase_state()
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.PASS_INTO_SPACE
        )
        result = simulate_tactical_phase(analyzed.game_state, phase)

        self.assertEqual(result.status, PhaseStatus.SUCCESS)
        self.assertTrue(result.validation.valid)
        self.assertEqual(
            result.resulting_state.possession.player_id,
            phase.primary_action.receiver_id,
        )
        self.assertTrue(
            {intention.player_id for intention in phase.defensive_intentions}
            <= set(result.changed_player_ids)
        )
        self.assertNotEqual(
            result.resulting_state.players_by_id["team1-3"].position,
            analyzed.game_state.players_by_id["team1-3"].position,
        )

    def test_rejects_pass_when_press_arrives_before_release(self) -> None:
        analyzed = phase_state()
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.PASS_INTO_SPACE
        )
        phase = replace(phase, ball_action_start_offset_seconds=1.0)
        presser_id = next(
            intention.player_id
            for intention in phase.defensive_intentions
            if intention.intention_type
            == DefensiveIntentionType.PRESS_BALL_CARRIER
        )
        players = dict(analyzed.game_state.players_by_id)
        players[presser_id] = replace(
            players[presser_id],
            position=Vector2(
                phase.primary_action.start.x - 100,
                phase.primary_action.start.y,
            ),
        )
        pressured_state = replace(
            analyzed.game_state,
            players_by_id=MappingProxyType(players),
        )

        result = simulate_tactical_phase(pressured_state, phase)

        self.assertEqual(result.status, PhaseStatus.TACKLED)
        self.assertFalse(result.validation.valid)
        self.assertAlmostEqual(result.actual_duration_seconds, 0.2)
        self.assertIn(
            PhaseIssueCode.BALL_CARRIER_TACKLED_BEFORE_RELEASE,
            {issue.code for issue in result.validation.issues},
        )

    def test_rejects_dribble_when_defender_can_intercept_trajectory(self) -> None:
        analyzed = phase_state()
        phase = next(
            phase
            for phase in generate_tactical_phases(
                analyzed.game_state,
                analyzed.action_candidates.feasible,
            )
            if phase.template_type == PhaseTemplateType.DRIBBLE_WITH_SUPPORT
        )
        defender_id = phase.defensive_intentions[0].player_id
        players = dict(analyzed.game_state.players_by_id)
        midpoint = Vector2(
            (phase.primary_action.start.x + phase.primary_action.destination.x) / 2,
            (phase.primary_action.start.y + phase.primary_action.destination.y) / 2,
        )
        players[defender_id] = replace(players[defender_id], position=midpoint)
        pressured_state = replace(
            analyzed.game_state,
            players_by_id=MappingProxyType(players),
        )

        result = simulate_tactical_phase(pressured_state, phase)

        self.assertEqual(result.status, PhaseStatus.TACKLED)
        self.assertFalse(result.validation.valid)
        self.assertIn(
            PhaseIssueCode.DRIBBLER_TACKLED,
            {issue.code for issue in result.validation.issues},
        )


class TacticalPhaseSearchTests(unittest.TestCase):
    def test_coordinated_runs_fill_remaining_phase_without_idle_gap(self) -> None:
        analyzed = phase_state(include_shape_defender=True)
        result = search_tactical_phases(
            analyzed,
            PhaseSearchPolicy(maximum_depth=1, beam_width=50),
        )
        sequence = next(
            node
            for node in result.best_sequences
            if node.steps[0].phase.template_type
            == PhaseTemplateType.PASS_INTO_SPACE
        )
        response = build_phase_animation_response(
            sequence,
            build_phase_planner_diagnostics(result, sequence),
        )
        runs = tuple(event for event in response.events if event.type == "RUN")

        self.assertTrue(runs)
        self.assertTrue(
            all(
                abs(event.start_time + event.duration - response.duration)
                <= 1e-6
                for event in runs
            )
        )

    def test_phase_search_is_bounded_and_does_not_mutate_root(self) -> None:
        analyzed = phase_state()
        original_players = analyzed.game_state.players_by_id
        result = search_tactical_phases(
            analyzed,
            PhaseSearchPolicy(maximum_depth=2, beam_width=3),
        )

        self.assertTrue(result.best_sequences)
        self.assertLessEqual(result.diagnostics.retained_node_count, 7)
        self.assertLessEqual(result.diagnostics.reached_depth, 2)
        self.assertIs(analyzed.game_state.players_by_id, original_players)

    def test_search_diagnostics_count_dribble_tackles(self) -> None:
        analyzed = phase_state()
        players = dict(analyzed.game_state.players_by_id)
        players["team2-1"] = replace(
            players["team2-1"],
            position=Vector2(2600, 4500),
        )
        analyzed = analyze_game_state(
            replace(
                analyzed.game_state,
                players_by_id=MappingProxyType(players),
            )
        )
        result = search_tactical_phases(
            analyzed,
            PhaseSearchPolicy(maximum_depth=1, beam_width=3),
        )

        issue_counts = dict(result.diagnostics.invalid_issue_counts)
        self.assertGreaterEqual(
            issue_counts.get(PhaseIssueCode.DRIBBLER_TACKLED.value, 0),
            1,
        )

    def test_phase_search_rewards_and_stops_on_goal(self) -> None:
        _, analyzed = shooting_state("team1")
        result = search_tactical_phases(
            analyzed,
            PhaseSearchPolicy(maximum_depth=3, beam_width=5),
        )
        scored = [
            node for node in result.best_sequences
            if node.analyzed_state.game_state.scoring_team_id == "team1"
        ]

        self.assertTrue(scored)
        self.assertEqual(scored[0].depth, 1)
        self.assertGreater(scored[0].cumulative_score, 900)
        self.assertEqual(
            scored[0].steps[-1].phase.template_type,
            PhaseTemplateType.SHOT,
        )
        response = build_phase_animation_response(
            scored[0],
            build_phase_planner_diagnostics(result, scored[0]),
        )
        payload = response.model_dump(by_alias=True)
        self.assertEqual(payload["diagnostics"]["plannerType"], "TACTICAL_PHASE")
        self.assertEqual(payload["diagnostics"]["phaseCount"], 1)
        selected_phase = payload["diagnostics"]["selectedPhases"][0]
        self.assertEqual(selected_phase["phaseType"], "SHOT")
        self.assertEqual(selected_phase["actionType"], "SHOT")
        self.assertEqual(selected_phase["actorId"], "team1-1")
        self.assertEqual(selected_phase["startTime"], 0)
        self.assertEqual(selected_phase["endTime"], response.duration)
        self.assertTrue(selected_phase["scoredGoal"])
        self.assertEqual(selected_phase["possessionBefore"], "controlled")
        self.assertEqual(selected_phase["possessionAfter"], "loose")
        self.assertTrue(any(event["type"] == "SHOT" for event in payload["events"]))


if __name__ == "__main__":
    unittest.main()
