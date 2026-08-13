import { Ball } from "./ball";
import { OpenSpace } from "./open-space";
import { Player } from "./player";

export const FIELD_FORMATS = ["5v5", "7v7", "9v9", "11v11"] as const;

export type FieldFormat = (typeof FIELD_FORMATS)[number];

export type FieldConfiguration = {
  label: string;
  fieldType: FieldFormat;
  players: Player[];
  ball: Ball;
  openSpaces: OpenSpace[];
};

export function createFieldConfiguration(
  fieldType: FieldFormat,
): FieldConfiguration {
  return {
    label: fieldType,
    fieldType,
    players: [],
    openSpaces: [],
    ball: {
      position: { x: 6_000, y: 4_500 },
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
