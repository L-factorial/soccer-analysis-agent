import { Position } from "./position";

export const FIELD_LENGTH_CM = 12_000;
export const FIELD_WIDTH_CM = 9_000;
export const GOAL_LENGTH_CM = 200;
export const GOAL_WIDTH_CM = 2_400;
export const CENTER_CIRCLE_RADIUS_CM = 915;
export const PENALTY_AREA_DEPTH_CM = 1_650;
export const PENALTY_AREA_WIDTH_CM = 4_032;
export const GOAL_AREA_DEPTH_CM = 550;
export const GOAL_AREA_WIDTH_CM = 1_832;
export const PENALTY_SPOT_DISTANCE_CM = 1_100;

export type FieldOrientation = "horizontal" | "vertical";

export type ScreenPosition = {
  // Normalized screen coordinates with origin at top-left.
  x: number;
  y: number;
};

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

export function clampFieldPosition(position: Position): Position {
  return {
    x: clamp(position.x, 0, FIELD_LENGTH_CM),
    y: clamp(position.y, 0, FIELD_WIDTH_CM),
  };
}

export function fieldToScreenPosition(
  position: Position,
  orientation: FieldOrientation,
): ScreenPosition {
  const fieldPosition = clampFieldPosition(position);

  if (orientation === "horizontal") {
    return {
      x: fieldPosition.x / FIELD_LENGTH_CM,
      y: 1 - fieldPosition.y / FIELD_WIDTH_CM,
    };
  }

  // 90-degree anticlockwise rotation of the horizontal tactical view.
  return {
    x: 1 - fieldPosition.y / FIELD_WIDTH_CM,
    y: 1 - fieldPosition.x / FIELD_LENGTH_CM,
  };
}

export function screenToFieldPosition(
  position: ScreenPosition,
  orientation: FieldOrientation,
): Position {
  const screenPosition = {
    x: clamp(position.x, 0, 1),
    y: clamp(position.y, 0, 1),
  };

  if (orientation === "horizontal") {
    return {
      x: screenPosition.x * FIELD_LENGTH_CM,
      y: (1 - screenPosition.y) * FIELD_WIDTH_CM,
    };
  }

  return {
    x: (1 - screenPosition.y) * FIELD_LENGTH_CM,
    y: (1 - screenPosition.x) * FIELD_WIDTH_CM,
  };
}

export function screenDeltaToFieldDelta(
  delta: ScreenPosition,
  orientation: FieldOrientation,
): Position {
  if (orientation === "horizontal") {
    return {
      x: delta.x * FIELD_LENGTH_CM,
      y: -delta.y * FIELD_WIDTH_CM,
    };
  }

  return {
    x: -delta.y * FIELD_LENGTH_CM,
    y: -delta.x * FIELD_WIDTH_CM,
  };
}
