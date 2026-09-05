import { useMemo, useRef } from "react";
import {
  Animated,
  GestureResponderEvent,
  PanResponder,
  Platform,
  StyleSheet,
  Text,
  View,
  ViewStyle,
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

const domedFinish = Platform.OS === "web" ? ({
  backgroundImage: "radial-gradient(circle at 32% 22%, rgba(255,255,255,0.65), transparent 45%), linear-gradient(155deg, transparent 35%, rgba(0,0,0,0.42) 100%)",
  boxShadow: "inset 0 1px 1px rgba(255,255,255,0.8), inset 0 -3px 2px rgba(0,0,0,0.25), 0 3px 0 #172B22, 2px 6px 5px rgba(0,0,0,0.4)",
} as ViewStyle) : undefined;

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
      <View style={styles.groundShadow} />
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
      {player.speedCategory === "SUPER_FAST" && (
        <Animated.View style={styles.superFastOuterRing} />
      )}
      <Animated.View
        style={[
          styles.marker,
          { backgroundColor: team.color },
          domedFinish,
          selected && styles.markerSelected,
          player.speedCategory === "FAST" && styles.markerFast,
          player.speedCategory === "SUPER_FAST" && styles.markerSuperFast,
        ]}
      >
        <View style={styles.highlight} />
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
    borderColor: "rgba(255,255,255,0.85)",
    borderRadius: 14,
    borderWidth: 1,
    cursor: "pointer",
    height: 26,
    justifyContent: "center",
    width: 26,
    elevation: 5,
    zIndex: 2,
  },
  markerContainerSelected: {
    zIndex: 8,
  },
  groundShadow: {
    position: "absolute",
    pointerEvents: "none",
    backgroundColor: "rgba(6, 23, 13, 0.3)",
    width: 30,
    height: 14,
    borderRadius: 15,
    top: 20,
    left: 3,
    transform: [{ rotate: "-15deg" }],
  },
  highlight: {
    position: "absolute",
    pointerEvents: "none",
    top: 2,
    left: 4,
    width: 12,
    height: 5,
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.24)",
    transform: [{ rotate: "-20deg" }],
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
    borderColor: "#F3FFD1",
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
    borderRadius: 17,
    borderWidth: 2,
    height: 32,
    left: -2,
    pointerEvents: "none",
    position: "absolute",
    top: -2,
    width: 32,
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
    fontSize: 11,
    fontWeight: "900",
    backgroundColor: "rgba(255,255,255,0.78)",
    borderRadius: 8,
    minWidth: 16,
    height: 16,
    lineHeight: 16,
    textAlign: "center",
  },
});
