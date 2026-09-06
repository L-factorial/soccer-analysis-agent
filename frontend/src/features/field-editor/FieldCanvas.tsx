import { forwardRef, useEffect, useRef, useState } from "react";
import {
  GestureResponderEvent,
  AccessibilityInfo,
  Animated,
  LayoutChangeEvent,
  Platform,
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

function FieldSetupHint({ configuration, onDismiss }: { configuration: FieldConfiguration; onDismiss?: () => void }) {
  const opacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    let disposed = false;
    let fade: Animated.CompositeAnimation | undefined;
    let reducedMotion = false;
    void AccessibilityInfo.isReduceMotionEnabled().then((reduced) => {
      reducedMotion = reduced;
    }).catch(() => {});
    const timer = setTimeout(() => {
      fade = Animated.timing(opacity, {
        toValue: 0, duration: reducedMotion ? 0 : 1200,
        useNativeDriver: true, isInteraction: false,
      });
      fade.start(({ finished }) => {
        if (finished && !disposed) onDismiss?.();
      });
    }, 3500);
    return () => {
      disposed = true;
      clearTimeout(timer);
      fade?.stop();
    };
  }, [opacity, onDismiss]);

  return (
    <View style={styles.setupHint}>
      <View style={styles.setupHintCard}>
        <Animated.View style={{ opacity, gap: 8 }}>
          <Text style={styles.setupHintTitle}>SET UP YOUR FIELD</Text>
          {configuration.players.length === 0 && (
            <Text style={styles.setupHintText}>Drag players from the configuration panel.</Text>
          )}
          <Text style={styles.setupHintText}>
            {Platform.OS === "web" ? "Click or tap" : "Tap"} a player to edit their name, change speed, or give them the ball.
          </Text>
          <Text style={styles.setupHintText}>Drag players and the ball to reposition them.</Text>
        </Animated.View>
      </View>
    </View>
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
  onSetupHintDismiss?: () => void;
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
      onSetupHintDismiss,
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
        {showSetupHint && <FieldSetupHint configuration={configuration} onDismiss={onSetupHintDismiss} />}
      </FieldSurface>
    );
  },
);

const styles = StyleSheet.create({
  setupHint: {
    pointerEvents: "none",
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
    padding: 16,
    width: "100%",
    maxWidth: 420,
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
