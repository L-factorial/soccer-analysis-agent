import { useMemo, useRef } from "react";
import {
  Animated,
  GestureResponderEvent,
  PanResponder,
  StyleSheet,
  Text,
} from "react-native";

import {
  fieldToScreenPosition,
  FieldOrientation,
  Player,
  Team,
} from "../../models";

type PlayerMarkerProps = {
  player: Player;
  team: Team;
  orientation: FieldOrientation;
  onMove?: (id: string, pageX: number, pageY: number) => void;
};

export function PlayerMarker({
  orientation,
  player,
  team,
  onMove,
}: PlayerMarkerProps) {
  const screenPosition = fieldToScreenPosition(player.position, orientation);
  const translation = useRef(new Animated.ValueXY()).current;
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderMove: Animated.event(
          [null, { dx: translation.x, dy: translation.y }],
          { useNativeDriver: false },
        ),
        onPanResponderRelease: (
          event: GestureResponderEvent,
          gesture,
        ) => {
          if (Math.hypot(gesture.dx, gesture.dy) >= 2) {
            onMove?.(
              player.id,
              gesture.moveX || event.nativeEvent.pageX,
              gesture.moveY || event.nativeEvent.pageY,
            );
          }
          translation.setValue({ x: 0, y: 0 });
        },
        onPanResponderTerminate: () => {
          translation.setValue({ x: 0, y: 0 });
        },
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [onMove, player.id, translation],
  );

  return (
    <Animated.View
      {...panResponder.panHandlers}
      accessibilityLabel={`${team.name} player ${player.number}`}
      hitSlop={8}
      style={[
        styles.marker,
        {
          backgroundColor: team.color,
          left: `${screenPosition.x * 100}%`,
          top: `${screenPosition.y * 100}%`,
          transform: [
            ...translation.getTranslateTransform(),
            { rotate: `${player.orientation}deg` },
          ],
        },
      ]}
    >
      <Text style={styles.label}>{player.number}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  marker: {
    alignItems: "center",
    backgroundColor: "#D8FF3E",
    borderColor: "#FFFFFF",
    borderRadius: 20,
    borderWidth: 2,
    cursor: "pointer",
    height: 40,
    justifyContent: "center",
    marginLeft: -20,
    marginTop: -20,
    position: "absolute",
    touchAction: "none",
    userSelect: "none",
    width: 40,
    zIndex: 3,
  },
  label: {
    color: "#152219",
    fontSize: 12,
    fontWeight: "800",
  },
});
