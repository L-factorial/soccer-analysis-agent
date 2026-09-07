import unittest
from dataclasses import replace
from types import MappingProxyType

from app.analysis.local_matchups import LocalMatchupPolicy, discover_local_matchup
from app.builders import build_phase_animation_response, build_phase_planner_diagnostics
from app.domain import AttackingDirection, PossessionStatus, Vector2
from app.phases import PhaseSearchPolicy, search_tactical_phases
from app.phases.scoring import PhaseScoringPolicy, score_phase_result
from app.planning import AnalysisPolicy
from test_tactical_phases import phase_state


def matchup_state(attackers=2, defenders=1, x=8000):
    state = phase_state().game_state
    template = state.players_by_id['team1-1']
    players = {}
    for index in range(attackers):
        player_id = f'team1-{index + 1}'
        position = Vector2(x, 4500) if index == 0 else Vector2(x - 200, 4500 + (-600 if index == 1 else 600))
        players[player_id] = replace(template, id=player_id, number=index + 6, position=position)
    for index in range(defenders):
        player_id = f'team2-{index + 1}'
        players[player_id] = replace(template, id=player_id, team_id='team2', number=index + 2, position=Vector2(x + 500, 4500 + index * 350))
    players['keeper'] = replace(template, id='keeper', team_id='team2', number=1, position=Vector2(11800, 4500))
    return replace(
        state, players_by_id=MappingProxyType(players),
        player_ids_by_team=MappingProxyType({team: tuple(p.id for p in players.values() if p.team_id == team) for team in ('team1', 'team2')}),
        ball=replace(state.ball, position=Vector2(x, 4500)),
    )


class LocalMatchupTests(unittest.TestCase):
    def test_classifies_each_requested_scenario_and_unopposed_play(self):
        for attackers, defenders in ((2, 1), (1, 1), (1, 2), (3, 1), (3, 2), (1, 0)):
            with self.subTest(attackers=attackers, defenders=defenders):
                result = discover_local_matchup(matchup_state(attackers, defenders))
                self.assertEqual(result.scenario, f'{attackers}v{defenders}')
                self.assertEqual(len(result.usable_support_ids), attackers - 1)
        self.assertGreater(discover_local_matchup(matchup_state(3, 1)).value, discover_local_matchup(matchup_state(2, 1)).value)
        self.assertGreater(discover_local_matchup(matchup_state(3, 2)).value, 0)
        self.assertLess(discover_local_matchup(matchup_state(1, 2)).value, 0)

    def test_radius_boundary_and_goalkeeper_are_separate(self):
        state = matchup_state()
        players = dict(state.players_by_id)
        players['team2-1'] = replace(players['team2-1'], position=Vector2(9000, 4500))
        players['keeper'] = replace(players['keeper'], position=Vector2(8900, 4500))
        state = replace(state, players_by_id=MappingProxyType(players))
        result = discover_local_matchup(state)
        self.assertEqual(result.scenario, '2v1')
        self.assertEqual(result.goalkeeper_ids, ('keeper',))
        self.assertEqual(discover_local_matchup(state, LocalMatchupPolicy(radius_cm=999)).scenario, '2v0')

    def test_crowding_and_offside_do_not_create_usable_support(self):
        for position in (Vector2(8050, 4500), Vector2(8800, 4500)):
            state = matchup_state()
            players = dict(state.players_by_id)
            players['team1-2'] = replace(players['team1-2'], position=position)
            result = discover_local_matchup(replace(state, players_by_id=MappingProxyType(players)))
            self.assertEqual(result.scenario, '2v1')
            self.assertEqual(result.usable_support_ids, ())
            self.assertEqual(result.value, 0)

    def test_blocked_pass_does_not_count_as_usable_support(self):
        state = matchup_state()
        players = dict(state.players_by_id)
        players['team2-1'] = replace(players['team2-1'], position=Vector2(7900, 4200))
        result = discover_local_matchup(replace(state, players_by_id=MappingProxyType(players)))
        self.assertEqual(result.scenario, '2v1')
        self.assertEqual(result.usable_support_ids, ())

    def test_attacking_location_and_direction(self):
        self.assertEqual(discover_local_matchup(matchup_state(x=4000)).value, 0)
        state = matchup_state()
        original = discover_local_matchup(state)
        mirror = lambda p: Vector2(state.field.length - p.x, p.y)
        teams = {key: replace(team,
            attacking_direction=AttackingDirection.NEGATIVE_X if key == 'team1' else AttackingDirection.POSITIVE_X,
            attacking_goal_id=team.defended_goal_id, defended_goal_id=team.attacking_goal_id,
        ) for key, team in state.teams_by_id.items()}
        mirrored = replace(state,
            teams_by_id=MappingProxyType(teams),
            players_by_id=MappingProxyType({key: replace(p, position=mirror(p.position)) for key, p in state.players_by_id.items()}),
            ball=replace(state.ball, position=mirror(state.ball.position)),
        )
        result = discover_local_matchup(mirrored)
        self.assertEqual(result.scenario, original.scenario)
        self.assertAlmostEqual(result.value, original.value)

    def test_no_region_after_possession_loss_or_goal(self):
        state = matchup_state()
        self.assertIsNone(discover_local_matchup(replace(state, possession=replace(state.possession, status=PossessionStatus.LOOSE))))
        self.assertIsNone(discover_local_matchup(replace(state, scored_goal_id='goal-right')))

    def test_invalid_configuration(self):
        for changes in ({'radius_cm': 0}, {'radius_cm': float('nan')}, {'minimum_support_spacing_cm': 1000}, {'attacking_progress_start': 1}):
            with self.assertRaises(ValueError):
                LocalMatchupPolicy(**changes)

    def test_custom_policy_and_scores_survive_response_serialization(self):
        result = search_tactical_phases(
            phase_state().game_state, PhaseSearchPolicy(maximum_depth=1),
            analysis_policy=AnalysisPolicy(local_matchups=LocalMatchupPolicy(radius_cm=1700)),
        )
        selected = result.best_sequences[0]
        response = build_phase_animation_response(selected, build_phase_planner_diagnostics(result, selected))
        snapshots = response.model_dump(by_alias=True)['phaseSnapshots']
        self.assertEqual(snapshots[0]['localMatchup']['radius'], 1700)
        for snapshot, step in zip(snapshots[1:], selected.steps, strict=True):
            self.assertEqual(snapshot['localMatchupScore'], step.score.local_matchup)
            self.assertEqual(snapshot['passingTriangleScore'], step.score.passing_triangle)
            if step.score.local_matchup_after is None:
                self.assertIsNone(snapshot['localMatchup'])
            else:
                self.assertEqual(snapshot['localMatchup']['scenario'], step.score.local_matchup_after.scenario)
                self.assertEqual(snapshot['localMatchup']['radius'], 1700)
                self.assertEqual(snapshot['localMatchup']['triangleValue'], step.score.local_matchup_after.triangle_value)
                self.assertEqual(len(snapshot['localMatchup']['triangles']), len(step.score.local_matchup_after.triangles))
        simulation = selected.steps[0].simulation
        before = discover_local_matchup(matchup_state(1, 1))
        after = discover_local_matchup(matchup_state(2, 1))
        self.assertGreater(score_phase_result(simulation, matchups=(before, after)).local_matchup, 0)
        self.assertEqual(score_phase_result(simulation, matchups=(after, after)).local_matchup, 0)
        self.assertEqual(score_phase_result(simulation, PhaseScoringPolicy(local_matchup_weight=0), matchups=(before, after)).local_matchup, 0)


if __name__ == '__main__':
    unittest.main()
