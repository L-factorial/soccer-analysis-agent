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
