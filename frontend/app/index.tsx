import { useCallback, useMemo, useRef, useState } from "react";
import {
  Animated,
  GestureResponderEvent,
  PanResponder,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";

import { FieldCanvas } from "../src/features/field-editor";
import {
  animationFrameToSeconds,
  ManualAnimationBuilder,
  useAnimationSession,
} from "../src/features/animation-playback";
import {
  AnimationResponse,
  createFieldConfiguration,
  FIELD_LENGTH_CM,
  FIELD_WIDTH_CM,
  FieldFormat,
  FIELD_FORMATS,
  FieldOrientation,
  OpenSpaceType,
  screenDeltaToFieldDelta,
  screenToFieldPosition,
} from "../src/models";

const PRESET_MAPS = ["Balanced", "High press", "Build from back"] as const;

type TeamRole = "Offense" | "Defense";
type SetupMode = "Create new" | "Use preset";

type ChoiceButtonProps = {
  label: string;
  selected: boolean;
  onPress: () => void;
};

function ChoiceButton({ label, selected, onPress }: ChoiceButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ pressed }) => [
        styles.choiceButton,
        selected && styles.choiceButtonSelected,
        pressed && styles.choiceButtonPressed,
      ]}
    >
      <Text
        style={[styles.choiceButtonText, selected && styles.choiceButtonTextSelected]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

type DraggablePlayerProps = {
  id: string;
  selected: boolean;
  role: TeamRole;
  placed: boolean;
  onDrop: (id: string, pageX: number, pageY: number) => void;
  onSelect: (id: string) => void;
};

function DraggablePlayer({
  id,
  role,
  placed,
  selected,
  onDrop,
  onSelect,
}: DraggablePlayerProps) {
  const translation = useRef(new Animated.ValueXY()).current;
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onStartShouldSetPanResponderCapture: () => true,
        onMoveShouldSetPanResponder: (_, gesture) =>
          Math.abs(gesture.dx) > 2 || Math.abs(gesture.dy) > 2,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderGrant: () => translation.setOffset({ x: 0, y: 0 }),
        onPanResponderMove: Animated.event(
          [null, { dx: translation.x, dy: translation.y }],
          { useNativeDriver: false },
        ),
        onPanResponderRelease: (
          event: GestureResponderEvent,
          gesture,
        ) => {
          if (Math.hypot(gesture.dx, gesture.dy) < 6) {
            onSelect(id);
          } else {
            onDrop(
              id,
              gesture.moveX || event.nativeEvent.pageX,
              gesture.moveY || event.nativeEvent.pageY,
            );
          }
          translation.setValue({ x: 0, y: 0 });
          translation.setOffset({ x: 0, y: 0 });
        },
        onPanResponderTerminate: () => {
          translation.setValue({ x: 0, y: 0 });
          translation.setOffset({ x: 0, y: 0 });
        },
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [id, onDrop, onSelect, translation],
  );

  return (
    <Animated.View
      {...panResponder.panHandlers}
      hitSlop={8}
      style={[
        styles.playerToken,
        role === "Defense" && styles.playerTokenDefense,
        placed && styles.playerTokenPlaced,
        selected && styles.playerTokenSelected,
        { transform: translation.getTranslateTransform() },
      ]}
    >
      <Text style={styles.playerTokenText}>{id}</Text>
    </Animated.View>
  );
}

export default function HomeScreen() {
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const fieldOrientation: FieldOrientation = isWide ? "horizontal" : "vertical";
  const [teamRole, setTeamRole] = useState<TeamRole>("Offense");
  const [fieldConfiguration, setFieldConfiguration] = useState(
    createFieldConfiguration("5v5"),
  );
  const [animationResponse, setAnimationResponse] = useState<AnimationResponse>(
    { duration: 10, events: [] },
  );
  const [setupMode, setSetupMode] = useState<SetupMode>("Create new");
  const [preset, setPreset] = useState<(typeof PRESET_MAPS)[number]>("Balanced");
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);
  const [openSpaceTool, setOpenSpaceTool] = useState<OpenSpaceType | null>(null);
  const [selectedOpenSpaceId, setSelectedOpenSpaceId] = useState<string | null>(
    null,
  );
  const [isSequenceEditorOpen, setIsSequenceEditorOpen] = useState(false);
  const fieldRef = useRef<View>(null);
  const openSpaceSequence = useRef(1);
  const playerCount = Number.parseInt(fieldConfiguration.fieldType, 10);
  const playerPrefix = teamRole === "Offense" ? "A" : "D";
  const availablePlayers = Array.from(
    { length: playerCount },
    (_, index) => `${playerPrefix}${index + 1}`,
  );
  const { pause, play, reset, session } = useAnimationSession(
    fieldConfiguration,
    animationResponse,
  );

  function changeFieldFormat(fieldType: FieldFormat) {
    setFieldConfiguration(createFieldConfiguration(fieldType));
    setAnimationResponse((current) => ({ ...current, events: [] }));
    setSelectedPlayerId(null);
    setOpenSpaceTool(null);
    setSelectedOpenSpaceId(null);
    openSpaceSequence.current = 1;
  }

  const placePlayer = useCallback((id: string, pageX: number, pageY: number) => {
    fieldRef.current?.measureInWindow((x, y, width, height) => {
      const isInsideField =
        pageX >= x &&
        pageX <= x + width &&
        pageY >= y &&
        pageY <= y + height;

      if (!isInsideField) {
        return;
      }

      const number = Number.parseInt(id.slice(1), 10);
      const position = screenToFieldPosition(
        {
          x: (pageX - x) / width,
          y: (pageY - y) / height,
        },
        fieldOrientation,
      );
      const player = {
        id,
        name: id.startsWith("A") ? `Attacker ${number}` : `Defender ${number}`,
        number,
        team: id.startsWith("A") ? ("attack" as const) : ("defense" as const),
        position,
        orientation: 0,
      };

      setFieldConfiguration((current) => ({
        ...current,
        players: [
          ...current.players.filter((currentPlayer) => currentPlayer.id !== id),
          player,
        ],
      }));
    });
  }, [fieldOrientation]);

  const placeBall = useCallback((pageX: number, pageY: number) => {
    fieldRef.current?.measureInWindow((x, y, width, height) => {
      const isInsideField =
        pageX >= x &&
        pageX <= x + width &&
        pageY >= y &&
        pageY <= y + height;

      if (!isInsideField) {
        return;
      }

      setFieldConfiguration((current) => ({
        ...current,
        ball: {
          ...current.ball,
          position: screenToFieldPosition(
            {
              x: (pageX - x) / width,
              y: (pageY - y) / height,
            },
            fieldOrientation,
          ),
        },
      }));
    });
  }, [fieldOrientation]);

  const selectPlayer = useCallback((id: string) => {
    setSelectedPlayerId(id);
    setOpenSpaceTool(null);
    setSelectedOpenSpaceId(null);
  }, []);

  const createOpenSpace = useCallback(
    (type: OpenSpaceType, pageX: number, pageY: number) => {
      fieldRef.current?.measureInWindow((x, y, width, height) => {
        const screenPosition = {
          x: (pageX - x) / width,
          y: (pageY - y) / height,
        };

        if (
          screenPosition.x < 0 ||
          screenPosition.x > 1 ||
          screenPosition.y < 0 ||
          screenPosition.y > 1
        ) {
          return;
        }

        const center = screenToFieldPosition(screenPosition, fieldOrientation);
        const name = `OpenSpace${openSpaceSequence.current}`;
        const id = name;
        openSpaceSequence.current += 1;
        const initialCircleRadius = 800;
        const openSpace =
          type === "circular"
            ? {
                id,
                name,
                type,
                center: {
                  x: Math.min(
                    FIELD_LENGTH_CM - initialCircleRadius,
                    Math.max(initialCircleRadius, center.x),
                  ),
                  y: Math.min(
                    FIELD_WIDTH_CM - initialCircleRadius,
                    Math.max(initialCircleRadius, center.y),
                  ),
                },
                radius: initialCircleRadius,
              }
            : {
                id,
                name,
                type,
                bottomLeft: {
                  x: Math.max(0, center.x - 900),
                  y: Math.max(0, center.y - 630),
                },
                topRight: {
                  x: Math.min(FIELD_LENGTH_CM, center.x + 900),
                  y: Math.min(FIELD_WIDTH_CM, center.y + 630),
                },
              };

        setFieldConfiguration((current) => ({
          ...current,
          openSpaces: [...current.openSpaces, openSpace],
        }));
        setSelectedOpenSpaceId(id);
        setOpenSpaceTool(null);
      });
    },
    [fieldOrientation],
  );

  const resizeOpenSpace = useCallback(
    (id: string, pageX: number, pageY: number) => {
      fieldRef.current?.measureInWindow((x, y, width, height) => {
        const position = screenToFieldPosition(
          {
            x: (pageX - x) / width,
            y: (pageY - y) / height,
          },
          fieldOrientation,
        );

        setFieldConfiguration((current) => ({
          ...current,
          openSpaces: current.openSpaces.map((openSpace) => {
            if (openSpace.id !== id) {
              return openSpace;
            }

            if (openSpace.type === "circular") {
              const requestedRadius = Math.hypot(
                position.x - openSpace.center.x,
                position.y - openSpace.center.y,
              );
              const maximumRadius = Math.min(
                openSpace.center.x,
                FIELD_LENGTH_CM - openSpace.center.x,
                openSpace.center.y,
                FIELD_WIDTH_CM - openSpace.center.y,
              );

              return {
                ...openSpace,
                radius: Math.max(300, Math.min(maximumRadius, requestedRadius)),
              };
            }

            return {
              ...openSpace,
              topRight: {
                x: Math.max(openSpace.bottomLeft.x + 300, position.x),
                y: Math.max(openSpace.bottomLeft.y + 300, position.y),
              },
            };
          }),
        }));
      });
    },
    [fieldOrientation],
  );

  const moveOpenSpace = useCallback(
    (id: string, deltaXPixels: number, deltaYPixels: number) => {
      fieldRef.current?.measureInWindow((_x, _y, width, height) => {
        const delta = screenDeltaToFieldDelta(
          { x: deltaXPixels / width, y: deltaYPixels / height },
          fieldOrientation,
        );

        setFieldConfiguration((current) => ({
          ...current,
          openSpaces: current.openSpaces.map((openSpace) => {
            if (openSpace.id !== id) {
              return openSpace;
            }

            if (openSpace.type === "circular") {
              return {
                ...openSpace,
                center: {
                  x: Math.min(
                    FIELD_LENGTH_CM - openSpace.radius,
                    Math.max(openSpace.radius, openSpace.center.x + delta.x),
                  ),
                  y: Math.min(
                    FIELD_WIDTH_CM - openSpace.radius,
                    Math.max(openSpace.radius, openSpace.center.y + delta.y),
                  ),
                },
              };
            }

            const minimumDeltaX = -openSpace.bottomLeft.x;
            const maximumDeltaX = FIELD_LENGTH_CM - openSpace.topRight.x;
            const minimumDeltaY = -openSpace.bottomLeft.y;
            const maximumDeltaY = FIELD_WIDTH_CM - openSpace.topRight.y;
            const constrainedDelta = {
              x: Math.min(maximumDeltaX, Math.max(minimumDeltaX, delta.x)),
              y: Math.min(maximumDeltaY, Math.max(minimumDeltaY, delta.y)),
            };

            return {
              ...openSpace,
              bottomLeft: {
                x: openSpace.bottomLeft.x + constrainedDelta.x,
                y: openSpace.bottomLeft.y + constrainedDelta.y,
              },
              topRight: {
                x: openSpace.topRight.x + constrainedDelta.x,
                y: openSpace.topRight.y + constrainedDelta.y,
              },
            };
          }),
        }));
      });
    },
    [fieldOrientation],
  );

  function selectOpenSpaceTool(type: OpenSpaceType) {
    setOpenSpaceTool(type);
    setSelectedPlayerId(null);
    setSelectedOpenSpaceId(null);
  }

  function selectOpenSpace(id: string) {
    setSelectedOpenSpaceId(id);
    setOpenSpaceTool(null);
    setSelectedPlayerId(null);
  }

  function deleteSelectedOpenSpace() {
    if (!selectedOpenSpaceId) {
      return;
    }

    setFieldConfiguration((current) => ({
      ...current,
      openSpaces: current.openSpaces.filter(
        (openSpace) => openSpace.id !== selectedOpenSpaceId,
      ),
    }));
    setSelectedOpenSpaceId(null);
  }

  function placeSelectedElement(event: GestureResponderEvent) {
    if (openSpaceTool) {
      createOpenSpace(
        openSpaceTool,
        event.nativeEvent.pageX,
        event.nativeEvent.pageY,
      );
      return;
    }

    if (selectedPlayerId) {
      placePlayer(
        selectedPlayerId,
        event.nativeEvent.pageX,
        event.nativeEvent.pageY,
      );
      setSelectedPlayerId(null);
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView
        scrollEnabled={!isWide}
        style={styles.pageScroller}
        contentContainerStyle={[
          styles.page,
          isWide && styles.pageWide,
        ]}
      >
        <ScrollView
          contentContainerStyle={styles.sidebarContent}
          nestedScrollEnabled
          scrollEnabled={isWide}
          showsVerticalScrollIndicator={isWide}
          style={[styles.sidebar, isWide && styles.sidebarWide]}
        >
          <View style={styles.brand}>
            <View style={styles.brandMark} />
            <View>
              <Text style={styles.eyebrow}>TACTICAL WORKSPACE</Text>
              <Text style={styles.title}>Soccer Analysis Agent</Text>
            </View>
          </View>

          <View style={styles.configuration}>
            <View style={styles.section}>
              <Text style={styles.sectionNumber}>01</Text>
              <Text style={styles.sectionLabel}>Team role</Text>
              <View style={styles.choiceRow}>
                {(["Offense", "Defense"] as const).map((role) => (
                  <ChoiceButton
                    key={role}
                    label={role}
                    selected={teamRole === role}
                    onPress={() => setTeamRole(role)}
                  />
                ))}
              </View>
            </View>

            <View style={styles.divider} />

            <View style={styles.section}>
              <Text style={styles.sectionNumber}>02</Text>
              <Text style={styles.sectionLabel}>Field configuration</Text>
              <View style={styles.choiceRow}>
                {FIELD_FORMATS.map((format) => (
                  <ChoiceButton
                    key={format}
                    label={format}
                    selected={fieldConfiguration.fieldType === format}
                    onPress={() => changeFieldFormat(format)}
                  />
                ))}
              </View>
            </View>

            <View style={styles.divider} />

            <View style={styles.section}>
              <Text style={styles.sectionNumber}>03</Text>
              <Text style={styles.sectionLabel}>
                {teamRole === "Offense" ? "Attack" : "Defense"} players
              </Text>
              <Text style={styles.sectionHelp}>
                Select a player, then tap the field
              </Text>
              <View style={styles.playerTray}>
                {availablePlayers.map((player) => (
                  <DraggablePlayer
                    id={player}
                    key={player}
                    onDrop={placePlayer}
                    onSelect={selectPlayer}
                    placed={fieldConfiguration.players.some(
                      ({ id }) => id === player,
                    )}
                    role={teamRole}
                    selected={selectedPlayerId === player}
                  />
                ))}
              </View>
            </View>

            <View style={styles.divider} />

            <View style={styles.section}>
              <Text style={styles.sectionNumber}>04</Text>
              <Text style={styles.sectionLabel}>Open spaces</Text>
              <Text style={styles.sectionHelp}>
                Choose a shape, then tap the field
              </Text>
              <View style={styles.choiceRow}>
                <ChoiceButton
                  label="Circle"
                  onPress={() => selectOpenSpaceTool("circular")}
                  selected={openSpaceTool === "circular"}
                />
                <ChoiceButton
                  label="Rectangle"
                  onPress={() => selectOpenSpaceTool("rectangular")}
                  selected={openSpaceTool === "rectangular"}
                />
              </View>
              {selectedOpenSpaceId && (
                <Pressable
                  accessibilityRole="button"
                  onPress={deleteSelectedOpenSpace}
                  style={styles.deleteButton}
                >
                  <Text style={styles.deleteButtonText}>Delete selected space</Text>
                </Pressable>
              )}
            </View>

            <View style={styles.divider} />

            <View style={styles.section}>
              <Text style={styles.sectionNumber}>05</Text>
              <Text style={styles.sectionLabel}>Starting layout</Text>
              <View style={styles.choiceRow}>
                {(["Create new", "Use preset"] as const).map((mode) => (
                  <ChoiceButton
                    key={mode}
                    label={mode}
                    selected={setupMode === mode}
                    onPress={() => setSetupMode(mode)}
                  />
                ))}
              </View>

              {setupMode === "Use preset" && (
                <View style={styles.presetList}>
                  {PRESET_MAPS.map((map) => {
                    const selected = preset === map;

                    return (
                      <Pressable
                        accessibilityRole="button"
                        accessibilityState={{ selected }}
                        key={map}
                        onPress={() => setPreset(map)}
                        style={[
                          styles.presetButton,
                          selected && styles.presetButtonSelected,
                        ]}
                      >
                        <View
                          style={[
                            styles.radio,
                            selected && styles.radioSelected,
                          ]}
                        />
                        <Text style={styles.presetText}>{map}</Text>
                      </Pressable>
                    );
                  })}
                </View>
              )}
            </View>

            <View style={styles.divider} />

            <View style={styles.section}>
              <Text style={styles.sectionNumber}>06</Text>
              <Text style={styles.sectionLabel}>Animation sequence</Text>
              <Text style={styles.sectionHelp}>
                Build an optional timeline for this layout
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ expanded: isSequenceEditorOpen }}
                onPress={() => setIsSequenceEditorOpen((current) => !current)}
                style={styles.sequenceToggleButton}
              >
                <Text style={styles.sequenceToggleButtonText}>
                  {isSequenceEditorOpen
                    ? "Close sequence editor"
                    : animationResponse.events.length > 0
                      ? `Edit sequence (${animationResponse.events.length})`
                      : "Add sequence of events"}
                </Text>
              </Pressable>
              {isSequenceEditorOpen && (
                <ManualAnimationBuilder
                  configuration={fieldConfiguration}
                  onChange={setAnimationResponse}
                  response={animationResponse}
                />
              )}
            </View>
          </View>
        </ScrollView>

        <View style={[styles.workspace, isWide && styles.workspaceWide]}>
          <View style={styles.workspaceHeader}>
            <View>
              <Text style={styles.workspaceTitle}>Field workspace</Text>
              <Text style={styles.workspaceSubtitle}>
                {fieldConfiguration.label} · {teamRole} · {setupMode}
              </Text>
            </View>
            <View style={styles.playbackControls}>
              <Text style={styles.playbackTime}>
                {animationFrameToSeconds(session.currentTime).toFixed(2)} / {session.response.duration}s
              </Text>
              <Pressable
                accessibilityRole="button"
                onPress={session.status === "playing" ? pause : play}
                style={styles.playbackButton}
              >
                <Text style={styles.playbackButtonText}>
                  {session.status === "playing" ? "Pause" : "Play"}
                </Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={reset}
                style={styles.resetButton}
              >
                <Text style={styles.resetButtonText}>Reset</Text>
              </Pressable>
            </View>
          </View>

          <View style={[styles.fieldFrame, isWide && styles.fieldFrameWide]}>
            <FieldCanvas
              configuration={session.animatedConfiguration}
              onBallMove={placeBall}
              onFieldPress={placeSelectedElement}
              onOpenSpaceMove={moveOpenSpace}
              onOpenSpaceResize={resizeOpenSpace}
              onOpenSpaceSelect={selectOpenSpace}
              onPlayerMove={placePlayer}
              orientation={fieldOrientation}
              ref={fieldRef}
              selectedOpenSpaceId={selectedOpenSpaceId}
            />
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: "#F3F1EA",
    flex: 1,
  },
  pageScroller: {
    flex: 1,
  },
  page: {
    flexGrow: 1,
    gap: 20,
    padding: 16,
  },
  pageWide: {
    flex: 1,
    flexDirection: "row",
    gap: 10,
    overflow: "hidden",
    padding: 10,
  },
  sidebar: {
    zIndex: 2,
  },
  sidebarContent: {
    gap: 14,
    paddingBottom: 16,
  },
  sidebarWide: {
    flexBasis: "20%",
    flexShrink: 0,
    height: "100%",
    maxWidth: 230,
    minWidth: 190,
  },
  brand: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
  },
  brandMark: {
    backgroundColor: "#D8FF3E",
    borderRadius: 5,
    height: 38,
    transform: [{ rotate: "8deg" }],
    width: 10,
  },
  eyebrow: {
    color: "#68716A",
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.5,
  },
  title: {
    color: "#14251D",
    fontSize: 18,
    fontWeight: "700",
  },
  configuration: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E1E3DD",
    borderRadius: 18,
    borderWidth: 1,
    padding: 11,
  },
  section: {
    gap: 9,
  },
  sectionNumber: {
    color: "#9BA19D",
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1,
  },
  sectionLabel: {
    color: "#18251F",
    fontSize: 15,
    fontWeight: "700",
  },
  sectionHelp: {
    color: "#778079",
    fontSize: 12,
    marginTop: -7,
  },
  choiceRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  choiceButton: {
    backgroundColor: "#F1F3EF",
    borderColor: "transparent",
    borderRadius: 9,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  choiceButtonSelected: {
    backgroundColor: "#183E2B",
    borderColor: "#183E2B",
  },
  choiceButtonPressed: {
    opacity: 0.72,
  },
  choiceButtonText: {
    color: "#455149",
    fontSize: 13,
    fontWeight: "600",
  },
  choiceButtonTextSelected: {
    color: "#FFFFFF",
  },
  divider: {
    backgroundColor: "#ECEDE9",
    height: 1,
    marginVertical: 13,
  },
  playerTray: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 9,
  },
  playerToken: {
    alignItems: "center",
    backgroundColor: "#D8FF3E",
    borderColor: "#8EAA27",
    borderRadius: 19,
    borderWidth: 1,
    cursor: "grab",
    height: 38,
    justifyContent: "center",
    touchAction: "none",
    userSelect: "none",
    width: 38,
    zIndex: 10,
  },
  playerTokenDefense: {
    backgroundColor: "#FF725E",
    borderColor: "#B94132",
  },
  playerTokenPlaced: {
    opacity: 0.7,
  },
  playerTokenSelected: {
    borderColor: "#14251D",
    borderWidth: 3,
    opacity: 1,
    transform: [{ scale: 1.12 }],
  },
  playerTokenText: {
    color: "#17231D",
    fontSize: 12,
    fontWeight: "800",
  },
  deleteButton: {
    alignItems: "center",
    borderColor: "#D66A5B",
    borderRadius: 9,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  deleteButtonText: {
    color: "#A63D30",
    fontSize: 12,
    fontWeight: "700",
  },
  sequenceToggleButton: {
    alignItems: "center",
    backgroundColor: "#183E2B",
    borderRadius: 9,
    marginTop: 4,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  sequenceToggleButtonText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "700",
  },
  presetList: {
    gap: 8,
    marginTop: 2,
  },
  presetButton: {
    alignItems: "center",
    borderColor: "#E3E5E0",
    borderRadius: 9,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    padding: 11,
  },
  presetButtonSelected: {
    backgroundColor: "#F5FBEA",
    borderColor: "#ABC754",
  },
  radio: {
    borderColor: "#A7ADA9",
    borderRadius: 6,
    borderWidth: 1,
    height: 12,
    width: 12,
  },
  radioSelected: {
    backgroundColor: "#A9D22D",
    borderColor: "#77971B",
  },
  presetText: {
    color: "#354139",
    fontSize: 13,
    fontWeight: "600",
  },
  workspace: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E1E3DD",
    borderRadius: 20,
    borderWidth: 1,
    flex: 1,
    minHeight: 500,
    padding: 14,
    zIndex: 1,
  },
  workspaceWide: {
    minHeight: 0,
    padding: 8,
  },
  workspaceHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  workspaceTitle: {
    color: "#18251F",
    fontSize: 18,
    fontWeight: "700",
  },
  workspaceSubtitle: {
    color: "#778079",
    fontSize: 12,
    marginTop: 3,
  },
  playbackControls: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  playbackTime: {
    color: "#68716A",
    fontSize: 11,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
  },
  playbackButton: {
    backgroundColor: "#183E2B",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  playbackButtonText: {
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "700",
  },
  resetButton: {
    backgroundColor: "#F2F4F0",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  resetButtonText: {
    color: "#485249",
    fontSize: 11,
    fontWeight: "700",
  },
  fieldFrame: {
    backgroundColor: "#143B29",
    borderRadius: 14,
    flex: 1,
    minHeight: 410,
    padding: 4,
  },
  fieldFrameWide: {
    minHeight: 0,
  },
});
