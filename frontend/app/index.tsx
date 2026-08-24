import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  GestureResponderEvent,
  PanResponder,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";

import { FieldCanvas } from "../src/features/field-editor";
import { CommentaryPanel } from "../src/features/commentary";
import {
  analyzeFieldConfiguration,
  generateCommentary,
} from "../src/api/analyze-field";
import {
  animationFrameToSeconds,
  ManualAnimationBuilder,
  useAnimationSession,
} from "../src/features/animation-playback";
import {
  AnimationResponse,
  AlternativePlan,
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
type SetupMode = "Create new" | "Use preset";
type AnalysisStatus = "idle" | "loading" | "success" | "error";
type CommentaryStatus = "idle" | "loading" | "ready" | "unavailable";

function alternativeResponse(plan: AlternativePlan): AnimationResponse {
  return {
    duration: plan.duration,
    events: plan.events,
    diagnostics: plan.diagnostics,
    phaseSnapshots: plan.phaseSnapshots,
    commentary: plan.commentary,
  };
}

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
  color: string;
  number: number;
  placed: boolean;
  onDrop: (id: string, pageX: number, pageY: number) => void;
  onSelect: (id: string) => void;
};

function DraggablePlayer({
  id,
  color,
  number,
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
        placed && styles.playerTokenPlaced,
        selected && styles.playerTokenSelected,
        { backgroundColor: color, transform: translation.getTranslateTransform() },
      ]}
    >
      <Text style={styles.playerTokenText}>{number}</Text>
    </Animated.View>
  );
}

export default function HomeScreen() {
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const fieldOrientation: FieldOrientation = isWide ? "horizontal" : "vertical";
  const [fieldConfiguration, setFieldConfiguration] = useState(
    createFieldConfiguration("5v5"),
  );
  const [selectedTeamId, setSelectedTeamId] = useState("team1");
  const [animationResponse, setAnimationResponse] = useState<AnimationResponse>(
    { duration: 0, events: [] },
  );
  const [primaryPlanResponse, setPrimaryPlanResponse] =
    useState<AnimationResponse | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState("requested");
  const [isPlanDropdownOpen, setIsPlanDropdownOpen] = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus>("idle");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [commentaryStatuses, setCommentaryStatuses] = useState<
    Record<string, CommentaryStatus>
  >({});
  const [tacticalInstruction, setTacticalInstruction] = useState("");
  const [setupMode, setSetupMode] = useState<SetupMode>("Create new");
  const [preset, setPreset] = useState<(typeof PRESET_MAPS)[number]>("Balanced");
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);
  const [orientationPlayerId, setOrientationPlayerId] = useState<string | null>(
    null,
  );
  const [openSpaceTool, setOpenSpaceTool] = useState<OpenSpaceType | null>(null);
  const [selectedOpenSpaceId, setSelectedOpenSpaceId] = useState<string | null>(
    null,
  );
  const [isSequenceEditorOpen, setIsSequenceEditorOpen] = useState(false);
  const fieldRef = useRef<View>(null);
  const analysisAbortController = useRef<AbortController | null>(null);
  const selectedPlanIdRef = useRef("requested");
  const openSpaceSequence = useRef(1);
  const playerCount = Number.parseInt(fieldConfiguration.fieldType, 10);
  const selectedTeam =
    fieldConfiguration.teams.find(({ id }) => id === selectedTeamId) ??
    fieldConfiguration.teams[0];
  const selectedFieldPlayer = orientationPlayerId
    ? fieldConfiguration.players.find(({ id }) => id === orientationPlayerId)
    : undefined;
  const availablePlayers = Array.from(
    { length: playerCount },
    (_, index) => ({
      id: `${selectedTeam.id}-${index + 1}`,
      number: index + 1,
    }),
  );
  const { pause, play, reset, session } = useAnimationSession(
    fieldConfiguration,
    animationResponse,
  );
  const displayedConfiguration = useMemo(() => {
    const profileNames = new Map(
      fieldConfiguration.players.map((player) => [player.id, player.profileName]),
    );
    return {
      ...session.animatedConfiguration,
      // Animation state updates through an effect. Overlay editor-only profile
      // metadata synchronously so the label appears on the same render as input.
      players: session.animatedConfiguration.players.map((player) => ({
        ...player,
        profileName: profileNames.get(player.id),
      })),
    };
  }, [fieldConfiguration.players, session.animatedConfiguration]);
  const isPlaybackReady =
    analysisStatus === "success" && animationResponse.events.length > 0;
  const playbackSeconds = animationFrameToSeconds(session.currentTime);
  const phaseSnapshots = animationResponse.phaseSnapshots ?? [];
  const activePhaseSnapshot = [...phaseSnapshots]
    .reverse()
    .find((snapshot) => snapshot.atTime <= playbackSeconds);
  const activeStandardOpenSpaces = activePhaseSnapshot?.openSpaces.filter(
    (space): space is {
      id: string;
      center: { x: number; y: number };
      radius: number;
    } => "radius" in space,
  );
  const responseHasStandardSnapshotSpaces = phaseSnapshots.some((snapshot) =>
    snapshot.openSpaces.some((space) => "radius" in space),
  );
  // Older standard responses only expose root spaces in diagnostics. Keep
  // that payload visible while newer responses use timed phase snapshots.
  const visibleStandardOpenSpaces = responseHasStandardSnapshotSpaces
    ? activeStandardOpenSpaces ?? []
    : animationResponse.diagnostics?.dynamicSpaces ?? [];
  const selectedPhases = animationResponse.diagnostics?.selectedPhases ?? [];
  const activePhase =
    selectedPhases.find(
      (phase) =>
        playbackSeconds >= phase.startTime && playbackSeconds < phase.endTime,
    ) ??
    (playbackSeconds >= animationResponse.duration
      ? selectedPhases.at(-1)
      : undefined);
  const offsideReleaseLineX =
    activePhase &&
    playbackSeconds >= activePhase.ballActionStartTime &&
    (activePhase.actionType === "PASS_TO_PLAYER" ||
      activePhase.actionType === "PASS_TO_SPACE")
      ? activePhase.offsideLineX
      : undefined;
  const selectedAlternative = primaryPlanResponse?.alternativePlans?.find(
    ({ id }) => id === selectedPlanId,
  );
  const selectedPlanLabel = selectedAlternative?.label ?? "Requested plan";

  useEffect(() => {
    analysisAbortController.current?.abort();
    setAnalysisStatus("idle");
    setAnalysisError(null);
    setCommentaryStatuses({});
    setAnimationResponse({ duration: 0, events: [] });
    setPrimaryPlanResponse(null);
    selectedPlanIdRef.current = "requested";
    setSelectedPlanId("requested");
    setIsPlanDropdownOpen(false);
  }, [fieldConfiguration]);

  useEffect(
    () => () => analysisAbortController.current?.abort(),
    [],
  );

  async function analyzeCurrentField() {
    analysisAbortController.current?.abort();
    const controller = new AbortController();
    analysisAbortController.current = controller;
    pause();
    setAnalysisStatus("loading");
    setAnalysisError(null);
    setCommentaryStatuses({});
    setAnimationResponse({ duration: 0, events: [] });

    try {
      const response = await analyzeFieldConfiguration(
        fieldConfiguration,
        tacticalInstruction,
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setAnimationResponse(response);
        setPrimaryPlanResponse(response);
        selectedPlanIdRef.current = "requested";
        setSelectedPlanId("requested");
        setIsPlanDropdownOpen(false);
        setAnalysisStatus("success");
        const commentaryPlans = [
          { id: "requested", response },
          ...(response.alternativePlans ?? []).map((plan) => ({
            id: plan.id,
            response: alternativeResponse(plan),
          })),
        ];
        setCommentaryStatuses(
          Object.fromEntries(commentaryPlans.map(({ id }) => [id, "loading"])),
        );
        // Each selectable plan owns an independent asynchronous commentary
        // request. One failure never blocks simulation or the other plans.
        for (const commentaryPlan of commentaryPlans) {
          void generateCommentary(
            fieldConfiguration,
            commentaryPlan.response,
            tacticalInstruction,
            controller.signal,
          )
            .then((commentary) => {
              if (controller.signal.aborted) return;
              setPrimaryPlanResponse((current) => {
                if (!current) return current;
                if (commentaryPlan.id === "requested") {
                  return { ...current, commentary };
                }
                return {
                  ...current,
                  alternativePlans: current.alternativePlans?.map((plan) =>
                    plan.id === commentaryPlan.id ? { ...plan, commentary } : plan,
                  ),
                };
              });
              if (selectedPlanIdRef.current === commentaryPlan.id) {
                pause();
                reset();
                setAnimationResponse({
                  ...commentaryPlan.response,
                  commentary,
                });
              }
              setCommentaryStatuses((current) => ({
                ...current,
                [commentaryPlan.id]: "ready",
              }));
            })
            .catch(() => {
              if (!controller.signal.aborted) {
                setCommentaryStatuses((current) => ({
                  ...current,
                  [commentaryPlan.id]: "unavailable",
                }));
              }
            });
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setAnalysisStatus("error");
        setAnalysisError(
          error instanceof Error ? error.message : "Unable to analyze the field.",
        );
      }
    }
  }

  function selectPlan(id: string, response: AnimationResponse) {
    pause();
    selectedPlanIdRef.current = id;
    setAnimationResponse(response);
    setSelectedPlanId(id);
    setIsPlanDropdownOpen(false);
  }

  function updateManualAnimation(response: AnimationResponse) {
    setAnimationResponse(response);
    setPrimaryPlanResponse(null);
    setAnalysisError(null);
    setAnalysisStatus(response.events.length > 0 ? "success" : "idle");
  }

  function changeFieldFormat(fieldType: FieldFormat) {
    setFieldConfiguration(createFieldConfiguration(fieldType));
    setAnimationResponse((current) => ({ ...current, events: [] }));
    setSelectedPlayerId(null);
    setOrientationPlayerId(null);
    setOpenSpaceTool(null);
    setSelectedOpenSpaceId(null);
    setSelectedTeamId("team1");
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

      const number = Number.parseInt(id.split("-").at(-1) ?? "", 10);
      const teamId = id.slice(0, id.lastIndexOf("-"));
      const position = screenToFieldPosition(
        {
          x: (pageX - x) / width,
          y: (pageY - y) / height,
        },
        fieldOrientation,
      );
      setFieldConfiguration((current) => {
        const team = current.teams.find(({ id }) => id === teamId);
        const existing = current.players.find((player) => player.id === id);
        const defendedGoal = current.goals.find(
          ({ id }) => id === team?.defendedGoalId,
        );
        const player = {
          id,
          // Preserve internal identity and the optional coach-facing profile
          // name when repositioning an existing player.
          name: existing?.name ?? `${team?.name ?? "team"}-${number}`,
          profileName: existing?.profileName,
          number,
          teamId,
          position,
          orientation:
            existing?.orientation ?? (defendedGoal?.side === "right" ? 180 : 0),
          speedCategory: existing?.speedCategory ?? "BASELINE",
        };

        return {
          ...current,
          players: [
            ...current.players.filter((currentPlayer) => currentPlayer.id !== id),
            player,
          ],
        };
      });
    });
  }, [fieldOrientation]);

  const setPlayerOrientation = useCallback((id: string, orientation: number) => {
    const normalizedOrientation = ((orientation % 360) + 360) % 360;
    setFieldConfiguration((current) => {
      const player = current.players.find((candidate) => candidate.id === id);
      if (!player) {
        return current;
      }
      const difference = Math.abs(
        ((normalizedOrientation - player.orientation + 540) % 360) - 180,
      );
      if (difference < 0.01) {
        return current;
      }
      return {
        ...current,
        players: current.players.map((candidate) =>
          candidate.id === id
            ? { ...candidate, orientation: normalizedOrientation }
            : candidate,
        ),
      };
    });
  }, []);

  const setPlayerProfileName = useCallback((id: string, profileName: string) => {
    setFieldConfiguration((current) => ({
      ...current,
      players: current.players.map((player) =>
        player.id === id ? { ...player, profileName } : player,
      ),
    }));
  }, []);


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
    setOrientationPlayerId(null);
    setOpenSpaceTool(null);
    setSelectedOpenSpaceId(null);
  }, []);

  const selectFieldPlayer = useCallback((id: string) => {
    if (orientationPlayerId === id) {
      setFieldConfiguration((current) => ({
        ...current,
        players: current.players.map((player) => {
          if (player.id !== id) {
            return player;
          }
          const speedCategory =
            player.speedCategory === "BASELINE"
              ? "FAST"
              : player.speedCategory === "FAST"
                ? "SUPER_FAST"
                : "BASELINE";
          return { ...player, speedCategory };
        }),
      }));
    }
    setOrientationPlayerId(id);
    setSelectedPlayerId(null);
    setOpenSpaceTool(null);
    setSelectedOpenSpaceId(null);
  }, [orientationPlayerId]);

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
    setOrientationPlayerId(null);
    setSelectedOpenSpaceId(null);
  }

  function selectOpenSpace(id: string) {
    setSelectedOpenSpaceId(id);
    setOpenSpaceTool(null);
    setSelectedPlayerId(null);
    setOrientationPlayerId(null);
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
    setOrientationPlayerId(null);
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
              <Text style={styles.sectionLabel}>Team</Text>
              <View style={styles.choiceRow}>
                {fieldConfiguration.teams.map((team) => (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ selected: selectedTeamId === team.id }}
                    key={team.id}
                    onPress={() => setSelectedTeamId(team.id)}
                    style={[
                      styles.teamButton,
                      selectedTeamId === team.id && styles.teamButtonSelected,
                    ]}
                  >
                    <View style={[styles.teamSwatch, { backgroundColor: team.color }]} />
                    <View>
                      <Text style={styles.teamButtonText}>{team.name}</Text>
                      <Text style={styles.teamGoalText}>
                        {fieldConfiguration.goals.find(({ id }) => id === team.defendedGoalId)?.name}
                      </Text>
                    </View>
                  </Pressable>
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
                {selectedTeam.name} players
              </Text>
              <Text style={styles.sectionHelp}>
                Drag to move; tap a field player to rotate
              </Text>
              <View style={styles.playerTray}>
                {availablePlayers.map((player) => (
                  <DraggablePlayer
                    color={selectedTeam.color}
                    id={player.id}
                    key={player.id}
                    number={player.number}
                    onDrop={placePlayer}
                    onSelect={selectPlayer}
                    placed={fieldConfiguration.players.some(
                      ({ id }) => id === player.id,
                    )}
                    selected={selectedPlayerId === player.id}
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
                  onChange={updateManualAnimation}
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
                {fieldConfiguration.label} · {selectedTeam.name} · {setupMode}
              </Text>
            </View>
            <View style={styles.playbackControls}>
              <TextInput
                accessibilityLabel="Tactical instruction"
                editable={analysisStatus !== "loading"}
                maxLength={500}
                onChangeText={setTacticalInstruction}
                placeholder="e.g. attack quickly through wide spaces"
                placeholderTextColor="#89918C"
                style={styles.tacticalInstructionInput}
                value={tacticalInstruction}
              />
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: analysisStatus === "loading" }}
                disabled={analysisStatus === "loading"}
                onPress={analyzeCurrentField}
                style={[
                  styles.analyzeButton,
                  analysisStatus === "loading" && styles.controlButtonDisabled,
                ]}
              >
                <Text style={styles.analyzeButtonText}>
                  {analysisStatus === "loading" ? "Analyzing…" : "Analyze"}
                </Text>
              </Pressable>
              {primaryPlanResponse &&
                (primaryPlanResponse.alternativePlans?.length ?? 0) > 0 && (
                  <View style={styles.headerPlanSelector}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityState={{ expanded: isPlanDropdownOpen }}
                      onPress={() => setIsPlanDropdownOpen((open) => !open)}
                      style={styles.headerPlanButton}
                    >
                      <Text style={styles.planOptionLabel}>{selectedPlanLabel}</Text>
                      <Text
                        style={[
                          styles.commentaryIndicator,
                          commentaryStatuses[selectedPlanId] === "ready" &&
                            styles.commentaryIndicatorReady,
                        ]}
                      >
                        {commentaryStatuses[selectedPlanId] === "loading"
                          ? "…"
                          : commentaryStatuses[selectedPlanId] === "ready"
                            ? "✓"
                            : ""}
                      </Text>
                      <Text style={styles.planDropdownChevron}>
                        {isPlanDropdownOpen ? "▲" : "▼"}
                      </Text>
                    </Pressable>
                    {isPlanDropdownOpen && (
                      <View style={styles.headerPlanMenu}>
                        <Pressable
                          onPress={() =>
                            selectPlan("requested", primaryPlanResponse)
                          }
                          style={[
                            styles.planDropdownItem,
                            selectedPlanId === "requested" &&
                              styles.planOptionSelected,
                          ]}
                        >
                          <View style={styles.planItemRow}>
                            <Text style={styles.planOptionLabel}>Requested plan</Text>
                            <Text
                              style={[
                                styles.commentaryIndicator,
                                commentaryStatuses.requested === "ready" &&
                                  styles.commentaryIndicatorReady,
                              ]}
                            >
                              {commentaryStatuses.requested === "loading"
                                ? "Loading…"
                                : commentaryStatuses.requested === "ready"
                                  ? "✓"
                                  : commentaryStatuses.requested === "unavailable"
                                    ? "—"
                                    : ""}
                            </Text>
                          </View>
                        </Pressable>
                        {primaryPlanResponse.alternativePlans?.map((plan) => (
                          <Pressable
                            key={plan.id}
                            onPress={() =>
                              selectPlan(plan.id, alternativeResponse(plan))
                            }
                            style={[
                              styles.planDropdownItem,
                              selectedPlanId === plan.id &&
                                styles.planOptionSelected,
                            ]}
                          >
                            <View style={styles.planItemRow}>
                              <Text style={styles.planOptionLabel}>{plan.label}</Text>
                              <Text
                                style={[
                                  styles.commentaryIndicator,
                                  commentaryStatuses[plan.id] === "ready" &&
                                    styles.commentaryIndicatorReady,
                                ]}
                              >
                                {commentaryStatuses[plan.id] === "loading"
                                  ? "Loading…"
                                  : commentaryStatuses[plan.id] === "ready"
                                    ? "✓"
                                    : commentaryStatuses[plan.id] === "unavailable"
                                      ? "—"
                                      : ""}
                              </Text>
                            </View>
                          </Pressable>
                        ))}
                      </View>
                    )}
                  </View>
                )}
              <Text style={styles.playbackTime}>
                {playbackSeconds.toFixed(2)} / {session.response.duration}s
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: !isPlaybackReady }}
                disabled={!isPlaybackReady}
                onPress={session.status === "playing" ? pause : play}
                style={[
                  styles.playbackButton,
                  !isPlaybackReady && styles.controlButtonDisabled,
                ]}
              >
                <Text style={styles.playbackButtonText}>
                  {session.status === "playing" ? "Pause" : "Play"}
                </Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: !isPlaybackReady }}
                disabled={!isPlaybackReady}
                onPress={reset}
                style={[
                  styles.resetButton,
                  !isPlaybackReady && styles.controlButtonDisabled,
                ]}
              >
                <Text style={styles.resetButtonText}>Reset</Text>
              </Pressable>
              <CommentaryPanel
                commentary={animationResponse.commentary}
                loading={commentaryStatuses[selectedPlanId] === "loading"}
                playbackSeconds={playbackSeconds}
                playbackStatus={session.status}
              />
            </View>
          </View>

          {analysisError && (
            <Text accessibilityRole="alert" style={styles.analysisError}>
              {analysisError}
            </Text>
          )}

          {selectedPhases.length > 0 && (
            <View style={styles.planSummary}>
              <View style={styles.planSummaryHeader}>
                <Text style={styles.planSummaryEyebrow}>SELECTED TACTICAL PLAN</Text>
                <Text style={styles.planSummaryScore}>
                  {animationResponse.diagnostics?.selectedSequenceScore?.toFixed(1)} pts
                </Text>
              </View>
              <View style={styles.phaseStrip}>
                {selectedPhases.map((phase, index) => {
                  const active = phase.id === activePhase?.id;
                  return (
                    <View
                      key={`${phase.id}-${index}`}
                      style={[styles.phaseCard, active && styles.phaseCardActive]}
                    >
                      <Text
                        style={[
                          styles.phaseCardIndex,
                          active && styles.phaseCardTextActive,
                        ]}
                      >
                        {index + 1} · {phase.startTime.toFixed(1)}–{phase.endTime.toFixed(1)}s
                      </Text>
                      <Text
                        style={[
                          styles.phaseCardTitle,
                          active && styles.phaseCardTextActive,
                        ]}
                      >
                        {phase.phaseType.replaceAll("_", " ")}
                      </Text>
                      <Text
                        style={[
                          styles.phaseCardDetail,
                          active && styles.phaseCardDetailActive,
                        ]}
                      >
                        {phase.actorId}
                        {phase.receiverId ? ` → ${phase.receiverId}` : ""}
                        {phase.scoredGoal ? " · GOAL" : ""}
                      </Text>
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          {selectedFieldPlayer && (
            <View style={styles.selectedPlayerEditor}>
              <View style={styles.selectedPlayerEditorHeading}>
                <Text style={styles.selectedPlayerEditorTitle}>
                  Player {selectedFieldPlayer.number}
                </Text>
                <Text style={styles.selectedPlayerEditorMeta}>
                  {selectedFieldPlayer.speedCategory.replaceAll("_", " ")} · {Math.round(selectedFieldPlayer.orientation)}°
                </Text>
              </View>
              <TextInput
                accessibilityLabel={`Player ${selectedFieldPlayer.number} name`}
                maxLength={40}
                onChangeText={(profileName) =>
                  setPlayerProfileName(selectedFieldPlayer.id, profileName)
                }
                placeholder="Enter profile name"
                placeholderTextColor="#89918C"
                selectTextOnFocus
                style={styles.playerNameInput}
                value={selectedFieldPlayer.profileName ?? ""}
              />
              <Text style={styles.selectedPlayerEditorHint}>
                Drag the dial for orientation. Click the player again to change capability.
              </Text>
            </View>
          )}

          <View style={[styles.fieldFrame, isWide && styles.fieldFrameWide]}>
            <FieldCanvas
              attackingTeamId={animationResponse.diagnostics?.attackingTeamId}
              configuration={displayedConfiguration}
              dynamicOpenSpaces={visibleStandardOpenSpaces}
              onBallMove={placeBall}
              onFieldPress={placeSelectedElement}
              onOpenSpaceMove={moveOpenSpace}
              onOpenSpaceResize={resizeOpenSpace}
              onOpenSpaceSelect={selectOpenSpace}
              offsideReleaseLineX={offsideReleaseLineX}
              onPlayerMove={placePlayer}
              onPlayerOrientationChange={setPlayerOrientation}
              onPlayerSelect={selectFieldPlayer}
              orientation={fieldOrientation}
              ref={fieldRef}
              selectedOpenSpaceId={selectedOpenSpaceId}
              selectedPlayerId={orientationPlayerId}
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
    cursor: "pointer",
    height: 38,
    justifyContent: "center",
    touchAction: "none",
    userSelect: "none",
    width: 38,
    zIndex: 10,
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
  teamButton: {
    alignItems: "center",
    borderColor: "#DADFD8",
    borderRadius: 9,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    padding: 7,
  },
  teamButtonSelected: {
    backgroundColor: "#F1F5F0",
    borderColor: "#183E2B",
  },
  teamSwatch: {
    borderColor: "#FFFFFF",
    borderRadius: 10,
    borderWidth: 2,
    height: 20,
    width: 20,
  },
  teamButtonText: {
    color: "#18251F",
    fontSize: 11,
    fontWeight: "700",
  },
  teamGoalText: {
    color: "#778079",
    fontSize: 9,
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
    overflow: "visible",
    position: "relative",
    zIndex: 200,
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
    zIndex: 30,
  },
  tacticalInstructionInput: {
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5C8",
    borderRadius: 8,
    borderWidth: 1,
    color: "#18251F",
    fontSize: 11,
    minWidth: 250,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  analyzeButton: {
    backgroundColor: "#A9D22D",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  analyzeButtonText: {
    color: "#17231D",
    fontSize: 11,
    fontWeight: "800",
  },
  controlButtonDisabled: {
    opacity: 0.4,
  },
  analysisError: {
    color: "#A63D30",
    fontSize: 12,
    fontWeight: "600",
    marginBottom: 8,
  },
  headerPlanSelector: {
    minWidth: 145,
    position: "relative",
    zIndex: 50,
  },
  headerPlanButton: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5C8",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    justifyContent: "space-between",
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  headerPlanMenu: {
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5C8",
    borderRadius: 8,
    borderWidth: 1,
    minWidth: 210,
    overflow: "hidden",
    position: "absolute",
    right: 0,
    top: 38,
    zIndex: 100,
  },
  planItemRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  commentaryIndicator: {
    color: "#7B847E",
    fontSize: 9,
    fontWeight: "800",
  },
  commentaryIndicatorReady: {
    color: "#4F7A11",
    fontSize: 13,
  },
  planDropdownChevron: {
    color: "#657264",
    fontSize: 9,
    marginLeft: 12,
  },
  planDropdownItem: {
    borderBottomColor: "#E8ECE5",
    borderBottomWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  planOptionSelected: {
    backgroundColor: "#EEF6D8",
    borderColor: "#A9D22D",
  },
  planOptionLabel: {
    color: "#203028",
    fontSize: 11,
    fontWeight: "800",
  },
  planSummary: {
    backgroundColor: "#F4F7EF",
    borderColor: "#DDE5D3",
    borderRadius: 10,
    borderWidth: 1,
    gap: 7,
    marginBottom: 8,
    padding: 8,
    position: "relative",
    zIndex: 1,
  },
  planSummaryHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  planSummaryEyebrow: {
    color: "#657264",
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1.1,
  },
  planSummaryScore: {
    color: "#657264",
    fontSize: 9,
    fontWeight: "700",
  },
  phaseStrip: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  phaseCard: {
    backgroundColor: "#FFFFFF",
    borderColor: "#DCE1D9",
    borderRadius: 7,
    borderWidth: 1,
    minWidth: 118,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  phaseCardActive: {
    backgroundColor: "#183E2B",
    borderColor: "#183E2B",
  },
  phaseCardIndex: {
    color: "#7A837C",
    fontSize: 8,
    fontWeight: "700",
  },
  phaseCardTitle: {
    color: "#203028",
    fontSize: 10,
    fontWeight: "800",
    marginTop: 2,
  },
  phaseCardDetail: {
    color: "#69736C",
    fontSize: 9,
    marginTop: 1,
  },
  phaseCardTextActive: {
    color: "#FFFFFF",
  },
  phaseCardDetailActive: {
    color: "#D9E8DE",
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
  selectedPlayerEditor: {
    alignItems: "center",
    backgroundColor: "#F5F7F2",
    borderColor: "#DCE3D7",
    borderRadius: 10,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    marginBottom: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  selectedPlayerEditorHeading: {
    minWidth: 100,
  },
  selectedPlayerEditorTitle: {
    color: "#18251F",
    fontSize: 12,
    fontWeight: "800",
  },
  selectedPlayerEditorMeta: {
    color: "#657264",
    fontSize: 10,
    marginTop: 2,
  },
  playerNameInput: {
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5C8",
    borderRadius: 8,
    borderWidth: 1,
    color: "#18251F",
    flexGrow: 1,
    fontSize: 12,
    maxWidth: 260,
    minWidth: 150,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  selectedPlayerEditorHint: {
    color: "#778079",
    flexShrink: 1,
    fontSize: 10,
  },
  fieldFrame: {
    backgroundColor: "#143B29",
    borderRadius: 14,
    flex: 1,
    minHeight: 410,
    padding: 4,
    position: "relative",
    zIndex: 0,
  },
  fieldFrameWide: {
    minHeight: 0,
  },
});
