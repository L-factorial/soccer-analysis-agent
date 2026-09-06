import { colors } from "../../theme/colors";
import { useMemo, useRef, useState } from "react";
import { PanResponder, StyleSheet, Text, View } from "react-native";

type TimelineRangeSliderProps = {
  end: number;
  maximum: number;
  onChange: (start: number, end: number) => void;
  start: number;
};

const STEP_SECONDS = 1;
const THUMB_SIZE = 16;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function roundToStep(value: number): number {
  return Math.round(value / STEP_SECONDS) * STEP_SECONDS;
}

export function TimelineRangeSlider({
  end,
  maximum,
  onChange,
  start,
}: TimelineRangeSliderProps) {
  const [trackWidth, setTrackWidth] = useState(0);
  const trackWidthRef = useRef(0);
  const dragStart = useRef({ start, end });
  const currentValues = useRef({ start, end });
  const maximumRef = useRef(maximum);
  const onChangeRef = useRef(onChange);
  currentValues.current = { start, end };
  maximumRef.current = maximum;
  onChangeRef.current = onChange;

  function secondsFromPixels(pixels: number): number {
    const usableWidth = trackWidthRef.current - THUMB_SIZE;
    return usableWidth > 0
      ? (pixels / usableWidth) * maximumRef.current
      : 0;
  }

  const startResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderGrant: () => {
          dragStart.current = currentValues.current;
        },
        onPanResponderMove: (_event, gesture) => {
          const nextStart = roundToStep(
            clamp(
              dragStart.current.start + secondsFromPixels(gesture.dx),
              0,
              Math.max(0, currentValues.current.end - STEP_SECONDS),
            ),
          );
          onChangeRef.current(nextStart, currentValues.current.end);
        },
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [],
  );
  const endResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderGrant: () => {
          dragStart.current = currentValues.current;
        },
        onPanResponderMove: (_event, gesture) => {
          const nextEnd = roundToStep(
            clamp(
              dragStart.current.end + secondsFromPixels(gesture.dx),
              currentValues.current.start + STEP_SECONDS,
              maximum,
            ),
          );
          onChangeRef.current(currentValues.current.start, nextEnd);
        },
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [],
  );

  const safeMaximum = Math.max(STEP_SECONDS, maximum);
  const startPercent = (clamp(start, 0, safeMaximum) / safeMaximum) * 100;
  const endPercent = (clamp(end, 0, safeMaximum) / safeMaximum) * 100;
  const usableWidth = Math.max(0, trackWidth - THUMB_SIZE);
  const startPosition = THUMB_SIZE / 2 + (startPercent / 100) * usableWidth;
  const endPosition = THUMB_SIZE / 2 + (endPercent / 100) * usableWidth;
  const ticks = Array.from(
    { length: Math.floor(safeMaximum) + 1 },
    (_, index) => index,
  );

  return (
    <View style={styles.container}>
      <View style={styles.labels}>
        <Text style={styles.value}>{Math.round(start)}s</Text>
        <Text style={styles.caption}>Drag start and end</Text>
        <Text style={styles.value}>{Math.round(end)}s</Text>
      </View>
      <View
        onLayout={(event) => {
          const width = event.nativeEvent.layout.width;
          trackWidthRef.current = width;
          setTrackWidth(width);
        }}
        style={styles.touchArea}
      >
        <View style={styles.track} />
        <View
          style={[
            styles.selectedTrack,
            { left: startPosition, width: Math.max(0, endPosition - startPosition) },
          ]}
        />
        <View
          {...startResponder.panHandlers}
          accessibilityLabel="Event start time"
          accessibilityRole="adjustable"
          hitSlop={8}
          style={[styles.thumb, styles.startThumb, { left: startPosition }]}
        />
        <View
          {...endResponder.panHandlers}
          accessibilityLabel="Event end time"
          accessibilityRole="adjustable"
          hitSlop={8}
          style={[styles.thumb, styles.endThumb, { left: endPosition }]}
        />
      </View>
      <View style={styles.tickRow}>
        {ticks.map((tick) => (
          <View
            key={tick}
            style={[
              styles.tick,
              { left: `${(tick / safeMaximum) * 100}%` },
            ]}
          />
        ))}
      </View>
      <View style={styles.scale}>
        <Text style={styles.scaleText}>0s</Text>
        <Text style={styles.scaleText}>{maximum}s</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 2, marginTop: 7 },
  labels: { flexDirection: "row", justifyContent: "space-between" },
  value: { color: colors.primary, fontSize: 9, fontWeight: "800" },
  caption: { color: colors.muted, fontSize: 8 },
  touchArea: { height: 28, justifyContent: "center", marginHorizontal: 7 },
  track: {
    backgroundColor: colors.border,
    borderRadius: 3,
    height: 5,
    left: THUMB_SIZE / 2,
    position: "absolute",
    right: THUMB_SIZE / 2,
  },
  selectedTrack: {
    backgroundColor: colors.accent,
    borderRadius: 3,
    height: 5,
    position: "absolute",
  },
  thumb: {
    backgroundColor: colors.primary,
    borderColor: "#FFFFFF",
    borderRadius: 8,
    borderWidth: 2,
    height: THUMB_SIZE,
    marginLeft: -THUMB_SIZE / 2,
    position: "absolute",
    touchAction: "none",
    userSelect: "none",
    width: THUMB_SIZE,
  },
  startThumb: { top: 2, zIndex: 3 },
  endThumb: { bottom: 2, zIndex: 2 },
  scale: { flexDirection: "row", justifyContent: "space-between" },
  scaleText: { color: colors.muted, fontSize: 8 },
  tickRow: { height: 3, marginHorizontal: 7, position: "relative" },
  tick: {
    backgroundColor: colors.border,
    height: 3,
    position: "absolute",
    width: 1,
  },
});
