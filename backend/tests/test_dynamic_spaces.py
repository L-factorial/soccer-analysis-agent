import unittest

from app.analysis import discover_dynamic_open_spaces
from app.domain import TargetZoneSource
from app.planning import analyze_game_state
from test_action_candidates import build_state


class DynamicSpaceTests(unittest.TestCase):
    def test_discovers_small_stable_team_specific_space_set(self) -> None:
        state = build_state()

        first = discover_dynamic_open_spaces(state, "team1")
        second = discover_dynamic_open_spaces(state, "team1")

        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 3)
        self.assertTrue(first)
        self.assertTrue(all(zone.source == TargetZoneSource.DYNAMIC for zone in first))
        self.assertTrue(all(zone.attacking_team_id == "team1" for zone in first))
        self.assertTrue(all(zone.radius is not None for zone in first))

    def test_analyzed_state_contains_computed_spaces_without_mutating_input(self) -> None:
        state = build_state()
        original_zone_ids = tuple(state.target_zones_by_id)

        analyzed = analyze_game_state(state)
        dynamic = [
            zone for zone in analyzed.game_state.target_zones_by_id.values()
            if zone.source == TargetZoneSource.DYNAMIC
        ]

        self.assertTrue(dynamic)
        self.assertEqual(tuple(state.target_zones_by_id), original_zone_ids)


if __name__ == "__main__":
    unittest.main()
