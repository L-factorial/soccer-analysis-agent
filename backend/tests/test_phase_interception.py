import unittest

from app.domain import Vector2
from app.phases.interception import earliest_linear_interception


class LinearInterceptionTests(unittest.TestCase):
    def test_defender_ahead_can_intercept_dribbler(self) -> None:
        result = earliest_linear_interception(
            mover_start=Vector2(4500, 2790),
            mover_end=Vector2(9000, 2790),
            duration_seconds=9,
            defender_start=Vector2(7004.2918454935625, 999.0865952496808),
            defender_speed_cm_per_second=500,
            tackle_radius_cm=150,
        )

        self.assertIsNotNone(result)
        self.assertLess(result.time_seconds, 9)
        self.assertGreater(result.position.x, 4500)

    def test_equally_fast_trailing_defender_cannot_catch_dribbler(self) -> None:
        result = earliest_linear_interception(
            mover_start=Vector2(1000, 1000),
            mover_end=Vector2(5500, 1000),
            duration_seconds=9,
            defender_start=Vector2(500, 1000),
            defender_speed_cm_per_second=500,
            tackle_radius_cm=150,
        )

        self.assertIsNone(result)

    def test_returns_immediate_tackle_inside_radius(self) -> None:
        result = earliest_linear_interception(
            mover_start=Vector2(1000, 1000),
            mover_end=Vector2(2000, 1000),
            duration_seconds=2,
            defender_start=Vector2(1100, 1000),
            defender_speed_cm_per_second=500,
            tackle_radius_cm=150,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.time_seconds, 0)

    def test_mover_remains_stationary_while_turning(self) -> None:
        result = earliest_linear_interception(
            mover_start=Vector2(1000, 1000),
            mover_end=Vector2(2000, 1000),
            duration_seconds=2.5,
            mover_start_offset_seconds=0.5,
            defender_start=Vector2(1400, 1000),
            defender_speed_cm_per_second=500,
            tackle_radius_cm=150,
        )

        self.assertIsNotNone(result)
        self.assertLessEqual(result.time_seconds, 0.5)


if __name__ == "__main__":
    unittest.main()
