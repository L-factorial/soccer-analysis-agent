import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Animated, StyleSheet, View } from "react-native";

export function AnalysisOverlay() {
  const opacity = useRef(new Animated.Value(1)).current;
  const [reduceMotion, setReduceMotion] = useState(true);
  useEffect(() => {
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (mounted) setReduceMotion(enabled);
    });
    const subscription = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduceMotion);
    return () => { mounted = false; subscription.remove(); };
  }, []);
  useEffect(() => {
    if (reduceMotion) { opacity.setValue(1); return; }
    const pulse = Animated.loop(Animated.sequence([
      Animated.timing(opacity, { toValue: 0.4, duration: 1100, useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 1, duration: 1100, useNativeDriver: true }),
    ]));
    pulse.start();
    return () => pulse.stop();
  }, [opacity, reduceMotion]);
  return (
    <View style={styles.overlay} accessibilityLiveRegion="polite" accessibilityLabel="Analysis in progress" accessibilityState={{ busy: true }}>
      <Animated.Text style={[styles.title, { opacity }]}>Analyzing the field…</Animated.Text>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(9, 30, 24, 0.62)",
    borderRadius: 14,
    padding: 20,
    zIndex: 100,
  },
  title: { color: "#FFFFFF", fontSize: 32, fontWeight: "800", textAlign: "center" },
});
