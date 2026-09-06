import { forwardRef, useState } from "react";
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  Platform,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { FieldConfiguration, FieldOrientation } from "../../models";
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
    },
    ref,
  ) {
    const [fieldSize, setFieldSize] = useState({ height: 0, width: 0 });

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
        {configuration.players.length === 0 && (
          <View style={styles.emptyMessage}>
            <Text style={styles.fieldLabel}>{configuration.label} FIELD</Text>
            <Text style={styles.fieldHint}>
              Drag players from the configuration panel
            </Text>
          </View>
        )}

        {showSetupHint && (
          <View pointerEvents="none" style={styles.setupHint}>
            <Text style={styles.setupHintText}>
              {Platform.OS === "web" ? "Click" : "Tap"} a player to set their name and speed.
            </Text>
            <Text style={styles.setupHintText}>
              Drag players to reposition them.
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
    bottom: "8%",
    left: "8%",
    right: "8%",
    alignItems: "center",
    gap: 4,
  },
  setupHintText: {
    color: "rgba(255, 255, 255, 0.55)",
    fontSize: 13,
    fontWeight: "500",
    lineHeight: 19,
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
