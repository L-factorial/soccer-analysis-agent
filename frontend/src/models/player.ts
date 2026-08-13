import { Position } from "./position";

export type Player = {
  id: string;
  name: string;
  number: number;
  teamId: string;
  position: Position;
  orientation: number;
  // Velocity in centimeters per second while animation playback is active.
  velocity?: Position;
};
