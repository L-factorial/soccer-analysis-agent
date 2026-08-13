import { forwardRef, ReactNode } from "react";
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  Pressable,
  StyleSheet,
  View,
} from "react-native";

import { FieldOrientation } from "../../models";

type FieldSurfaceProps = {
  children: ReactNode;
  onLayout?: (event: LayoutChangeEvent) => void;
  onPress?: (event: GestureResponderEvent) => void;
  orientation: FieldOrientation;
};

export const FieldSurface = forwardRef<View, FieldSurfaceProps>(
  function FieldSurface({ children, onLayout, onPress, orientation }, ref) {
    return (
      <Pressable
        accessibilityRole="button"
        onLayout={onLayout}
        onPress={onPress}
        ref={ref}
        style={[
          styles.surface,
          orientation === "horizontal"
            ? styles.horizontalSurface
            : styles.verticalSurface,
        ]}
      >
        <View
          style={[
            styles.halfwayLine,
            orientation === "horizontal"
              ? styles.horizontalHalfwayLine
              : styles.verticalHalfwayLine,
          ]}
        />
        <View style={styles.centerCircle} />
        {children}
      </Pressable>
    );
  },
);

const styles = StyleSheet.create({
  surface: {
    alignItems: "center",
    backgroundColor: "#1E6944",
    borderColor: "rgba(255, 255, 255, 0.65)",
    borderRadius: 9,
    borderWidth: 1,
    cursor: "pointer",
    justifyContent: "center",
    overflow: "hidden",
    position: "relative",
  },
  horizontalSurface: {
    aspectRatio: 4 / 3,
    maxHeight: "100%",
    width: "100%",
  },
  verticalSurface: {
    aspectRatio: 3 / 4,
    height: "100%",
    maxWidth: "100%",
  },
  halfwayLine: {
    backgroundColor: "rgba(255, 255, 255, 0.45)",
    position: "absolute",
  },
  horizontalHalfwayLine: {
    bottom: 0,
    left: "50%",
    top: 0,
    width: 1,
  },
  verticalHalfwayLine: {
    height: 1,
    left: 0,
    right: 0,
    top: "50%",
  },
  centerCircle: {
    borderColor: "rgba(255, 255, 255, 0.45)",
    borderRadius: 55,
    borderWidth: 1,
    height: 110,
    left: "50%",
    marginLeft: -55,
    marginTop: -55,
    position: "absolute",
    top: "50%",
    width: 110,
  },
});
