import unittest

from app.analysis import ActionType
from app.domain import PossessionStatus
from app.planning import analyze_game_state, expand_analyzed_state
from test_action_candidates import build_state


class AnalyzedGameStateTests(unittest.TestCase):
    def test_builds_complete_analysis_snapshot(self) -> None:
        raw_state = build_state(resolve=False)
        analyzed = analyze_game_state(raw_state)

        self.assertEqual(
            analyzed.game_state.possession.status,
            PossessionStatus.CONTROLLED,
        )
        self.assertEqual(analyzed.game_state.possession.player_id, "team1-1")
        self.assertEqual(tuple(analyzed.player_contexts), ("team1-1", "team1-2", "team2-1"))
        self.assertEqual(tuple(analyzed.target_zones_by_team), ("team1", "team2"))
        self.assertEqual(
            tuple(analyzed.target_zones_by_team["team1"]),
            (
                "DynamicSpace-team1-1",
                "DynamicSpace-team1-2",
                "DynamicSpace-team1-3",
                "GoalSpace-team1",
                "OpenSpace1",
                "OpenSpace2",
            ),
        )
        self.assertNotIn("GoalSpace-team2", analyzed.target_zones_by_team["team1"])
        self.assertEqual(
            analyzed.diagnostics.candidate_count,
            len(analyzed.action_candidates.all),
        )
        self.assertEqual(
            analyzed.diagnostics.feasible_candidate_count,
            len(analyzed.action_candidates.feasible),
        )
        self.assertTrue(
            all(
                candidate.originating_state_fingerprint
                == analyzed.state_fingerprint
                for candidate in analyzed.action_candidates.all
            )
        )

    def test_analysis_mappings_are_immutable(self) -> None:
        analyzed = analyze_game_state(build_state(resolve=False))

        with self.assertRaises(TypeError):
            analyzed.player_contexts["another"] = analyzed.player_contexts["team1-1"]
        with self.assertRaises(TypeError):
            analyzed.target_zones_by_team["another"] = analyzed.target_zones_by_team["team1"]


class BranchExpansionTests(unittest.TestCase):
    def test_expands_every_feasible_candidate_once_in_stable_order(self) -> None:
        analyzed = analyze_game_state(build_state(resolve=False))
        branches = expand_analyzed_state(analyzed)

        self.assertEqual(len(branches), len(analyzed.action_candidates.feasible))
        self.assertEqual(branches[0].id, "branch-01-0001")
        self.assertEqual(branches[-1].id, f"branch-01-{len(branches):04d}")
        self.assertEqual(
            tuple(branch.selected_candidate for branch in branches),
            analyzed.action_candidates.feasible,
        )
        self.assertTrue(
            all(branch.depth == 1 for branch in branches)
        )

    def test_child_is_reanalyzed_and_has_fresh_candidates(self) -> None:
        analyzed = analyze_game_state(build_state(resolve=False))
        branch = next(
            branch
            for branch in expand_analyzed_state(analyzed)
            if branch.selected_candidate.action_type == ActionType.PASS_TO_PLAYER
        )
        child = branch.resulting_analysis

        self.assertEqual(child.game_state.possession.player_id, "team1-2")
        self.assertNotEqual(child.state_fingerprint, analyzed.state_fingerprint)
        self.assertTrue(
            all(
                candidate.originating_state_fingerprint == child.state_fingerprint
                for candidate in child.action_candidates.all
            )
        )
        self.assertTrue(
            all(
                candidate.actor_id == "team1-2"
                for candidate in child.action_candidates.all
                if candidate.action_type
                in {
                    ActionType.MOVE_WITH_BALL,
                    ActionType.PASS_TO_PLAYER,
                    ActionType.PASS_TO_SPACE,
                }
            )
        )

    def test_space_values_are_recomputed_for_resulting_positions(self) -> None:
        analyzed = analyze_game_state(build_state(resolve=False))
        parent_distance = analyzed.target_zones_by_team["team1"][
            "OpenSpace1"
        ].nearest_defender_distance_cm
        branch = next(
            branch
            for branch in expand_analyzed_state(analyzed)
            if branch.selected_candidate.action_type == ActionType.RUN
            and branch.selected_candidate.actor_id == "team2-1"
            and branch.selected_candidate.target_zone_id == "OpenSpace1"
        )
        child_distance = branch.resulting_analysis.target_zones_by_team["team1"][
            "OpenSpace1"
        ].nearest_defender_distance_cm

        self.assertGreater(parent_distance, 0)
        self.assertEqual(child_distance, 0)

    def test_parent_state_remains_unchanged_across_all_branches(self) -> None:
        analyzed = analyze_game_state(build_state(resolve=False))
        parent_time = analyzed.game_state.time_seconds
        parent_positions = {
            player_id: player.position
            for player_id, player in analyzed.game_state.players_by_id.items()
        }

        expand_analyzed_state(analyzed)

        self.assertEqual(analyzed.game_state.time_seconds, parent_time)
        self.assertEqual(
            {
                player_id: player.position
                for player_id, player in analyzed.game_state.players_by_id.items()
            },
            parent_positions,
        )

    def test_rejects_invalid_depth(self) -> None:
        with self.assertRaises(ValueError):
            expand_analyzed_state(
                analyze_game_state(build_state(resolve=False)),
                depth=0,
            )


if __name__ == "__main__":
    unittest.main()
