import { forwardRef, ReactNode } from "react";
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  Platform,
  StyleSheet,
  View,
  ViewStyle,
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
  fillViewport?: boolean;
};

const lengthPercent = (centimeters: number) =>
  `${(centimeters / FIELD_LENGTH_CM) * 100}%` as const;
const widthPercent = (centimeters: number) =>
  `${(centimeters / FIELD_WIDTH_CM) * 100}%` as const;

// CSS grass grain is decorative; the native surface retains the mowing bands.
const grassTexture = Platform.OS === "web" ? ({
  backgroundImage: "radial-gradient(ellipse at 45% 35%, rgba(177,211,103,0.16), transparent 65%), repeating-linear-gradient(83deg, transparent 0px, rgba(8,43,20,0.13) 1px, transparent 2px, transparent 5px), repeating-linear-gradient(7deg, transparent 0px, rgba(204,229,137,0.08) 1px, transparent 2px, transparent 4px)",
  boxShadow: "inset 0 0 65px rgba(4,25,14,0.35)",
} as ViewStyle) : undefined;

export const FieldSurface = forwardRef<View, FieldSurfaceProps>(
  function FieldSurface({ children, onLayout, onPress, orientation, fillViewport = false }, ref) {
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
      <View
        onLayout={onLayout}
        onResponderRelease={onPress}
        onStartShouldSetResponder={() => Boolean(onPress)}
        ref={ref}
        style={[
          styles.surface,
          fillViewport ? styles.fullSurface : horizontal ? styles.horizontalSurface : styles.verticalSurface,
        ]}
      >
        <View style={[StyleSheet.absoluteFill, styles.nonInteractive]}>
          {Array.from({ length: 12 }, (_, index) => (
            <View
              key={index}
              style={[
                styles.mowingBand,
                { backgroundColor: index % 2 ? "#367C40" : "#2E7038" },
                horizontal
                  ? { left: `${index * 100 / 12}%`, width: `${100 / 12}%`, top: 0, bottom: 0 }
                  : { top: `${index * 100 / 12}%`, height: `${100 / 12}%`, left: 0, right: 0 },
              ]}
            />
          ))}
          <View style={[StyleSheet.absoluteFill, grassTexture]} />
        </View>
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
          <View
            key={end}
            style={[StyleSheet.absoluteFill, styles.nonInteractive]}
          >
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
      </View>
    );
  },
);

const styles = StyleSheet.create({
  nonInteractive: {
    pointerEvents: "none",
  },
  surface: {
    alignItems: "center",
    backgroundColor: "#2E7038",
    borderColor: "rgba(248, 250, 227, 0.85)",
    borderRadius: 3,
    borderWidth: 2,
    cursor: "pointer",
    justifyContent: "center",
    overflow: "hidden",
    position: "relative",
  },
  horizontalSurface: { aspectRatio: 4 / 3, maxHeight: "100%", width: "100%" },
  fullSurface: { width: "100%", height: "100%", borderRadius: 0 },
  verticalSurface: { aspectRatio: 3 / 4, height: "100%", maxWidth: "100%" },
  mowingBand: { position: "absolute" },
  halfwayLine: { pointerEvents: "none", backgroundColor: "rgba(248, 250, 227, 0.8)", position: "absolute" },
  horizontalHalfwayLine: { bottom: 0, left: "50%", top: 0, width: 1 },
  verticalHalfwayLine: { height: 1, left: 0, right: 0, top: "50%" },
  centerCircle: {
    pointerEvents: "none",
    borderColor: "rgba(248, 250, 227, 0.8)",
    borderRadius: 999,
    borderWidth: 2,
    position: "absolute",
  },
  centerSpot: {
    pointerEvents: "none",
    backgroundColor: "rgba(255, 255, 255, 0.8)",
    borderRadius: 3,
    height: 5,
    position: "absolute",
    width: 5,
  },
  markingBox: {
    borderColor: "rgba(248, 250, 227, 0.8)",
    borderWidth: 2,
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
