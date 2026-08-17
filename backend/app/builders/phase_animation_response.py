from app.analysis import ActionType
from app.models.animation_response import (
    AnimationResponse,
    MoveEvent,
    PassEvent,
    PassToSpaceEvent,
    PlannerDiagnostics,
    ReceiveEvent,
    ShotEvent,
    TurnEvent,
)
from app.models.position import Position
from app.phases import PhaseSearchNode
# Presentation-time turning rate. Simulation already determines whether the
# phase is feasible; the scheduler uses this to place TURN before RUN/ball events.
TURNING_SPEED_DEGREES_PER_SECOND = 180


def _time(value: float) -> float:
    return round(value, 6)


def _position(x: float, y: float) -> Position:
    return Position(x=x, y=y)


def _turn_duration(current: float, target: float) -> float:
    difference = abs((target - current) % 360)
    return min(difference, 360 - difference) / TURNING_SPEED_DEGREES_PER_SECOND


def build_phase_animation_response(
    sequence: PhaseSearchNode,
    diagnostics: PlannerDiagnostics,
) -> AnimationResponse:
    """Compile coordinated phase steps into the existing frontend event union."""
    events = []
    event_number = 1
    phase_start = 0.0

    def next_id() -> str:
        nonlocal event_number
        value = f"action{event_number}"
        event_number += 1
        return value

    def add_turn_event(
        player_id: str,
        start_time: float,
        start_orientation: float,
        target_orientation: float,
    ) -> float:
        duration = _turn_duration(start_orientation, target_orientation)
        if duration <= 1e-9:
            return 0
        events.append(
            TurnEvent(
                id=next_id(),
                type="TURN",
                player_id=player_id,
                start_time=_time(start_time),
                duration=_time(duration),
                start_orientation=start_orientation,
                target_orientation=target_orientation,
            )
        )
        return duration

    for step in sequence.steps:
        phase = step.phase
        action = phase.primary_action
        simulation = step.simulation
        phase_end = phase_start + phase.duration_seconds
        previous_players = simulation.previous_state.players_by_id
        resulting_players = simulation.resulting_state.players_by_id

        for intention in phase.attacking_intentions:
            player = previous_players[intention.player_id]
            resulting = resulting_players[intention.player_id]
            if player.position == resulting.position:
                continue
            turn_duration = add_turn_event(
                player.id,
                phase_start + intention.start_offset_seconds,
                player.orientation,
                resulting.orientation,
            )
            run_start = (
                phase_start
                + intention.start_offset_seconds
                + turn_duration
            )
            # The simulator already caps the resulting destination by maximum
            # speed. Spreading that distance over the remaining phase prevents
            # early arrival followed by an artificial idle pause.
            run_duration = max(0, phase_end - run_start)
            if run_duration <= 0:
                continue
            events.append(
                MoveEvent(
                    id=next_id(),
                    type="RUN",
                    player_id=intention.player_id,
                    start_time=_time(run_start),
                    duration=_time(run_duration),
                    target=_position(resulting.position.x, resulting.position.y),
                )
            )

        for intention in phase.defensive_intentions:
            player = previous_players[intention.player_id]
            resulting = resulting_players[intention.player_id]
            if player.position == resulting.position:
                continue
            turn_duration = add_turn_event(
                player.id,
                phase_start + intention.start_offset_seconds,
                player.orientation,
                resulting.orientation,
            )
            start = (
                phase_start
                + intention.start_offset_seconds
                + turn_duration
            )
            duration = max(0, phase_end - start)
            if duration <= 0:
                continue
            events.append(
                MoveEvent(
                    id=next_id(),
                    type="RUN",
                    player_id=intention.player_id,
                    start_time=_time(start),
                    duration=_time(duration),
                    target=_position(resulting.position.x, resulting.position.y),
                )
            )

        target = _position(action.destination.x, action.destination.y)
        if action.action_type in {
            ActionType.PASS_TO_SPACE,
            ActionType.PASS_TO_PLAYER,
            ActionType.SHOT,
            ActionType.MOVE_WITH_BALL,
        }:
            actor = previous_players[action.actor_id]
            add_turn_event(
                actor.id,
                phase_start,
                actor.orientation,
                action.source_analysis.orientation_degrees,
            )
        if action.action_type == ActionType.PASS_TO_SPACE:
            raw_duration = action.metrics.ball_travel_duration_seconds or action.metrics.duration_seconds
            pass_start = phase_start + phase.ball_action_start_offset_seconds
            events.append(
                PassToSpaceEvent(
                    id=next_id(),
                    type="PASS_TO_SPACE",
                    player_id=action.actor_id,
                    intended_receiver_id=action.receiver_id,
                    space_id=action.target_zone_id,
                    start_time=_time(pass_start),
                    duration=_time(raw_duration),
                    target=target,
                )
            )
            events.append(
                ReceiveEvent(
                    id=next_id(), type="RECEIVE",
                    player_id=action.receiver_id,
                    start_time=_time(phase_end),
                )
            )
        elif action.action_type == ActionType.PASS_TO_PLAYER:
            events.append(
                PassEvent(
                    id=next_id(), type="PASS", player_id=action.actor_id,
                    target_player_id=action.receiver_id,
                    start_time=_time(phase_start),
                    duration=_time(phase.duration_seconds),
                )
            )
            events.append(
                ReceiveEvent(
                    id=next_id(), type="RECEIVE",
                    player_id=action.receiver_id,
                    start_time=_time(phase_end),
                )
            )
        elif action.action_type == ActionType.SHOT:
            raw_duration = (
                action.metrics.ball_travel_duration_seconds
                or action.metrics.duration_seconds
            )
            events.append(
                ShotEvent(
                    id=next_id(), type="SHOT", player_id=action.actor_id,
                    goal_id=action.source_analysis.goal_id,
                    start_time=_time(
                        phase_start + phase.ball_action_start_offset_seconds
                    ),
                    duration=_time(raw_duration),
                    target=target,
                )
            )
        elif action.action_type == ActionType.MOVE_WITH_BALL:
            movement = action.source_analysis
            events.append(
                MoveEvent(
                    id=next_id(), type="MOVE_WITH_BALL",
                    player_id=action.actor_id,
                    start_time=_time(
                        phase_start + movement.turn_duration_seconds
                    ),
                    duration=_time(movement.travel_duration_seconds),
                    target=target,
                )
            )
        phase_start = phase_end

    return AnimationResponse(
        duration=_time(phase_start),
        events=tuple(sorted(events, key=lambda event: (event.start_time, event.id))),
        diagnostics=diagnostics,
    )
