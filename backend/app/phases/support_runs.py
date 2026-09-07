"""Bounded off-ball alternatives for local overloads and passing triangles."""

from dataclasses import dataclass, replace
from itertools import permutations

from app.analysis import ActionType
from app.analysis.local_matchups import LocalMatchupPolicy
from app.domain import AttackingDirection, GameState, Vector2, is_goalkeeper
from app.phases.models import AttackingIntention, AttackingIntentionType, TacticalPhase
from app.spatial import distance, move_toward


@dataclass(frozen=True, slots=True)
class SupportRunPolicy:
    maximum_variant_fraction: float = 0.25
    maximum_run_distance_cm: float = 1800
    reaction_seconds: float = 0.15

    def __post_init__(self) -> None:
        if not 0 <= self.maximum_variant_fraction <= 0.5:
            raise ValueError("Support alternatives may use at most half the phase budget")
        if not 0 < self.maximum_run_distance_cm < float('inf'):
            raise ValueError("Support run distance must be finite and positive")
        if not 0 <= self.reaction_seconds < float('inf'):
            raise ValueError("Support reaction time must be finite and nonnegative")


def local_support_variants(
    state: GameState,
    phase: TacticalPhase,
    matchup_policy: LocalMatchupPolicy,
    policy: SupportRunPolicy,
) -> tuple[TacticalPhase, ...]:
    """Offer one or two angled outlets behind the next ball controller.

    Keep the primary ball action, receiving run and defensive intentions intact.
    Reassign support/formation players, also considering forward runners in
    three-player attacks. Larger teams preserve width and a deeper outfielder;
    decoy and goalkeeping roles remain intact. The simulator limits actual
    displacement and scores the result after defenders react.
    """
    action = phase.primary_action
    if action.action_type == ActionType.SHOT:
        return ()
    center = action.destination
    team = state.teams_by_id[phase.attacking_team_id]
    sign = 1 if team.attacking_direction == AttackingDirection.POSITIVE_X else -1
    radius = matchup_policy.radius_cm
    outfield = tuple(p for p in state.players_by_id.values() if p.team_id == team.id and not is_goalkeeper(p))
    allowed_roles = {AttackingIntentionType.SUPPORT_BALL, AttackingIntentionType.SHIFT_WITH_PLAY}
    # A three-player attack needs both teammates to offer a triangle. Retain
    # the original wide-run plan as a competing baseline, not a mandatory role.
    if len(outfield) <= 3:
        allowed_roles.add(AttackingIntentionType.FORWARD_RUN)
    cover = min(outfield, key=lambda p: (sign * p.position.x, p.id)) if len(outfield) >= 4 else None
    targets = tuple(
        Vector2(center.x - sign * radius * 0.4, center.y + side * radius * 0.85)
        for side in (-1, 1)
    )
    # Reject out-of-field anchors rather than collapsing a triangle at a sideline.
    targets = tuple(target for target in targets if 0 <= target.x <= state.field.length and 0 <= target.y <= state.field.width)
    eligible = tuple(
        state.players_by_id[intention.player_id]
        for intention in phase.attacking_intentions
        if intention.intention_type in allowed_roles
        and intention.player_id not in {action.actor_id, action.receiver_id}
        and (cover is None or intention.player_id != cover.id)
        and not is_goalkeeper(state.players_by_id[intention.player_id])
    )
    if not eligible or not targets:
        return ()
    variants = []
    for count in range(1, min(2, len(eligible), len(targets)) + 1):
        assignments = []
        for players in permutations(eligible, count):
            for anchors in permutations(targets, count):
                cost = sum(distance(player.position, target) / player.speed_category.multiplier for player, target in zip(players, anchors))
                assignments.append((cost, tuple(p.id for p in players), anchors))
        _, player_ids, anchors = min(assignments, key=lambda item: (item[0], item[1], tuple((p.x, p.y) for p in item[2])))
        replacements = {
            player_id: AttackingIntention(
                player_id=player_id,
                intention_type=AttackingIntentionType.SUPPORT_BALL,
                target=move_toward(state.players_by_id[player_id].position, target, policy.maximum_run_distance_cm),
                start_offset_seconds=policy.reaction_seconds,
            )
            for player_id, target in zip(player_ids, anchors)
        }
        intentions = tuple(replacements.get(item.player_id, item) for item in phase.attacking_intentions)
        if intentions != phase.attacking_intentions:
            variants.append(replace(phase, id=f'{phase.id}-support-{count}', attacking_intentions=intentions))
    return tuple(variants)
