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
  playbackSpeed = 1.5,
) {
  const [session, setSession] = useState<AnimationSession>(() =>
    createAnimationSession(sourceConfiguration, response),
  );


  useEffect(() => {
    setSession(createAnimationSession(sourceConfiguration, response));
  }, [response, sourceConfiguration]);

  useEffect(() => {
    if (session.status !== "playing") {
      return;
    }

    let lastTime = performance.now();
    let pendingFrames = 0;
    let frameId: number;
    const tick = (now: number) => {
      pendingFrames += (now - lastTime) * ANIMATION_FRAMES_PER_SECOND * playbackSpeed / 1000;
      lastTime = now;
      const frames = Math.floor(pendingFrames);
      pendingFrames -= frames;
      if (frames > 0) {
        setSession((current) => current.status === "playing"
          ? advanceAnimationSession(current, current.currentTime + frames)
          : current);
      }
      frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [playbackSpeed, session.status, response, sourceConfiguration]);

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
