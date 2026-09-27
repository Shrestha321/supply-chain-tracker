# simulator/

Telemetry generator — moves containers along their routes (GPS position,
temperature, status) and POSTs each point to the API's `/telemetry`
endpoint over HTTP, like a real AIS/IoT feed. Never touches the database.

**State comes from the API** (`GET /routes` + `GET /containers`): each
container's DB position is projected onto its route to recover progress,
so the simulator is restart-safe (resumes where containers actually are),
works against any deployment, and needs no manifest file. Delivered
containers are skipped — refresh with `backend/seed.py --reset`.

## Run locally

1. API running: from `backend/`, `.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
2. DB seeded once: from `backend/`, `.venv\Scripts\python.exe seed.py`
3. Simulate:

```
C:\dev\supply-chain-tracker\backend\.venv\Scripts\python.exe C:\dev\supply-chain-tracker\simulator\simulate.py
```

Useful flags: `--ticks 3 --interval 1` (short smoke test),
`--hours-per-tick 4` (faster voyages),
`--api-url https://<your-api>.onrender.com` (feed a deployed stack).

Each tick = 2 simulated hours per 5 real seconds by default; ships move at
~34 km/h. Random delay events (0.5% chance/container/tick, 12–48 simulated
hours) flip containers to `delayed`; arrival posts a final `delivered`
point and the container goes quiet. Transport errors are retried twice,
then logged and skipped — one dropped connection never kills the feed.

## On Render

The `sct-simulator` worker (see `render.yaml`) runs this continuously
against the deployed API: seed → simulate → reset → loop.
