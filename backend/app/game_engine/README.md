# Deterministic game engine

This package is the application-neutral entry point for soccer planning. Call
`SoccerGameEngine.plan(game_state, instruction)` to analyze an immutable state,
run the bounded tactical search, and receive distinct goal-scoring routes. It
has no dependency on FastAPI, frontend response models, animation scheduling,
or AI commentary.

## Boundary and flow

1. [`service.py`](service.py) coordinates the complete engine operation.
2. [`state_analysis.py`](../planning/state_analysis.py) resolves possession and
   recomputes derived state: player pressure, dynamic spaces, reachable actions,
   passing options, dribbles, and shots.
3. [`instructions.py`](instructions.py) applies the small supported deterministic
   prompt vocabulary to search/scoring policy. It does not call an LLM.
4. [`templates.py`](../phases/templates.py) generates coordinated phases: one
   primary ball action plus simultaneous attacking and defensive intentions.
5. [`simulation.py`](../phases/simulation.py) applies a phase to a `GameState`;
   [`validation.py`](../phases/validation.py),
   [`offside.py`](../phases/offside.py), and
   [`interception.py`](../phases/interception.py) reject impossible outcomes.
6. [`scoring.py`](../phases/scoring.py) scores valid resulting states and
   [`search.py`](../phases/search.py) adapts those rules to the generic bounded
   beam implementation in [`beam.py`](../planning/beam.py).
7. [`service.py`](service.py) keeps only goal routes, while
   [`solutions.py`](solutions.py) removes alternatives that would look
   tactically identical in the UI.

After this boundary returns, [`scheduling/phase.py`](../scheduling/phase.py)
converts a selected route into timestamps. The API and commentary layers then
serialize or narrate that scheduled result without changing engine decisions.

## Dynamic open-space computation

Open spaces are recomputed for the initial state and after every valid phase in
[`dynamic_spaces.py`](../analysis/dynamic_spaces.py). The algorithm is deliberately
small and deterministic:

1. Sample fixed longitudinal and lateral fractions of the field.
2. Measure every point's nearest-defender clearance, nearest-teammate clearance,
   distance from the ball, and forward progress for the attacking direction.
3. Reject points that are too close to a defender or teammate, or too far from
   every attacker to be reachable.
4. Rank the survivors by clearance, forward value, ball reachability, and
   attacker reachability.
5. Retain separated candidates up to the configured limit and represent each as
   a circular dynamic target whose radius is clamped to policy bounds.

The relevant thresholds live in `DynamicSpacePolicy`; changing them does not
change the discovery code. These circles are tactical candidates and diagnostic
overlays—not permanent objects from the submitted field configuration.

## Local attacking matchups

[`local_matchups.py`](../analysis/local_matchups.py) discovers one circular
contest around the outfield ball carrier at each controlled-possession state.
`AnalysisPolicy.local_matchups` configures its radius (default 1,000 cm), minimum
support spacing (300 cm), and the attacking progress at which value starts
increasing (0.5 of field length). Counts include players exactly on the radius;
attacking goalkeepers are excluded and defending goalkeeper IDs are separate.
Exact labels include `1v1`, `2v1`, `1v2`, `3v1`, `3v2`, and unopposed cases.

Raw counts describe geometry. Numerical value uses the carrier plus spaced,
onside teammates with feasible direct passes, compared with local outfield
defenders. Pass feasibility still checks opponents outside the circle. Value
is multiplied by forward progress and goal proximity; a crowd in the team's
own half earns no attacking bonus. This is a deterministic heuristic, not a
probability of scoring.

State analysis computes the result once for each search state. Phase scoring
uses the before/after difference with `PhaseScoringPolicy.local_matchup_weight`
(default 8; zero disables its scoring effect). Unchanged value adds no bonus;
terminal outcomes keep their existing outcome scoring. Existing beam depth
discounting still applies, so the contribution is a search preference rather
than a promise of globally optimal play.

The response's `phaseSnapshots` include nullable `localMatchup` and numeric
`localMatchupScore` (the incoming phase's undiscounted contribution; zero at
the root). The matchup contains `teamId`, `carrierId`, `center`, `radius`,
`scenario`, `attackerIds`, `defenderIds`, `goalkeeperIds`, `usableSupportIds`,
`attackingValue`, `numericalValue`, and `value`. These are the exact stored
scoring inputs, including custom radii, rather than a presentation recomputation.
No region is emitted after a goal or without an outfield controller.

The frontend displays a dotted circle and scenario label from the active
snapshot. Green/blue/orange indicates positive/neutral/negative usable numerical
value; `+ GK` indicates a nearby defending goalkeeper. Geometry remains fixed
between phase boundaries, matching the time of the reported counts. Older
responses without matchup data render normally.

### Purposeful off-ball support

[`support_runs.py`](../phases/support_runs.py) adds competing one-player and
two-player support runs behind the next ball controller, at distinct lateral
angles inside the configured matchup radius. Assignment minimizes travel cost
adjusted for player speed. Each target is bounded to an 18 m displacement;
simulation still determines how far a player actually moves during the phase.
Out-of-field anchors are discarded. Receivers, goalkeepers, and the deepest
outfielder in teams of four or more retain their existing assignments. Larger
teams also retain explicit forward/width runs; three-player attacks may compare
those runs against a two-support triangle. Defenders retain their normal
pressing, tracking and cover behavior during evaluation.

`PhaseGenerationPolicy.support_runs` configures reaction time, displacement
and the maximum share of phase candidates reserved for alternatives (25% by
default; zero disables them). Candidates rotate across ball-action types and
terminal shot candidates are preserved. This reserves room for off-ball choices
even when ordinary actions fill the candidate budget.

[`passing_triangles.py`](../analysis/passing_triangles.py) detects connected
triangles among the carrier and usable local support. All three angles must
exceed the configurable minimum (20 degrees by default), and at least one
direction of the support-to-support pass must be feasible and onside. This
third connection is a static opportunity; search simulates subsequent passes
and defensive reactions before accepting a route. Only the best triangle's
quality contributes, avoiding rewards for redundant overlapping triangles.

`PhaseScoringPolicy.passing_triangle_weight` (default 6) rewards the change in
triangle quality, weighted by attacking location. It adds angle/connectivity
value separately from the numerical-advantage component. Repeated unchanged
triangles earn no extra bonus. Snapshots expose `localMatchup.triangles`
(`playerIds`, matching `vertices` in centimeters, `quality`),
`localMatchup.triangleValue`, and the incoming phase's `passingTriangleScore`.
The UI draws two glowing dotted rows around each triangle and fades them out
over two seconds. The same trio does not restart its animation at every phase
boundary. Open-space rectangles use transparent, continuously pulsing dot fills.

## Package responsibilities

| Area | Responsibility |
| --- | --- |
| [`domain/`](../domain/) | Immutable authoritative soccer state. |
| [`spatial/`](../spatial/) | Geometry and movement primitives with no tactical policy. |
| [`analysis/`](../analysis/) | Derived facts and feasible primitive actions for one state. |
| [`phases/`](../phases/) | Coordinated decisions, simulation, validation, scoring, and search adapter. |
| [`planning/beam.py`](../planning/beam.py) | Generic beam mechanics only; no soccer decisions. |
| [`game_engine/`](./) | Stable orchestration, configuration, instruction adapter, and solution selection. |
| [`scheduling/`](../scheduling/) | Presentation timeline after tactics have been selected. |
| [`api/`](../api/) | HTTP validation, error mapping, and response serialization. |
| [`commentary/`](../commentary/) | Optional narration of an already completed plan. |

When adding behavior, put geometry in `spatial`, state-derived soccer facts in
`analysis`, tactical rules in `phases`, and cross-cutting engine orchestration in
this package. Do not put soccer decisions in the API or scheduler.
