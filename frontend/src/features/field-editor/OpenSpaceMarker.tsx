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
  FIELD_LENGTH_CM,
  FIELD_WIDTH_CM,
  fieldToScreenPosition,
  FieldOrientation,
  OpenSpace,
} from "../../models";

const DOT_PATTERN = Array.from({ length: 48 }, (_, index) => index);

type OpenSpaceMarkerProps = {
  fieldSize: { height: number; width: number };
  openSpace: OpenSpace;
  orientation: FieldOrientation;
  selected: boolean;
  onMove: (id: string, deltaX: number, deltaY: number) => void;
  onResize: (id: string, pageX: number, pageY: number) => void;
  onSelect: (id: string) => void;
};

export function OpenSpaceMarker({
  fieldSize,
  openSpace,
  orientation,
  selected,
  onMove,
  onResize,
  onSelect,
}: OpenSpaceMarkerProps) {
  const moveTranslation = useRef(new Animated.ValueXY()).current;
  const resizeTranslation = useRef(new Animated.ValueXY()).current;
  const moveResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderMove: Animated.event(
          [null, { dx: moveTranslation.x, dy: moveTranslation.y }],
          { useNativeDriver: false },
        ),
        onPanResponderRelease: (_event, gesture) => {
          if (Math.hypot(gesture.dx, gesture.dy) < 3) {
            onSelect(openSpace.id);
          } else {
            onMove(openSpace.id, gesture.dx, gesture.dy);
          }
          moveTranslation.setValue({ x: 0, y: 0 });
        },
        onPanResponderTerminate: () => {
          moveTranslation.setValue({ x: 0, y: 0 });
        },
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [moveTranslation, onMove, onSelect, openSpace.id],
  );
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderMove: Animated.event(
          [null, { dx: resizeTranslation.x, dy: resizeTranslation.y }],
          { useNativeDriver: false },
        ),
        onPanResponderRelease: (
          event: GestureResponderEvent,
          gesture,
        ) => {
          onResize(
            openSpace.id,
            gesture.moveX || event.nativeEvent.pageX,
            gesture.moveY || event.nativeEvent.pageY,
          );
          resizeTranslation.setValue({ x: 0, y: 0 });
        },
        onPanResponderTerminate: () => {
          resizeTranslation.setValue({ x: 0, y: 0 });
        },
        onPanResponderTerminationRequest: () => false,
      }),
    [onResize, openSpace.id, resizeTranslation],
  );

  const shapeStyle = (() => {
    if (openSpace.type === "circular") {
      const center = fieldToScreenPosition(openSpace.center, orientation);
      const horizontalRadius =
        openSpace.radius /
        (orientation === "horizontal" ? FIELD_LENGTH_CM : FIELD_WIDTH_CM);
      const verticalRadius =
        openSpace.radius /
        (orientation === "horizontal" ? FIELD_WIDTH_CM : FIELD_LENGTH_CM);

      return {
        borderRadius: 999,
        height: verticalRadius * fieldSize.height * 2,
        left: (center.x - horizontalRadius) * fieldSize.width,
        top: (center.y - verticalRadius) * fieldSize.height,
        width: horizontalRadius * fieldSize.width * 2,
      };
    }

    const firstCorner = fieldToScreenPosition(
      openSpace.bottomLeft,
      orientation,
    );
    const secondCorner = fieldToScreenPosition(openSpace.topRight, orientation);
    const left = Math.min(firstCorner.x, secondCorner.x);
    const right = Math.max(firstCorner.x, secondCorner.x);
    const top = Math.min(firstCorner.y, secondCorner.y);
    const bottom = Math.max(firstCorner.y, secondCorner.y);

    return {
      height: (bottom - top) * fieldSize.height,
      left: left * fieldSize.width,
      top: top * fieldSize.height,
      width: (right - left) * fieldSize.width,
    };
  })();

  return (
    <Animated.View
      {...moveResponder.panHandlers}
      accessibilityLabel={`${openSpace.name}, ${openSpace.type} open space`}
      style={[
        styles.shape,
        shapeStyle,
        selected && styles.selectedShape,
        { transform: moveTranslation.getTranslateTransform() },
      ]}
    >
      <View
        style={[
          styles.dotPattern,
          openSpace.type === "circular" && styles.circularDotPattern,
        ]}
      >
        {DOT_PATTERN.map((dot) => (
          <View key={dot} style={styles.dotCell}>
            <View
              style={[
                styles.dot,
                dot % 2 === 0 ? styles.whiteDot : styles.blackDot,
              ]}
            />
          </View>
        ))}
      </View>

      <Text style={styles.nameLabel}>
        {openSpace.name}
      </Text>

      {selected && (
        <Animated.View
          {...panResponder.panHandlers}
          hitSlop={10}
          style={[
            styles.resizeHandle,
            orientation === "horizontal"
              ? styles.horizontalResizeHandle
              : styles.verticalResizeHandle,
            { transform: resizeTranslation.getTranslateTransform() },
          ]}
        />
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  shape: {
    backgroundColor: "rgba(15, 20, 17, 0.035)",
    borderColor: "rgba(255, 255, 255, 0.5)",
    borderStyle: "dotted",
    borderWidth: 2,
    cursor: "pointer",
    position: "absolute",
    touchAction: "none",
    zIndex: 1,
  },
  selectedShape: {
    backgroundColor: "rgba(255, 255, 255, 0.07)",
    borderColor: "rgba(255, 255, 255, 0.9)",
  },
  nameLabel: {
    backgroundColor: "rgba(20, 37, 29, 0.78)",
    borderRadius: 4,
    color: "#FFFFFF",
    fontSize: 9,
    fontWeight: "700",
    left: 5,
    paddingHorizontal: 5,
    paddingVertical: 2,
    position: "absolute",
    pointerEvents: "none",
    top: 5,
    zIndex: 2,
  },
  dotPattern: {
    bottom: 0,
    flexDirection: "row",
    flexWrap: "wrap",
    left: 0,
    overflow: "hidden",
    position: "absolute",
    pointerEvents: "none",
    right: 0,
    top: 0,
  },
  circularDotPattern: {
    borderRadius: 999,
  },
  dotCell: {
    alignItems: "center",
    height: "16.666%",
    justifyContent: "center",
    width: "12.5%",
  },
  dot: {
    borderRadius: 2,
    height: 3,
    opacity: 0.24,
    width: 3,
  },
  whiteDot: {
    backgroundColor: "#FFFFFF",
  },
  blackDot: {
    backgroundColor: "#0C120F",
  },
  resizeHandle: {
    backgroundColor: "#E7FF9B",
    borderColor: "#183E2B",
    borderRadius: 8,
    borderWidth: 2,
    cursor: "pointer",
    height: 16,
    position: "absolute",
    touchAction: "none",
    width: 16,
    zIndex: 5,
  },
  horizontalResizeHandle: {
    right: -8,
    top: -8,
  },
  verticalResizeHandle: {
    left: -8,
    top: -8,
  },
});
