import math

from app.domain import Vector2

# Absolute tolerance for zero-length vectors and floating-point geometry checks.
EPSILON = 1e-9

# Player orientation is currently useful for presentation, but the editor does
# not yet provide reliable enough facing data to charge physical time for a
# turn. Keep this switch centralized so a future orientation model can restore
# turn duration consistently across analysis, simulation, offside, and output.
ACCOUNT_FOR_TURN_DURATION = False


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


def turn_duration_seconds(
    current_orientation: float,
    target_orientation: float,
    turning_speed_degrees_per_second: float,
) -> float:
    """Return physical turn time, currently disabled by temporary policy."""
    if not ACCOUNT_FOR_TURN_DURATION:
        return 0
    difference = abs((target_orientation - current_orientation) % 360)
    return min(difference, 360 - difference) / turning_speed_degrees_per_second


def interpolate(start: Vector2, end: Vector2, fraction: float) -> Vector2:
    return add(start, scale(subtract(end, start), fraction))


def almost_equal(left: Vector2, right: Vector2, tolerance: float = EPSILON) -> bool:
    return distance(left, right) <= tolerance
