from app.analysis import ActionType
from app.models.animation_response import (
    AnimationResponse,
    MoveEvent,
    PassEvent,
    PassToSpaceEvent,
    ReceiveEvent,
    ShotEvent,
)
from app.models.position import Position
from app.planning import SearchSequence
from app.models.animation_response import PlannerDiagnostics


# Cap purely visual pauses so a valid plan does not appear frozen in playback.
MAXIMUM_VISIBLE_HOLD_SECONDS = 1.5


def _time(value: float) -> float:
    return round(value, 6)


def _position(x: float, y: float) -> Position:
    return Position(x=x, y=y)


def build_animation_response(
    sequence: SearchSequence,
    diagnostics: PlannerDiagnostics | None = None,
) -> AnimationResponse:
    events = []
    next_event_number = 1
    start_time = 0.0

    def player_available_time(player_id: str) -> float:
        return max(
            (
                event.start_time + getattr(event, "duration", 0)
                for event in events
                if event.player_id == player_id
            ),
            default=0.0,
        )

    for step in sequence.steps:
        candidate = step.candidate
        step_duration = candidate.metrics.duration_seconds
        raw_duration = (
            candidate.metrics.ball_travel_duration_seconds or step_duration
        )
        duration = _time(raw_duration)
        event_id = f"action{next_event_number}"
        target = _position(candidate.destination.x, candidate.destination.y)
        step_end_time = start_time + step_duration
        reaction_start_time = start_time
        reaction_duration = step_duration

        if candidate.action_type in {
            ActionType.MOVE,
            ActionType.RUN,
            ActionType.MOVE_WITH_BALL,
        }:
            events.append(
                MoveEvent(
                    id=event_id,
                    type=candidate.action_type.value,
                    player_id=candidate.actor_id,
                    start_time=_time(start_time),
                    duration=duration,
                    target=target,
                )
            )
            next_event_number += 1
        elif candidate.action_type == ActionType.PASS_TO_PLAYER:
            if candidate.receiver_id is None:
                raise ValueError("Pass candidate is missing its receiver")
            events.append(
                PassEvent(
                    id=event_id,
                    type="PASS",
                    player_id=candidate.actor_id,
                    target_player_id=candidate.receiver_id,
                    start_time=_time(start_time),
                    duration=duration,
                )
            )
            next_event_number += 1
            events.append(
                ReceiveEvent(
                    id=f"action{next_event_number}",
                    type="RECEIVE",
                    player_id=candidate.receiver_id,
                    start_time=_time(start_time + duration),
                )
            )
            next_event_number += 1
        elif candidate.action_type == ActionType.PASS_TO_SPACE:
            if candidate.receiver_id is None or candidate.target_zone_id is None:
                raise ValueError("Space pass is missing its receiver or target space")
            receiver_duration = candidate.metrics.receiver_arrival_time_seconds or 0
            # A future receiver may start a supporting run during earlier
            # actions. Use their earliest conflict-free start; the old formula
            # targeted the latest permitted arrival and therefore inserted the
            # full 1.5-second hold even when no wait was necessary.
            receiver_start_time = max(
                player_available_time(candidate.receiver_id),
                start_time,
                0,
            )
            step_end_time = max(
                start_time + raw_duration,
                receiver_start_time + receiver_duration,
            )
            natural_pass_start = max(start_time, step_end_time - raw_duration)
            # Legacy action sequences can leave the receiver occupied by an
            # earlier animation after the next search step has begun. Cap the
            # visible preparation pause and stretch only the presentation-time
            # ball event so it still reaches the receiver at step_end_time.
            pass_start_time = min(
                natural_pass_start,
                start_time + MAXIMUM_VISIBLE_HOLD_SECONDS,
            )
            scheduled_pass_duration = step_end_time - pass_start_time
            coordinated_duration = step_end_time - start_time
            # Defensive pressure continues while the passer prepares and while
            # the ball travels, rather than beginning only at release time.
            reaction_start_time = start_time
            reaction_duration = coordinated_duration
            if receiver_duration > 0:
                events.append(
                    MoveEvent(
                        id=event_id,
                        type="RUN",
                        player_id=candidate.receiver_id,
                        start_time=_time(receiver_start_time),
                        duration=_time(receiver_duration),
                        target=target,
                    )
                )
                next_event_number += 1
            events.append(
                PassToSpaceEvent(
                    id=f"action{next_event_number}",
                    type="PASS_TO_SPACE",
                    player_id=candidate.actor_id,
                    intended_receiver_id=candidate.receiver_id,
                    space_id=candidate.target_zone_id,
                    start_time=_time(pass_start_time),
                    duration=_time(scheduled_pass_duration),
                    target=target,
                )
            )
            next_event_number += 1
            events.append(
                ReceiveEvent(
                    id=f"action{next_event_number}",
                    type="RECEIVE",
                    player_id=candidate.receiver_id,
                    start_time=_time(step_end_time),
                )
            )
            next_event_number += 1
        elif candidate.action_type == ActionType.SHOT:
            events.append(
                ShotEvent(
                    id=event_id,
                    type="SHOT",
                    player_id=candidate.actor_id,
                    goal_id=candidate.source_analysis.goal_id,
                    start_time=_time(start_time),
                    duration=_time(reaction_duration),
                    target=target,
                )
            )
            next_event_number += 1

        explicitly_animated_players = {candidate.actor_id}
        if candidate.action_type == ActionType.PASS_TO_SPACE:
            explicitly_animated_players.add(candidate.receiver_id)
        previous_players = step.transition.previous_state.players_by_id
        resulting_players = step.transition.resulting_state.players_by_id
        for player_id in step.transition.changed_player_ids:
            if player_id in explicitly_animated_players:
                continue
            previous = previous_players[player_id]
            resulting = resulting_players[player_id]
            if previous.position == resulting.position:
                continue
            events.append(
                MoveEvent(
                    id=f"action{next_event_number}",
                    type="RUN",
                    player_id=player_id,
                    start_time=_time(reaction_start_time),
                    duration=_time(reaction_duration),
                    target=_position(
                        resulting.position.x,
                        resulting.position.y,
                    ),
                )
            )
            next_event_number += 1

        start_time = step_end_time

    duration = _time(start_time)
    if events:
        event_end = max(
            event.start_time + getattr(event, "duration", 0) for event in events
        )
        # Event components and response duration are serialized independently
        # to six decimals, so their reconstructed sums may differ by one unit
        # in the final decimal place.
        if event_end > duration + 2e-6:
            raise ValueError(
                f"Animation events end at {event_end}, after sequence {duration}"
            )
    return AnimationResponse(
        duration=duration,
        events=tuple(events),
        diagnostics=diagnostics,
    )
