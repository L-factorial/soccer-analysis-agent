import { randomUUID } from "expo-crypto";
import { AnalysisOverlay } from "../src/features/field-editor/AnalysisOverlay";
import { colors } from "../src/theme/colors";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  GestureResponderEvent,
  Image,
  Modal,
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
import { AnalysisMetricsDisplay } from "../src/features/field-editor/AnalysisMetricsDisplay";
import { CommentaryPanel } from "../src/features/commentary";
import {
  analyzeFieldConfiguration,
  cancelAnalysis,
  generateCommentary,
} from "../src/api/analyze-field";
import {
  animationFrameToSeconds,
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
  PlayerSpeedCategory,
  screenDeltaToFieldDelta,
  screenToFieldPosition,
} from "../src/models";

type AnalysisStatus = "idle" | "loading" | "success" | "error";
type CommentaryStatus = "idle" | "loading" | "ready" | "unavailable";

const PLAYER_SPEED_OPTIONS: { value: PlayerSpeedCategory; label: string }[] = [
  { value: "BASELINE", label: "Normal" },
  { value: "FAST", label: "Fast" },
  { value: "SUPER_FAST", label: "Super fast" },
];

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
  const [setupHintDismissed, setSetupHintDismissed] = useState(false);
  const [animationResponse, setAnimationResponse] = useState<AnimationResponse>(
    { duration: 0, events: [] },
  );
  const [primaryPlanResponse, setPrimaryPlanResponse] =
    useState<AnimationResponse | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState("requested");
  const [isPlanDropdownOpen, setIsPlanDropdownOpen] = useState(false);
  const [isPlanSummaryExpanded, setIsPlanSummaryExpanded] = useState(false);
  const [isFormatDropdownOpen, setIsFormatDropdownOpen] = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus>("idle");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [commentaryEnabled, setCommentaryEnabled] = useState(false);
  const commentaryEnabledRef = useRef(false);
  const commentaryAbortController = useRef<AbortController | null>(null);
  const [commentaryStatuses, setCommentaryStatuses] = useState<
    Record<string, CommentaryStatus>
  >({});
  const [tacticalInstruction, setTacticalInstruction] = useState("");
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);
  const [orientationPlayerId, setOrientationPlayerId] = useState<string | null>(
    null,
  );
  const [openSpaceTool, setOpenSpaceTool] = useState<OpenSpaceType | null>(null);
  const [selectedOpenSpaceId, setSelectedOpenSpaceId] = useState<string | null>(
    null,
  );
  const fieldRef = useRef<View>(null);
  const activeAnalysisId = useRef<string | null>(null);
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
  const selectedFieldPlayerTeam = selectedFieldPlayer
    ? fieldConfiguration.teams.find(({ id }) => id === selectedFieldPlayer.teamId)
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
    stopActiveAnalysis();
    commentaryAbortController.current?.abort();
    setAnalysisStatus("idle");
    setAnalysisError(null);
    setCommentaryStatuses({});
    setAnimationResponse({ duration: 0, events: [] });
    setPrimaryPlanResponse(null);
    selectedPlanIdRef.current = "requested";
    setSelectedPlanId("requested");
    setIsPlanDropdownOpen(false);
    setIsPlanSummaryExpanded(false);
  }, [fieldConfiguration]);

  useEffect(
    () => () => {
      stopActiveAnalysis();
      commentaryAbortController.current?.abort();
    },
    [],
  );

  function startCommentary(response: AnimationResponse) {
    commentaryAbortController.current?.abort();
    const controller = new AbortController();
    commentaryAbortController.current = controller;
    const commentaryPlans = [
      { id: "requested", response },
      ...(response.alternativePlans ?? []).map((plan) => ({
        id: plan.id,
        response: alternativeResponse(plan),
      })),
    ];
    setCommentaryStatuses(
      Object.fromEntries(commentaryPlans.map(({ id, response: plan }) =>
        [id, plan.commentary ? "ready" : "loading"],
      )),
    );
    // Each selectable plan owns an independent asynchronous commentary
    // request. One failure never blocks simulation or the other plans.
    for (const commentaryPlan of commentaryPlans) {
      if (commentaryPlan.response.commentary) continue;
      void generateCommentary(
        fieldConfiguration,
        commentaryPlan.response,
        true,
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

  function toggleCommentary() {
    const enabled = !commentaryEnabledRef.current;
    commentaryEnabledRef.current = enabled;
    setCommentaryEnabled(enabled);
    if (!enabled) {
      commentaryAbortController.current?.abort();
      setCommentaryStatuses({});
    } else if (primaryPlanResponse && analysisStatus === "success") {
      startCommentary(primaryPlanResponse);
    }
  }

  function stopActiveAnalysis() {
    const id = activeAnalysisId.current;
    activeAnalysisId.current = null;
    analysisAbortController.current?.abort();
    if (id) {
      void cancelAnalysis(id).catch(() => {
        setAnalysisError("The field was reset, but server cancellation could not be confirmed. The analysis may still be running.");
      });
    }
  }

  function cancelCurrentAnalysis() {
    stopActiveAnalysis();
    commentaryAbortController.current?.abort();
    reset();
    setAnalysisStatus("idle");
    setAnalysisError(null);
    setCommentaryStatuses({});
    setAnimationResponse({ duration: 0, events: [] });
    setPrimaryPlanResponse(null);
    selectedPlanIdRef.current = "requested";
    setSelectedPlanId("requested");
    setIsPlanDropdownOpen(false);
    setIsPlanSummaryExpanded(false);
    setSelectedPlayerId(null);
    setOrientationPlayerId(null);
    setOpenSpaceTool(null);
  }

  async function analyzeCurrentField() {
    stopActiveAnalysis();
    const analysisId = randomUUID();
    activeAnalysisId.current = analysisId;
    commentaryAbortController.current?.abort();
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
        analysisId,
        tacticalInstruction,
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setAnimationResponse(response);
        setPrimaryPlanResponse(response);
        selectedPlanIdRef.current = "requested";
        setSelectedPlanId("requested");
        setIsPlanDropdownOpen(false);
        setIsPlanSummaryExpanded(false);
        setAnalysisStatus("success");
        if (commentaryEnabledRef.current) {
          startCommentary(response);
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setAnalysisStatus("error");
        setAnalysisError(
          error instanceof Error ? error.message : "Unable to analyze the field.",
        );
      }
    } finally {
      if (activeAnalysisId.current === analysisId) activeAnalysisId.current = null;
    }
  }

  function selectPlan(id: string, response: AnimationResponse) {
    pause();
    selectedPlanIdRef.current = id;
    setAnimationResponse(response);
    setSelectedPlanId(id);
    setIsPlanDropdownOpen(false);
    setIsPlanSummaryExpanded(false);
  }

  function changeFieldFormat(fieldType: FieldFormat) {
    setSetupHintDismissed(false);
    setFieldConfiguration(createFieldConfiguration(fieldType));
    setAnimationResponse((current) => ({ ...current, events: [] }));
    setSelectedPlayerId(null);
    setOrientationPlayerId(null);
    setOpenSpaceTool(null);
    setSelectedOpenSpaceId(null);
    setSelectedTeamId("team1");
    openSpaceSequence.current = 1;
  }

  function startNewField() {
    cancelCurrentAnalysis();
    changeFieldFormat("5v5");
    setTacticalInstruction("");
    setIsFormatDropdownOpen(false);
    commentaryEnabledRef.current = false;
    setCommentaryEnabled(false);
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

  const setPlayerSpeed = useCallback((id: string, speedCategory: PlayerSpeedCategory) => {
    setFieldConfiguration((current) => ({
      ...current,
      players: current.players.map((player) =>
        player.id === id ? { ...player, speedCategory } : player,
      ),
    }));
  }, []);


  function giveBallToPlayer(id: string) {
    if (isPlaybackReady || analysisStatus === "loading") return;
    setFieldConfiguration((current) => {
      const player = current.players.find((candidate) => candidate.id === id);
      if (!player) return current;
      return {
        ...current,
        ball: {
          ...current.ball,
          position: { ...player.position },
          direction: player.orientation,
          speed: 0,
        },
      };
    });
    setOrientationPlayerId(null);
  }

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
    setSetupHintDismissed(true);
    setSelectedPlayerId(id);
    setOrientationPlayerId(null);
    setOpenSpaceTool(null);
    setSelectedOpenSpaceId(null);
  }, []);

  const selectFieldPlayer = useCallback((id: string) => {
    setSetupHintDismissed(true);
    setOrientationPlayerId(id);
    setSelectedPlayerId(null);
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
        <View style={[styles.workspace, isWide && styles.workspaceWide]}>
          <View style={styles.workspaceHeader}>
            <View style={[styles.workspaceIdentity, !isWide && styles.workspaceIdentityCompact]}>
              <View style={styles.workspaceBrand}>
                <Image
                  source={require("../assets/logo.png")}
                  style={styles.workspaceLogo}
                  accessibilityLabel="L factorial soccer logo"
                />
                <Text style={styles.workspaceTitle}>Field workspace</Text>
              </View>
              <View style={styles.formatSelector}>
                <Pressable
                  accessibilityLabel="Select field size"
                  accessibilityRole="button"
                  accessibilityState={{ expanded: isFormatDropdownOpen }}
                  onPress={() => setIsFormatDropdownOpen((open) => !open)}
                  style={styles.formatSelectorButton}
                >
                  <Text style={styles.formatSelectorButtonText}>
                    {fieldConfiguration.fieldType}
                  </Text>
                  <Text style={styles.formatSelectorChevron}>
                    {isFormatDropdownOpen ? "▲" : "▼"}
                  </Text>
                </Pressable>
                {isFormatDropdownOpen && (
                  <View style={styles.formatSelectorMenu}>
                    {FIELD_FORMATS.map((format) => (
                      <Pressable
                        accessibilityRole="button"
                        accessibilityState={{
                          selected: fieldConfiguration.fieldType === format,
                        }}
                        key={format}
                        onPress={() => {
                          changeFieldFormat(format);
                          setIsFormatDropdownOpen(false);
                        }}
                        style={[
                          styles.formatSelectorOption,
                          fieldConfiguration.fieldType === format &&
                            styles.formatSelectorOptionSelected,
                        ]}
                      >
                        <Text style={styles.formatSelectorOptionText}>{format}</Text>
                      </Pressable>
                    ))}
                  </View>
                )}
              </View>
              <AnalysisMetricsDisplay refreshKey={analysisStatus} compact={!isWide} />
            </View>
            <View
              style={[
                styles.playbackControls,
                !isWide && styles.playbackControlsNarrow,
              ]}
            >
              <TextInput
                accessibilityLabel="Tactical instruction"
                editable={analysisStatus !== "loading"}
                maxLength={500}
                onChangeText={setTacticalInstruction}
                placeholder="LLM prompts for goal-scoring actions are currently disabled and under construction."
                placeholderTextColor={colors.muted}
                style={[
                  styles.tacticalInstructionInput,
                  !isWide && styles.tacticalInstructionInputNarrow,
                ]}
                value={tacticalInstruction}
              />
              {(analysisStatus !== "success" || commentaryEnabled) && <Pressable
                accessibilityRole="switch"
                accessibilityLabel="Generate commentary"
                accessibilityState={{ checked: commentaryEnabled }}
                onPress={toggleCommentary}
                style={[
                  styles.commentaryToggle,
                  commentaryEnabled && styles.commentaryToggleEnabled,
                ]}
              >
                <Text style={styles.commentaryToggleText}>
                  Commentary: {commentaryEnabled ? "On" : "Off"}
                </Text>
              </Pressable>}
              {!isPlaybackReady ? (
                <Pressable
                  accessibilityRole="button"
                  onPress={analysisStatus === "loading" ? cancelCurrentAnalysis : analyzeCurrentField}
                  style={[
                    styles.analyzeButton,
                    analysisStatus === "loading" && styles.cancelAnalysisButton,
                  ]}
                >
                  <Text style={styles.analyzeButtonText}>
                    {analysisStatus === "loading" ? "Cancel analysis" : "Analyze"}
                  </Text>
                </Pressable>
              ) : (
                <>
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
                <Text style={styles.resetButtonText}>Replay</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityHint="Clear the simulation and restore the default 5v5 field"
                onPress={startNewField}
                style={styles.resetButton}
              >
                <Text style={styles.resetButtonText}>New field</Text>
              </Pressable>
              {commentaryEnabled && <CommentaryPanel
                commentary={animationResponse.commentary}
                loading={commentaryStatuses[selectedPlanId] === "loading"}
                playbackSeconds={playbackSeconds}
                playbackStatus={session.status}
              />}
                </>
              )}
            </View>
          </View>

          {analysisError && (
            <Text accessibilityRole="alert" style={styles.analysisError}>
              {analysisError}
            </Text>
          )}

          {selectedPhases.length > 0 && (
            <View
              style={[
                styles.planSummary,
                !isPlanSummaryExpanded && styles.planSummaryCollapsed,
              ]}
            >
              <Pressable
                accessibilityLabel={`${isPlanSummaryExpanded ? "Collapse" : "Expand"} selected tactical plan`}
                accessibilityRole="button"
                accessibilityState={{ expanded: isPlanSummaryExpanded }}
                onPress={() => setIsPlanSummaryExpanded((expanded) => !expanded)}
                style={styles.planSummaryHeader}
              >
                <Text style={styles.planSummaryEyebrow}>SELECTED TACTICAL PLAN</Text>
                <View style={styles.planSummaryHeaderMeta}>
                  <Text style={styles.planSummaryScore}>
                    {animationResponse.diagnostics?.selectedSequenceScore?.toFixed(1)} pts
                  </Text>
                  <Text style={styles.planSummaryToggle}>
                    {isPlanSummaryExpanded ? "Collapse" : "Expand"}
                  </Text>
                </View>
              </Pressable>
              {isPlanSummaryExpanded && <View style={styles.phaseStrip}>
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
              </View>}
            </View>
          )}

          <Modal
            animationType="fade"
            onRequestClose={() => setOrientationPlayerId(null)}
            transparent
            visible={Boolean(selectedFieldPlayer)}
          >
            <View style={styles.playerEditorOverlay}>
              <Pressable
              accessibilityLabel="Close player editor"
              onPress={() => setOrientationPlayerId(null)}
              style={styles.playerEditorBackdrop}
              />
              <View style={styles.selectedPlayerEditor}>
                <View style={styles.playerEditorHeader}>
                  <View
                    style={[
                      styles.playerEditorAvatar,
                      { backgroundColor: selectedFieldPlayerTeam?.color ?? fieldConfiguration.teams[0].color },
                    ]}
                  >
                    <Text style={styles.playerEditorAvatarText}>
                      {selectedFieldPlayer?.number}
                    </Text>
                  </View>
                  <View style={styles.playerEditorHeading}>
                    <Text style={styles.selectedPlayerEditorTitle}>Edit player</Text>
                    <Text style={styles.playerEditorSubtitle}>
                      {selectedFieldPlayerTeam?.name ?? "Team"} · Player {selectedFieldPlayer?.number}
                    </Text>
                  </View>
                  <Pressable
                    accessibilityLabel="Close player editor"
                    accessibilityRole="button"
                    hitSlop={8}
                    onPress={() => setOrientationPlayerId(null)}
                    style={styles.playerEditorCloseButton}
                  >
                    <Text style={styles.playerEditorCloseText}>×</Text>
                  </Pressable>
                </View>
                <Text style={styles.playerEditorInputLabel}>Display name</Text>
                <TextInput
                  accessibilityLabel={`Player ${selectedFieldPlayer?.number} name`}
                  autoFocus
                  maxLength={40}
                  onChangeText={(profileName) =>
                    selectedFieldPlayer &&
                    setPlayerProfileName(selectedFieldPlayer.id, profileName)
                  }
                  placeholder="Enter profile name"
                  placeholderTextColor={colors.muted}
                  selectTextOnFocus
                  style={styles.playerNameInput}
                  value={selectedFieldPlayer?.profileName ?? ""}
                />
                <Text style={styles.playerEditorHelperText}>
                  This name appears beside the player on the field.
                </Text>
                <Text style={styles.playerEditorInputLabel}>Player speed</Text>
                <View style={styles.choiceRow}>
                  {PLAYER_SPEED_OPTIONS.map(({ value, label }) => (
                    <ChoiceButton
                      key={value}
                      label={label}
                      selected={selectedFieldPlayer?.speedCategory === value}
                      onPress={() => selectedFieldPlayer && setPlayerSpeed(selectedFieldPlayer.id, value)}
                    />
                  ))}
                </View>
                {!isPlaybackReady && analysisStatus !== "loading" && (
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => selectedFieldPlayer && giveBallToPlayer(selectedFieldPlayer.id)}
                    style={styles.playerEditorBallButton}
                  >
                    <Text style={styles.analyzeButtonText}>Give ball to this player</Text>
                  </Pressable>
                )}
                <Pressable
                  accessibilityRole="button"
                  onPress={() => setOrientationPlayerId(null)}
                  style={styles.playerEditorDoneButton}
                >
                  <Text style={styles.playerEditorDoneButtonText}>Save changes</Text>
                </Pressable>
              </View>
            </View>
          </Modal>

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
              onPlayerSelect={selectFieldPlayer}
              orientation={fieldOrientation}
              ref={fieldRef}
              selectedOpenSpaceId={selectedOpenSpaceId}
              selectedPlayerId={orientationPlayerId}
              separateBallDuringSetup={!isPlaybackReady && analysisStatus !== "loading"}
              showSetupHint={!setupHintDismissed && !isPlaybackReady && analysisStatus !== "loading" && !openSpaceTool && !orientationPlayerId}
            />
            {analysisStatus === "loading" && <AnalysisOverlay />}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.canvas,
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
    overflow: "hidden",
    padding: 8,
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
    backgroundColor: colors.accent,
    borderRadius: 5,
    height: 38,
    transform: [{ rotate: "8deg" }],
    width: 10,
  },
  eyebrow: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.5,
  },
  title: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "700",
  },
  configuration: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    padding: 11,
  },
  section: {
    gap: 9,
  },
  sectionNumber: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1,
  },
  sectionLabel: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "700",
  },
  sectionHelp: {
    color: colors.muted,
    fontSize: 12,
    marginTop: -7,
  },
  choiceRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  choiceButton: {
    backgroundColor: colors.inset,
    borderColor: "transparent",
    borderRadius: 9,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  choiceButtonSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  choiceButtonPressed: {
    opacity: 0.72,
  },
  choiceButtonText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
  },
  choiceButtonTextSelected: {
    color: colors.onPrimary,
  },
  divider: {
    backgroundColor: colors.divider,
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
    backgroundColor: colors.accent,
    borderColor: colors.accentBorder,
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
    borderColor: colors.ink,
    borderWidth: 3,
    opacity: 1,
    transform: [{ scale: 1.12 }],
  },
  playerTokenText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "800",
  },
  teamButton: {
    alignItems: "center",
    borderColor: colors.border,
    borderRadius: 9,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    padding: 7,
  },
  teamButtonSelected: {
    backgroundColor: colors.inset,
    borderColor: colors.primary,
  },
  teamSwatch: {
    borderColor: "#FFFFFF",
    borderRadius: 10,
    borderWidth: 2,
    height: 20,
    width: 20,
  },
  teamButtonText: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "700",
  },
  teamGoalText: {
    color: colors.muted,
    fontSize: 9,
  },
  workspace: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 20,
    borderWidth: 1,
    flex: 1,
    minHeight: 500,
    padding: 14,
    zIndex: 1,
  },
  workspaceWide: {
    minHeight: 0,
    padding: 6,
  },
  workspaceIdentity: {
    minWidth: 0,
    maxWidth: "100%",
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  workspaceIdentityCompact: { width: "100%", gap: 6 },
  formatSelector: {
    position: "relative",
    zIndex: 100,
  },
  formatSelectorButton: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 8,
    flexDirection: "row",
    gap: 8,
    minWidth: 72,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  formatSelectorButtonText: {
    color: colors.onPrimary,
    fontSize: 12,
    fontWeight: "800",
  },
  formatSelectorChevron: {
    color: colors.accent,
    fontSize: 8,
  },
  formatSelectorMenu: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    left: 0,
    minWidth: 90,
    overflow: "hidden",
    position: "absolute",
    top: 36,
    zIndex: 110,
  },
  formatSelectorOption: {
    borderBottomColor: colors.divider,
    borderBottomWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  formatSelectorOptionSelected: {
    backgroundColor: colors.accentSoft,
  },
  formatSelectorOptionText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "700",
  },
  workspaceHeader: {
    backgroundColor: colors.inset,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 14,
    padding: 10,
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    justifyContent: "space-between",
    marginBottom: 8,
    overflow: "visible",
    position: "relative",
    zIndex: 200,
  },
  workspaceTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "700",
  },
  workspaceBrand: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  workspaceLogo: {
    width: 40,
    height: 40,
  },
  playbackControls: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    zIndex: 30,
  },
  playbackControlsNarrow: {
    flexBasis: "100%",
    width: "100%",
  },
  tacticalInstructionInput: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 11,
    minWidth: 250,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  tacticalInstructionInputNarrow: {
    flex: 1,
    minWidth: 160,
  },
  commentaryToggle: {
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    backgroundColor: colors.inset,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  commentaryToggleEnabled: {
    backgroundColor: colors.accentSoft,
    borderColor: colors.accentBorder,
  },
  commentaryToggleText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "700",
  },
  analyzeButton: {
    backgroundColor: colors.accent,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  cancelAnalysisButton: {
    backgroundColor: "#FFE3CC",
  },
  analyzeButtonText: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "800",
  },
  controlButtonDisabled: {
    opacity: 0.4,
  },
  analysisError: {
    color: colors.danger,
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
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    justifyContent: "space-between",
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  headerPlanMenu: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
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
    color: colors.muted,
    fontSize: 9,
    fontWeight: "800",
  },
  commentaryIndicatorReady: {
    color: colors.success,
    fontSize: 13,
  },
  planDropdownChevron: {
    color: colors.muted,
    fontSize: 9,
    marginLeft: 12,
  },
  planDropdownItem: {
    borderBottomColor: colors.divider,
    borderBottomWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  planOptionSelected: {
    backgroundColor: colors.accentSoft,
    borderColor: colors.accent,
  },
  planOptionLabel: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "800",
  },
  planSummary: {
    backgroundColor: colors.accentSoft,
    borderColor: colors.accentBorder,
    borderRadius: 10,
    borderWidth: 1,
    gap: 7,
    marginBottom: 8,
    padding: 8,
    position: "relative",
    zIndex: 1,
  },
  planSummaryCollapsed: {
    gap: 0,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  planSummaryHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  planSummaryHeaderMeta: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
  },
  planSummaryEyebrow: {
    color: colors.muted,
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1.1,
  },
  planSummaryScore: {
    color: colors.muted,
    fontSize: 9,
    fontWeight: "700",
  },
  planSummaryToggle: {
    color: colors.muted,
    fontSize: 9,
    fontWeight: "800",
  },
  phaseStrip: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  phaseCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 7,
    borderWidth: 1,
    minWidth: 118,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  phaseCardActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  phaseCardIndex: {
    color: colors.muted,
    fontSize: 8,
    fontWeight: "700",
  },
  phaseCardTitle: {
    color: colors.ink,
    fontSize: 10,
    fontWeight: "800",
    marginTop: 2,
  },
  phaseCardDetail: {
    color: colors.muted,
    fontSize: 9,
    marginTop: 1,
  },
  phaseCardTextActive: {
    color: colors.onPrimary,
  },
  phaseCardDetailActive: {
    color: "#D9E8DE",
  },
  playbackTime: {
    color: colors.muted,
    fontSize: 11,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
  },
  playbackButton: {
    backgroundColor: colors.primary,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  playbackButtonText: {
    color: colors.onPrimary,
    fontSize: 11,
    fontWeight: "700",
  },
  resetButton: {
    backgroundColor: colors.inset,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  resetButtonText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },
  selectedPlayerEditor: {
    backgroundColor: colors.surface,
    borderColor: "rgba(24, 62, 43, 0.10)",
    borderRadius: 20,
    borderWidth: 1,
    elevation: 12,
    gap: 10,
    maxWidth: 400,
    padding: 22,
    shadowColor: "#07140D",
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.2,
    shadowRadius: 30,
    width: "92%",
  },
  playerEditorHeader: {
    alignItems: "center",
    flexDirection: "row",
    marginBottom: 8,
  },
  playerEditorAvatar: {
    alignItems: "center",
    borderColor: "rgba(24, 37, 31, 0.16)",
    borderRadius: 22,
    borderWidth: 1,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  playerEditorAvatarText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  playerEditorHeading: {
    flex: 1,
    marginLeft: 12,
  },
  selectedPlayerEditorTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  playerEditorSubtitle: {
    color: colors.muted,
    fontSize: 12,
    marginTop: 2,
  },
  playerEditorCloseButton: {
    alignItems: "center",
    backgroundColor: colors.inset,
    borderRadius: 16,
    height: 32,
    justifyContent: "center",
    width: 32,
  },
  playerEditorCloseText: {
    color: colors.muted,
    fontSize: 22,
    fontWeight: "400",
    lineHeight: 24,
  },
  playerEditorOverlay: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    padding: 20,
  },
  playerEditorBackdrop: {
    backgroundColor: "rgba(10, 24, 17, 0.48)",
    bottom: 0,
    left: 0,
    position: "absolute",
    right: 0,
    top: 0,
  },
  playerNameInput: {
    backgroundColor: colors.inset,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 15,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  playerEditorInputLabel: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "700",
    marginBottom: -3,
  },
  playerEditorHelperText: {
    color: colors.muted,
    fontSize: 11,
    marginBottom: 4,
  },
  playerEditorBallButton: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: 12,
    marginTop: 4,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  playerEditorDoneButton: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 12,
    marginTop: 4,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  playerEditorDoneButtonText: {
    color: colors.onPrimary,
    fontSize: 13,
    fontWeight: "800",
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
