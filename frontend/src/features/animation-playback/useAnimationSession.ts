import { useCallback, useEffect, useState } from "react";

import {
  AnimationResponse,
  AnimationSession,
  createAnimationSession,
  FieldConfiguration,
} from "../../models";
import {
  advanceAnimationSession,
  ANIMATION_FRAMES_PER_SECOND,
} from "./animation-engine";

export function useAnimationSession(
  sourceConfiguration: FieldConfiguration,
  response: AnimationResponse,
) {
  const [session, setSession] = useState<AnimationSession>(() =>
    createAnimationSession(sourceConfiguration, response),
  );
  const frameIntervalMilliseconds = 1_000 / ANIMATION_FRAMES_PER_SECOND;

  useEffect(() => {
    setSession(createAnimationSession(sourceConfiguration, response));
  }, [response, sourceConfiguration]);

  useEffect(() => {
    if (session.status !== "playing") {
      return;
    }

    const intervalId = setInterval(() => {
      setSession((current) =>
        advanceAnimationSession(current, current.currentTime + 1),
      );
    }, frameIntervalMilliseconds);

    return () => clearInterval(intervalId);
  }, [frameIntervalMilliseconds, session.status]);

  const play = useCallback(() => {
    setSession((current) => {
      return {
        ...(current.status === "completed"
          ? advanceAnimationSession(current, 0)
          : current),
        status: "playing",
      };
    });
  }, []);

  const pause = useCallback(() => {
    setSession((current) => ({ ...current, status: "paused" }));
  }, []);

  const reset = useCallback(() => {
    setSession(createAnimationSession(sourceConfiguration, response));
  }, [response, sourceConfiguration]);

  return { pause, play, reset, session };
}
