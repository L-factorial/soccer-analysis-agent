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

export type TurnEvent = TimedAnimationEventBase & {
  type: "TURN";
  startOrientation: number;
  targetOrientation: number;
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

export type ShotEvent = TimedAnimationEventBase & {
  type: "SHOT";
  goalId: string;
  target: EventTarget;
};

export type AnimationEvent =
  | RunEvent
  | MoveEvent
  | MoveWithBallEvent
  | TurnEvent
  | PassEvent
  | PassToSpaceEvent
  | ShotEvent
  | ReceiveEvent;

export type AnimationEventType = AnimationEvent["type"];

export type PlannerDiagnostics = {
    tacticalInstruction?: string | null;
    appliedDirectives?: string[];
    agentMode?: "DETERMINISTIC" | "AGENTIC" | "TOOL_AGENT" | "AGENTIC_FALLBACK";
    agentModel?: string | null;
    agentAttempts?: number;
    tacticalIntent?: Record<string, unknown> | null;
    planEvaluation?: Record<string, unknown> | null;
    agentFallbackReason?: string | null;
    agentToolCalls?: number;
    agentIterations?: number;
    objective: "SCORE_GOAL";
    plannerType: "ACTION" | "TACTICAL_PHASE";
    phaseCount: number | null;
    attackingTeamId: string | null;
    reachedDepth: number;
    evaluatedCandidateCount: number;
    rootCandidateCount: number;
    rootFeasibleCandidateCount: number;
    prunedByBeamCount: number;
    prunedByDurationCount: number;
    prunedByOffsideCount: number;
    prunedByPossessionCount: number;
    prunedByActionPatternCount: number;
    rejectionReasons: Record<string, number>;
    dynamicSpaces: { id: string; center: EventTarget; radius: number }[];
    selectedSequenceScore: number | null;
    selectedSequenceDepth: number | null;
    selectedPhases: SelectedPhaseDiagnostic[];
    explanation: string[];
};

export type PhaseIntentionDiagnostic = {
  side: "ATTACKING" | "DEFENSIVE";
  playerId: string;
  intentionType: string;
  target: EventTarget;
  targetPlayerId: string | null;
};

export type SelectedPhaseDiagnostic = {
  id: string;
  phaseType: string;
  actionType: string;
  actorId: string;
  receiverId: string | null;
  targetZoneId: string | null;
  target: EventTarget;
  startTime: number;
  duration: number;
  endTime: number;
  ballActionStartTime: number;
  offsideLineX: number | null;
  possessionBefore: string;
  possessionAfter: string;
  score: number;
  scoredGoal: boolean;
  intentions: PhaseIntentionDiagnostic[];
};

export type AnimationResponse = {
  duration: number;
  events: AnimationEvent[];
  diagnostics?: PlannerDiagnostics;
  alternativePlans?: AlternativePlan[];
};

export type AlternativePlan = {
  id: string;
  label: string;
  reason: string;
  duration: number;
  events: AnimationEvent[];
  diagnostics?: PlannerDiagnostics;
};
