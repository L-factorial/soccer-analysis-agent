import { StyleSheet, View } from "react-native";

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

/**
 * Draws the regular planner's computed circular spaces as a passive overlay.
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
          <View
            key={space.id}
            style={[
              styles.circle,
              {
                height: `${heightPercent}%`,
                left: `${center.x * 100 - widthPercent / 2}%`,
                top: `${center.y * 100 - heightPercent / 2}%`,
                width: `${widthPercent}%`,
              },
            ]}
          />
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    zIndex: 3,
  },
  circle: {
    backgroundColor: "rgba(255, 90, 90, 0.08)",
    borderColor: "rgba(255, 175, 175, 0.95)",
    borderRadius: 999,
    borderStyle: "dotted",
    borderWidth: 2,
    position: "absolute",
  },
});
