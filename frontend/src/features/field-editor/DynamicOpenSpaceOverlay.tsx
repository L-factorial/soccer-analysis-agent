import { useEffect, useRef } from "react";
import { Animated, Easing, StyleSheet, View } from "react-native";

import {
  FIELD_LENGTH_CM,
  FIELD_WIDTH_CM,
  fieldToScreenPosition,
  FieldOrientation,
  Position,
} from "../../models";

export type DynamicOpenSpace = {
  id: string;
  center: Position;
  radius: number;
};

type Props = {
  openSpaces: DynamicOpenSpace[];
  orientation: FieldOrientation;
};

const FILL_DOTS = Array.from({ length: 48 }, (_, index) => ({
  x: ((index % 8) + 0.5) * 100 / 8,
  y: (Math.floor(index / 8) + 0.5) * 100 / 6,
}));

/**
 * Highlights computed spaces with luminous dotted rectangular bounds.
 *
 * Backend coordinates and radii are centimeters. Horizontal and vertical
 * scales differ because the pitch is rectangular, and swap when the UI rotates
 * the field. The overlay ignores pointer events so editing gestures continue to
 * reach the field, players, ball, and user-created open-space markers.
 */
export function DynamicOpenSpaceOverlay({
  openSpaces,
  orientation,
}: Props) {
  const opacity = useRef(new Animated.Value(0.25)).current;
  useEffect(() => {
    const animation = Animated.loop(Animated.sequence([
      Animated.timing(opacity, { toValue: 0.95, duration: 1100, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
      Animated.timing(opacity, { toValue: 0.25, duration: 1100, easing: Easing.inOut(Easing.quad), useNativeDriver: false }),
    ]));
    animation.start();
    return () => animation.stop();
  }, [opacity]);

  const horizontalExtent =
    orientation === "horizontal" ? FIELD_LENGTH_CM : FIELD_WIDTH_CM;
  const verticalExtent =
    orientation === "horizontal" ? FIELD_WIDTH_CM : FIELD_LENGTH_CM;

  return (
    <View
      style={[StyleSheet.absoluteFill, styles.overlay, { pointerEvents: "none" }]}
    >
      {openSpaces.map((space) => {
        const center = fieldToScreenPosition(space.center, orientation);
        const widthPercent = (space.radius * 2 * 100) / horizontalExtent;
        const heightPercent = (space.radius * 2 * 100) / verticalExtent;

        return (
          <Animated.View
            key={space.id}
            style={[
              styles.rectangle,
              {
                opacity,
                height: `${heightPercent}%`,
                left: `${center.x * 100 - widthPercent / 2}%`,
                top: `${center.y * 100 - heightPercent / 2}%`,
                width: `${widthPercent}%`,
              },
            ]}
          >
            {FILL_DOTS.map((dot, index) => (
              <View key={index} style={[styles.dot, { left: `${dot.x}%`, top: `${dot.y}%` }]} />
            ))}
          </Animated.View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    zIndex: 3,
  },
  rectangle: {
    backgroundColor: "transparent",
    borderColor: "rgba(255, 235, 178, 0.98)",
    borderRadius: 3,
    borderStyle: "dotted",
    borderWidth: 2,
    boxShadow: "0 0 12px rgba(255, 219, 125, 0.55), inset 0 0 10px rgba(255, 219, 125, 0.16)",
    position: "absolute",
  },
  dot: {
    position: "absolute", width: 2, height: 2, marginLeft: -1, marginTop: -1,
    borderRadius: 1, backgroundColor: "rgba(255, 235, 178, 0.9)",
    boxShadow: "0 0 5px rgba(255, 219, 125, 0.8)",
  },
});
