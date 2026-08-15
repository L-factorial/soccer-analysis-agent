import unittest

from app.domain import TargetZoneShape, TargetZoneSource, TargetZoneState, Vector2
from app.spatial import (
    closest_point_on_segment,
    contains_point,
    distance_to_segment,
    distance_to_zone,
    is_within_segment_corridor,
    nearest_point_in_zone,
    projection_fraction,
)


class SegmentTests(unittest.TestCase):
    def test_projection_and_distance_on_segment(self) -> None:
        start = Vector2(0, 0)
        end = Vector2(10, 0)

        self.assertEqual(projection_fraction(Vector2(5, 3), start, end), 0.5)
        self.assertEqual(closest_point_on_segment(Vector2(5, 3), start, end), Vector2(5, 0))
        self.assertEqual(distance_to_segment(Vector2(5, 3), start, end), 3)
        self.assertEqual(closest_point_on_segment(Vector2(15, 2), start, end), end)
        self.assertTrue(is_within_segment_corridor(Vector2(5, 2), start, end, 2))

    def test_zero_length_segment(self) -> None:
        point = Vector2(3, 4)
        origin = Vector2(0, 0)
        self.assertEqual(closest_point_on_segment(point, origin, origin), origin)
        self.assertEqual(distance_to_segment(point, origin, origin), 5)


class ZoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.circle = TargetZoneState(
            id="circle",
            name="circle",
            shape=TargetZoneShape.CIRCULAR,
            source=TargetZoneSource.USER_DEFINED,
            center=Vector2(10, 10),
            bottom_left=Vector2(5, 5),
            top_right=Vector2(15, 15),
            radius=5,
        )
        self.rectangle = TargetZoneState(
            id="rectangle",
            name="rectangle",
            shape=TargetZoneShape.RECTANGULAR,
            source=TargetZoneSource.USER_DEFINED,
            center=Vector2(5, 5),
            bottom_left=Vector2(0, 0),
            top_right=Vector2(10, 10),
        )

    def test_circle_containment_and_nearest_point(self) -> None:
        self.assertTrue(contains_point(self.circle, Vector2(10, 15)))
        self.assertFalse(contains_point(self.circle, Vector2(20, 10)))
        self.assertEqual(nearest_point_in_zone(self.circle, Vector2(20, 10)), Vector2(15, 10))
        self.assertEqual(distance_to_zone(self.circle, Vector2(20, 10)), 5)

    def test_rectangle_containment_and_nearest_point(self) -> None:
        self.assertTrue(contains_point(self.rectangle, Vector2(0, 0)))
        self.assertEqual(nearest_point_in_zone(self.rectangle, Vector2(12, -2)), Vector2(10, 0))
        self.assertEqual(distance_to_zone(self.rectangle, Vector2(13, 4)), 3)


if __name__ == "__main__":
    unittest.main()
