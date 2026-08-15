from app.domain import GoalState, Vector2
from app.spatial.vector import direction, distance


def goal_mouth_segment(goal: GoalState) -> tuple[Vector2, Vector2]:
    mouth_x = (
        goal.top_right.x if goal.side == "left" else goal.bottom_left.x
    )
    return (
        Vector2(mouth_x, goal.bottom_left.y),
        Vector2(mouth_x, goal.top_right.y),
    )


def distance_to_goal(position: Vector2, goal: GoalState) -> float:
    return distance(position, goal.center)


def direction_to_goal(position: Vector2, goal: GoalState) -> Vector2:
    return direction(position, goal.center)
