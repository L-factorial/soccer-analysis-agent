import { forwardRef, useState } from "react";
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  Platform,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { FieldConfiguration, FieldOrientation, fieldToScreenPosition } from "../../models";
import { getBallDisplayOffset, PLAYER_DIAMETER, PLAYER_RING_DIAMETER } from "./marker-layout";
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
          radius: (player.speedCategory === "SUPER_FAST" ? PLAYER_RING_DIAMETER : PLAYER_DIAMETER) / 2,
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
        {dynamicOpenSpaces.length > 0 && (
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

        {showSetupHint && (
          <View pointerEvents="none" style={styles.setupHint}>
            {configuration.players.length === 0 && (
              <View style={styles.emptyMessage}>
                <Text style={styles.fieldLabel}>{configuration.label} FIELD</Text>
                <Text style={styles.fieldHint}>
                  Drag players from the configuration panel
                </Text>
              </View>
            )}
            <Text style={styles.setupHintText}>
              {Platform.OS === "web" ? "Click" : "Tap"} a player to set their name and speed.
            </Text>
            <Text style={styles.setupHintText}>
              Drag players and the ball to reposition them.
            </Text>
          </View>
        )}

        {configuration.goals.map((goal) => (
          <GoalMarker goal={goal} key={goal.id} orientation={orientation} />
        ))}

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
      </FieldSurface>
    );
  },
);

const styles = StyleSheet.create({
  setupHint: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
    gap: 8,
  },
  setupHintText: {
    color: "rgba(255, 255, 255, 0.55)",
    fontSize: 17,
    fontWeight: "600",
    lineHeight: 26,
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
