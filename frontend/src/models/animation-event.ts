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

export type ActionPace = "SLOW" | "REGULAR" | "SPRINT";

export type PlayerMovementTiming = {
  pace?: ActionPace;
  speedCmPerSecond?: number;
};

export type PassTiming = {
  passCategory?: "SHORT" | "MODERATE" | "LONG";
  ballSpeedCmPerSecond?: number;
  receiveTime?: number;
};

export type RunEvent = TimedAnimationEventBase & PlayerMovementTiming & {
  type: "RUN";
  target: EventTarget;
};

export type MoveEvent = TimedAnimationEventBase & PlayerMovementTiming & {
  type: "MOVE";
  target: EventTarget;
};

export type MoveWithBallEvent = TimedAnimationEventBase & PlayerMovementTiming & {
  type: "MOVE_WITH_BALL";
  target: EventTarget;
};

export type TurnEvent = TimedAnimationEventBase & {
  type: "TURN";
  startOrientation: number;
  targetOrientation: number;
};

export type PassEvent = TimedAnimationEventBase & PassTiming & {
  type: "PASS";
  targetPlayerId: string;
};

export type PassToSpaceEvent = TimedAnimationEventBase & PassTiming & {
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
  fieldHash?: string | null;
  analysisId?: string | null;
  duration: number;
  events: AnimationEvent[];
  diagnostics?: PlannerDiagnostics;
  alternativePlans?: AlternativePlan[];
  phaseSnapshots?: PhaseSnapshot[];
  commentary?: CommentaryTrack;
  commentaryByLanguage?: Partial<Record<CommentaryLanguage, CommentaryTrack>>;
};

export type CommentaryCue = {
  id: string;
  phaseId: string;
  startTime: number;
  endTime: number;
  text: string;
};

export type CommentaryLanguage = "en" | "ne";

export type CommentaryTrack = {
  language?: CommentaryLanguage;
  script?: "latin" | "devanagari";
  title: string;
  summary: string;
  cues: CommentaryCue[];
};

export type PassingTriangle = {
  playerIds: [string, string, string];
  vertices?: [EventTarget, EventTarget, EventTarget];
  quality: number;
};

export type LocalMatchup = {
  teamId: string;
  carrierId: string;
  center: EventTarget;
  radius: number;
  scenario: string;
  attackerIds: string[];
  defenderIds: string[];
  goalkeeperIds: string[];
  usableSupportIds: string[];
  attackingValue: number;
  numericalValue: number;
  triangles?: PassingTriangle[];
  triangleValue?: number;
  value: number;
};

export type PhaseSnapshot = {
  phaseId: string;
  phaseIndex: number;
  atTime: number;
  openSpaces: { id: string; center: EventTarget; radius: number }[];
  localMatchup?: LocalMatchup | null;
  localMatchupScore?: number;
  passingTriangleScore?: number;
};

export type AlternativePlan = {
  id: string;
  label: string;
  reason: string;
  duration: number;
  events: AnimationEvent[];
  diagnostics?: PlannerDiagnostics;
  phaseSnapshots?: PhaseSnapshot[];
  commentary?: CommentaryTrack;
  commentaryByLanguage?: Partial<Record<CommentaryLanguage, CommentaryTrack>>;
};
