import unittest

from app.game_engine import interpret_tactical_instruction
from app.phases import PhaseScoringPolicy, PhaseSearchPolicy


class TacticalInstructionTests(unittest.TestCase):
    def test_maps_free_text_to_search_and_scoring_preferences(self) -> None:
        interpreted = interpret_tactical_instruction(
            "Attack quickly through wide space",
            PhaseSearchPolicy(),
        )

        self.assertEqual(
            interpreted.applied_directives,
            ("FAST_TEMPO", "ATTACK_AGGRESSIVELY", "CREATE_SPACE"),
        )
        self.assertEqual(interpreted.search.score_discount, 0.82)
        self.assertEqual(interpreted.scoring.forward_progress_weight, 55)
        self.assertEqual(interpreted.scoring.coordination_weight, 20)
        self.assertEqual(interpreted.scoring.duration_penalty_weight, 20)

    def test_unknown_text_preserves_default_planner_policy(self) -> None:
        search = PhaseSearchPolicy()
        scoring = PhaseScoringPolicy()
        interpreted = interpret_tactical_instruction(
            "Keep the goalkeeper calm",
            search,
            scoring,
        )

        self.assertEqual(interpreted.applied_directives, ())
        self.assertEqual(interpreted.search, search)
        self.assertEqual(interpreted.scoring, scoring)


if __name__ == "__main__":
    unittest.main()
