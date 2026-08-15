# Soccer Analysis Agent

Minimal monorepo containing an Expo frontend and a FastAPI backend.

## Frontend

Requires Node.js 22.13 or newer.

```bash
cd frontend
npm install
```

Start Expo:

```bash
npm start
```

Run the frontend directly in a web browser:

```bash
npm run web
```

From the Expo development server, you can also choose an iOS simulator or an
Android emulator when those development tools are installed.

## Backend

Create and activate a virtual environment, then install the dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

Test the health endpoint in another terminal:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Feature-flagged agentic planning

The default analysis path is deterministic. It does not call an LLM and keeps
using the tactical instruction keyword adapter.

Planning can be selected explicitly with `SOCCER_PLANNING_MODE`:

- `DETERMINISTIC` runs only the rules engine and keyword adapter.
- `LLM_INTENT` uses one structured LLM intent followed by deterministic search.
- `LLM_TOOL_AGENT` lets a bounded LLM loop run deterministic searches and select
  a requested plan plus up to two explained alternatives.

To enable the bounded agentic path, install the backend requirements and set:

```bash
export OPENAI_API_KEY="your-api-key"
export SOCCER_AGENTIC_PLANNING_ENABLED="true"
export SOCCER_PLANNING_MODE="LLM_INTENT"
export SOCCER_AGENT_MODEL="gpt-5-mini"
uvicorn app.main:app --reload
```

Optional settings:

- `SOCCER_AGENT_TIMEOUT_SECONDS` defaults to `8`.
- `SOCCER_AGENT_MAXIMUM_REVISIONS` defaults to `1` and is capped at one.
- `SOCCER_TOOL_AGENT_MAX_TOOL_CALLS` defaults to `8`.
- `SOCCER_TOOL_AGENT_MAX_ITERATIONS` defaults to `6`.
- `SOCCER_TOOL_MAX_BEAM_WIDTH` defaults to and is capped at `30`.

`SOCCER_AGENTIC_PLANNING_ENABLED` remains supported for compatibility. When
`SOCCER_PLANNING_MODE` is set, the explicit mode takes precedence.

The frontend sends `tacticalInstruction` with the field configuration. With
the flag enabled and a non-empty instruction, the backend performs this bounded
loop:

1. Build a compact tactical observation from deterministic analysis.
2. Ask OpenAI for a Pydantic-validated `TacticalIntent` using Structured
   Outputs.
3. Remove unknown player, space, and action references.
4. Translate the intent into deterministic search and scoring policies.
5. Run the existing rules engine and beam search.
6. Evaluate goal completion and instruction alignment.
7. Make at most one LLM revision and one additional engine run.

The LLM never generates raw animation events or overrides movement, offside,
goalkeeper, interception, or validation rules. Any missing SDK/API key, timeout,
API failure, or invalid model response automatically falls back to deterministic
planning. Response diagnostics report `agentMode`, `agentAttempts`, the validated
intent, evaluation, and fallback reason.

### Open spaces in tactical instructions

The LLM observation contains a unified `spaces` catalog. It includes spaces
drawn and labeled in the UI (`USER_DEFINED`) and spaces detected by the backend
(`DYNAMIC`). Each entry provides its stable ID, editable name, geometry,
attacking-relative lateral channel and field third, nearest attacker, and nearest
defender distance. The LLM sees the human-readable name but must return the
stable ID in `preferredSpaceIds`; the backend removes unknown IDs.

For example, if a UI space named `Left wing opening` has ID `OpenSpace1`, the
instruction can say `Attack through the Left wing opening`. The validated intent
should reference `OpenSpace1`, which is rewarded during beam search and checked
again during deterministic plan evaluation.

## Field coordinate system

Frontend field and animation models use centimeters in a standard
`12000 cm × 9000 cm` field:

- `(0, 0)` is the bottom-left corner in the horizontal tactical view.
- `x` runs along the 120-meter field length.
- `y` runs along the 90-meter field width.
- On narrow/mobile screens, the rendered field is the horizontal view rotated
  90 degrees anticlockwise. Stored coordinates do not change.

Backend animation responses should use the same centimeter coordinates.
Screen-coordinate conversion is kept at the frontend rendering and input
boundaries.
