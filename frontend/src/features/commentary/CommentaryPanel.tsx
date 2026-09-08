import { useEffect, useRef, useState } from "react";
import { Platform } from "react-native";

import { AnimationStatus, CommentaryTrack } from "../../models";

type CommentaryPanelProps = {
  commentary?: CommentaryTrack;
  playbackSeconds: number;
  playbackStatus: AnimationStatus;
  onNarrationActiveChange: (active: boolean) => void;
};

function preferredBroadcastVoice(): SpeechSynthesisVoice | undefined {
  const voices = globalThis.speechSynthesis.getVoices();
  const englishVoices = voices.filter((voice) =>
    voice.lang.toLowerCase().startsWith("en"),
  );
  // Voice availability differs by browser and operating system. Prefer names
  // commonly used for enhanced/natural voices, then any local English voice.
  const preference = [
    "natural",
    "premium",
    "enhanced",
    "google uk english male",
    "daniel",
    "jamie",
    "aaron",
    "samantha",
  ];
  return (
    preference
      .map((hint) =>
        englishVoices.find((voice) => voice.name.toLowerCase().includes(hint)),
      )
      .find(Boolean) ??
    englishVoices.find((voice) => voice.localService) ??
    englishVoices[0]
  );
}

/**
 * Removable web prototype for synchronized spoken commentary.
 *
 * The backend returns text cues with authoritative phase timestamps. This
 * component uses the browser speech engine only for playback; it never changes
 * animation time or simulation state.
 */
export function CommentaryPanel({
  commentary,
  playbackSeconds,
  playbackStatus,
  onNarrationActiveChange,
}: CommentaryPanelProps) {
  const narrationStarted = useRef(false);
  const activeUtterance = useRef<SpeechSynthesisUtterance | null>(null);
  const stopNarration = () => {
    const utterance = activeUtterance.current;
    if (utterance) {
      utterance.onend = null;
      utterance.onerror = null;
      activeUtterance.current = null;
    }
    if (speechAvailable) globalThis.speechSynthesis.cancel();
    onNarrationActiveChange(false);
  };
  const [voiceRevision, setVoiceRevision] = useState(0);
  const speechAvailable =
    Platform.OS === "web" &&
    typeof globalThis !== "undefined" &&
    "speechSynthesis" in globalThis;
  useEffect(() => {
    if (!speechAvailable) return;
    const update = () => setVoiceRevision((revision) => revision + 1);
    globalThis.speechSynthesis.addEventListener("voiceschanged", update);
    return () => globalThis.speechSynthesis.removeEventListener("voiceschanged", update);
  }, [speechAvailable]);


  useEffect(() => {
    narrationStarted.current = false;
    stopNarration();
  }, [commentary, speechAvailable]);

  useEffect(() => {
    if (
      playbackStatus !== "playing" ||
      narrationStarted.current ||
      !commentary ||
      !speechAvailable
    ) {
      return;
    }
    const remainingCues = commentary.cues.filter(
      (cue) => cue.endTime > playbackSeconds,
    );
    if (remainingCues.length === 0) {
      return;
    }
    narrationStarted.current = true;
    globalThis.speechSynthesis.cancel();
    // One utterance avoids the audible browser initialization gap between
    // phase-sized speech items. Em dashes preserve a light broadcast pause.
    const continuousScript = remainingCues.map((cue) => cue.text).join(" — ");
    const utterance = new SpeechSynthesisUtterance(continuousScript);
    const voice = preferredBroadcastVoice();
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang;
    } else {
      utterance.lang = "en-GB";
    }
    // Narration stays at the normal speaking rate, independent of video speed.
    utterance.rate = 1;
    utterance.pitch = 0.94;
    utterance.volume = 1;
    activeUtterance.current = utterance;
    const finish = () => {
      if (activeUtterance.current !== utterance) return;
      activeUtterance.current = null;
      onNarrationActiveChange(false);
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    onNarrationActiveChange(true);
    try {
      globalThis.speechSynthesis.speak(utterance);
    } catch {
      finish();
    }
  }, [commentary, playbackSeconds, playbackStatus, speechAvailable, voiceRevision]);

  useEffect(() => {
    // A user Pause or Reset is an explicit stop. Natural completion is not:
    // allow narration to finish while the final animation frame stays visible.
    if (
      (playbackStatus === "paused" || playbackStatus === "idle") &&
      speechAvailable
    ) {
      stopNarration();
      narrationStarted.current = false;
    }
    if (playbackStatus === "completed") {
      // Do not cancel the closing coda, but arm narration for a future replay.
      narrationStarted.current = false;
    }
  }, [playbackSeconds, playbackStatus, speechAvailable]);

  useEffect(
    () => () => {
      stopNarration();
    },
    [speechAvailable],
  );

  // Narration stays mounted without a duplicate visible status control.
  return null;
}
