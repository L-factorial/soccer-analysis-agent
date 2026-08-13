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
