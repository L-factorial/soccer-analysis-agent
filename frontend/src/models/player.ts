import { Position } from "./position";

export type PlayerTeam = "attack" | "defense";

export type Player = {
  id: string;
  name: string;
  number: number;
  team: PlayerTeam;
  position: Position;
  orientation: number;
  // Velocity in centimeters per second while animation playback is active.
  velocity?: Position;
};
