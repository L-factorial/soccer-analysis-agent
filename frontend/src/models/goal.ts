import { Position } from "./position";

export type GoalSide = "left" | "right";

export type Goal = {
  id: string;
  name: string;
  side: GoalSide;
  // Clockwise corners in standard field coordinates.
  coordinates: [Position, Position, Position, Position];
};
