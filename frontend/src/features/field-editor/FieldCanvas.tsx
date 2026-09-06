import { forwardRef, useState } from "react";
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { FieldConfiguration, FieldOrientation, fieldToScreenPosition } from "../../models";
import { getBallDisplayOffset, MOBILE_PLAYER_SCALE, PLAYER_DIAMETER, PLAYER_RING_DIAMETER } from "./marker-layout";
import { BallMarker } from "./BallMarker";
import {
  DynamicOpenSpace,
  DynamicOpenSpaceOverlay,
} from "./DynamicOpenSpaceOverlay";
import { FieldSurface } from "./FieldSurface";
import { GoalMarker } from "./GoalMarker";
import { OpenSpaceMarker } from "./OpenSpaceMarker";
import { OffsideLineOverlay } from "./OffsideLineOverlay";
import { PlayerMarker } from "./PlayerMarker";

function FieldSetupHint({ configuration, onStart }: {
  configuration: FieldConfiguration;
  onStart?: () => void;
}) {
  return (
    <Pressable
      style={styles.setupHint}
      accessibilityRole="button"
      accessibilityLabel="Tap anywhere to start setting up your field"
      onPress={(event) => {
        event.stopPropagation();
        onStart?.();
      }}
    >
      <View style={styles.setupHintCard}>
        <View style={{ gap: 8 }}>
          <Text style={styles.setupHintTitle}>SET UP YOUR FIELD</Text>
          {configuration.players.length === 0 && (
            <Text style={styles.setupHintText}>Drag players from the configuration panel.</Text>
          )}
          <Text style={styles.setupHintText}>
            {Platform.OS === "web" ? "Click or tap" : "Tap"} a player to edit their name, change speed, or give them the ball.
          </Text>
          <Text style={styles.setupHintText}>Drag players and the ball to reposition them.</Text>
          <Text style={styles.setupHintStart}>Tap anywhere to start</Text>
        </View>
      </View>
    </Pressable>
  );
}

type FieldCanvasProps = {
  attackingTeamId?: string | null;
  configuration: FieldConfiguration;
  dynamicOpenSpaces?: DynamicOpenSpace[];
  orientation: FieldOrientation;
  offsideReleaseLineX?: number | null;
  onLayout?: (event: LayoutChangeEvent) => void;
  onFieldPress?: (event: GestureResponderEvent) => void;
  onBallMove?: (pageX: number, pageY: number) => void;
  onPlayerMove?: (id: string, pageX: number, pageY: number) => void;
  onPlayerSelect?: (id: string) => void;
  onOpenSpaceResize?: (id: string, pageX: number, pageY: number) => void;
  onOpenSpaceMove?: (id: string, deltaX: number, deltaY: number) => void;
  onOpenSpaceSelect?: (id: string) => void;
  selectedOpenSpaceId?: string | null;
  selectedPlayerId?: string | null;
  showSetupHint?: boolean;
  onSetupStart?: () => void;
  separateBallDuringSetup?: boolean;
};

export const FieldCanvas = forwardRef<View, FieldCanvasProps>(
  function FieldCanvas(
    {
      configuration,
      dynamicOpenSpaces = [],
      attackingTeamId,
      orientation,
      offsideReleaseLineX,
      onBallMove,
      onFieldPress,
      onLayout,
      onOpenSpaceMove,
      onOpenSpaceResize,
      onOpenSpaceSelect,
      onPlayerMove,
      onPlayerSelect,
      selectedOpenSpaceId,
      selectedPlayerId,
      showSetupHint = false,
      onSetupStart,
      separateBallDuringSetup = false,
    },
    ref,
  ) {
    const [fieldSize, setFieldSize] = useState({ height: 0, width: 0 });
    const ballScreenPosition = fieldToScreenPosition(configuration.ball.position, orientation);
    const ballDisplayOffset = separateBallDuringSetup ? getBallDisplayOffset(
      { x: ballScreenPosition.x * fieldSize.width, y: ballScreenPosition.y * fieldSize.height },
      configuration.players.map((player) => {
        const position = fieldToScreenPosition(player.position, orientation);
        return {
          x: position.x * fieldSize.width,
          y: position.y * fieldSize.height,
          radius: (player.speedCategory === "SUPER_FAST" ? PLAYER_RING_DIAMETER : PLAYER_DIAMETER)
            * (orientation === "vertical" ? MOBILE_PLAYER_SCALE : 1) / 2,
        };
      }),
      fieldSize,
    ) : { x: 0, y: 0 };

    return (
      <FieldSurface
        onLayout={(event) => {
          setFieldSize(event.nativeEvent.layout);
          onLayout?.(event);
        }}
        onPress={onFieldPress}
        orientation={orientation}
        ref={ref}
      >
        {!showSetupHint && dynamicOpenSpaces.length > 0 && (
          <DynamicOpenSpaceOverlay
            openSpaces={dynamicOpenSpaces}
            orientation={orientation}
          />
        )}
        {configuration.players.length === 0 && !showSetupHint && (
          <View style={styles.emptyMessage}>
            <Text style={styles.fieldLabel}>{configuration.label} FIELD</Text>
            <Text style={styles.fieldHint}>
              Drag players from the configuration panel
            </Text>
          </View>
        )}

        {configuration.goals.map((goal) => (
          <GoalMarker goal={goal} key={goal.id} orientation={orientation} />
        ))}

        {!showSetupHint && <>
        {configuration.openSpaces.map((openSpace) => (
          <OpenSpaceMarker
            fieldSize={fieldSize}
            key={openSpace.id}
            onMove={onOpenSpaceMove ?? (() => undefined)}
            onResize={onOpenSpaceResize ?? (() => undefined)}
            onSelect={onOpenSpaceSelect ?? (() => undefined)}
            openSpace={openSpace}
            orientation={orientation}
            selected={selectedOpenSpaceId === openSpace.id}
          />
        ))}

        <OffsideLineOverlay
          attackingTeamId={attackingTeamId}
          configuration={configuration}
          orientation={orientation}
          releaseLineX={offsideReleaseLineX}
        />

        <BallMarker
          ball={configuration.ball}
          displayOffset={ballDisplayOffset}
          onMove={onBallMove}
          orientation={orientation}
        />

        {configuration.players.map((player) => (
          <PlayerMarker
            key={player.id}
            onMove={onPlayerMove}
            onSelect={onPlayerSelect}
            orientation={orientation}
            player={player}
            selected={selectedPlayerId === player.id}
            team={
              configuration.teams.find(({ id }) => id === player.teamId) ??
              configuration.teams[0]
            }
          />
        ))}
        </>}
        {showSetupHint && <FieldSetupHint configuration={configuration} onStart={onSetupStart} />}
      </FieldSurface>
    );
  },
);

const styles = StyleSheet.create({
  setupHint: {
    zIndex: 50,
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
    gap: 8,
  },
  setupHintCard: {
    backgroundColor: "rgba(8, 28, 19, 0.95)",
    borderColor: "rgba(216, 255, 140, 0.65)",
    borderWidth: 1,
    borderRadius: 14,
    padding: 16,
    width: "100%",
    maxWidth: 420,
  },
  setupHintStart: {
    color: "#E5FFAB",
    fontSize: 14,
    fontWeight: "800",
    textAlign: "center",
    marginTop: 10,
  },
  setupHintTitle: {
    color: "#E5FFAB",
    textShadowColor: "#102B1B",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 1.2,
    textAlign: "center",
  },
  setupHintText: {
    color: "#FFFFFF",
    textShadowColor: "#102B1B",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 21,
    textAlign: "center",
    userSelect: "none",
  },
  emptyMessage: {
    alignItems: "center",
    padding: 20,
  },
  fieldLabel: {
    color: "rgba(255, 255, 255, 0.82)",
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 2.2,
  },
  fieldHint: {
    color: "rgba(255, 255, 255, 0.58)",
    fontSize: 12,
    marginTop: 8,
    textAlign: "center",
  },
});
