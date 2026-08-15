import unittest

from app.domain import AttackingDirection, FieldState, Vector2
from app.models.field import FieldType
from app.spatial import (
    InvalidDurationError,
    InvalidSpeedError,
    clamp_to_field,
    direction,
    distance,
    forward_progress,
    interpolate,
    is_inside_field,
    normalize,
    orientation_degrees,
    position_after,
    required_speed,
    required_velocity,
    travel_time,
)


class VectorAndMovementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.field = FieldState(FieldType.FIVE_V_FIVE, 12000, 9000, "cm")

    def test_distance_direction_and_orientation(self) -> None:
        start = Vector2(0, 0)
        target = Vector2(3, 4)

        self.assertEqual(distance(start, target), 5)
        result = direction(start, target)
        self.assertAlmostEqual(result.x, 0.6)
        self.assertAlmostEqual(result.y, 0.8)
        self.assertAlmostEqual(orientation_degrees(start, target), 53.130102, places=5)
        self.assertEqual(orientation_degrees(start, Vector2(-1, 0)), 180)
        self.assertEqual(orientation_degrees(start, Vector2(0, -1)), 270)

    def test_zero_vector_policy_and_interpolation(self) -> None:
        self.assertEqual(normalize(Vector2(0, 0)), Vector2(0, 0))
        self.assertEqual(interpolate(Vector2(0, 0), Vector2(10, 20), 0.5), Vector2(5, 10))

    def test_speed_velocity_time_and_position(self) -> None:
        start = Vector2(0, 0)
        target = Vector2(300, 400)

        self.assertEqual(required_speed(start, target, 2), 250)
        velocity = required_velocity(start, target, 2)
        self.assertEqual(velocity, Vector2(150, 200))
        self.assertEqual(travel_time(start, target, 100), 5)
        self.assertEqual(position_after(start, velocity, 2), target)

    def test_invalid_time_and_speed_are_rejected(self) -> None:
        with self.assertRaises(InvalidDurationError):
            required_speed(Vector2(0, 0), Vector2(1, 0), 0)
        with self.assertRaises(InvalidSpeedError):
            travel_time(Vector2(0, 0), Vector2(1, 0), 0)
        with self.assertRaises(InvalidDurationError):
            position_after(Vector2(0, 0), Vector2(1, 0), -1)

    def test_field_boundaries_and_progress(self) -> None:
        self.assertTrue(is_inside_field(Vector2(0, 9000), self.field))
        self.assertFalse(is_inside_field(Vector2(-1, 100), self.field))
        self.assertEqual(clamp_to_field(Vector2(-4, 9500), self.field), Vector2(0, 9000))
        self.assertEqual(
            forward_progress(AttackingDirection.POSITIVE_X, Vector2(10, 0), Vector2(30, 0)),
            20,
        )
        self.assertEqual(
            forward_progress(AttackingDirection.NEGATIVE_X, Vector2(30, 0), Vector2(10, 0)),
            20,
        )


if __name__ == "__main__":
    unittest.main()
