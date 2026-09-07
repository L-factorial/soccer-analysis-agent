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

function normalizeOrientation(orientation: number): number {
  return ((orientation % 360) + 360) % 360;
}

function smoothStep(progress: number): number {
  return progress * progress * (3 - 2 * progress);
}

function easedFrameStep(
  event: AnimationEvent,
  currentFrame: number,
): number {
  const startFrame = secondsToAnimationFrame(event.startTime);
  const endFrame = secondsToAnimationFrame(
    event.startTime + (event.duration ?? 0),
  );
  const totalFrames = Math.max(1, endFrame - startFrame);
  const previousProgress = Math.min(
    1,
    Math.max(0, (currentFrame - startFrame - 1) / totalFrames),
  );
  const currentProgress = Math.min(
    1,
    Math.max(0, (currentFrame - startFrame) / totalFrames),
  );
  // Keep most of the motion linear so adjacent sequence events flow into one
  // another instead of visibly braking at every phase boundary. The remaining
  // smoothstep contribution softens starts and finishes without masking real
  // tactical gaps encoded in the event timeline.
  const linearWeight = 0.8;
  const eased = (progress: number) =>
    linearWeight * progress + (1 - linearWeight) * smoothStep(progress);
  const previousEased = eased(previousProgress);
  const currentEased = eased(currentProgress);
  return Math.min(
    1,
    Math.max(0, (currentEased - previousEased) / (1 - previousEased)),
  );
}

function updatePlayerOrientation(
  configuration: FieldConfiguration,
  playerId: string,
  targetOrientation: number,
  frameStep: number,
): FieldConfiguration {
  return {
    ...configuration,
    players: configuration.players.map((player) => {
      if (player.id !== playerId) {
        return player;
      }
      const current = normalizeOrientation(player.orientation);
      const target = normalizeOrientation(targetOrientation);
      const clockwiseDifference = (target - current + 360) % 360;
      const difference =
        clockwiseDifference <= 180
          ? clockwiseDifference
          : clockwiseDifference - 360;

      return {
        ...player,
        orientation: normalizeOrientation(
          current + difference * frameStep,
        ),
        velocity: { x: 0, y: 0 },
      };
    }),
  };
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
  frameStep: number,
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
      const distancePerFrame = remainingDistance * frameStep;
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
        event.type === "MOVE_WITH_BALL" ||
        event.type === "TURN"),
  );
}

function latestBallEvent(events: AnimationEvent[]): AnimationEvent | undefined {
  return events.findLast(
    (event) =>
      event.type === "MOVE_WITH_BALL" ||
      event.type === "PASS" ||
      event.type === "PASS_TO_SPACE" ||
      event.type === "SHOT" ||
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
      return event.duration === undefined || event.duration === 0
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
  const playerFrameStep = easedFrameStep(event, currentFrame);

  switch (event.type) {
    case "TURN":
      return updatePlayerOrientation(
        configuration,
        event.playerId,
        event.targetOrientation,
        // Zero-duration turns update facing on their start frame without
        // introducing a stationary animation window. When turn time is enabled
        // again, positive-duration events continue to interpolate normally.
        event.duration === 0 ? 1 : playerFrameStep,
      );

    case "RUN":
    case "MOVE":
      return updatePlayer(
        configuration,
        event.playerId,
        event.target,
        playerFrameStep,
      );

    case "MOVE_WITH_BALL": {
      const movedConfiguration = updatePlayer(
        configuration,
        event.playerId,
        event.target,
        playerFrameStep,
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

    case "SHOT":
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
  let animatedConfiguration = session.animatedConfiguration;
  if (currentFrame > session.currentTime) {
    // Process every simulation step, including instantaneous actions, while
    // rendering only once. Never replay the whole timeline to catch up.
    for (let frame = session.currentTime + 1; frame <= currentFrame; frame += 1) {
      animatedConfiguration = advanceConfigurationOneFrame(
        animatedConfiguration, eventsActiveAtFrame(session.response.events, frame), frame,
      );
    }
  } else {
    animatedConfiguration = configurationAtFrame(
      session.sourceConfiguration, session.response.events, currentFrame,
    );
  }

  return {
    ...session,
    animatedConfiguration,
    currentTime: currentFrame,
    status: currentFrame >= totalFrames ? "completed" : session.status,
  };
}
