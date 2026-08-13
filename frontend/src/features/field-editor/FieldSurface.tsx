import { forwardRef, ReactNode } from "react";
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  Pressable,
  StyleSheet,
  View,
} from "react-native";

import {
  CENTER_CIRCLE_RADIUS_CM,
  FIELD_LENGTH_CM,
  FIELD_WIDTH_CM,
  FieldOrientation,
  GOAL_AREA_DEPTH_CM,
  GOAL_AREA_WIDTH_CM,
  PENALTY_AREA_DEPTH_CM,
  PENALTY_AREA_WIDTH_CM,
  PENALTY_SPOT_DISTANCE_CM,
} from "../../models";

type FieldSurfaceProps = {
  children: ReactNode;
  onLayout?: (event: LayoutChangeEvent) => void;
  onPress?: (event: GestureResponderEvent) => void;
  orientation: FieldOrientation;
};

const lengthPercent = (centimeters: number) =>
  `${(centimeters / FIELD_LENGTH_CM) * 100}%` as const;
const widthPercent = (centimeters: number) =>
  `${(centimeters / FIELD_WIDTH_CM) * 100}%` as const;

export const FieldSurface = forwardRef<View, FieldSurfaceProps>(
  function FieldSurface({ children, onLayout, onPress, orientation }, ref) {
    const horizontal = orientation === "horizontal";
    const penaltyAreaStyle = horizontal
      ? {
          height: widthPercent(PENALTY_AREA_WIDTH_CM),
          top: widthPercent((FIELD_WIDTH_CM - PENALTY_AREA_WIDTH_CM) / 2),
          width: lengthPercent(PENALTY_AREA_DEPTH_CM),
        }
      : {
          height: lengthPercent(PENALTY_AREA_DEPTH_CM),
          left: widthPercent((FIELD_WIDTH_CM - PENALTY_AREA_WIDTH_CM) / 2),
          width: widthPercent(PENALTY_AREA_WIDTH_CM),
        };
    const goalAreaStyle = horizontal
      ? {
          height: widthPercent(GOAL_AREA_WIDTH_CM),
          top: widthPercent((FIELD_WIDTH_CM - GOAL_AREA_WIDTH_CM) / 2),
          width: lengthPercent(GOAL_AREA_DEPTH_CM),
        }
      : {
          height: lengthPercent(GOAL_AREA_DEPTH_CM),
          left: widthPercent((FIELD_WIDTH_CM - GOAL_AREA_WIDTH_CM) / 2),
          width: widthPercent(GOAL_AREA_WIDTH_CM),
        };
    const centerCircleStyle = horizontal
      ? {
          height: widthPercent(CENTER_CIRCLE_RADIUS_CM * 2),
          width: lengthPercent(CENTER_CIRCLE_RADIUS_CM * 2),
        }
      : {
          height: lengthPercent(CENTER_CIRCLE_RADIUS_CM * 2),
          width: widthPercent(CENTER_CIRCLE_RADIUS_CM * 2),
        };
    const penaltySpotOffset = horizontal
      ? { top: "50%" as const }
      : { left: "50%" as const };

    return (
      <Pressable
        accessibilityRole="button"
        onLayout={onLayout}
        onPress={onPress}
        ref={ref}
        style={[
          styles.surface,
          horizontal ? styles.horizontalSurface : styles.verticalSurface,
        ]}
      >
        <View
          style={[
            styles.halfwayLine,
            horizontal
              ? styles.horizontalHalfwayLine
              : styles.verticalHalfwayLine,
          ]}
        />
        <View style={[styles.centerCircle, centerCircleStyle]} />
        <View style={styles.centerSpot} />

        {(["first", "second"] as const).map((end) => (
          <View key={end} style={StyleSheet.absoluteFill} pointerEvents="none">
            <View
              style={[
                styles.markingBox,
                penaltyAreaStyle,
                horizontal
                  ? end === "first"
                    ? styles.leftBox
                    : styles.rightBox
                  : end === "first"
                    ? styles.topBox
                    : styles.bottomBox,
              ]}
            />
            <View
              style={[
                styles.markingBox,
                goalAreaStyle,
                horizontal
                  ? end === "first"
                    ? styles.leftBox
                    : styles.rightBox
                  : end === "first"
                    ? styles.topBox
                    : styles.bottomBox,
              ]}
            />
            <View
              style={[
                styles.penaltySpot,
                penaltySpotOffset,
                horizontal
                  ? end === "first"
                    ? { left: lengthPercent(PENALTY_SPOT_DISTANCE_CM) }
                    : { right: lengthPercent(PENALTY_SPOT_DISTANCE_CM) }
                  : end === "first"
                    ? { top: lengthPercent(PENALTY_SPOT_DISTANCE_CM) }
                    : { bottom: lengthPercent(PENALTY_SPOT_DISTANCE_CM) },
              ]}
            />
          </View>
        ))}
        {children}
      </Pressable>
    );
  },
);

const styles = StyleSheet.create({
  surface: {
    alignItems: "center",
    backgroundColor: "#1E6944",
    borderColor: "rgba(255, 255, 255, 0.72)",
    borderRadius: 9,
    borderWidth: 1,
    cursor: "pointer",
    justifyContent: "center",
    overflow: "hidden",
    position: "relative",
  },
  horizontalSurface: { aspectRatio: 4 / 3, maxHeight: "100%", width: "100%" },
  verticalSurface: { aspectRatio: 3 / 4, height: "100%", maxWidth: "100%" },
  halfwayLine: { backgroundColor: "rgba(255, 255, 255, 0.55)", position: "absolute" },
  horizontalHalfwayLine: { bottom: 0, left: "50%", top: 0, width: 1 },
  verticalHalfwayLine: { height: 1, left: 0, right: 0, top: "50%" },
  centerCircle: {
    borderColor: "rgba(255, 255, 255, 0.58)",
    borderRadius: 999,
    borderWidth: 1,
    position: "absolute",
  },
  centerSpot: {
    backgroundColor: "rgba(255, 255, 255, 0.8)",
    borderRadius: 3,
    height: 5,
    position: "absolute",
    width: 5,
  },
  markingBox: {
    borderColor: "rgba(255, 255, 255, 0.58)",
    borderWidth: 1,
    position: "absolute",
  },
  leftBox: { left: -1 },
  rightBox: { right: -1 },
  topBox: { top: -1 },
  bottomBox: { bottom: -1 },
  penaltySpot: {
    backgroundColor: "rgba(255, 255, 255, 0.82)",
    borderRadius: 3,
    height: 5,
    marginLeft: -2.5,
    marginTop: -2.5,
    position: "absolute",
    width: 5,
  },
});
