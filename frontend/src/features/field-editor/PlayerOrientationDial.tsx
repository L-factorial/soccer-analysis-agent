import { useCallback, useMemo } from "react";
import {
  GestureResponderEvent,
  PanResponder,
  StyleSheet,
  Text,
  View,
} from "react-native";

import {
  fieldToScreenPosition,
  FieldOrientation,
  Player,
} from "../../models";

const DIAL_SIZE = 90;
const DIAL_RADIUS = DIAL_SIZE / 2;

type PlayerOrientationDialProps = {
  orientation: FieldOrientation;
  player: Player;
  onChange: (id: string, orientation: number) => void;
};

function normalizeOrientation(value: number): number {
  return ((value % 360) + 360) % 360;
}

export function PlayerOrientationDial({
  orientation,
  player,
  onChange,
}: PlayerOrientationDialProps) {
  const screenPosition = fieldToScreenPosition(player.position, orientation);
  const updateOrientation = useCallback(
    (event: GestureResponderEvent) => {
      const deltaX = event.nativeEvent.locationX - DIAL_RADIUS;
      const deltaY = event.nativeEvent.locationY - DIAL_RADIUS;
      if (Math.hypot(deltaX, deltaY) < 12) {
        return;
      }
      const screenDegrees = (Math.atan2(deltaY, deltaX) * 180) / Math.PI;
      const fieldDegrees =
        orientation === "horizontal"
          ? -screenDegrees
          : -screenDegrees - 90;
      onChange(player.id, normalizeOrientation(fieldDegrees));
    },
    [onChange, orientation, player.id],
  );
  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: updateOrientation,
        onPanResponderMove: updateOrientation,
        onShouldBlockNativeResponder: () => true,
      }),
    [updateOrientation],
  );
  const screenOrientation =
    orientation === "horizontal"
      ? -player.orientation
      : -(player.orientation + 90);

  return (
    <View
      {...responder.panHandlers}
      accessibilityLabel={`Player ${player.number} orientation ${Math.round(player.orientation)} degrees`}
      accessibilityRole="adjustable"
      style={[
        styles.dial,
        {
          left: `${screenPosition.x * 100}%`,
          top: `${screenPosition.y * 100}%`,
        },
      ]}
    >
      <View style={styles.ring} />
      <View
        style={[
          styles.needleLayer,
          { transform: [{ rotate: `${screenOrientation}deg` }] },
        ]}
      >
        <View style={styles.needle} />
        <View style={styles.needleHead} />
      </View>
      <Text style={styles.value}>
        {Math.round(normalizeOrientation(player.orientation))}°
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  dial: {
    height: DIAL_SIZE,
    marginLeft: -DIAL_RADIUS,
    marginTop: -DIAL_RADIUS,
    position: "absolute",
    touchAction: "none",
    width: DIAL_SIZE,
    zIndex: 6,
  },
  ring: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    borderColor: "rgba(255, 255, 255, 0.9)",
    borderRadius: DIAL_RADIUS,
    borderWidth: 1,
    bottom: 0,
    left: 0,
    position: "absolute",
    right: 0,
    top: 0,
  },
  needleLayer: {
    bottom: 0,
    left: 0,
    position: "absolute",
    pointerEvents: "none",
    right: 0,
    top: 0,
  },
  needle: {
    backgroundColor: "#FFFFFF",
    height: 2,
    left: DIAL_RADIUS,
    position: "absolute",
    top: DIAL_RADIUS - 1,
    width: 32,
  },
  needleHead: {
    borderBottomColor: "transparent",
    borderBottomWidth: 5,
    borderLeftColor: "#D8FF3E",
    borderLeftWidth: 8,
    borderTopColor: "transparent",
    borderTopWidth: 5,
    height: 0,
    left: DIAL_RADIUS + 29,
    position: "absolute",
    top: DIAL_RADIUS - 5,
    width: 0,
  },
  value: {
    backgroundColor: "rgba(20, 37, 29, 0.9)",
    borderRadius: 8,
    color: "#FFFFFF",
    fontSize: 9,
    fontWeight: "800",
    left: 27,
    paddingHorizontal: 5,
    paddingVertical: 2,
    position: "absolute",
    pointerEvents: "none",
    textAlign: "center",
    top: -20,
  },
});
