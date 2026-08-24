import { useMemo, useRef } from "react";
import {
  Animated,
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
  Team,
} from "../../models";

type PlayerMarkerProps = {
  player: Player;
  team: Team;
  orientation: FieldOrientation;
  onMove?: (id: string, pageX: number, pageY: number) => void;
  onSelect?: (id: string) => void;
  selected?: boolean;
};

export function PlayerMarker({
  orientation,
  player,
  team,
  onMove,
  onSelect,
  selected = false,
}: PlayerMarkerProps) {
  const screenPosition = fieldToScreenPosition(player.position, orientation);
  const translation = useRef(new Animated.ValueXY()).current;
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onStartShouldSetPanResponderCapture: () => true,
        onMoveShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderGrant: () => {
          translation.setOffset({ x: 0, y: 0 });
        },
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
          } else {
            onSelect?.(player.id);
          }
          translation.setValue({ x: 0, y: 0 });
        },
        onPanResponderTerminate: () => {
          translation.setValue({ x: 0, y: 0 });
        },
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [onMove, onSelect, player.id, translation],
  );

  const screenOrientation =
    orientation === "horizontal"
      ? -player.orientation
      : -(player.orientation + 90);

  return (
    <Animated.View
      {...panResponder.panHandlers}
      accessibilityLabel={`${team.name} player ${player.number}`}
      accessibilityRole="button"
      hitSlop={8}
      style={[
        styles.markerContainer,
        selected && styles.markerContainerSelected,
        {
          left: `${screenPosition.x * 100}%`,
          top: `${screenPosition.y * 100}%`,
          transform: translation.getTranslateTransform(),
        },
      ]}
    >
      {!!player.profileName?.trim() && (
        <View
          style={[
            styles.playerNameContainer,
            screenPosition.y < 0.06 && styles.playerNameContainerBelow,
          ]}
        >
          <Text numberOfLines={1} style={styles.playerName}>
            {player.profileName.trim()}
          </Text>
        </View>
      )}
      <Animated.View
        style={[styles.arrowLayer, { transform: [{ rotate: `${screenOrientation}deg` }] }]}
      >
        <Animated.View style={styles.arrowShaft} />
        <Animated.View style={styles.arrowHead} />
      </Animated.View>
      {player.speedCategory === "SUPER_FAST" && (
        <Animated.View style={styles.superFastOuterRing} />
      )}
      <Animated.View
        style={[
          styles.marker,
          { backgroundColor: team.color },
          selected && styles.markerSelected,
          player.speedCategory === "FAST" && styles.markerFast,
          player.speedCategory === "SUPER_FAST" && styles.markerSuperFast,
        ]}
      >
        <Text style={styles.label}>{player.number}</Text>
      </Animated.View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  markerContainer: {
    alignItems: "center",
    height: 28,
    justifyContent: "center",
    marginLeft: -14,
    marginTop: -14,
    position: "absolute",
    touchAction: "none",
    userSelect: "none",
    width: 28,
    zIndex: 3,
  },
  marker: {
    alignItems: "center",
    borderColor: "#FFFFFF",
    borderRadius: 10,
    borderWidth: 1,
    cursor: "pointer",
    height: 20,
    justifyContent: "center",
    width: 20,
    zIndex: 2,
  },
  markerContainerSelected: {
    zIndex: 8,
  },
  playerNameContainer: {
    alignItems: "center",
    left: -220,
    pointerEvents: "none",
    position: "absolute",
    right: -220,
    top: -22,
    zIndex: 10,
  },
  playerNameContainerBelow: {
    top: 34,
  },
  playerName: {
    backgroundColor: "rgba(15, 35, 26, 0.82)",
    borderRadius: 4,
    color: "#FFFFFF",
    fontSize: 10,
    fontWeight: "700",
    paddingHorizontal: 4,
    paddingVertical: 2,
    textAlign: "center",
  },
  markerSelected: {
    borderColor: "#14251D",
    borderWidth: 2,
  },
  markerFast: {
    borderColor: "#14251D",
    borderWidth: 3,
  },
  markerSuperFast: {
    borderColor: "#14251D",
    borderWidth: 3,
  },
  superFastOuterRing: {
    borderColor: "#14251D",
    borderRadius: 14,
    borderWidth: 2,
    height: 26,
    left: 1,
    pointerEvents: "none",
    position: "absolute",
    top: 1,
    width: 26,
    zIndex: 1,
  },
  arrowLayer: {
    bottom: 0,
    left: 0,
    position: "absolute",
    pointerEvents: "none",
    right: 0,
    top: 0,
    zIndex: 1,
  },
  arrowShaft: {
    backgroundColor: "#FFFFFF",
    height: 2,
    left: 14,
    position: "absolute",
    top: 13,
    width: 10,
  },
  arrowHead: {
    borderBottomColor: "transparent",
    borderBottomWidth: 4,
    borderLeftColor: "#FFFFFF",
    borderLeftWidth: 6,
    borderTopColor: "transparent",
    borderTopWidth: 4,
    left: 22,
    height: 0,
    position: "absolute",
    top: 10,
    width: 0,
  },
  label: {
    color: "#152219",
    fontSize: 10,
    fontWeight: "800",
  },
});
