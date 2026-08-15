import { FieldConfiguration, FieldFormat } from "./field-configuration";
import {
  FIELD_LENGTH_CM,
  FIELD_WIDTH_CM,
  GOAL_LENGTH_CM,
  GOAL_WIDTH_CM,
} from "./field-coordinate";
import { Goal } from "./goal";
import { OpenSpace } from "./open-space";
import { Position } from "./position";
import { PlayerSpeedCategory } from "./player";
import { Team } from "./team";

export const FIELD_SUBMISSION_SCHEMA_VERSION = "1.0" as const;

export type SubmittedPlayer = {
  id: string;
  name: string;
  number: number;
  teamId: string;
  position: Position;
  orientation: number;
  velocity: Position;
  speedCategory: PlayerSpeedCategory;
};

export type FieldSubmission = {
  schemaVersion: typeof FIELD_SUBMISSION_SCHEMA_VERSION;
  tacticalInstruction?: string;
  fieldConfiguration: {
    label: string;
    fieldType: FieldFormat;
    dimensions: {
      length: number;
      width: number;
      unit: "cm";
    };
    goalDimensions: {
      length: number;
      width: number;
      unit: "cm";
    };
    teams: [Team, Team];
    goals: [Goal, Goal];
    players: SubmittedPlayer[];
    ball: {
      position: Position;
      direction: number;
      speed: number;
    };
    openSpaces: OpenSpace[];
  };
};

/** Builds the immutable JSON-compatible snapshot submitted to the backend. */
export function createFieldSubmission(
  configuration: FieldConfiguration,
  tacticalInstruction?: string,
): FieldSubmission {
  const normalizedInstruction = tacticalInstruction?.trim();
  return {
    schemaVersion: FIELD_SUBMISSION_SCHEMA_VERSION,
    ...(normalizedInstruction
      ? { tacticalInstruction: normalizedInstruction }
      : {}),
    fieldConfiguration: {
      label: configuration.label,
      fieldType: configuration.fieldType,
      dimensions: {
        length: FIELD_LENGTH_CM,
        width: FIELD_WIDTH_CM,
        unit: "cm",
      },
      goalDimensions: {
        length: GOAL_LENGTH_CM,
        width: GOAL_WIDTH_CM,
        unit: "cm",
      },
      teams: configuration.teams.map((team) => ({ ...team })) as [Team, Team],
      goals: configuration.goals.map((goal) => ({
        ...goal,
        coordinates: goal.coordinates.map((coordinate) => ({
          ...coordinate,
        })) as Goal["coordinates"],
      })) as [Goal, Goal],
      players: configuration.players.map((player) => ({
        id: player.id,
        name: player.name,
        number: player.number,
        teamId: player.teamId,
        position: { ...player.position },
        orientation: player.orientation,
        speedCategory: player.speedCategory,
        // The editor submits a static snapshot, not an in-progress animation.
        velocity: { x: 0, y: 0 },
      })),
      ball: {
        position: { ...configuration.ball.position },
        direction: configuration.ball.direction,
        speed: 0,
      },
      openSpaces: configuration.openSpaces.map((openSpace) =>
        openSpace.type === "circular"
          ? { ...openSpace, center: { ...openSpace.center } }
          : {
              ...openSpace,
              bottomLeft: { ...openSpace.bottomLeft },
              topRight: { ...openSpace.topRight },
            },
      ),
    },
  };
}
