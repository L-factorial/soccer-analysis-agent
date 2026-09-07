import unittest
from dataclasses import replace
from types import MappingProxyType

from app.analysis.local_matchups import LocalMatchupPolicy, discover_local_matchup
from app.analysis.passing_triangles import discover_passing_triangles
from app.builders import build_phase_animation_response, build_phase_planner_diagnostics
from app.domain import AttackingDirection, Vector2
from app.phases import PhaseSearchPolicy, generate_tactical_phases, simulate_tactical_phase, search_tactical_phases
from app.phases.scoring import score_phase_result
from app.phases.support_runs import SupportRunPolicy, local_support_variants
from app.phases.templates import PhaseGenerationPolicy
from app.planning import analyze_game_state
from app.spatial import distance
from test_local_matchups import matchup_state


def support_state(wide=True):
    state = matchup_state(3, 1)
    players = dict(state.players_by_id)
    positions = {
        'team1-2': (7700, 3300) if wide else (7600, 3800),
        'team1-3': (7700, 5700) if wide else (7600, 5200),
        'team2-1': (9500, 4500),
    }
    for player_id, position in positions.items():
        players[player_id] = replace(players[player_id], position=Vector2(*position))
    return replace(state, players_by_id=MappingProxyType(players))


class PassingTriangleTests(unittest.TestCase):
    def test_response_triangle_vertices_match_snapshot_players(self):
        state = support_state(False)
        result = search_tactical_phases(state, PhaseSearchPolicy(maximum_depth=1))
        selected = result.best_sequences[0]
        response = build_phase_animation_response(selected, build_phase_planner_diagnostics(result, selected))
        snapshots = response.model_dump(mode='json', by_alias=True)['phaseSnapshots']
        self.assertTrue(snapshots[0]['localMatchup']['triangles'])
        states = [selected.steps[0].simulation.previous_state, *(step.simulation.resulting_state for step in selected.steps)]
        for snapshot, snapshot_state in zip(snapshots, states, strict=True):
            for triangle in (snapshot['localMatchup'] or {}).get('triangles', []):
                self.assertEqual(len(triangle['vertices']), 3)
                for player_id, vertex in zip(triangle['playerIds'], triangle['vertices'], strict=True):
                    position = snapshot_state.players_by_id[player_id].position
                    self.assertEqual(vertex, {'x': position.x, 'y': position.y})
                self.assertGreater(triangle['quality'], 0)

    def test_connected_triangle_has_value_beyond_raw_numbers(self):
        state = support_state(False)
        result = discover_local_matchup(state)
        self.assertEqual(len(result.triangles), 1)
        self.assertGreater(result.triangle_value, 0)
        players = dict(state.players_by_id)
        players['team1-2'] = replace(players['team1-2'], position=Vector2(7400, 4500))
        players['team1-3'] = replace(players['team1-3'], position=Vector2(7100, 4500))
        flat = discover_local_matchup(replace(state, players_by_id=MappingProxyType(players)))
        self.assertEqual(flat.scenario, result.scenario)
        self.assertEqual(flat.triangles, ())
        self.assertEqual(flat.triangle_value, 0)

    def test_blocked_third_connection_is_not_a_triangle(self):
        state = support_state(False)
        players = dict(state.players_by_id)
        players['team2-1'] = replace(players['team2-1'], position=Vector2(7600, 4500))
        blocked = replace(state, players_by_id=MappingProxyType(players))
        self.assertEqual(discover_passing_triangles(blocked, 'team1-1', ('team1-2', 'team1-3')), ())

    def test_advantage_ordering(self):
        values = [discover_local_matchup(matchup_state(a, d)).value
                  for a, d in ((3, 1), (2, 1), (1, 1), (1, 2), (1, 3))]
        self.assertTrue(all(first > second for first, second in zip(values, values[1:])))


class LocalSupportRunTests(unittest.TestCase):
    def test_support_anchors_mirror_with_attacking_direction(self):
        analyzed = analyze_game_state(support_state())
        state = analyzed.game_state
        base = generate_tactical_phases(state, analyzed.action_candidates.feasible)[0]
        mirror = lambda point: Vector2(state.field.length - point.x, point.y)
        mirrored = replace(state,
            players_by_id=MappingProxyType({key: replace(player, position=mirror(player.position)) for key, player in state.players_by_id.items()}),
            teams_by_id=MappingProxyType({key: replace(team,
                attacking_direction=AttackingDirection.NEGATIVE_X if key == 'team1' else AttackingDirection.POSITIVE_X,
            ) for key, team in state.teams_by_id.items()}),
        )
        mirrored_phase = replace(base,
            primary_action=replace(base.primary_action, destination=mirror(base.primary_action.destination)),
            attacking_intentions=tuple(replace(item, target=mirror(item.target)) for item in base.attacking_intentions),
        )
        original = local_support_variants(state, base, LocalMatchupPolicy(), SupportRunPolicy())
        reflected = local_support_variants(mirrored, mirrored_phase, LocalMatchupPolicy(), SupportRunPolicy())
        self.assertTrue(original)
        self.assertEqual(len(original), len(reflected))
        for first, second in zip(original, reflected):
            for a, b in zip(first.attacking_intentions, second.attacking_intentions):
                self.assertEqual(a.player_id, b.player_id)
                self.assertAlmostEqual(mirror(a.target).x, b.target.x)
                self.assertAlmostEqual(a.target.y, b.target.y)

    def test_simulated_pair_creates_triangle_and_beats_baseline(self):
        analyzed = analyze_game_state(support_state())
        phases = generate_tactical_phases(analyzed.game_state, analyzed.action_candidates.feasible)
        variant = next(phase for phase in phases if '-support-2' in phase.id)
        baseline = next(phase for phase in phases if phase.id == variant.id.split('-support-')[0])
        simulation = simulate_tactical_phase(analyzed.game_state, variant)
        original = simulate_tactical_phase(analyzed.game_state, baseline)
        self.assertTrue(simulation.validation.valid)
        self.assertTrue(original.validation.valid)
        score = score_phase_result(simulation)
        original_score = score_phase_result(original)
        self.assertEqual(score.local_matchup_after.scenario, '3v1')
        self.assertGreater(score.local_matchup, 0)
        self.assertGreater(score.passing_triangle, 0)
        self.assertGreater(score.total, original_score.total)
        self.assertEqual(variant.primary_action, baseline.primary_action)
        self.assertEqual(variant.defensive_intentions, baseline.defensive_intentions)
        unchanged = score_phase_result(simulation, matchups=(score.local_matchup_after, score.local_matchup_after))
        self.assertEqual(unchanged.passing_triangle, 0)

    def test_budget_and_disable_switch(self):
        analyzed = analyze_game_state(support_state())
        policy = PhaseGenerationPolicy(maximum_phases=12)
        phases = generate_tactical_phases(analyzed.game_state, analyzed.action_candidates.feasible, policy)
        self.assertLessEqual(len(phases), 12)
        self.assertGreater(sum('-support-' in phase.id for phase in phases), 0)
        self.assertLessEqual(sum('-support-' in phase.id for phase in phases), 3)
        disabled = replace(policy, support_runs=SupportRunPolicy(maximum_variant_fraction=0))
        self.assertFalse(any('-support-' in phase.id for phase in generate_tactical_phases(analyzed.game_state, analyzed.action_candidates.feasible, disabled)))
        self.assertEqual(phases, generate_tactical_phases(analyzed.game_state, analyzed.action_candidates.feasible, policy))

    def test_custom_radius_and_movement_limit(self):
        analyzed = analyze_game_state(support_state())
        base = generate_tactical_phases(
            analyzed.game_state, analyzed.action_candidates.feasible,
            PhaseGenerationPolicy(support_runs=SupportRunPolicy(maximum_variant_fraction=0)),
        )[0]
        variants = local_support_variants(analyzed.game_state, base,
            LocalMatchupPolicy(radius_cm=1400), SupportRunPolicy(maximum_run_distance_cm=100))
        self.assertTrue(variants)
        baseline = {item.player_id: item for item in base.attacking_intentions}
        for variant in variants:
            ids = [item.player_id for item in variant.attacking_intentions]
            self.assertEqual(len(ids), len(set(ids)))
            for item in variant.attacking_intentions:
                if item != baseline[item.player_id]:
                    self.assertLessEqual(distance(analyzed.game_state.players_by_id[item.player_id].position, item.target), 100 + 1e-6)

    def test_delayed_runs_do_not_credit_unreached_triangle(self):
        analyzed = analyze_game_state(support_state())
        phases = generate_tactical_phases(analyzed.game_state, analyzed.action_candidates.feasible)
        variant = next(phase for phase in phases if '-support-2' in phase.id)
        delayed = replace(variant, attacking_intentions=tuple(
            replace(item, start_offset_seconds=variant.duration_seconds + 1)
            for item in variant.attacking_intentions
        ))
        simulation = simulate_tactical_phase(analyzed.game_state, delayed)
        # Planned targets earn nothing when the supporting players have not
        # started moving by the end of the phase.
        self.assertEqual(score_phase_result(simulation).passing_triangle, 0)
        for item in delayed.attacking_intentions:
            self.assertEqual(simulation.resulting_state.players_by_id[item.player_id].position,
                             analyzed.game_state.players_by_id[item.player_id].position)


if __name__ == '__main__':
    unittest.main()
