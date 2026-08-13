import { Position } from "./position";

type OpenSpaceBase = {
  id: string;
  name: string;
};

export type CircularOpenSpace = OpenSpaceBase & {
  type: "circular";
  center: Position;
  radius: number;
};

export type RectangularOpenSpace = OpenSpaceBase & {
  type: "rectangular";
  bottomLeft: Position;
  topRight: Position;
};

export type OpenSpace = CircularOpenSpace | RectangularOpenSpace;
export type OpenSpaceType = OpenSpace["type"];
