"""Quality of local passing triangles with two already usable support options."""

from dataclasses import dataclass, replace
from itertools import combinations
from math import isfinite, radians, sin

from app.analysis.passing import PassPolicy, analyze_pass_to_player
from app.domain import AttackingDirection, GameState
from app.spatial import distance


@dataclass(frozen=True, slots=True)
class PassingTrianglePolicy:
    minimum_angle_degrees: float = 20

    def __post_init__(self) -> None:
        if not isfinite(self.minimum_angle_degrees) or not 0 < self.minimum_angle_degrees < 60:
            raise ValueError("Minimum triangle angle must be between 0 and 60 degrees")


@dataclass(frozen=True, slots=True)
class PassingTriangle:
    player_ids: tuple[str, str, str]
    quality: float


def discover_passing_triangles(
    state: GameState,
    carrier_id: str,
    support_ids: tuple[str, ...],
    pass_policy: PassPolicy = PassPolicy(),
    policy: PassingTrianglePolicy = PassingTrianglePolicy(),
) -> tuple[PassingTriangle, ...]:
    """Require separated angles and a feasible connection between supporters.

    The caller supplies onside, spaced supporters with feasible carrier passes.
    The third edge is a static next-pass opportunity, not a guaranteed sequence;
    subsequent search phases simulate the actual defensive response.
    """
    carrier = state.players_by_id[carrier_id]
    direction = state.teams_by_id[carrier.team_id].attacking_direction
    def progress(position):
        return position.x if direction == AttackingDirection.POSITIVE_X else state.field.length - position.x
    defenders = sorted((progress(p.position) for p in state.players_by_id.values() if p.team_id != carrier.team_id), reverse=True)
    triangles = []
    for first_id, second_id in combinations(sorted(support_ids), 2):
        first, second = (state.players_by_id[key] for key in (first_id, second_id))
        a, b, c = carrier.position, first.position, second.position
        lengths = (distance(a, b), distance(a, c), distance(b, c))
        if min(lengths) <= 0:
            continue
        area_twice = abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x))
        smallest_sine = min(area_twice / (x * y) for x, y in combinations(lengths, 2))
        if smallest_sine < sin(radians(policy.minimum_angle_degrees)):
            continue
        connected = False
        for passer, receiver in ((first, second), (second, first)):
            if len(defenders) >= 2 and progress(receiver.position) > max(
                state.field.length / 2, progress(passer.position), defenders[1]
            ) + 1:
                continue
            hypothetical = replace(
                state,
                possession=replace(state.possession, player_id=passer.id),
                ball=replace(state.ball, position=passer.position),
            )
            if analyze_pass_to_player(hypothetical, passer.id, receiver.id, policy=pass_policy).feasible:
                connected = True
                break
        if connected:
            triangles.append(PassingTriangle(
                (carrier_id, first_id, second_id),
                min(1, smallest_sine / sin(radians(60))),
            ))
    return tuple(sorted(triangles, key=lambda triangle: (-triangle.quality, triangle.player_ids)))
