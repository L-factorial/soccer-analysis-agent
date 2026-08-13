import {
  AnimationEvent,
  AnimationSession,
  clampFieldPosition,
  cloneFieldConfiguration,
  FieldConfiguration,
  Position,
} from "../../models";

export const ANIMATION_FRAMES_PER_SECOND = 100;

type Movement = {
  direction: Position;
  orientation: number;
  position: Position;
  reachedTarget: boolean;
};

export function secondsToAnimationFrame(seconds: number): number {
  return Math.round(seconds * ANIMATION_FRAMES_PER_SECOND);
}

export function animationFrameToSeconds(frame: number): number {
  return frame / ANIMATION_FRAMES_PER_SECOND;
}

function orientationToward(from: Position, to: Position): number {
  return (Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI;
}

function moveToward(
  from: Position,
  target: Position,
  maximumDistance: number,
): Movement {
  const deltaX = target.x - from.x;
  const deltaY = target.y - from.y;
  const distance = Math.hypot(deltaX, deltaY);
  const orientation = orientationToward(from, target);

  if (distance === 0) {
    return {
      direction: { x: 0, y: 0 },
      orientation,
      position: from,
      reachedTarget: true,
    };
  }

  const direction = { x: deltaX / distance, y: deltaY / distance };
  const traveledDistance = Math.min(distance, maximumDistance);

  return {
    direction,
    orientation,
    position: clampFieldPosition({
      x: from.x + direction.x * traveledDistance,
      y: from.y + direction.y * traveledDistance,
    }),
    reachedTarget: traveledDistance >= distance,
  };
}

function updatePlayer(
  configuration: FieldConfiguration,
  playerId: string,
  target: Position,
  remainingFrames: number,
): FieldConfiguration {
  return {
    ...configuration,
    players: configuration.players.map((player) => {
      if (player.id !== playerId) {
        return player;
      }

      const safeTarget = clampFieldPosition(target);
      const remainingDistance = Math.hypot(
        safeTarget.x - player.position.x,
        safeTarget.y - player.position.y,
      );
      const distancePerFrame = remainingDistance / Math.max(1, remainingFrames);
      const movement = moveToward(player.position, safeTarget, distancePerFrame);
      const speed = distancePerFrame * ANIMATION_FRAMES_PER_SECOND;

      return {
        ...player,
        position: movement.position,
        orientation: movement.orientation,
        velocity: movement.reachedTarget
          ? { x: 0, y: 0 }
          : {
              x: movement.direction.x * speed,
              y: movement.direction.y * speed,
            },
      };
    }),
  };
}

function updateBall(
  configuration: FieldConfiguration,
  target: Position,
  remainingFrames: number,
): FieldConfiguration {
  const safeTarget = clampFieldPosition(target);
  const remainingDistance = Math.hypot(
    safeTarget.x - configuration.ball.position.x,
    safeTarget.y - configuration.ball.position.y,
  );
  const distancePerFrame = remainingDistance / Math.max(1, remainingFrames);
  const movement = moveToward(
    configuration.ball.position,
    safeTarget,
    distancePerFrame,
  );

  return {
    ...configuration,
    ball: {
      ...configuration.ball,
      position: movement.position,
      direction: movement.orientation,
      speed: movement.reachedTarget
        ? 0
        : distancePerFrame * ANIMATION_FRAMES_PER_SECOND,
    },
  };
}

function latestEventForPlayer(
  events: AnimationEvent[],
  playerId: string,
): AnimationEvent | undefined {
  return events.findLast(
    (event) =>
      event.playerId === playerId &&
      (event.type === "RUN" ||
        event.type === "MOVE" ||
        event.type === "MOVE_WITH_BALL"),
  );
}

function latestBallEvent(events: AnimationEvent[]): AnimationEvent | undefined {
  return events.findLast(
    (event) =>
      event.type === "MOVE_WITH_BALL" ||
      event.type === "PASS" ||
      event.type === "PASS_TO_SPACE" ||
      event.type === "RECEIVE",
  );
}

function eventsActiveAtFrame(
  events: AnimationEvent[],
  frame: number,
): AnimationEvent[] {
  return events
    .filter((event) => {
      const startFrame = secondsToAnimationFrame(event.startTime);
      const endFrame = secondsToAnimationFrame(
        event.startTime + (event.duration ?? 0),
      );
      return event.duration === undefined
        ? frame === startFrame
        : startFrame < frame && frame <= endFrame;
    })
    .sort((left, right) => left.startTime - right.startTime);
}

export function applyAnimationEvent(
  configuration: FieldConfiguration,
  event: AnimationEvent,
  currentFrame = secondsToAnimationFrame(event.startTime) + 1,
): FieldConfiguration {
  const endFrame = secondsToAnimationFrame(
    event.startTime + (event.duration ?? 0),
  );
  const remainingFrames = Math.max(1, endFrame - currentFrame + 1);

  switch (event.type) {
    case "RUN":
    case "MOVE":
      return updatePlayer(
        configuration,
        event.playerId,
        event.target,
        remainingFrames,
      );

    case "MOVE_WITH_BALL": {
      const movedConfiguration = updatePlayer(
        configuration,
        event.playerId,
        event.target,
        remainingFrames,
      );
      const player = movedConfiguration.players.find(
        ({ id }) => id === event.playerId,
      );

      const playerSpeed = player?.velocity
        ? Math.hypot(player.velocity.x, player.velocity.y)
        : 0;

      return player
        ? {
            ...movedConfiguration,
            ball: {
              ...movedConfiguration.ball,
              position: { ...player.position },
              direction: player.orientation,
              speed: playerSpeed,
            },
          }
        : movedConfiguration;
    }

    case "PASS": {
      const receiver = configuration.players.find(
        ({ id }) => id === event.targetPlayerId,
      );
      return receiver
        ? updateBall(configuration, receiver.position, remainingFrames)
        : configuration;
    }

    case "PASS_TO_SPACE":
      return updateBall(configuration, event.target, remainingFrames);

    case "RECEIVE": {
      const receiver = configuration.players.find(
        ({ id }) => id === event.playerId,
      );
      return receiver
        ? {
            ...configuration,
            ball: {
              ...configuration.ball,
              position: { ...receiver.position },
              speed: 0,
            },
          }
        : configuration;
    }
  }
}

function advanceConfigurationOneFrame(
  configuration: FieldConfiguration,
  events: AnimationEvent[],
  currentFrame: number,
): FieldConfiguration {
  let nextConfiguration = configuration;
  const playerIds = new Set(configuration.players.map(({ id }) => id));

  for (const playerId of playerIds) {
    const event = latestEventForPlayer(events, playerId);
    if (event) {
      nextConfiguration = applyAnimationEvent(
        nextConfiguration,
        event,
        currentFrame,
      );
    }
  }

  const ballEvent = latestBallEvent(events);
  if (ballEvent && ballEvent.type !== "MOVE_WITH_BALL") {
    nextConfiguration = applyAnimationEvent(
      nextConfiguration,
      ballEvent,
      currentFrame,
    );
  }

  return nextConfiguration;
}

function configurationAtFrame(
  sourceConfiguration: FieldConfiguration,
  events: AnimationEvent[],
  targetFrame: number,
): FieldConfiguration {
  let configuration = cloneFieldConfiguration(sourceConfiguration);

  for (let frame = 0; frame <= targetFrame; frame += 1) {
    const activeEvents = eventsActiveAtFrame(events, frame);
    configuration = advanceConfigurationOneFrame(
      configuration,
      activeEvents,
      frame,
    );
  }

  return configuration;
}

export function advanceAnimationSession(
  session: AnimationSession,
  requestedFrame: number,
): AnimationSession {
  const totalFrames = secondsToAnimationFrame(session.response.duration);
  const currentFrame = Math.min(
    totalFrames,
    Math.max(0, Math.floor(requestedFrame)),
  );
  const isNextFrame = currentFrame === session.currentTime + 1;
  const animatedConfiguration = isNextFrame
    ? advanceConfigurationOneFrame(
        session.animatedConfiguration,
        eventsActiveAtFrame(session.response.events, currentFrame),
        currentFrame,
      )
    : configurationAtFrame(
        session.sourceConfiguration,
        session.response.events,
        currentFrame,
      );

  return {
    ...session,
    animatedConfiguration,
    currentTime: currentFrame,
    status: currentFrame >= totalFrames ? "completed" : session.status,
  };
}
