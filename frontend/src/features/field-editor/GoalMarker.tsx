import { StyleSheet, Text, View } from "react-native";

import { fieldToScreenPosition, FieldOrientation, Goal } from "../../models";

type GoalMarkerProps = {
  goal: Goal;
  orientation: FieldOrientation;
};

const NET_LINES = [1, 2, 3];

export function GoalMarker({ goal, orientation }: GoalMarkerProps) {
  const screenCorners = goal.coordinates.map((coordinate) =>
    fieldToScreenPosition(coordinate, orientation),
  );
  const xValues = screenCorners.map(({ x }) => x);
  const yValues = screenCorners.map(({ y }) => y);
  const left = Math.min(...xValues);
  const right = Math.max(...xValues);
  const top = Math.min(...yValues);
  const bottom = Math.max(...yValues);
  const isHorizontal = orientation === "horizontal";
  const mouthAtEnd = isHorizontal
    ? goal.side === "left"
    : goal.side === "right";

  return (
    <View
      accessibilityLabel={`${goal.name}, ${goal.side} goal`}
      style={[
        styles.goal,
        {
          height: `${(bottom - top) * 100}%`,
          left: `${left * 100}%`,
          top: `${top * 100}%`,
          width: `${(right - left) * 100}%`,
        },
      ]}
    >
      <View style={styles.netFill} />
      {NET_LINES.map((line) => (
        <View
          key={`across-${line}`}
          style={[
            styles.netLine,
            isHorizontal
              ? { bottom: 0, left: 0, top: 0, width: 1, marginLeft: `${line * 25}%` }
              : { height: 1, left: 0, right: 0, top: `${line * 25}%` },
          ]}
        />
      ))}
      {NET_LINES.map((line) => (
        <View
          key={`depth-${line}`}
          style={[
            styles.netLine,
            isHorizontal
              ? { height: 1, left: 0, right: 0, top: `${line * 25}%` }
              : { bottom: 0, left: `${line * 25}%`, top: 0, width: 1 },
          ]}
        />
      ))}

      <View
        style={[
          styles.mouth,
          isHorizontal
            ? [styles.verticalMouth, mouthAtEnd ? styles.mouthRight : styles.mouthLeft]
            : [styles.horizontalMouth, mouthAtEnd ? styles.mouthBottom : styles.mouthTop],
        ]}
      >
        <View style={[styles.post, isHorizontal ? styles.postTop : styles.postLeft]} />
        <View style={[styles.post, isHorizontal ? styles.postBottom : styles.postRight]} />
      </View>

      <Text
        style={[
          styles.label,
          !isHorizontal && styles.verticalLabel,
        ]}
      >
        {goal.name}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  goal: {
    alignItems: "center",
    borderColor: "rgba(255, 255, 255, 0.76)",
    borderWidth: 1,
    justifyContent: "center",
    overflow: "visible",
    position: "absolute",
    pointerEvents: "none",
    zIndex: 1,
  },
  netFill: {
    backgroundColor: "rgba(238, 247, 241, 0.1)",
    bottom: 0,
    left: 0,
    position: "absolute",
    right: 0,
    top: 0,
  },
  netLine: {
    backgroundColor: "rgba(255, 255, 255, 0.22)",
    position: "absolute",
  },
  mouth: {
    backgroundColor: "#F8FBF9",
    position: "absolute",
  },
  verticalMouth: { bottom: -2, top: -2, width: 3 },
  horizontalMouth: { height: 3, left: -2, right: -2 },
  mouthLeft: { left: -2 },
  mouthRight: { right: -2 },
  mouthTop: { top: -2 },
  mouthBottom: { bottom: -2 },
  post: {
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5CF",
    borderRadius: 5,
    borderWidth: 1,
    height: 7,
    position: "absolute",
    width: 7,
  },
  postTop: { left: -2, top: -3 },
  postBottom: { bottom: -3, left: -2 },
  postLeft: { left: -3, top: -2 },
  postRight: { right: -3, top: -2 },
  label: {
    backgroundColor: "rgba(20, 37, 29, 0.7)",
    borderRadius: 3,
    color: "#FFFFFF",
    fontSize: 7,
    fontWeight: "800",
    paddingHorizontal: 3,
    paddingVertical: 1,
    position: "absolute",
  },
  verticalLabel: {
    transform: [{ rotate: "-90deg" }],
  },
});
