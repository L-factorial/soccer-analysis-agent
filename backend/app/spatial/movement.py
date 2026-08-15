from app.domain import AttackingDirection, FieldState, Vector2
from app.spatial.errors import InvalidDurationError, InvalidSpeedError
from app.spatial.vector import add, direction, distance, scale


def required_speed(start: Vector2, target: Vector2, duration: float) -> float:
    if duration <= 0:
        raise InvalidDurationError("Duration must be greater than zero")
    return distance(start, target) / duration


def required_velocity(start: Vector2, target: Vector2, duration: float) -> Vector2:
    return scale(direction(start, target), required_speed(start, target, duration))


def travel_time(start: Vector2, target: Vector2, speed: float) -> float:
    if speed <= 0:
        raise InvalidSpeedError("Speed must be greater than zero")
    return distance(start, target) / speed


def position_after(start: Vector2, velocity: Vector2, duration: float) -> Vector2:
    if duration < 0:
        raise InvalidDurationError("Duration cannot be negative")
    return add(start, scale(velocity, duration))


def move_toward(start: Vector2, target: Vector2, travel_distance: float) -> Vector2:
    if travel_distance < 0:
        raise ValueError("Travel distance cannot be negative")
    remaining = distance(start, target)
    if remaining == 0 or travel_distance >= remaining:
        return target
    return add(start, scale(direction(start, target), travel_distance))


def is_inside_field(position: Vector2, field: FieldState) -> bool:
    return 0 <= position.x <= field.length and 0 <= position.y <= field.width


def clamp_to_field(position: Vector2, field: FieldState) -> Vector2:
    return Vector2(
        x=min(field.length, max(0, position.x)),
        y=min(field.width, max(0, position.y)),
    )


def distance_to_nearest_boundary(position: Vector2, field: FieldState) -> float:
    if not is_inside_field(position, field):
        return 0
    return min(position.x, field.length - position.x, position.y, field.width - position.y)


def forward_progress(
    direction_of_attack: AttackingDirection,
    start: Vector2,
    target: Vector2,
) -> float:
    delta_x = target.x - start.x
    return (
        delta_x
        if direction_of_attack == AttackingDirection.POSITIVE_X
        else -delta_x
    )
