import { useEffect, useRef } from "react";
import { Animated, Easing, StyleSheet, View } from "react-native";
import { FieldOrientation, fieldToScreenPosition } from "../../models";
import { PassingTriangle } from "../../models/animation-event";

type Props = {
  triangles: PassingTriangle[];
  orientation: FieldOrientation;
  fieldSize: { width: number; height: number };
};

function Triangle({ triangle, orientation, fieldSize }: Omit<Props, "triangles"> & { triangle: PassingTriangle }) {
  const opacity = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const animation = Animated.sequence([
      Animated.timing(opacity, { toValue: 1, duration: 250, useNativeDriver: false }),
      Animated.timing(opacity, { toValue: 0.35, duration: 450, useNativeDriver: false }),
      Animated.timing(opacity, { toValue: 1, duration: 300, useNativeDriver: false }),
      Animated.timing(opacity, { toValue: 0, duration: 1000, easing: Easing.in(Easing.quad), useNativeDriver: false }),
    ]);
    animation.start();
    return () => animation.stop();
  }, [opacity]);

  if (!triangle.vertices || fieldSize.width <= 0 || fieldSize.height <= 0) return null;
  const vertices = triangle.vertices.map((point) => {
    const screen = fieldToScreenPosition(point, orientation);
    return { x: screen.x * fieldSize.width, y: screen.y * fieldSize.height };
  });
  const dots: { x: number; y: number }[] = [];
  vertices.forEach((start, edge) => {
    const end = vertices[(edge + 1) % 3];
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const length = Math.hypot(dx, dy);
    if (length === 0) return;
    const steps = Math.max(1, Math.ceil(length / 7));
    for (const offset of [-2.5, 2.5]) {
      for (let index = 0; index < steps; index++) {
        dots.push({
          x: start.x + dx * index / steps - dy / length * offset,
          y: start.y + dy * index / steps + dx / length * offset,
        });
      }
    }
  });
  return (
    <Animated.View style={[StyleSheet.absoluteFill, { opacity }]}>
      {dots.map((dot, index) => <View key={index} style={[styles.dot, { left: dot.x - 1.5, top: dot.y - 1.5 }]} />)}
    </Animated.View>
  );
}

export function PassingTriangleOverlay({ triangles, orientation, fieldSize }: Props) {
  if (fieldSize.width <= 0 || fieldSize.height <= 0) return null;
  return (
    <View style={[StyleSheet.absoluteFill, { pointerEvents: "none", zIndex: 4 }]}>
      {triangles.filter((triangle) => triangle.vertices).map((triangle) => (
        <Triangle
          key={[...triangle.playerIds].sort().join("|")}
          triangle={triangle} orientation={orientation} fieldSize={fieldSize}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  dot: {
    position: "absolute", width: 3, height: 3, borderRadius: 2,
    backgroundColor: "#B6FFEC",
    boxShadow: "0 0 5px #78FFD8, 0 0 10px rgba(120, 255, 216, 0.75)",
  },
});
