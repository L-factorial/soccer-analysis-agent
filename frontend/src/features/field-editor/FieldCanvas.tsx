import { forwardRef, useState } from "react";
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { FieldConfiguration, FieldOrientation } from "../../models";
import { BallMarker } from "./BallMarker";
import { FieldSurface } from "./FieldSurface";
import { OpenSpaceMarker } from "./OpenSpaceMarker";
import { PlayerMarker } from "./PlayerMarker";

type FieldCanvasProps = {
  configuration: FieldConfiguration;
  orientation: FieldOrientation;
  onLayout?: (event: LayoutChangeEvent) => void;
  onFieldPress?: (event: GestureResponderEvent) => void;
  onBallMove?: (pageX: number, pageY: number) => void;
  onPlayerMove?: (id: string, pageX: number, pageY: number) => void;
  onOpenSpaceResize?: (id: string, pageX: number, pageY: number) => void;
  onOpenSpaceMove?: (id: string, deltaX: number, deltaY: number) => void;
  onOpenSpaceSelect?: (id: string) => void;
  selectedOpenSpaceId?: string | null;
};

export const FieldCanvas = forwardRef<View, FieldCanvasProps>(
  function FieldCanvas(
    {
      configuration,
      orientation,
      onBallMove,
      onFieldPress,
      onLayout,
      onOpenSpaceMove,
      onOpenSpaceResize,
      onOpenSpaceSelect,
      onPlayerMove,
      selectedOpenSpaceId,
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
        {configuration.players.length === 0 && (
          <View style={styles.emptyMessage}>
            <Text style={styles.fieldLabel}>{configuration.label} FIELD</Text>
            <Text style={styles.fieldHint}>
              Drag players from the configuration panel
            </Text>
          </View>
        )}

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

        <BallMarker
          ball={configuration.ball}
          onMove={onBallMove}
          orientation={orientation}
        />

        {configuration.players.map((player) => (
          <PlayerMarker
            key={player.id}
            onMove={onPlayerMove}
            orientation={orientation}
            player={player}
          />
        ))}
      </FieldSurface>
    );
  },
);

const styles = StyleSheet.create({
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
