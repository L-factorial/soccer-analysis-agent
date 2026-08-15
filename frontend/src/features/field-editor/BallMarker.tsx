import { useMemo, useRef } from "react";
import {
  Animated,
  GestureResponderEvent,
  PanResponder,
  StyleSheet,
  Text,
} from "react-native";

import { Ball, fieldToScreenPosition, FieldOrientation } from "../../models";

type BallMarkerProps = {
  ball: Ball;
  orientation: FieldOrientation;
  onMove?: (pageX: number, pageY: number) => void;
};

export function BallMarker({ ball, orientation, onMove }: BallMarkerProps) {
  const screenPosition = fieldToScreenPosition(ball.position, orientation);
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
    [onMove, translation],
  );

  return (
    <Animated.View
      {...panResponder.panHandlers}
      accessibilityLabel="Ball"
      hitSlop={10}
      style={[
        styles.marker,
        {
          left: `${screenPosition.x * 100}%`,
          top: `${screenPosition.y * 100}%`,
          transform: [
            ...translation.getTranslateTransform(),
            { rotate: `${ball.direction}deg` },
          ],
        },
      ]}
    >
      <Text style={styles.ballGraphic}>⚽</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  marker: {
    alignItems: "center",
    borderRadius: 7,
    cursor: "pointer",
    height: 14,
    justifyContent: "center",
    marginLeft: -7,
    marginTop: -7,
    position: "absolute",
    touchAction: "none",
    userSelect: "none",
    width: 14,
    zIndex: 4,
  },
  ballGraphic: {
    fontSize: 12,
    lineHeight: 14,
    textAlign: "center",
  },
});
