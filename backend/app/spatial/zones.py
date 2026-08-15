from app.domain import TargetZoneShape, TargetZoneState, Vector2
from app.spatial.vector import direction, distance


def contains_point(zone: TargetZoneState, point: Vector2) -> bool:
    if zone.shape == TargetZoneShape.CIRCULAR:
        return distance(zone.center, point) <= (zone.radius or 0)
    return (
        zone.bottom_left.x <= point.x <= zone.top_right.x
        and zone.bottom_left.y <= point.y <= zone.top_right.y
    )


def nearest_point_in_zone(zone: TargetZoneState, point: Vector2) -> Vector2:
    if contains_point(zone, point):
        return point
    if zone.shape == TargetZoneShape.CIRCULAR:
        radius = zone.radius or 0
        return Vector2(
            zone.center.x + direction(zone.center, point).x * radius,
            zone.center.y + direction(zone.center, point).y * radius,
        )
    return Vector2(
        x=min(zone.top_right.x, max(zone.bottom_left.x, point.x)),
        y=min(zone.top_right.y, max(zone.bottom_left.y, point.y)),
    )


def distance_to_zone(zone: TargetZoneState, point: Vector2) -> float:
    return distance(point, nearest_point_in_zone(zone, point))
