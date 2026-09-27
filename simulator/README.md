# simulator/

Telemetry generator — moves fake containers along fixed routes (GPS
position, temperature, status) and POSTs each point to the API's
`/telemetry` endpoint over HTTP, like a real AIS/IoT feed. It never
touches the database directly.

## Prerequisites

1. API running: from `backend/`, `.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
2. DB seeded: from `backend/`, `.venv\Scripts\python.exe seed.py`
   (creates routes + containers and writes `data/sim_manifest.json`)

## Run

```
C:\dev\supply-chain-tracker\backend\.venv\Scripts\python.exe C:\dev\supply-chain-tracker\simulator\simulate.py
```

Useful flags: `--ticks 3 --interval 1` (short smoke test),
`--hours-per-tick 4` (faster voyages), `--api-url http://localhost:8000`.

Each tick = 2 simulated hours by default; ships move at ~34 km/h, so a
Shanghai→Rotterdam voyage finishes in ~23 minutes of wall-clock time.
Random delay events (0.5% chance/container/tick, 12–48 simulated hours)
put containers into `delayed` status; containers post a final `delivered`
point and then go quiet.
