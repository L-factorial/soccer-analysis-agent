import { useEffect, useRef } from "react";
import { Animated, Easing, StyleSheet, Text, View } from "react-native";
import { FIELD_LENGTH_CM, FIELD_WIDTH_CM, FieldOrientation, fieldToScreenPosition } from "../../models";
import { LocalMatchup } from "../../models/animation-event";

/** Snapshot geometry stays fixed until the next computed phase boundary. */
export function LocalMatchupOverlay({ matchup, orientation }: {
  matchup: LocalMatchup;
  orientation: FieldOrientation;
}) {
  const opacity = useRef(new Animated.Value(0)).current;
  const shouldPulse = ["2v1", "3v1", "3v2"].includes(matchup.scenario);
  // Following the same players through short phase boundaries should not
  // restart the effect indefinitely. A newly discovered contest pulses again.
  const contestKey = JSON.stringify([
    matchup.teamId, matchup.carrierId, matchup.scenario,
    matchup.attackerIds, matchup.defenderIds, matchup.goalkeeperIds,
  ]);
  useEffect(() => {
    opacity.setValue(shouldPulse ? 0 : 1);
    if (!shouldPulse) return;
    const pulse = () => Animated.sequence([
      Animated.timing(opacity, {
        toValue: 1, duration: 350, easing: Easing.out(Easing.quad), useNativeDriver: false,
      }),
      Animated.timing(opacity, {
        toValue: 0, duration: 650, easing: Easing.inOut(Easing.quad), useNativeDriver: false,
      }),
    ]);
    const animation = Animated.sequence([pulse(), pulse()]);
    animation.start();
    return () => animation.stop();
  }, [contestKey, opacity, shouldPulse]);

  const center = fieldToScreenPosition(matchup.center, orientation);
  const horizontalExtent = orientation === "horizontal" ? FIELD_LENGTH_CM : FIELD_WIDTH_CM;
  const verticalExtent = orientation === "horizontal" ? FIELD_WIDTH_CM : FIELD_LENGTH_CM;
  const width = matchup.radius * 200 / horizontalExtent;
  const height = matchup.radius * 200 / verticalExtent;
  const color = matchup.numericalValue > 0 ? "#76E8B0" : matchup.numericalValue < 0 ? "#FFB570" : "#A8CEFF";
  return (
    <View style={[StyleSheet.absoluteFill, { pointerEvents: "none", zIndex: 3 }]}>
      <Animated.View
        accessibilityLabel={`Local attacking matchup ${matchup.scenario}, radius ${matchup.radius / 100} metres`}
        style={[styles.circle, {
          opacity,
          boxShadow: shouldPulse ? `0 0 20px ${color}, inset 0 0 14px ${color}66` : undefined,
          backgroundColor: shouldPulse ? `${color}18` : "transparent",
          borderColor: color,
          left: `${center.x * 100 - width / 2}%`,
          top: `${center.y * 100 - height / 2}%`,
          width: `${width}%`, height: `${height}%`,
        }]}
      >
        <Text style={[styles.label, { color }]}>{matchup.scenario}{matchup.goalkeeperIds.length > 0 ? " + GK" : ""}</Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  circle: { position: "absolute", borderRadius: 999, borderStyle: "dotted", borderWidth: 2, alignItems: "center" },
  label: { position: "absolute", top: -12, backgroundColor: "#142D29", paddingHorizontal: 6, borderRadius: 6, fontSize: 11, fontWeight: "700" },
});
