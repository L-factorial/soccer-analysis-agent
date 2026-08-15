import unittest

from app.planning import (
    InvalidSearchPolicyError,
    SearchPolicy,
    analyze_game_state,
    search_tactical_sequences,
)
from test_action_candidates import build_state


class SearchPolicyTests(unittest.TestCase):
    def test_rejects_invalid_search_bounds(self) -> None:
        with self.assertRaises(InvalidSearchPolicyError):
            SearchPolicy(maximum_depth=0)
        with self.assertRaises(InvalidSearchPolicyError):
            SearchPolicy(beam_width=0)
        with self.assertRaises(InvalidSearchPolicyError):
            SearchPolicy(score_discount=1.1)
        with self.assertRaises(InvalidSearchPolicyError):
            SearchPolicy(maximum_retained_nodes=0)
        with self.assertRaises(InvalidSearchPolicyError):
            SearchPolicy(maximum_consecutive_off_ball_actions=-1)


class TacticalSearchTests(unittest.TestCase):
    def test_search_respects_depth_and_beam_width(self) -> None:
        result = search_tactical_sequences(
            build_state(resolve=False),
            SearchPolicy(maximum_depth=2, beam_width=3),
        )

        self.assertEqual(result.diagnostics.reached_depth, 2)
        self.assertTrue(result.best_sequences)
        self.assertTrue(
            all(1 <= sequence.depth <= 2 for sequence in result.best_sequences)
        )
        self.assertTrue(
            all(len(sequence.steps) == sequence.depth for sequence in result.best_sequences)
        )

    def test_cumulative_score_uses_depth_discount(self) -> None:
        discount = 0.5
        result = search_tactical_sequences(
            build_state(resolve=False),
            SearchPolicy(maximum_depth=2, beam_width=1, score_discount=discount),
        )
        sequence = result.best_sequences[0]

        self.assertEqual(len(sequence.steps), 2)
        self.assertAlmostEqual(
            sequence.cumulative_score,
            sequence.steps[0].step_score
            + discount * sequence.steps[1].step_score,
        )
        self.assertAlmostEqual(
            sequence.steps[1].discounted_score,
            discount * sequence.steps[1].step_score,
        )

    def test_search_accepts_preanalyzed_root(self) -> None:
        root = analyze_game_state(build_state(resolve=False))
        result = search_tactical_sequences(
            root,
            SearchPolicy(maximum_depth=1, beam_width=2),
        )

        self.assertIs(result.root, root)
        self.assertLessEqual(len(result.best_sequences), 2)

    def test_duration_limit_prunes_long_sequences(self) -> None:
        result = search_tactical_sequences(
            build_state(resolve=False),
            SearchPolicy(
                maximum_depth=2,
                beam_width=3,
                maximum_sequence_duration_seconds=0.01,
            ),
        )

        self.assertFalse(result.best_sequences)
        self.assertGreater(result.diagnostics.pruned_by_duration_count, 0)

    def test_node_limit_stops_search(self) -> None:
        result = search_tactical_sequences(
            build_state(resolve=False),
            SearchPolicy(
                maximum_depth=4,
                beam_width=5,
                maximum_retained_nodes=3,
            ),
        )

        self.assertTrue(result.diagnostics.stopped_by_node_limit)
        self.assertEqual(result.diagnostics.retained_node_count, 3)
        self.assertGreater(result.diagnostics.pruned_by_node_limit_count, 0)

    def test_beam_pruning_occurs_before_retained_node_budget(self) -> None:
        result = search_tactical_sequences(
            build_state(resolve=False),
            SearchPolicy(
                maximum_depth=2,
                beam_width=3,
                maximum_retained_nodes=75,
            ),
        )

        self.assertEqual(result.diagnostics.reached_depth, 2)
        self.assertFalse(result.diagnostics.stopped_by_node_limit)
        self.assertLessEqual(result.diagnostics.retained_node_count, 7)

    def test_sequence_order_is_deterministic_and_score_descending(self) -> None:
        policy = SearchPolicy(maximum_depth=2, beam_width=3)
        first = search_tactical_sequences(build_state(resolve=False), policy)
        second = search_tactical_sequences(build_state(resolve=False), policy)

        self.assertEqual(
            tuple(sequence.cumulative_score for sequence in first.best_sequences),
            tuple(
                sorted(
                    (
                        sequence.cumulative_score
                        for sequence in first.best_sequences
                    ),
                    reverse=True,
                )
            ),
        )
        self.assertEqual(
            tuple(
                tuple(step.candidate.id for step in sequence.steps)
                for sequence in first.best_sequences
            ),
            tuple(
                tuple(step.candidate.id for step in sequence.steps)
                for sequence in second.best_sequences
            ),
        )

    def test_search_does_not_mutate_initial_state(self) -> None:
        state = build_state(resolve=False)
        original_time = state.time_seconds
        original_positions = {
            player_id: player.position
            for player_id, player in state.players_by_id.items()
        }

        search_tactical_sequences(
            state,
            SearchPolicy(maximum_depth=2, beam_width=2),
        )

        self.assertEqual(state.time_seconds, original_time)
        self.assertEqual(
            {
                player_id: player.position
                for player_id, player in state.players_by_id.items()
            },
            original_positions,
        )

    def test_prevents_repeated_off_ball_actions(self) -> None:
        result = search_tactical_sequences(
            build_state(resolve=False),
            SearchPolicy(maximum_depth=3, beam_width=5),
        )
        ball_action_types = {
            "MOVE_WITH_BALL",
            "PASS_TO_PLAYER",
            "PASS_TO_SPACE",
            "SHOT",
        }

        for sequence in result.best_sequences:
            consecutive_off_ball = 0
            for step in sequence.steps:
                if step.candidate.action_type.value in ball_action_types:
                    consecutive_off_ball = 0
                else:
                    consecutive_off_ball += 1
                self.assertLessEqual(consecutive_off_ball, 1)


if __name__ == "__main__":
    unittest.main()
