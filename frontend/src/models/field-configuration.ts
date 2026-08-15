import { Ball } from "./ball";
import { FIELD_LENGTH_CM, FIELD_WIDTH_CM, GOAL_LENGTH_CM, GOAL_WIDTH_CM } from "./field-coordinate";
import { Goal } from "./goal";
import { OpenSpace } from "./open-space";
import { Player } from "./player";
import { Team } from "./team";

export const FIELD_FORMATS = ["5v5", "7v7", "9v9", "11v11"] as const;

export type FieldFormat = (typeof FIELD_FORMATS)[number];

export type FieldConfiguration = {
  label: string;
  fieldType: FieldFormat;
  players: Player[];
  teams: [Team, Team];
  ball: Ball;
  goals: [Goal, Goal];
  openSpaces: OpenSpace[];
};

const FORMATIONS: Record<FieldFormat, ReadonlyArray<readonly [number, number]>> = {
  "5v5": [
    [0.1, 0.5], [0.27, 0.25], [0.27, 0.75], [0.43, 0.35], [0.43, 0.65],
  ],
  "7v7": [
    [0.08, 0.5], [0.23, 0.25], [0.23, 0.75], [0.36, 0.2],
    [0.36, 0.5], [0.36, 0.8], [0.46, 0.5],
  ],
  "9v9": [
    [0.07, 0.5], [0.2, 0.2], [0.2, 0.5], [0.2, 0.8],
    [0.34, 0.2], [0.34, 0.5], [0.34, 0.8], [0.46, 0.35], [0.46, 0.65],
  ],
  "11v11": [
    [0.06, 0.5], [0.18, 0.12], [0.18, 0.37], [0.18, 0.63], [0.18, 0.88],
    [0.33, 0.12], [0.33, 0.37], [0.33, 0.63], [0.33, 0.88],
    [0.46, 0.35], [0.46, 0.65],
  ],
};

function createDefaultPlayers(fieldType: FieldFormat): Player[] {
  return (["team1", "team2"] as const).flatMap((teamId) =>
    FORMATIONS[fieldType].map(([xFraction, yFraction], index) => ({
      id: `${teamId}-${index + 1}`,
      name: `${teamId}-${index + 1}`,
      number: index + 1,
      teamId,
      position: {
        x: (teamId === "team1" ? xFraction : 1 - xFraction) * FIELD_LENGTH_CM,
        y: yFraction * FIELD_WIDTH_CM,
      },
      orientation: teamId === "team1" ? 0 : 180,
      speedCategory: "BASELINE",
    })),
  );
}

function createGoals(): [Goal, Goal] {
  const goalBottom = (FIELD_WIDTH_CM - GOAL_WIDTH_CM) / 2;
  const goalTop = goalBottom + GOAL_WIDTH_CM;

  return [
    {
      id: "goal-left",
      name: "Goal1",
      side: "left",
      coordinates: [
        { x: 0, y: goalBottom },
        { x: GOAL_LENGTH_CM, y: goalBottom },
        { x: GOAL_LENGTH_CM, y: goalTop },
        { x: 0, y: goalTop },
      ],
    },
    {
      id: "goal-right",
      name: "Goal2",
      side: "right",
      coordinates: [
        { x: FIELD_LENGTH_CM - GOAL_LENGTH_CM, y: goalBottom },
        { x: FIELD_LENGTH_CM, y: goalBottom },
        { x: FIELD_LENGTH_CM, y: goalTop },
        { x: FIELD_LENGTH_CM - GOAL_LENGTH_CM, y: goalTop },
      ],
    },
  ];
}

export function createFieldConfiguration(
  fieldType: FieldFormat,
): FieldConfiguration {
  const players = createDefaultPlayers(fieldType);
  const initialBallCarrier = players.findLast(
    ({ teamId }) => teamId === "team1",
  );

  return {
    label: fieldType,
    fieldType,
    players,
    teams: [
      {
        id: "team1",
        name: "team1",
        color: "#D8FF3E",
        defendedGoalId: "goal-left",
      },
      {
        id: "team2",
        name: "team2",
        color: "#FF725E",
        defendedGoalId: "goal-right",
      },
    ],
    goals: createGoals(),
    openSpaces: [],
    ball: {
      position: initialBallCarrier
        ? { ...initialBallCarrier.position }
        : { x: 6_000, y: 4_500 },
      direction: 0,
      speed: 0,
    },
  };
}

export function cloneFieldConfiguration(
  configuration: FieldConfiguration,
): FieldConfiguration {
  return {
    ...configuration,
    ball: {
      ...configuration.ball,
      position: { ...configuration.ball.position },
    },
    players: configuration.players.map((player) => ({
      ...player,
      position: { ...player.position },
    })),
    teams: configuration.teams.map((team) => ({ ...team })) as [Team, Team],
    goals: configuration.goals.map((goal) => ({
      ...goal,
      coordinates: goal.coordinates.map((position) => ({ ...position })) as Goal["coordinates"],
    })) as [Goal, Goal],
    openSpaces: configuration.openSpaces.map((openSpace) =>
      openSpace.type === "circular"
        ? {
            ...openSpace,
            center: { ...openSpace.center },
          }
        : {
            ...openSpace,
            bottomLeft: { ...openSpace.bottomLeft },
            topRight: { ...openSpace.topRight },
          },
    ),
  };
}
