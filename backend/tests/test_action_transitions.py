import unittest
from dataclasses import replace

from app.analysis import ActionType, PassPolicy, generate_action_candidates
from app.domain import PossessionStatus, Vector2
from app.transitions import (
    InfeasibleActionError,
    StaleActionCandidateError,
    apply_action_candidate,
)
from test_action_candidates import build_state


def candidate_for(result, action_type: ActionType, **attributes):
    return next(
        candidate
        for candidate in result.all
        if candidate.action_type == action_type
        and all(getattr(candidate, name) == value for name, value in attributes.items())
    )


class ActionTransitionTests(unittest.TestCase):
    def test_move_creates_new_state_and_leaves_parent_unchanged(self) -> None:
        state = build_state()
        candidate = candidate_for(
            generate_action_candidates(state),
            ActionType.RUN,
            actor_id="team2-1",
            target_zone_id="OpenSpace1",
        )
        transition = apply_action_candidate(state, candidate)

        self.assertIs(transition.previous_state, state)
        self.assertIsNot(transition.resulting_state, state)
        self.assertEqual(
            transition.resulting_state.players_by_id["team2-1"].position,
            candidate.destination,
        )
        self.assertEqual(
            transition.resulting_state.players_by_id["team2-1"].velocity,
            Vector2(0, 0),
        )
        self.assertEqual(state.players_by_id["team2-1"].position, Vector2(8000, 7000))
        self.assertEqual(transition.changed_player_ids, ("team2-1", "team1-2"))
        self.assertFalse(transition.ball_changed)
        self.assertEqual(
            transition.resulting_time_seconds,
            state.time_seconds + candidate.metrics.duration_seconds,
        )

    def test_move_with_ball_moves_actor_and_preserves_control(self) -> None:
        state = build_state()
        candidate = candidate_for(
            generate_action_candidates(state),
            ActionType.MOVE_WITH_BALL,
            actor_id="team1-1",
            target_zone_id="OpenSpace1",
        )
        transition = apply_action_candidate(state, candidate)
        next_state = transition.resulting_state

        self.assertEqual(next_state.players_by_id["team1-1"].position, candidate.destination)
        self.assertEqual(next_state.ball.position, candidate.destination)
        self.assertEqual(next_state.ball.speed, 0)
        self.assertEqual(next_state.possession.status, PossessionStatus.CONTROLLED)
        self.assertEqual(next_state.possession.player_id, "team1-1")
        self.assertTrue(transition.ball_changed)

    def test_direct_pass_transfers_ball_and_moves_nearest_defender(self) -> None:
        state = build_state()
        candidate = candidate_for(
            generate_action_candidates(state),
            ActionType.PASS_TO_PLAYER,
            receiver_id="team1-2",
        )
        transition = apply_action_candidate(state, candidate)
        next_state = transition.resulting_state

        self.assertEqual(next_state.ball.position, state.players_by_id["team1-2"].position)
        self.assertEqual(next_state.ball.velocity, Vector2(0, 0))
        self.assertEqual(next_state.possession.player_id, "team1-2")
        self.assertEqual(transition.changed_player_ids, ("team2-1",))
        self.assertNotEqual(
            next_state.players_by_id["team2-1"].position,
            state.players_by_id["team2-1"].position,
        )
        self.assertTrue(transition.ball_changed)
        self.assertTrue(transition.possession_changed)

    def test_space_pass_moves_receiver_to_arrival_point(self) -> None:
        state = build_state()
        candidate = candidate_for(
            generate_action_candidates(state),
            ActionType.PASS_TO_SPACE,
            receiver_id="team1-2",
            target_zone_id="OpenSpace1",
        )
        transition = apply_action_candidate(state, candidate)
        next_state = transition.resulting_state

        self.assertEqual(next_state.players_by_id["team1-2"].position, candidate.destination)
        self.assertEqual(next_state.ball.position, candidate.destination)
        self.assertEqual(next_state.possession.player_id, "team1-2")
        self.assertEqual(transition.changed_player_ids, ("team1-2", "team2-1"))

    def test_rejects_infeasible_candidate(self) -> None:
        state = build_state()
        candidate = next(
            candidate
            for candidate in generate_action_candidates(
                state,
                pass_policy=PassPolicy(receiver_arrival_tolerance_seconds=0),
            ).rejected
        )

        with self.assertRaises(InfeasibleActionError):
            apply_action_candidate(state, candidate)

    def test_rejects_candidate_after_state_changes(self) -> None:
        state = build_state()
        candidate = generate_action_candidates(state).feasible[0]
        changed_state = replace(state, time_seconds=1)

        with self.assertRaises(StaleActionCandidateError):
            apply_action_candidate(changed_state, candidate)

    def test_two_candidates_create_independent_branches(self) -> None:
        state = build_state()
        candidates = generate_action_candidates(state)
        first_candidate = candidate_for(
            candidates,
            ActionType.RUN,
            actor_id="team2-1",
            target_zone_id="OpenSpace1",
        )
        second_candidate = candidate_for(
            candidates,
            ActionType.RUN,
            actor_id="team2-1",
            target_zone_id="OpenSpace2",
        )
        first = apply_action_candidate(state, first_candidate).resulting_state
        second = apply_action_candidate(state, second_candidate).resulting_state

        self.assertIsNot(first, second)
        self.assertNotEqual(first.players_by_id, second.players_by_id)
        self.assertEqual(state.time_seconds, 0)


if __name__ == "__main__":
    unittest.main()
