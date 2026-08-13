import { AnimationResponse } from "./animation-event";
import {
  cloneFieldConfiguration,
  FieldConfiguration,
} from "./field-configuration";

export type AnimationStatus = "idle" | "playing" | "paused" | "completed";

export type AnimationSession = {
  response: AnimationResponse;
  sourceConfiguration: FieldConfiguration;
  animatedConfiguration: FieldConfiguration;
  // Logical animation frame (100 frames represent one response second).
  currentTime: number;
  status: AnimationStatus;
};

export function createAnimationSession(
  sourceConfiguration: FieldConfiguration,
  response: AnimationResponse,
): AnimationSession {
  return {
    response,
    sourceConfiguration: cloneFieldConfiguration(sourceConfiguration),
    animatedConfiguration: cloneFieldConfiguration(sourceConfiguration),
    currentTime: 0,
    status: "idle",
  };
}
