from app.domain import Vector2
from app.spatial.vector import EPSILON, add, distance, dot, scale, subtract


def segment_length(start: Vector2, end: Vector2) -> float:
    return distance(start, end)


def projection_fraction(point: Vector2, start: Vector2, end: Vector2) -> float:
    segment = subtract(end, start)
    squared_length = dot(segment, segment)
    if squared_length <= EPSILON:
        return 0
    return dot(subtract(point, start), segment) / squared_length


def closest_point_on_segment(
    point: Vector2,
    start: Vector2,
    end: Vector2,
) -> Vector2:
    fraction = min(1, max(0, projection_fraction(point, start, end)))
    return add(start, scale(subtract(end, start), fraction))


def distance_to_segment(point: Vector2, start: Vector2, end: Vector2) -> float:
    return distance(point, closest_point_on_segment(point, start, end))


def is_within_segment_corridor(
    point: Vector2,
    start: Vector2,
    end: Vector2,
    radius: float,
) -> bool:
    if radius < 0:
        raise ValueError("Corridor radius cannot be negative")
    return distance_to_segment(point, start, end) <= radius
