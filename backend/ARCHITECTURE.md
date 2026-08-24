# Backend architecture

This document describes the backend from an incoming field submission to the
animation events returned to the UI. The backend treats soccer analysis as a
pure planning problem: every transition creates a new immutable game state;
the submitted layout is never mutated.

For a shorter, code-linked guide to the separated planning boundary, see the
[`app/game_engine` guide](app/game_engine/README.md).

## Game-engine boundary

`app/game_engine` is the single application-neutral entry point for tactical
planning. It owns state analysis, bounded search, instruction-policy adaptation,
goal filtering, and alternative-route selection. It does not import FastAPI,
frontend response models, animation scheduling, or commentary.

The surrounding layers have deliberately narrower jobs:

- `api/` validates transport input, maps engine failures to HTTP responses, and
  serializes output;
- `builders/` translates transport models to immutable domain state and builds
  diagnostics;
- `scheduling/` projects a chosen engine route onto an animation timeline; and
- `commentary/` narrates an already completed timeline asynchronously.

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

1. [`api/field_configurations.py`](app/api/field_configurations.py) validates the
   JSON schema and soccer-specific field constraints.
2. [`builders/game_state.py`](app/builders/game_state.py) converts submitted
   models into immutable domain objects and derives attacking goals/directions.
3. [`game_engine/service.py`](app/game_engine/service.py) enters the deterministic
   planning boundary.
4. [`planning/state_analysis.py`](app/planning/state_analysis.py) resolves
   possession, player context, target zones, dynamic spaces, and feasible actions.
5. [`game_engine/instructions.py`](app/game_engine/instructions.py)
   deterministically maps supported instruction words to bounded policy changes.
6. [`phases/decision_rules.py`](app/phases/decision_rules.py) exposes phase
   generation and scoring; coordinated rules live in
   [`phases/templates.py`](app/phases/templates.py).
7. [`phases/search.py`](app/phases/search.py) connects the soccer phase lifecycle
   to the generic deterministic beam in
   [`planning/beam.py`](app/planning/beam.py).
8. [`phases/simulation.py`](app/phases/simulation.py) executes one candidate
   phase concurrently and returns a new `GameState`. Offside, interception, and
   validation can reject it.
9. [`game_engine/solutions.py`](app/game_engine/solutions.py) filters scoring
   routes and removes alternatives that differ only by small geometric noise.
10. [`scheduling/phase.py`](app/scheduling/phase.py) turns the selected sequence
   into timestamped animation events without changing tactical decisions.
11. The API returns the primary animation plus up to two alternative plans.

## Planner, phases, and scheduler

These names refer to different responsibilities rather than interchangeable
parts of the same algorithm:

| Component | Responsibility | Main code |
| --- | --- | --- |
| Game-engine planner | Orchestrates analysis, instruction-policy adaptation, search, goal filtering, and distinct solution selection. | [`game_engine/service.py`](app/game_engine/service.py) |
| State analyzer | Recomputes possession, pressure, open spaces, passes, dribbles, shots, and feasible candidates for each state. | [`planning/state_analysis.py`](app/planning/state_analysis.py) |
| Phase generator | Combines one primary ball action with simultaneous attacking and defensive off-ball intentions. | [`phases/templates.py`](app/phases/templates.py) |
| Phase simulator | Applies a generated phase to immutable state and checks physical timing, tackles, blocks, interceptions, and possession. | [`phases/simulation.py`](app/phases/simulation.py) |
| Phase scorer | Produces an explainable additive reward/penalty breakdown for a valid simulated phase. | [`phases/scoring.py`](app/phases/scoring.py) |
| Beam-search adapter | Expands phase nodes, applies soccer validation/scoring, reanalyzes child states, and collects diagnostics. | [`phases/search.py`](app/phases/search.py) |
| Generic beam search | Performs deterministic frontier ranking, duplicate-state pruning, width pruning, and retained-node limiting. It contains no soccer rules. | [`planning/beam.py`](app/planning/beam.py) |
| Solution selector | Keeps goal-scoring routes and rejects visually duplicate alternatives. | [`game_engine/solutions.py`](app/game_engine/solutions.py) |
| Scheduler | Converts the already selected plan into frontend timestamps and events. It cannot change the plan. | [`scheduling/phase.py`](app/scheduling/phase.py) and [`builders/phase_animation_response.py`](app/builders/phase_animation_response.py) |

## Incoming analysis JSON

`POST /api/v1/field-configurations/analyze` accepts the camelCase transport
contract defined by
[`models/field_submission.py`](app/models/field_submission.py). The complete
submission is validated by
[`validation/field_submission.py`](app/validation/field_submission.py) before
[`builders/game_state.py`](app/builders/game_state.py) converts it into engine
state.

The following is a compact valid-shape example. Production submissions normally
contain all players for the selected field type.

```json
{
  "schemaVersion": "1.0",
  "tacticalInstruction": "attack quickly through wide space",
  "fieldConfiguration": {
    "label": "5v5",
    "fieldType": "5v5",
    "dimensions": { "length": 12000, "width": 9000, "unit": "cm" },
    "goalDimensions": { "length": 200, "width": 2400, "unit": "cm" },
    "teams": [
      {
        "id": "team1",
        "name": "Home",
        "color": "#D8FF3E",
        "defendedGoalId": "goal-left"
      },
      {
        "id": "team2",
        "name": "Away",
        "color": "#FF725E",
        "defendedGoalId": "goal-right"
      }
    ],
    "goals": [
      {
        "id": "goal-left",
        "name": "Left goal",
        "side": "left",
        "coordinates": [
          { "x": 0, "y": 3300 },
          { "x": 200, "y": 3300 },
          { "x": 200, "y": 5700 },
          { "x": 0, "y": 5700 }
        ]
      },
      {
        "id": "goal-right",
        "name": "Right goal",
        "side": "right",
        "coordinates": [
          { "x": 11800, "y": 3300 },
          { "x": 12000, "y": 3300 },
          { "x": 12000, "y": 5700 },
          { "x": 11800, "y": 5700 }
        ]
      }
    ],
    "players": [
      {
        "id": "team1-7",
        "name": "team1-7",
        "profileName": "Alex",
        "number": 7,
        "teamId": "team1",
        "position": { "x": 3200, "y": 2200 },
        "orientation": 0,
        "velocity": { "x": 0, "y": 0 },
        "speedCategory": "FAST"
      },
      {
        "id": "team2-4",
        "name": "team2-4",
        "profileName": null,
        "number": 4,
        "teamId": "team2",
        "position": { "x": 7000, "y": 3000 },
        "orientation": 180,
        "velocity": { "x": 0, "y": 0 },
        "speedCategory": "BASELINE"
      }
    ],
    "ball": {
      "position": { "x": 3200, "y": 2200 },
      "direction": 0,
      "speed": 0
    },
    "openSpaces": [
      {
        "id": "coach-space-1",
        "name": "Wide channel",
        "type": "circular",
        "center": { "x": 7200, "y": 1200 },
        "radius": 600
      }
    ]
  }
}
```

Important request rules:

- `schemaVersion` is currently exactly `"1.0"`.
- Coordinates, radii, dimensions, and submitted speeds use centimeters.
- `tacticalInstruction` is optional and limited to 500 characters. The current
  deterministic adapter supports only documented keyword-based weight changes.
- There must be exactly two teams and two goals. Each team references the goal
  it defends; the builder derives its attacking goal and direction.
- `profileName` is an optional display label. Stable engine identity uses player
  `id`; `speedCategory` is `BASELINE`, `FAST`, or `SUPER_FAST`.
- Initial player velocity and ball speed must be zero, positions must be inside
  the field, IDs must be unique, and the ball must be close enough to one player
  for controlled possession before planning can begin.
- `openSpaces` may contain circular or rectangular coach-authored spaces. These
  remain distinct from dynamic circular spaces recomputed by the engine.

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
controlled by `DynamicSpacePolicy` in
[`app/analysis/dynamic_spaces.py`](app/analysis/dynamic_spaces.py).

Discovery samples a fixed set of field fractions and measures each point's
nearest-defender clearance, teammate clearance, ball reachability, and forward
value in the attacking direction. Points that violate clearance or attacker
reachability limits are rejected. The survivors are ranked using those four
signals, then greedily retained subject to the configured separation and count
limits. Each retained point becomes a circular target with a radius clamped to
the configured minimum and maximum. Because `analyze_game_state` invokes this
process after every successful simulation, the spaces evolve phase by phase.

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

### Transport JSON to immutable game state

The API models are not the simulation state. The mapping is centralized in
[`build_initial_game_state`](app/builders/game_state.py):

| Incoming JSON | Derived engine state |
| --- | --- |
| `dimensions` and `fieldType` | `FieldState` with X length, Y width, and centimeter unit. |
| Goal coordinate polygons | Normalized `GoalState` bounds and computed centers. |
| Team `defendedGoalId` | Derived attacking goal and `POSITIVE_X`/`NEGATIVE_X` direction. |
| Player array | Immutable `players_by_id` and `player_ids_by_team` indexes. |
| Ball | `BallState`; velocity starts at zero. |
| Submitted open spaces | User-defined `TargetZoneState` entries. |
| Derived attacking goals | Ball-only attacking goal target zones, one per team. |
| No submitted possession field | Initial `UNRESOLVED` possession, resolved during state analysis. |

Every valid phase creates a new `GameState`; it does not mutate the parent.
[`analyze_game_state`](app/planning/state_analysis.py) then attaches derived
possession, player context, dynamic spaces, and action candidates as an
`AnalyzedGameState` for the next search expansion.

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

## Phase scoring policy

Only valid simulated phases are scored. The authoritative policy and formula
are in [`phases/scoring.py`](app/phases/scoring.py). The scorer returns a
`PhaseScore` component breakdown so diagnostics can explain why one branch was
preferred; scoring never changes the simulated state and cannot make an illegal
phase legal.

The phase total is additive:

```text
phase total = forward progress
            + goal proximity
            + possession
            + coordination
            + duration penalty
            + goal reward
            + tactical preference
            + sequence adjustment
            + dribble-space adjustment
```

### Core score components

| Component | Computation | Default policy |
| --- | --- | ---: |
| Forward progress | Action progress along the team's attacking direction, normalized by field length to `[-1, 1]`. | `forward_progress_weight = 35` |
| Goal proximity | Improvement in distance to the attacking goal, normalized by field length to `[-1, 1]`. | `goal_proximity_weight = 25` |
| Possession | Full positive reward when the attacking team retains controlled possession; the same amount is negative when it does not. | `possession_weight = 30` |
| Coordination | Rewards assigned intentions, the best supporting runner's defender clearance/lateral separation, and total attacking width. It penalizes attacker pairs that finish too close together. | `coordination_weight = 8`, `attacking_width_weight = 6`, `close_spacing_penalty_weight = 5` |
| Duration | Negative value scaled up to the first 12 seconds of a phase. Faster otherwise-equivalent phases rank higher. | `duration_penalty_weight = 8` |
| Goal | Terminal reward when the attacking team scores. It dominates ordinary positional progress. | `goal_reward = 1000` |
| Tactical preference | Optional reward for configured action types, players, spaces, or off-ball intentions. The current keyword adapter mainly adjusts core weights; these fields support more targeted future adapters. | `tactical_preference_weight = 12`, `preferred_space_weight = 250` |
| Sequence adjustment | Applied by the search adapter because it can inspect the preceding phase. Repeating a same-carrier dribble is penalized; a meaningful direction/presser change retains only part of that penalty. | `consecutive_dribble_penalty = 12`, change ratio `0.25` |
| Dribble-space adjustment | Rewards destinations inside/near a computed dynamic space and penalizes arbitrary pressured destinations unless a tactical exception applies. | inside `+10`, near up to `+5`, pressured non-space `-10` |

### Scoring-policy fields

All defaults below belong to
[`PhaseScoringPolicy`](app/phases/scoring.py). Distances are centimeters.

| Policy group | Fields and defaults | Purpose |
| --- | --- | --- |
| Positional reward | `forward_progress_weight=35`, `goal_proximity_weight=25` | Prefer phases that advance and improve shooting proximity. |
| Ball security | `possession_weight=30` | Reward controlled attacking possession and penalize its loss. |
| Team structure | `coordination_weight=8`, `attacking_width_weight=6`, `close_spacing_penalty_weight=5`, `minimum_attacking_spacing_cm=800` | Reward useful supporting assignments and width; discourage attackers collapsing into one lane. |
| Time | `duration_penalty_weight=8` | Prefer efficient phases when tactical value is comparable. |
| Repeated dribbles | `consecutive_dribble_penalty=12`, `meaningful_dribble_change_penalty_ratio=0.25` | Stop a carrier farming progress through nearly identical short phases while allowing genuine tactical changes. |
| Open-space dribbles | `dribble_inside_open_space_reward=10`, `dribble_near_open_space_reward=5`, `dribble_near_open_space_distance_cm=700` | Reward deliberate use of computed circular spaces. |
| Pressured dribbles | `pressured_non_space_dribble_penalty=10`, `dribble_pressure_distance_cm=1000` | Penalize pressured endpoints that do not use space or change the tactical problem. |
| Dribble exceptions | forward `1200`, channel change `1200`, shooting range `2468.88`, pressure escape gain `300` | Avoid penalizing a non-space dribble that advances materially, changes channel, enters shooting range, or escapes its presser. |
| Terminal goal | `goal_reward=1000` | Ensure a valid goal outranks ordinary field-position gains. |
| Instruction preferences | `tactical_preference_weight=12`, `preferred_space_weight=250`; preferred action/player/space/intention tuples are empty by default | Provide bounded ranking preferences without bypassing simulation or legality. |

The scoring function also uses fixed normalization distances for support quality:
1,500 cm for defender clearance and 1,200 cm for lateral separation. These are
currently local formula constants rather than `PhaseScoringPolicy` fields.

At search depth `d`, the accepted phase score is discounted before it is added
to the route:

```text
discounted phase score = score_discount ** (d - 1) * phase total
route score            = parent route score + discounted phase score
```

This accumulation is implemented in
[`phases/search.py`](app/phases/search.py); it allows immediate tactical value to
matter slightly more than speculative value several phases later.

## Beam search

[`planning/beam.py`](app/planning/beam.py) owns the generic deterministic search
algorithm; [`phases/search.py`](app/phases/search.py) supplies the soccer-specific
expansion, validation, simulation, scoring, and terminal-goal functions.
At each depth the engine:

1. asks the adapter to expand every nonterminal frontier node;
2. rejects states already reached with an equal or better cumulative score;
3. sorts children using a deterministic score/duration/path key;
4. keeps only the best instance of each state at that depth;
5. applies `beam_width`;
6. applies the global retained-node budget; and
7. repeats until depth, terminal, capacity, or expansion limits stop it.

### Beam-search configuration

The reusable library defaults are declared in
[`PhaseSearchPolicy`](app/phases/search.py). The public engine intentionally
overrides several values in
[`game_engine/config.py`](app/game_engine/config.py):

| Setting | Library default | Public engine | Meaning |
| --- | ---: | ---: | --- |
| `maximum_depth` | 4 | 8 | Maximum number of tactical phases in a searched route. |
| `beam_width` | 5 | 8 | Maximum best child states retained as the frontier after each level. |
| `maximum_play_duration_seconds` | 30 | 30 | Reject routes whose accumulated phase duration exceeds this limit. |
| `maximum_retained_nodes` | 75 | 100 | Global memory/expansion budget for retained search nodes. |
| `score_discount` | 0.9 | 0.9 | Multiplier applied once per additional search depth. |
| `maximum_solution_count` | 2 | 2 | Maximum public plans, including the selected primary plan. |

`beam_width` is not the number of actions generated from one state. The phase
generator may create up to 50 candidates per state by default; after validation,
simulation, scoring, and duplicate removal, beam search retains only the best
eight states across the entire next frontier. These limits bound latency and
memory; they are not soccer laws.

`maximum_solution_count` defaults to 2 and caps the total public plans, including
the primary plan. After goal and instruction filtering, the game engine keeps
the highest-scoring route and then the next tactically distinct route. Diversity is
based on action types, actors, receivers, and broad left/central/right channels.
Repeated identical actions are collapsed for comparison, so a long dribble split
across phases and nearby dynamic-space endpoints cannot make the same visible
play appear as a second alternative.

## Deterministic planning responsibility

The deterministic engine owns geometry, offside, interception, player speeds,
state transitions, phase validity, scoring, search, and animation. There is no
external-model planning path or fallback. Free-text tactical instructions
only affect the explicitly supported local keyword-to-policy mapping.

## Frontend animation JSON

The analyze endpoint returns the camelCase serialization of
[`AnimationResponse`](app/models/animation_response.py). The scheduler builds it
in [`builders/phase_animation_response.py`](app/builders/phase_animation_response.py),
the frontend fetches it in
[`frontend/src/api/analyze-field.ts`](../frontend/src/api/analyze-field.ts), and
its matching TypeScript contract is
[`frontend/src/models/animation-event.ts`](../frontend/src/models/animation-event.ts).

This representative response shows the complete top-level structure and a
single selected shot phase. IDs, positions, scores, timings, and diagnostics are
illustrative.

```json
{
  "duration": 2.4,
  "events": [
    {
      "id": "action1",
      "type": "RUN",
      "playerId": "team1-9",
      "startTime": 0.2,
      "duration": 2.2,
      "target": { "x": 10800, "y": 5200 },
      "pace": "SPRINT",
      "speedCmPerSecond": 780
    },
    {
      "id": "action2",
      "type": "SHOT",
      "playerId": "team1-7",
      "startTime": 0,
      "duration": 0.8,
      "goalId": "goal-right",
      "target": { "x": 11900, "y": 4500 }
    }
  ],
  "diagnostics": {
    "objective": "SCORE_GOAL",
    "tacticalInstruction": "attack quickly through wide space",
    "appliedDirectives": [
      "FAST_TEMPO",
      "ATTACK_AGGRESSIVELY",
      "CREATE_SPACE"
    ],
    "plannerType": "TACTICAL_PHASE",
    "phaseCount": 1,
    "attackingTeamId": "team1",
    "reachedDepth": 1,
    "evaluatedCandidateCount": 24,
    "rootCandidateCount": 18,
    "rootFeasibleCandidateCount": 12,
    "prunedByBeamCount": 8,
    "prunedByDurationCount": 0,
    "prunedByOffsideCount": 1,
    "prunedByPossessionCount": 2,
    "prunedByActionPatternCount": 0,
    "rejectionReasons": {
      "shot_blocked": 1,
      "pass_intercepted": 2
    },
    "dynamicSpaces": [
      {
        "id": "DynamicSpace-team1-1",
        "center": { "x": 9000, "y": 1800 },
        "radius": 700
      }
    ],
    "selectedSequenceScore": 1038.5,
    "selectedSequenceDepth": 1,
    "selectedPhases": [
      {
        "id": "phase-0001",
        "phaseType": "SHOT",
        "actionType": "SHOT",
        "actorId": "team1-7",
        "receiverId": null,
        "targetZoneId": "GoalSpace-team1",
        "target": { "x": 11900, "y": 4500 },
        "startTime": 0,
        "duration": 2.4,
        "endTime": 2.4,
        "ballActionStartTime": 0,
        "offsideLineX": 10100,
        "possessionBefore": "controlled",
        "possessionAfter": "loose",
        "score": 1038.5,
        "scoredGoal": true,
        "intentions": [
          {
            "side": "ATTACKING",
            "playerId": "team1-9",
            "intentionType": "FORWARD_RUN",
            "target": { "x": 10800, "y": 5200 },
            "targetPlayerId": null
          }
        ]
      }
    ],
    "explanation": [
      "Selected a valid terminal scoring route."
    ]
  },
  "alternativePlans": [],
  "phaseSnapshots": [
    {
      "phaseId": "initial",
      "phaseIndex": 0,
      "atTime": 0,
      "openSpaces": [
        {
          "id": "DynamicSpace-team1-1",
          "center": { "x": 9000, "y": 1800 },
          "radius": 700
        }
      ]
    },
    {
      "phaseId": "phase-0001",
      "phaseIndex": 1,
      "atTime": 2.4,
      "openSpaces": []
    }
  ],
  "commentary": null
}
```

### Response sections

| Field | Meaning | Authoritative code |
| --- | --- | --- |
| `duration` | End time of the scheduled primary animation in seconds. | [`builders/phase_animation_response.py`](app/builders/phase_animation_response.py) |
| `events` | Chronologically sortable discriminated event union used by the playback engine. Events may overlap for concurrent movement. | [`models/animation_response.py`](app/models/animation_response.py) |
| `diagnostics` | Search counters, applied instruction directives, selected score/depth, dynamic spaces, and per-phase explanations. | [`builders/phase_diagnostics.py`](app/builders/phase_diagnostics.py) and [`builders/phase_animation_response.py`](app/builders/phase_animation_response.py) |
| `alternativePlans` | Up to `maximum_solution_count - 1` distinct plans, each with its own duration, events, diagnostics, and snapshots. | [`game_engine/solutions.py`](app/game_engine/solutions.py) |
| `phaseSnapshots` | Dynamic open-space geometry at time zero and every selected phase boundary, allowing the overlay to update during playback. | [`builders/phase_animation_response.py`](app/builders/phase_animation_response.py) |
| `commentary` | Optional phase-aligned narration. Analyze initially returns it as `null`; the frontend requests commentary asynchronously. | [`commentary/models.py`](app/commentary/models.py) and [`commentary/service.py`](app/commentary/service.py) |

The event list is sorted deterministically by timestamp and event ID before the
response is returned. Overlapping timestamps are intentional: a pass, support
run, press, and defensive cover can occur during the same tactical phase.

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

The prototype is isolated in `app/commentary/` and its independent API endpoint.
Removing that package, endpoint, optional response field, and the frontend
commentary component restores the application to its prior behavior.
