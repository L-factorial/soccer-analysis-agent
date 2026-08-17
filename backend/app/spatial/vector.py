import math

from app.domain import Vector2

# Absolute tolerance for zero-length vectors and floating-point geometry checks.
EPSILON = 1e-9


def add(left: Vector2, right: Vector2) -> Vector2:
    return Vector2(left.x + right.x, left.y + right.y)


def subtract(left: Vector2, right: Vector2) -> Vector2:
    return Vector2(left.x - right.x, left.y - right.y)


def scale(vector: Vector2, factor: float) -> Vector2:
    return Vector2(vector.x * factor, vector.y * factor)


def dot(left: Vector2, right: Vector2) -> float:
    return left.x * right.x + left.y * right.y


def magnitude(vector: Vector2) -> float:
    return math.hypot(vector.x, vector.y)


def normalize(vector: Vector2) -> Vector2:
    length = magnitude(vector)
    return Vector2(0, 0) if length <= EPSILON else scale(vector, 1 / length)


def distance(start: Vector2, end: Vector2) -> float:
    return magnitude(subtract(end, start))


def direction(start: Vector2, end: Vector2) -> Vector2:
    return normalize(subtract(end, start))


def orientation_degrees(start: Vector2, end: Vector2) -> float:
    delta = subtract(end, start)
    if magnitude(delta) <= EPSILON:
        return 0
    return math.degrees(math.atan2(delta.y, delta.x)) % 360


def interpolate(start: Vector2, end: Vector2, fraction: float) -> Vector2:
    return add(start, scale(subtract(end, start), fraction))


def almost_equal(left: Vector2, right: Vector2, tolerance: float = EPSILON) -> bool:
    return distance(left, right) <= tolerance
