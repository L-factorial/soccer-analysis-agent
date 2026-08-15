import { StyleSheet, Text, View } from "react-native";

import {
  FIELD_LENGTH_CM,
  FieldConfiguration,
  FieldOrientation,
} from "../../models";

type OffsideLineOverlayProps = {
  attackingTeamId?: string | null;
  configuration: FieldConfiguration;
  orientation: FieldOrientation;
  releaseLineX?: number | null;
};

function offsideLineX(
  configuration: FieldConfiguration,
  attackingTeamId: string,
): number | null {
  const attackingTeam = configuration.teams.find(
    ({ id }) => id === attackingTeamId,
  );
  const defendedGoal = configuration.goals.find(
    ({ id }) => id === attackingTeam?.defendedGoalId,
  );
  const defenders = configuration.players.filter(
    ({ teamId }) => teamId !== attackingTeamId,
  );
  if (!attackingTeam || !defendedGoal || defenders.length < 2) {
    return null;
  }

  const attacksRight = defendedGoal.side === "left";
  const orderedDefenderX = defenders
    .map(({ position }) => position.x)
    .sort((left, right) => (attacksRight ? right - left : left - right));
  const secondLastDefenderX = orderedDefenderX[1];
  const ballX = configuration.ball.position.x;

  return attacksRight
    ? Math.max(secondLastDefenderX, ballX)
    : Math.min(secondLastDefenderX, ballX);
}

export function OffsideLineOverlay({
  attackingTeamId,
  configuration,
  orientation,
  releaseLineX,
}: OffsideLineOverlayProps) {
  const lineX = releaseLineX ?? (
    attackingTeamId ? offsideLineX(configuration, attackingTeamId) : null
  );
  if (lineX === null) {
    return null;
  }

  const horizontal = orientation === "horizontal";
  const positionPercent = horizontal
    ? (lineX / FIELD_LENGTH_CM) * 100
    : (1 - lineX / FIELD_LENGTH_CM) * 100;

  return (
    <View
      pointerEvents="none"
      style={[
        styles.line,
        horizontal
          ? {
              borderLeftWidth: 2,
              borderTopWidth: 0,
              bottom: 0,
              left: `${positionPercent}%`,
              top: 0,
              width: 0,
            }
          : {
              borderLeftWidth: 0,
              borderTopWidth: 2,
              height: 0,
              left: 0,
              right: 0,
              top: `${positionPercent}%`,
            },
      ]}
    >
      <Text
        style={[
          styles.label,
          horizontal ? styles.horizontalLabel : styles.verticalLabel,
        ]}
      >
        OFFSIDE
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  line: {
    borderColor: "rgba(220, 255, 105, 0.46)",
    borderStyle: "dashed",
    position: "absolute",
    zIndex: 6,
  },
  label: {
    backgroundColor: "rgba(20, 59, 41, 0.58)",
    color: "rgba(231, 255, 158, 0.75)",
    fontSize: 7,
    fontWeight: "800",
    letterSpacing: 0.8,
    paddingHorizontal: 4,
    paddingVertical: 2,
    position: "absolute",
  },
  horizontalLabel: {
    left: 4,
    top: 5,
  },
  verticalLabel: {
    left: 5,
    top: 4,
  },
});
