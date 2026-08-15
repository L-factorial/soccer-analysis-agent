import unittest

from app.analysis import ActionType
from app.planning import (
    InvalidScoringPolicyError,
    ScoringPolicy,
    TacticalFlag,
    analyze_game_state,
    expand_analyzed_state,
    rank_branches,
    score_action_candidate,
    score_resulting_state,
)
from test_action_candidates import build_state


def zero_weight_policy(**overrides) -> ScoringPolicy:
    values = {
        "forward_progress_weight": 0,
        "goal_proximity_weight": 0,
        "target_space_weight": 0,
        "lane_safety_weight": 0,
        "backward_action_penalty": 0,
        "duration_penalty": 0,
        "possession_weight": 0,
        "controller_pressure_penalty": 0,
        "follow_up_options_weight": 0,
        "available_spaces_weight": 0,
    }
    values.update(overrides)
    return ScoringPolicy(**values)


class ScoringPolicyTests(unittest.TestCase):
    def test_rejects_invalid_weights_and_normalizers(self) -> None:
        with self.assertRaises(InvalidScoringPolicyError):
            ScoringPolicy(forward_progress_weight=-1)
        with self.assertRaises(InvalidScoringPolicyError):
            ScoringPolicy(duration_normalizer_seconds=0)


class CandidateScoringTests(unittest.TestCase):
    def test_action_score_matches_explainable_breakdown(self) -> None:
        analyzed = analyze_game_state(build_state(resolve=False))
        candidate = next(
            candidate
            for candidate in analyzed.action_candidates.feasible
            if candidate.action_type == ActionType.PASS_TO_PLAYER
        )
        scored = score_action_candidate(analyzed, candidate)

        self.assertAlmostEqual(scored.score, scored.breakdown.total)
        self.assertGreater(scored.breakdown.forward_progress, 0)
        self.assertIn(TacticalFlag.ADVANCES_TOWARD_GOAL, scored.flags)

    def test_forward_weight_can_isolate_forward_progress(self) -> None:
        analyzed = analyze_game_state(build_state(resolve=False))
        candidate = next(
            candidate
            for candidate in analyzed.action_candidates.feasible
            if candidate.metrics.forward_progress_cm > 0
        )
        policy = zero_weight_policy(forward_progress_weight=100)
        scored = score_action_candidate(analyzed, candidate, policy)

        expected = (
            candidate.metrics.forward_progress_cm
            / analyzed.game_state.field.length
            * 100
        )
        self.assertAlmostEqual(scored.score, expected)
        self.assertEqual(scored.breakdown.forward_progress, scored.score)

    def test_resulting_state_rewards_retained_possession(self) -> None:
        parent = analyze_game_state(build_state(resolve=False))
        pass_branch = next(
            branch
            for branch in expand_analyzed_state(parent)
            if branch.selected_candidate.action_type == ActionType.PASS_TO_PLAYER
        )
        scored = score_resulting_state(
            pass_branch.resulting_analysis,
            "team1",
        )

        self.assertGreater(scored.breakdown.possession, 0)
        self.assertIn(TacticalFlag.RETAINS_POSSESSION, scored.flags)
        self.assertAlmostEqual(scored.score, scored.breakdown.total)


class BranchRankingTests(unittest.TestCase):
    def test_ranks_every_branch_with_stable_sequential_ranks(self) -> None:
        parent = analyze_game_state(build_state(resolve=False))
        branches = expand_analyzed_state(parent)
        ranked = rank_branches(parent, branches)

        self.assertEqual(len(ranked), len(branches))
        self.assertEqual(
            tuple(item.rank for item in ranked),
            tuple(range(1, len(ranked) + 1)),
        )
        self.assertEqual(
            tuple(item.total_score for item in ranked),
            tuple(sorted((item.total_score for item in ranked), reverse=True)),
        )
        self.assertTrue(
            all(
                abs(
                    item.total_score
                    - item.immediate_action.score
                    - item.resulting_state.score
                )
                < 1e-9
                for item in ranked
            )
        )

    def test_shorter_duration_breaks_otherwise_equal_tie(self) -> None:
        parent = analyze_game_state(build_state(resolve=False))
        branches = tuple(
            branch
            for branch in expand_analyzed_state(parent)
            if branch.selected_candidate.actor_id == "team2-1"
            and branch.selected_candidate.target_zone_id == "OpenSpace1"
            and branch.selected_candidate.action_type
            in {ActionType.MOVE, ActionType.RUN}
        )
        ranked = rank_branches(parent, branches, zero_weight_policy())

        self.assertEqual(ranked[0].branch.selected_candidate.action_type, ActionType.RUN)
        self.assertEqual(ranked[1].branch.selected_candidate.action_type, ActionType.MOVE)

    def test_ranking_does_not_mutate_branch_order(self) -> None:
        parent = analyze_game_state(build_state(resolve=False))
        branches = expand_analyzed_state(parent)
        original_ids = tuple(branch.id for branch in branches)

        rank_branches(parent, branches)

        self.assertEqual(tuple(branch.id for branch in branches), original_ids)


if __name__ == "__main__":
    unittest.main()
