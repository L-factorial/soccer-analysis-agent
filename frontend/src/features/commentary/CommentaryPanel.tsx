import { useEffect, useRef, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { AnimationStatus, CommentaryTrack } from "../../models";

type CommentaryPanelProps = {
  commentary?: CommentaryTrack;
  loading?: boolean;
  playbackSeconds: number;
  playbackStatus: AnimationStatus;
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
  loading = false,
  playbackSeconds,
  playbackStatus,
}: CommentaryPanelProps) {
  const narrationStarted = useRef(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const speechAvailable =
    Platform.OS === "web" &&
    typeof globalThis !== "undefined" &&
    "speechSynthesis" in globalThis;
  const activeCue = commentary?.cues.find(
    (cue) => playbackSeconds >= cue.startTime && playbackSeconds < cue.endTime,
  );

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
    // Classic radio delivery is brisk but intelligible, with a grounded vocal
    // register and enough pace to carry continuous descriptive play-by-play.
    utterance.rate = 1.03;
    utterance.pitch = 0.94;
    utterance.volume = 1;
    globalThis.speechSynthesis.speak(utterance);
  }, [commentary, playbackSeconds, playbackStatus, speechAvailable]);

  useEffect(() => {
    // A user Pause or Reset is an explicit stop. Natural completion is not:
    // allow the last utterance a brief grace period beyond the animation end.
    if (
      (playbackStatus === "paused" || playbackStatus === "idle") &&
      speechAvailable
    ) {
      globalThis.speechSynthesis.cancel();
      narrationStarted.current = false;
    }
    if (playbackStatus === "completed") {
      // Do not cancel the closing coda, but arm narration for a future replay.
      narrationStarted.current = false;
    }
  }, [playbackSeconds, playbackStatus, speechAvailable]);

  useEffect(
    () => () => {
      if (speechAvailable) {
        globalThis.speechSynthesis.cancel();
      }
    },
    [speechAvailable],
  );

  if (!commentary && !loading) {
    return null;
  }

  return (
    <View style={styles.anchor}>
      <Pressable
        accessibilityLabel="Commentary status"
        onHoverIn={() => setShowTooltip(true)}
        onHoverOut={() => setShowTooltip(false)}
        onPress={() => setShowTooltip((visible) => !visible)}
        style={[styles.badge, commentary && styles.badgeReady]}
      >
        <Text style={[styles.badgeText, commentary && styles.badgeTextReady]}>
          {loading ? "Commentary …" : "Commentary ✓"}
        </Text>
      </Pressable>
      {showTooltip && commentary && (
        <View style={[styles.tooltip, { pointerEvents: "none" }]}>
          <Text style={styles.eyebrow}>AI MATCH COMMENTARY · READY</Text>
          <Text style={styles.title}>{commentary.title}</Text>
          <Text style={styles.summary}>{commentary.summary}</Text>
          {activeCue && <Text style={styles.activeCue}>{activeCue.text}</Text>}
          {!speechAvailable && (
            <Text style={styles.note}>Spoken commentary is currently available on web.</Text>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  anchor: { position: "relative", zIndex: 40 },
  badge: {
    borderColor: "#CBD5C8",
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  badgeReady: { backgroundColor: "#EAF5CB", borderColor: "#86A91F" },
  badgeText: { color: "#68716A", fontSize: 10, fontWeight: "800" },
  badgeTextReady: { color: "#36500D" },
  tooltip: {
    backgroundColor: "#132A20",
    borderRadius: 10,
    gap: 6,
    padding: 12,
    position: "absolute",
    right: 0,
    top: 38,
    width: 340,
    zIndex: 100,
  },
  eyebrow: {
    color: "#A9D22D",
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1.2,
  },
  title: { color: "#FFFFFF", fontSize: 15, fontWeight: "800", marginTop: 2 },
  summary: { color: "#C7D3CC", fontSize: 11, lineHeight: 16 },
  activeCue: { color: "#FFFFFF", fontSize: 14, fontWeight: "600", lineHeight: 20 },
  note: { color: "#94A39B", fontSize: 10 },
});
