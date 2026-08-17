# Backend architecture

This document describes the backend from an incoming field submission to the
animation events returned to the UI. The backend treats soccer analysis as a
pure planning problem: every transition creates a new immutable game state;
the submitted layout is never mutated.

## Units and coordinate system

- Positions and distances are in **centimeters**.
- Durations and timestamps are in **seconds**.
- Orientations are in **degrees**, with `0` pointing along positive X.
- X runs from the left goal to the right goal. Y runs across the field.
- A team's `attacking_direction` determines whether increasing or decreasing X
  is forward. Rules must use that value instead of assuming team 1 attacks right.
- Floating-point spatial comparisons use `EPSILON = 1e-9` to avoid treating
  insignificant rounding noise as meaningful movement.

## Request-to-response flow

1. `api/field_configurations.py` validates the JSON schema and soccer-specific
   field constraints.
2. `builders/game_state.py` converts submitted models into immutable domain
   objects and derives attacking goals and directions.
3. `planning/state_analysis.py` resolves possession, player context, target
   zones, dynamic spaces, and feasible actions.
4. `orchestration/planner.py` selects deterministic, LLM-intent, or LLM-tool
   orchestration. The LLM never changes game state directly: it selects bounded
   policies or asks the deterministic search tool to run.
5. `phases/decision_rules.py` is the public entry point for phase generation
   and phase scoring rules. Detailed coordinated-run generation currently lives
   in `phases/templates.py`.
6. `planning/beam.py` performs generic frontier traversal, duplicate removal,
   beam pruning, and retained-node limiting. Both planner implementations use it.
7. `phases/simulation.py` executes one candidate phase concurrently and returns
   a new `GameState`. Offside and phase validation can reject it.
8. `scheduling/phase.py` turns the selected sequence into timestamped animation
   events. Scheduling does not select tactics or resimulate the play.
9. The API returns the primary animation plus up to two alternative plans.

## State model

The input models in `app/models` represent user-provided JSON. The dataclasses
in `domain/game_state.py` are the authoritative runtime state.

| State | Meaning |
| --- | --- |
| `FieldState` | Field length, width, type, and unit. |
| `GoalState` | Goal polygon, normalized bounds, side, and computed center. |
| `TeamState` | Defended/attacking goals and derived attacking direction. |
| `PlayerState` | Identity, team, position, facing, velocity, and speed category. |
| `BallState` | Position, direction, scalar speed, and velocity vector. |
| `TargetZoneState` | User, goal, or dynamically computed tactical space. |
| `PossessionState` | Whether possession is resolved and who controls/contests it. |
| `GameState` | Complete immutable snapshot at one simulation time. |
| `AnalyzedGameState` | A `GameState` plus derived context and feasible actions. |

### Possession lifecycle

- `UNRESOLVED`: possession analysis has not selected a controller.
- `CONTROLLED`: exactly one player controls the ball; player and team IDs exist.
- `LOOSE`: no player is within the control conditions.
- `CONTESTED`: multiple players have a credible claim; IDs list the contestants.

The analyze endpoint requires `CONTROLLED` possession because planning without
an unambiguous attacking team would make actor selection nondeterministic.

### Speed categories

| Category | Multiplier |
| --- | ---: |
| `BASELINE` | 1.00 |
| `FAST` | 1.15 |
| `SUPER_FAST` | 1.20 |

The multiplier scales the applicable movement speed; it does not decide a
player's tactical role by itself. Lane suitability, distance, and role rules
still determine assignments.

### Terminal scoring state

`scored_goal_id` and `scoring_team_id` are set together after a successful shot.
A phase-search node containing a scored goal is terminal and is not expanded.

## Actions, tactical phases, and simulation

An `ActionCandidate` is one feasible ball or player action. A `TacticalPhase`
wraps one primary action with simultaneous attacking and defensive intentions.

Primary action types:

- `MOVE`: off-ball player movement used by the legacy action planner.
- `MOVE_WITH_BALL`: controlled dribble.
- `PASS_TO_PLAYER`: pass to a teammate's position.
- `PASS_TO_SPACE`: pass to a target zone with an intended receiver.
- `SHOT`: attempt at the opponent's goal.

Phase templates:

- `DIRECT_PASS`: direct pass plus receiver/support/defensive reactions.
- `PASS_INTO_SPACE`: timed run and pass into a target zone.
- `DRIBBLE_WITH_SUPPORT`: dribble with support and forward-run options.
- `SHOT`: shot with defensive and goalkeeper reactions.

Attacking intentions describe off-ball jobs: receive, support, run forward,
hold, shift with play, or make a decoy run. Defensive intentions describe
pressing, tracking, goal coverage, holding shape, or covering a passing lane.
Each intention has a start offset so all players do not react simultaneously.

Simulation status values:

- `SUCCESS`: the phase completed and produced a usable next state.
- `INVALID`: static phase validation failed.
- `INTERCEPTED`: a defender reached a pass trajectory first.
- `POSSESSION_LOST`: the attacking team did not retain control.
- `TIMING_CONFLICT`: coordinated arrivals could not occur as scheduled.
- `TACKLED`: the carrier was reached during a dribble or before release.

## Beam search

`planning/beam.py` owns the search algorithm; domain adapters own soccer rules.
At each depth the engine:

1. asks the adapter to expand every nonterminal frontier node;
2. rejects states already reached with an equal or better cumulative score;
3. sorts children using a deterministic score/duration/path key;
4. keeps only the best instance of each state at that depth;
5. applies `beam_width`;
6. applies the global retained-node budget; and
7. repeats until depth, terminal, capacity, or expansion limits stop it.

Important phase-search defaults are depth 4, beam width 5, 30 seconds maximum
play duration, 75 retained nodes, and a 0.9 future-score discount. The API uses
depth 8 while retaining the same beam width and node budget. These limits bound
latency; they are not soccer laws.

## Deterministic rules and LLM responsibility

The deterministic engine remains authoritative for geometry, offside,
interception, player speeds, state transitions, phase validity, scoring, and
animation. An LLM may produce a validated `TacticalIntent` or call a bounded
search tool. Intent is translated into numeric policy preferences; unknown
players/spaces are removed before search. If an external LLM call fails, normal
deterministic planning runs and diagnostics report `AGENTIC_FALLBACK`.

Planning modes:

- `DETERMINISTIC`: no LLM call.
- `LLM_INTENT`: LLM returns structured intent; backend searches.
- `LLM_TOOL_AGENT`: LLM invokes complete deterministic searches and selects one.

## Animation event reference

Events are a discriminated union keyed by `type`.

| Event | Meaning |
| --- | --- |
| `TURN` | Rotate a player from one orientation to another. |
| `MOVE` | Off-ball movement generated by the legacy planner. |
| `RUN` | Coordinated attacking or defensive phase movement. |
| `MOVE_WITH_BALL` | Dribble while retaining ball control. |
| `PASS` | Direct pass to `targetPlayerId`. |
| `PASS_TO_SPACE` | Ball travels to a point/space for `intendedReceiverId`. |
| `RECEIVE` | Instantaneous possession handoff at `startTime`; no duration. |
| `SHOT` | Ball travels toward a specified goal and target point. |

Timed events have `startTime` and a strictly positive `duration`. `RECEIVE` is
instantaneous. Events may overlap intentionally because players react and move
concurrently. IDs (`action1`, `action2`, ...) are stable within one response but
are not persistent database identifiers.

The scheduler uses a turning speed of 180 degrees/second. It spreads simulated
off-ball displacement across the remaining phase time, preventing a player from
arriving early and appearing artificially idle.

## Policy constants

Policy dataclasses group tunable constants by concern:

- analysis: possession, movement, passing, shooting, pressure, spaces;
- phase generation: support distances, lateral lanes, reactions, and run counts;
- simulation/validation: movement speeds, tolerances, interception, and timing;
- scoring: progress, goal proximity, possession, coordination, duration, goal,
  and instruction-preference weights;
- search: depth, width, duration, discount, and retained-node limits.

Defaults are constructor arguments so tests and agent tools can replace them
without modifying global state. Distances are centimeters and times are seconds
unless a field explicitly states otherwise.

## Extension rules

- Add soccer decisions to the phase decision-rule/generation layer, not beam search.
- Add legality checks to validation/offside/interception, not the LLM prompt.
- Add state evolution to simulation/transitions, not scheduling.
- Add timeline presentation to scheduling, not tactical scoring.
- Keep API request/response translation out of domain objects.
- Add a regression test whenever a constant changes observable tactical behavior.
