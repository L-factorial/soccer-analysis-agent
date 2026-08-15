import { Position } from "./position";

export type PlayerSpeedCategory = "BASELINE" | "FAST" | "SUPER_FAST";

export type Player = {
  id: string;
  name: string;
  number: number;
  teamId: string;
  position: Position;
  orientation: number;
  speedCategory: PlayerSpeedCategory;
  // Velocity in centimeters per second while animation playback is active.
  velocity?: Position;
};
