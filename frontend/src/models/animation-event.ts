export type EventTarget = {
  // Standard field coordinates in centimeters, with origin at bottom-left.
  x: number;
  y: number;
};

export type AnimationEventBase = {
  id: string;
  playerId: string;
  startTime: number;
};

export type TimedAnimationEventBase = AnimationEventBase & {
  duration: number;
};

export type RunEvent = TimedAnimationEventBase & {
  type: "RUN";
  target: EventTarget;
};

export type MoveEvent = TimedAnimationEventBase & {
  type: "MOVE";
  target: EventTarget;
};

export type MoveWithBallEvent = TimedAnimationEventBase & {
  type: "MOVE_WITH_BALL";
  target: EventTarget;
};

export type PassEvent = TimedAnimationEventBase & {
  type: "PASS";
  targetPlayerId: string;
};

export type PassToSpaceEvent = TimedAnimationEventBase & {
  type: "PASS_TO_SPACE";
  intendedReceiverId: string;
  spaceId: string;
  target: EventTarget;
};

export type ReceiveEvent = AnimationEventBase & {
  type: "RECEIVE";
  duration?: number;
};

export type AnimationEvent =
  | RunEvent
  | MoveEvent
  | MoveWithBallEvent
  | PassEvent
  | PassToSpaceEvent
  | ReceiveEvent;

export type AnimationEventType = AnimationEvent["type"];

export type AnimationResponse = {
  duration: number;
  events: AnimationEvent[];
};
