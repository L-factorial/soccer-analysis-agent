# Soccer Analysis Agent

- Given a soccer field configuration—including player positions, ball position, teams, goals, and open spaces—the simulation engine searches for a route to goal.
- It models an attack as tactical phases containing passes, dribbles, shots, supporting runs, and defensive reactions.
- Deterministic simulation, tactical scoring, and bounded beam search select goal-scoring sequences and distinct alternatives.
- An asynchronous AI layer generates continuous commentary and detailed analysis for each scheduled route.
- Directing beam search through free-form prompt instructions is a work in progress; currently, only a limited deterministic keyword adapter is supported.

## Technical documentation

- [Backend architecture](backend/ARCHITECTURE.md) — request flow, planner,
  tactical phases, simulation, scoring policies, deterministic beam search,
  current search configuration, scheduler, incoming field JSON, immutable game
  state mapping, and the frontend animation-response JSON.
- [Game-engine code guide](backend/app/game_engine/README.md) — the separated
  deterministic engine boundary, open-space algorithm, package ownership, and
  direct links to implementation files.
- [RAG ingestion and query API](backend/app/rag/API.md) — embedding-provider
  boundary, ingestion and Qdrant persistence, query retrieval, response
  contracts, proximity scoring, configuration, and errors.

The project is a monorepo containing an Expo/React Native frontend and a FastAPI
backend.

## Project setup

### Frontend

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

### Backend

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

### Backend with Docker (optional)

Native Python development above does not require Docker. To run the container,
use Docker Compose from the repository root. Create `backend/.env` from
`backend/.env.example` if it does not already exist, then run:

```bash
docker compose up --build -d --wait
```

The backend is available at `http://127.0.0.1:8000`. Stop it with
`docker compose down`. This deployment does not configure vector database storage.
See [container setup and GitHub image builds](deploy/README.md) for configuration
and validation details. GitHub Actions publishes tested images on pushes to
`main` and deploys the tested image to the droplet with health checks and rollback.

## Planning behavior

Planning uses the local rules engine, tactical phase simulation, scoring policy,
and bounded beam search. Prompt-directed search remains experimental; currently,
a small deterministic keyword adapter can adjust selected search and scoring
weights without allowing an external model to control simulation decisions.

## Optional commentary prototype

The completed, scheduled plan can optionally be sent to an OpenAI model for
phase-aligned commentary. This post-processing cannot change the plan and fails
open: analysis still returns normally if commentary generation is disabled or
fails. Copy `backend/.env.example` to `backend/.env`, add the API key, and set:

```dotenv
SOCCER_COMMENTARY_ENABLED=true
OPENAI_API_KEY=your-key
```

Restart the backend after changing these settings. Analysis returns the
simulation first while a second request generates commentary. When commentary
arrives, playback resets; press **Play** to hear phase-aligned narration. Pause
or Reset also stops speech. The spoken prototype currently uses the browser
speech engine and is therefore web-only.

## Basic screen and field information

The main screen provides field-configuration controls, a tactical-instruction
input, Analyze/Play/Reset controls, a selector for alternative plans, animation
playback, phase diagnostics, and asynchronous commentary status. Hovering over
the commentary indicator displays the generated text without reducing the
available field area.

### Field coordinate system

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
