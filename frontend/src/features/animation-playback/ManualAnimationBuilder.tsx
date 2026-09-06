import { colors } from "../../theme/colors";
import { useEffect, useMemo, useState } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  AnimationEvent,
  AnimationEventType,
  AnimationResponse,
  FieldConfiguration,
  Position,
} from "../../models";
import { TimelineRangeSlider } from "./TimelineRangeSlider";

type ManualAnimationEventType = Exclude<AnimationEventType, "SHOT" | "TURN">;

const EVENT_TYPES: ManualAnimationEventType[] = [
  "MOVE",
  "RUN",
  "MOVE_WITH_BALL",
  "PASS",
  "PASS_TO_SPACE",
  "RECEIVE",
];

type DestinationType = "player" | "openSpace";

type ManualAnimationBuilderProps = {
  configuration: FieldConfiguration;
  onChange: (response: AnimationResponse) => void;
  response: AnimationResponse;
};

type OptionPickerProps = {
  label: string;
  onChange: (value: string) => void;
  options: { label: string; value: string }[];
  value: string;
};

function OptionPicker({ label, onChange, options, value }: OptionPickerProps) {
  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.inputLabel}>{label}</Text>
      {options.length === 0 ? (
        <Text style={styles.emptyText}>No options available in the layout.</Text>
      ) : (
        <View style={styles.optionRow}>
          {options.map((option) => (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ selected: option.value === value }}
              key={option.value}
              onPress={() => onChange(option.value)}
              style={[
                styles.option,
                option.value === value && styles.optionSelected,
              ]}
            >
              <Text
                style={[
                  styles.optionText,
                  option.value === value && styles.optionTextSelected,
                ]}
              >
                {option.label}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

function openSpaceTarget(
  configuration: FieldConfiguration,
  openSpaceId: string,
): Position | undefined {
  const openSpace = configuration.openSpaces.find(({ id }) => id === openSpaceId);
  if (!openSpace) {
    return undefined;
  }

  if (openSpace.type === "circular") {
    return { ...openSpace.center };
  }

  return {
    x: (openSpace.bottomLeft.x + openSpace.topRight.x) / 2,
    y: (openSpace.bottomLeft.y + openSpace.topRight.y) / 2,
  };
}

function eventSummary(event: AnimationEvent): string {
  switch (event.type) {
    case "MOVE":
    case "RUN":
    case "MOVE_WITH_BALL":
      return `${event.type} · ${event.playerId} → (${Math.round(event.target.x)}, ${Math.round(event.target.y)})`;
    case "PASS":
      return `PASS · ${event.playerId} → ${event.targetPlayerId}`;
    case "PASS_TO_SPACE":
      return `PASS TO SPACE · ${event.playerId} → ${event.intendedReceiverId} via ${event.spaceId}`;
    case "SHOT":
      return `SHOT · ${event.playerId} → ${event.goalId}`;
    case "TURN":
      return `TURN · ${event.playerId} → ${Math.round(event.targetOrientation)}°`;
    case "RECEIVE":
      return `RECEIVE · ${event.playerId}`;
  }
}

function nextActionId(events: AnimationEvent[]): string {
  const usedNumbers = events
    .map(({ id }) => Number.parseInt(id.replace(/^action/, ""), 10))
    .filter(Number.isFinite);
  return `action${Math.max(0, ...usedNumbers) + 1}`;
}

export function ManualAnimationBuilder({
  configuration,
  onChange,
  response,
}: ManualAnimationBuilderProps) {
  const [eventType, setEventType] = useState<ManualAnimationEventType>("MOVE");
  const [playerId, setPlayerId] = useState("");
  const [receiverId, setReceiverId] = useState("");
  const [destinationType, setDestinationType] =
    useState<DestinationType>("openSpace");
  const [destinationId, setDestinationId] = useState("");
  const [totalDuration, setTotalDuration] = useState(String(response.duration));
  const [startTime, setStartTime] = useState("0");
  const [eventDuration, setEventDuration] = useState("1");
  const [error, setError] = useState<string | null>(null);

  const playerOptions = useMemo(
    () =>
      configuration.players.map((player) => ({
        label: player.id,
        value: player.id,
      })),
    [configuration.players],
  );
  const openSpaceOptions = useMemo(
    () =>
      configuration.openSpaces.map((space) => ({
        label: space.name,
        value: space.id,
      })),
    [configuration.openSpaces],
  );

  useEffect(() => {
    if (!configuration.players.some(({ id }) => id === playerId)) {
      setPlayerId(configuration.players[0]?.id ?? "");
    }
    if (!configuration.players.some(({ id }) => id === receiverId)) {
      setReceiverId(configuration.players[1]?.id ?? configuration.players[0]?.id ?? "");
    }
    const availableDestinations =
      destinationType === "player" ? configuration.players : configuration.openSpaces;
    if (!availableDestinations.some(({ id }) => id === destinationId)) {
      setDestinationId(availableDestinations[0]?.id ?? "");
    }
  }, [configuration, destinationId, destinationType, playerId, receiverId]);

  function commitDuration() {
    const duration = Number(totalDuration);
    if (!Number.isFinite(duration) || duration <= 0) {
      setTotalDuration(String(response.duration));
      setError("Total duration must be greater than zero.");
      return;
    }
    setError(null);
    updateTotalDuration(duration);
  }

  function updateTotalDuration(duration: number) {
    onChange({
      ...response,
      duration,
      events: response.events.map((event) => {
        const startTime = Math.min(
          Math.round(event.startTime),
          Math.max(0, Math.floor(duration) - 1),
        );
        const endTime = Math.min(
          Math.floor(duration),
          Math.max(
            startTime + 1,
            Math.round(event.startTime + (event.duration ?? 1)),
          ),
        );
        return { ...event, startTime, duration: endTime - startTime };
      }),
    });
  }

  function changeTotalDuration(value: string) {
    setTotalDuration(value);
    const duration = Number(value);
    if (Number.isFinite(duration) && duration > 0) {
      setError(null);
      updateTotalDuration(duration);
    }
  }

  function resolveDestination(): Position | undefined {
    if (destinationType === "player") {
      const player = configuration.players.find(({ id }) => id === destinationId);
      return player ? { ...player.position } : undefined;
    }
    return openSpaceTarget(configuration, destinationId);
  }

  function addEvent() {
    const parsedStartTime = Number(startTime);
    const parsedDuration = Number(eventDuration);

    if (!playerId) {
      setError("Add and select a player first.");
      return;
    }
    if (!Number.isFinite(parsedStartTime) || parsedStartTime < 0) {
      setError("Start time must be zero or greater.");
      return;
    }
    if (parsedStartTime > response.duration) {
      setError("Start time must be within the total duration.");
      return;
    }
    if (eventType !== "RECEIVE" && (!Number.isFinite(parsedDuration) || parsedDuration <= 0)) {
      setError("Event duration must be greater than zero.");
      return;
    }
    if (
      eventType !== "RECEIVE" &&
      parsedStartTime + parsedDuration > response.duration
    ) {
      setError("The event must finish within the total duration.");
      return;
    }

    let event: AnimationEvent;
    const id = nextActionId(response.events);
    if (eventType === "PASS") {
      if (!receiverId || receiverId === playerId) {
        setError("Choose a different receiving player.");
        return;
      }
      event = {
        id,
        type: "PASS",
        playerId,
        targetPlayerId: receiverId,
        startTime: parsedStartTime,
        duration: parsedDuration,
      };
    } else if (eventType === "PASS_TO_SPACE") {
      const target = openSpaceTarget(configuration, destinationId);
      if (!receiverId || !target || !destinationId) {
        setError("Choose a receiver and an open space.");
        return;
      }
      event = {
        id,
        type: "PASS_TO_SPACE",
        playerId,
        intendedReceiverId: receiverId,
        spaceId: destinationId,
        startTime: parsedStartTime,
        duration: parsedDuration,
        target,
      };
    } else if (eventType === "RECEIVE") {
      event = {
        id,
        type: "RECEIVE",
        playerId,
        startTime: parsedStartTime,
        duration: parsedDuration,
      };
    } else {
      const target = resolveDestination();
      if (!target) {
        setError("Choose a valid destination.");
        return;
      }
      event = {
        id,
        type: eventType,
        playerId,
        startTime: parsedStartTime,
        duration: parsedDuration,
        target,
      };
    }

    setError(null);
    onChange({
      ...response,
      events: [...response.events, event].sort(
        (left, right) => left.startTime - right.startTime,
      ),
    });
  }

  function deleteEvent(index: number) {
    onChange({
      ...response,
      events: response.events.filter((_, eventIndex) => eventIndex !== index),
    });
  }

  function updateEventRange(eventId: string, start: number, end: number) {
    onChange({
      ...response,
      events: response.events.map((event) =>
        event.id === eventId
          ? { ...event, startTime: start, duration: end - start }
          : event,
      ),
    });
  }

  const isMovementEvent =
    eventType === "MOVE" ||
    eventType === "RUN" ||
    eventType === "MOVE_WITH_BALL";

  return (
    <View style={styles.container}>
      <View style={styles.fieldGroup}>
        <Text style={styles.inputLabel}>Total duration (seconds)</Text>
        <TextInput
          inputMode="decimal"
          onChangeText={changeTotalDuration}
          onEndEditing={commitDuration}
          style={styles.input}
          value={totalDuration}
        />
      </View>

      <OptionPicker
        label="Event type"
        onChange={(value) => {
          setEventType(value as ManualAnimationEventType);
          if (value === "PASS_TO_SPACE") {
            setDestinationType("openSpace");
          }
          setError(null);
        }}
        options={EVENT_TYPES.map((type) => ({
          label: type.replaceAll("_", " "),
          value: type,
        }))}
        value={eventType}
      />

      <View style={styles.timeRow}>
        <View style={styles.timeField}>
          <Text style={styles.inputLabel}>Start (seconds)</Text>
          <TextInput
            inputMode="decimal"
            onChangeText={setStartTime}
            style={styles.input}
            value={startTime}
          />
        </View>
        {eventType !== "RECEIVE" && (
          <View style={styles.timeField}>
            <Text style={styles.inputLabel}>Duration (seconds)</Text>
            <TextInput
              inputMode="decimal"
              onChangeText={setEventDuration}
              style={styles.input}
              value={eventDuration}
            />
          </View>
        )}
      </View>

      <OptionPicker
        label={
          eventType === "RECEIVE"
            ? "Receiving player"
            : eventType === "PASS" || eventType === "PASS_TO_SPACE"
              ? "Passing player"
              : "Player"
        }
        onChange={setPlayerId}
        options={playerOptions}
        value={playerId}
      />

      {(eventType === "PASS" || eventType === "PASS_TO_SPACE") && (
        <OptionPicker
          label="Receiving player"
          onChange={setReceiverId}
          options={playerOptions}
          value={receiverId}
        />
      )}

      {isMovementEvent && (
        <>
          <OptionPicker
            label="Destination type"
            onChange={(value) => setDestinationType(value as DestinationType)}
            options={[
              { label: "Open space", value: "openSpace" },
              { label: "Player", value: "player" },
            ]}
            value={destinationType}
          />
          <OptionPicker
            label="Destination"
            onChange={setDestinationId}
            options={
              destinationType === "player" ? playerOptions : openSpaceOptions
            }
            value={destinationId}
          />
        </>
      )}

      {eventType === "PASS_TO_SPACE" && (
        <OptionPicker
          label="Open space"
          onChange={setDestinationId}
          options={openSpaceOptions}
          value={destinationId}
        />
      )}

      {error && <Text style={styles.error}>{error}</Text>}
      <Pressable accessibilityRole="button" onPress={addEvent} style={styles.addButton}>
        <Text style={styles.addButtonText}>Add event</Text>
      </Pressable>

      <View style={styles.sequence}>
        <Text style={styles.sequenceTitle}>Sequence ({response.events.length})</Text>
        {response.events.length === 0 ? (
          <Text style={styles.emptyText}>No events yet.</Text>
        ) : (
          response.events.map((event, index) => (
            <View key={event.id} style={styles.eventRow}>
              <View style={styles.eventDescription}>
                <Text style={styles.eventTime}>
                  {event.id} · {Math.round(event.startTime)}–
                  {Math.round(event.startTime + (event.duration ?? 0))}s
                </Text>
                <Text style={styles.eventText}>{eventSummary(event)}</Text>
                <TimelineRangeSlider
                  end={event.startTime + (event.duration ?? 1)}
                  maximum={response.duration}
                  onChange={(start, end) => updateEventRange(event.id, start, end)}
                  start={event.startTime}
                />
              </View>
              <Pressable
                accessibilityLabel={`Delete ${event.type} event`}
                accessibilityRole="button"
                onPress={() => deleteEvent(index)}
                style={styles.deleteButton}
              >
                <Text style={styles.deleteText}>×</Text>
              </Pressable>
            </View>
          ))
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 14, paddingTop: 8 },
  fieldGroup: { gap: 6 },
  inputLabel: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    color: colors.ink,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  optionRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  option: {
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 6,
  },
  optionSelected: { backgroundColor: colors.ink, borderColor: colors.ink },
  optionText: { color: colors.muted, fontSize: 10, fontWeight: "700" },
  optionTextSelected: { color: colors.onPrimary },
  emptyText: { color: colors.muted, fontSize: 11 },
  timeRow: { flexDirection: "row", gap: 8 },
  timeField: { flex: 1, gap: 6 },
  error: { color: colors.danger, fontSize: 11 },
  addButton: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: 9,
    paddingVertical: 10,
  },
  addButtonText: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  sequence: { borderTopColor: colors.border, borderTopWidth: 1, gap: 8, paddingTop: 12 },
  sequenceTitle: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  eventRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 8,
    flexDirection: "row",
    gap: 8,
    padding: 8,
  },
  eventDescription: { flex: 1, gap: 2 },
  eventTime: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  eventText: { color: colors.ink, fontSize: 10, fontWeight: "600" },
  deleteButton: { alignItems: "center", height: 24, justifyContent: "center", width: 24 },
  deleteText: { color: colors.danger, fontSize: 20, lineHeight: 20 },
});
