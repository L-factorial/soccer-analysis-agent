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
4. `tactical_instruction.py` deterministically maps supported instruction words
   to bounded search and scoring policy adjustments.
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

### Dynamic open spaces

The regular planner discovers circular open spaces from every analyzed game
state, including the new state produced by each simulated phase. Discovery is
controlled by `DynamicSpacePolicy` in `app/analysis/dynamic_spaces.py`.

`maximum_spaces_per_team` caps how many candidates survive (five by default), while
`minimum_separation_cm` prevents near-duplicate candidates. The default
separation is 1,800 cm (18 m). Both values are policy parameters and can be
overridden together through `AnalysisPolicy.dynamic_spaces` for experiments
without modifying the discovery algorithm.

`minimum_radius_cm` is 500 cm (5 m), producing circles at least 10 m in
diameter. Discovery also uses this value as the minimum clearance from an
attacking player, ensuring that a selected center has room for the full minimum
radius rather than merely inflating a geometrically occupied candidate.

The standard animation response exposes its root-state circles through
`diagnostics.dynamicSpaces` and includes timed `phaseSnapshots` for the initial
state and every selected phase boundary. The frontend renders the active
snapshot as a passive dotted overlay, so displayed spaces change with playback.
They are diagnostic geometry rather than editable submission spaces.

### Player identity and profile names

Each player retains `id` and `name` as internal identity fields. The optional
`profileName` is a separate coach-facing display label, limited to 40
characters. It is submitted to the backend and retained in `PlayerState`, but
tactical rules continue to reference the stable player ID. The field UI renders
only a non-empty `profileName` above the player circle.

### Speed categories

| Category | Multiplier |
| --- | ---: |
| `BASELINE` | 1.00 |
| `FAST` | 1.20 |
| `SUPER_FAST` | 1.56 |

`FAST` is 20% above baseline. `SUPER_FAST` is 30% above `FAST`, so its
compounded baseline multiplier is `1.20 × 1.30 = 1.56`.

Player capability is separate from action pace. Every generated short dribble
is evaluated at `SLOW`, `REGULAR`, and `SPRINT`; scheduled off-ball runs report
the pace matching their effective movement speed. Defaults are configurable in
`MovementPolicy`:

| Action pace | Run speed for a baseline player | Dribble speed |
| --- | --- | --- |
| `SLOW` | 400 cm/s | 280 cm/s |
| `REGULAR` | 600 cm/s | 420 cm/s |
| `SPRINT` | 900 cm/s | 630 cm/s |

Regular pace is 50% faster than slow, sprint is 50% faster than regular, and
dribbling is 30% slower than the corresponding run. The player's capability
multiplier is applied after pace selection. Movement response events expose
`pace` and the resulting `speedCmPerSecond`.

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

### Consecutive dribble phases

Dribbles remain bounded 1.5- or 3-second search primitives so pressure,
support, possession, and open spaces are recomputed frequently. Beam scoring
applies `consecutive_dribble_penalty` when the same carrier is selected again;
the penalty is reduced by `meaningful_dribble_change_penalty_ratio` when the
carrier changes direction or a different defender becomes the primary presser.
This prevents repeated primitives from accumulating progress reward as though
each were a new tactical idea.

The response scheduler separately merges adjacent `MOVE_WITH_BALL` events when
the carrier continues without a turn. This is presentation-only: the internal
phase boundaries and all simultaneous attacking and defensive reactions remain
unchanged.

Dribble phase scoring also compares the destination with the dynamic circular
spaces present in the phase's starting state. Endpoints inside a circle receive
`dribble_inside_open_space_reward`; nearby endpoints receive a distance-scaled
`dribble_near_open_space_reward`. A pressured endpoint outside those areas gets
`pressured_non_space_dribble_penalty`, except when the dribble materially moves
forward, changes channel, escapes its primary presser, or enters configured
shooting range. These are preferences rather than validity rules because the
sampled circles do not describe every tactically useful patch of field.

Attacking intentions describe off-ball jobs: receive, support, run forward,
hold, shift with play, or make a decoy run. Defensive intentions describe
pressing, tracking, goal coverage, holding shape, or covering a passing lane.
Each intention has a start offset so all players do not react simultaneously.

### Defensive cover and decoy handoff

During a dribble, the nearest outfield defender presses while a second defender
protects a point between the dribble destination and the defended goal. This is
represented as `COVER_PASSING_LANE`, not `TRACK_RECEIVER`, because a dribble has
no receiver. A covering defender may follow a decoy only when another
non-pressing outfield defender remains both sufficiently goal-side and within
the central corridor. Otherwise the marker hands off the decoy and retains
cover. This invariant prevents the attack-oriented beam from selecting a branch
whose only advantage is an implausible defensive abandonment.

The relevant generation constants are `goal_side_cover_distance_cm`,
`minimum_cover_depth_cm`, and `central_cover_half_width_cm`.

Unassigned defenders use ordinary formation lanes while the threat is deeper on
the field. Once the ball reaches 60% of the attacking path, `HOLD_SHAPE` becomes
threat-aware: the lane is blended toward the defended goal corridor, and the
target is clamped so it cannot increase the defender's existing lateral gap
from that corridor. This keeps weak-side/far-post cover compact and makes a
later `COVER_GOAL` assignment a continuation rather than an abrupt reversal.
The normal maximum shape-shift distance still applies.

This behavior is controlled by `threat_aware_shape_progress_ratio` and
`threat_aware_corridor_weight`.

### Wide attacks and crossing runs

When a dribble destination is at least 65% of the way toward the attacking goal
and lies within the outer 25% of the field width, the phase generator switches
from ordinary support lanes to a crossing pattern. Two available teammates are
jointly assigned to near-post and far-post arrival points 1,200 cm in front of
the goal line and 300 cm inside each post. Arrival time and lateral displacement
determine which runner receives each target. The remaining teammate supports
behind the carrier.

These roles are concurrent intentions in one phase. They are not separate beam
alternatives, so the selected animation shows both box runs while the wide
carrier advances. Player speed categories still cap how far each runner can
actually travel during that phase; targets do not teleport players.

The corresponding generation constants are `crossing_trigger_progress_ratio`,
`crossing_wide_channel_ratio`, `crossing_box_depth_cm`, and
`crossing_post_inset_cm`.

An advanced central dribble also reserves an explicit width provider. The
naturally widest available teammate advances in their existing lateral lane,
while the remaining runners occupy inside lanes and one teammate supports the
carrier. For ordinary forward-run assignments, a player who is already wider
than the proposed target retains that natural width. Phase scoring adds a small
reward for total attacking width and a penalty for attackers finishing too
close together, so beam search prefers distinct passing lanes when otherwise
similar phases are available. These rules are controlled by
`width_provider_progress_ratio`, `width_provider_forward_cm`,
`attacking_width_weight`, `minimum_attacking_spacing_cm`, and
`close_spacing_penalty_weight`.

### Shot roles and blocking

A shot phase does not use generic `SHIFT_WITH_PLAY` for every non-shooter. The
deepest available teammate receives `HOLD_POSITION` as rest defense, while two
other teammates are jointly matched to near-post and far-post rebound targets.
This prevents attackers from converging on the shooter and retains protection
against a clearance or counterattack.

Defensive responsibilities are complementary. The nearest defender presses the
shooter, while a second outfield defender covers a distinct point 35% along the
shot segment. The goalkeeper retains goal coverage. The phase simulator uses
the shooter's release hold, each defender's reaction time, player speed
multipliers, and the moving ball trajectory to determine whether a block
is reachable. A reachable block rejects the phase with `shot_blocked`; the
defensive run is therefore part of simulation rather than cosmetic animation.

Shot-role behavior is controlled by `shot_rebound_depth_cm`,
`shot_rebound_post_inset_cm`, `shot_rebound_reaction_seconds`, and
`shot_secondary_block_fraction`.

Shot generation also has a hard distance limit of 27 yards (2,468.88 cm) from
the selected goal-mouth target. This represents the top of the standard penalty
arc, approximately 22 yards from the goal line, plus a five-yard allowance.
More distant shots are rejected with `shot_out_of_range` before beam ranking;
the goal reward therefore cannot make a prohibited long shot selectable.

Simulation status values:

- `SUCCESS`: the phase completed and produced a usable next state.
- `INVALID`: static phase validation failed.
- `INTERCEPTED`: a defender reached a pass trajectory first.
- `POSSESSION_LOST`: the attacking team did not retain control.
- `TIMING_CONFLICT`: coordinated arrivals could not occur as scheduled.
- `TACKLED`: the carrier was reached during a dribble or before release.

`SHOT_BLOCKED` is a phase issue rather than a separate status: it produces the
existing `INTERCEPTED` simulation status and identifies the responsible
defender and trajectory point in diagnostics.

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

Important phase-search library defaults are depth 4, beam width 5, 30 seconds
maximum play duration, 75 retained nodes, and a 0.9 future-score discount. The
public API uses depth 8, beam width 8, and a 100-node retained budget so distinct
goal routes have more opportunity to survive. These limits bound latency; they
are not soccer laws.

`maximum_solution_count` defaults to 2 and caps the total public plans, including
the primary plan. After goal and instruction filtering, the API keeps the
highest-scoring route and then the next tactically distinct route. Diversity is
based on action types, actors, receivers, and broad left/central/right channels.
Repeated identical actions are collapsed for comparison, so a long dribble split
across phases and nearby dynamic-space endpoints cannot make the same visible
play appear as a second alternative.

## Deterministic planning responsibility

The deterministic engine owns geometry, offside, interception, player speeds,
state transitions, phase validity, scoring, search, and animation. There is no
external-model planning path or fallback. Free-text tactical instructions
only affect the explicitly supported local keyword-to-policy mapping.

## Animation event reference

Events are a discriminated union keyed by `type`.

| Event | Meaning |
| --- | --- |
| `TURN` | Update a player from one orientation to another. Currently instantaneous. |
| `MOVE` | Off-ball movement generated by the legacy planner. |
| `RUN` | Coordinated attacking or defensive phase movement. |
| `MOVE_WITH_BALL` | Dribble while retaining ball control. |
| `PASS` | Direct pass to `targetPlayerId`. |
| `PASS_TO_SPACE` | Ball travels to a point/space for `intendedReceiverId`. |
| `RECEIVE` | Instantaneous possession handoff at `startTime`; no duration. |
| `SHOT` | Ball travels toward a specified goal and target point. |

Timed movement and ball events have `startTime` and a strictly positive
`duration`. `RECEIVE` is instantaneous. `TURN` currently has zero duration:
orientation remains available for presentation, but facing data is not yet
reliable enough to charge physical simulation time. The centralized
`ACCOUNT_FOR_TURN_DURATION` policy documents where turn cost can be restored
later. Events may overlap intentionally because players react and move
concurrently. IDs (`action1`, `action2`, ...) are stable within one response but
are not persistent database identifiers.

For `PASS_TO_SPACE`, possession chains do not insert a stationary preparation
pause after `RECEIVE`. The pass begins at the next phase boundary. For an
implicitly timed lead pass, analysis weights the ball speed so its travel time
matches a longer receiver run. When the receiver needs less time, the scheduler
starts that run later instead. Explicitly timed passes that the receiver cannot
meet remain infeasible. This keeps timing synchronized without granting the
receiver impossible speed or overlapping a run with the preceding phase.

Direct and into-space passes share a configurable hard distance limit through
`PassPolicy.maximum_pass_distance_cm`. Its default is 6,000 cm (60 m); longer
passes are rejected before planner scoring.

Nominal pass speed is selected from configurable distance bands in `PassPolicy`:

| Category | Distance | Nominal ball speed |
| --- | --- | --- |
| Short | up to and including 10 m | 1,200 cm/s (12 m/s) |
| Moderate | over 10 m, up to and including 30 m | 1,800 cm/s (18 m/s) |
| Long | over 30 m, up to and including 60 m | 2,400 cm/s (24 m/s) |

The thresholds and all three speeds are policy fields. An implicitly timed pass
into space may use a lower effective speed so the ball and receiver arrive
together; direct passes and explicitly timed passes use the category speed or
their requested timing respectively.

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

Defaults are constructor arguments so tests and experiments can replace them
without modifying global state. Distances are centimeters and times are seconds
unless a field explicitly states otherwise.

## Extension rules

- Add soccer decisions to the phase decision-rule/generation layer, not beam search.
- Add legality checks to validation/offside/interception, not presentation text.
- Add state evolution to simulation/transitions, not scheduling.
- Add timeline presentation to scheduling, not tactical scoring.
- Keep API request/response translation out of domain objects.
- Add a regression test whenever a constant changes observable tactical behavior.
# Optional commentary prototype

The commentary integration is deliberately downstream from planning and
scheduling. The analyze response returns without waiting. The frontend then
sends the completed animation to the independent commentary endpoint. When
`SOCCER_COMMENTARY_ENABLED=true`, selected-phase facts are sent to a language
model. Structured output supplies
prose keyed by existing phase IDs; the backend then attaches scheduler-owned
timestamps and ignores unknown or duplicate IDs. Any provider error returns the
original animation unchanged.

The frontend starts one independent commentary request for the primary plan and
each returned alternative. Per-plan loading/ready state is shown inside the
header plan selector. Commentary copy is rendered as a hover/click tooltip so
it overlays the workspace instead of reducing the field's available height.

The prototype is isolated in `app/commentary/`. Removing that package, the
single enrichment call in the analyze endpoint, the optional response field,
and the frontend commentary component restores the application to its prior
behavior.
