from dataclasses import dataclass

from app.domain import Vector2
from app.spatial import distance


@dataclass(frozen=True, slots=True)
class TrajectoryInterception:
    time_seconds: float
    position: Vector2


def position_on_linear_trajectory(
    start: Vector2,
    end: Vector2,
    duration_seconds: float,
    time_seconds: float,
    start_offset_seconds: float = 0,
) -> Vector2:
    if duration_seconds <= start_offset_seconds:
        return end
    progress = min(
        1,
        max(
            0,
            (time_seconds - start_offset_seconds)
            / (duration_seconds - start_offset_seconds),
        ),
    )
    return Vector2(
        start.x + (end.x - start.x) * progress,
        start.y + (end.y - start.y) * progress,
    )


def earliest_linear_interception(
    mover_start: Vector2,
    mover_end: Vector2,
    duration_seconds: float,
    defender_start: Vector2,
    defender_speed_cm_per_second: float,
    tackle_radius_cm: float,
    defender_start_offset_seconds: float = 0,
    mover_start_offset_seconds: float = 0,
) -> TrajectoryInterception | None:
    """Return the earliest time a defender can reach a linear moving target."""
    if duration_seconds <= 0 or defender_speed_cm_per_second <= 0:
        return None
    start_time = min(
        duration_seconds,
        max(0, defender_start_offset_seconds),
    )

    def clearance(time_seconds: float) -> float:
        mover = position_on_linear_trajectory(
            mover_start,
            mover_end,
            duration_seconds,
            time_seconds,
            mover_start_offset_seconds,
        )
        defender_travel = defender_speed_cm_per_second * max(
            0,
            time_seconds - defender_start_offset_seconds,
        )
        return distance(defender_start, mover) - defender_travel - tackle_radius_cm

    if clearance(start_time) <= 0:
        return TrajectoryInterception(
            time_seconds=start_time,
            position=position_on_linear_trajectory(
                mover_start,
                mover_end,
                duration_seconds,
                start_time,
                mover_start_offset_seconds,
            ),
        )

    # Clearance is convex for linear motion. Locate its minimum, then bisect
    # the descending side to find the first reachable tackle point.
    low = start_time
    high = duration_seconds
    for _ in range(60):
        third = (high - low) / 3
        left = low + third
        right = high - third
        if clearance(left) <= clearance(right):
            high = right
        else:
            low = left
    minimum_time = (low + high) / 2
    if clearance(minimum_time) > 1e-6:
        return None

    low = start_time
    high = minimum_time
    for _ in range(60):
        middle = (low + high) / 2
        if clearance(middle) <= 0:
            high = middle
        else:
            low = middle
    intercept_time = high
    return TrajectoryInterception(
        time_seconds=intercept_time,
        position=position_on_linear_trajectory(
            mover_start,
            mover_end,
            duration_seconds,
            intercept_time,
            mover_start_offset_seconds,
        ),
    )
