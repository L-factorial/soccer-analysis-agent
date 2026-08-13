import { AnimationResponse } from "../../models";

// Temporary frontend fixtures. Delete this file and replace its imports with the
// backend response once the API is available.
export const DEMO_ANIMATION_RESPONSES: AnimationResponse[] = [
  {
    duration: 6,
    events: [
      {
        id: "action1",
        type: "MOVE_WITH_BALL",
        playerId: "A3",
        startTime: 0,
        duration: 1.5,
        target: { x: 5_300, y: 4_500 },
      },
      {
        id: "action2",
        type: "RUN",
        playerId: "A5",
        startTime: 0,
        duration: 2.5,
        target: { x: 7_200, y: 2_500 },
      },
      {
        id: "action3",
        type: "PASS_TO_SPACE",
        playerId: "A3",
        intendedReceiverId: "A5",
        spaceId: "O1",
        startTime: 1.5,
        duration: 1,
        target: { x: 7_200, y: 2_500 },
      },
      { id: "action4", type: "RECEIVE", playerId: "A5", startTime: 2.5 },
    ],
  },
  {
    duration: 6,
    events: [
      {
        id: "action1",
        type: "MOVE",
        playerId: "A4",
        startTime: 0,
        duration: 1.5,
        target: { x: 5_100, y: 6_300 },
      },
      {
        id: "action2",
        type: "PASS",
        playerId: "A3",
        targetPlayerId: "A4",
        startTime: 1,
        duration: 0.8,
      },
      { id: "action3", type: "RECEIVE", playerId: "A4", startTime: 1.8 },
      {
        id: "action4",
        type: "MOVE_WITH_BALL",
        playerId: "A4",
        startTime: 2,
        duration: 2,
        target: { x: 7_100, y: 6_400 },
      },
    ],
  },
  {
    duration: 7,
    events: [
      {
        id: "action1",
        type: "RUN",
        playerId: "A2",
        startTime: 0,
        duration: 2,
        target: { x: 6_000, y: 2_000 },
      },
      {
        id: "action2",
        type: "PASS",
        playerId: "A3",
        targetPlayerId: "A2",
        startTime: 1,
        duration: 1,
      },
      { id: "action3", type: "RECEIVE", playerId: "A2", startTime: 2 },
      {
        id: "action4",
        type: "PASS_TO_SPACE",
        playerId: "A2",
        intendedReceiverId: "A5",
        spaceId: "O1",
        startTime: 3,
        duration: 1.2,
        target: { x: 7_200, y: 2_500 },
      },
      { id: "action5", type: "RECEIVE", playerId: "A5", startTime: 4.2 },
    ],
  },
];

// Kept for the current single-response playback API.
export const DEMO_ANIMATION_RESPONSE = DEMO_ANIMATION_RESPONSES[0];
