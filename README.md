# Supply Chain Container Tracking & Delay Prediction

Tracks shipping containers on a map and predicts delivery delays.
When predicted delay risk crosses a threshold, the dashboard raises an alert.

## Architecture

| Layer      | Tech                                          |
|------------|-----------------------------------------------|
| Frontend   | React + Vite + Leaflet.js (deployed to Vercel) |
| Backend    | Python FastAPI (deployed to Render)            |
| Database   | PostgreSQL (Supabase or Render free tier)      |
| Prediction | scikit-learn — baseline linear regression first, then RandomForest/XGBoost |

## Repository layout

```
supply-chain-tracker/
├── backend/          # FastAPI app (API + in-process prediction scheduler)
│   └── app/
│       ├── main.py       # App entrypoint
│       ├── db.py         # DB engine/session (Phase 2)
│       ├── models.py     # SQLAlchemy tables (Phase 2)
│       ├── schemas.py    # Pydantic request/response models (Phase 2)
│       └── routers/      # Endpoint modules (Phase 2–4)
├── prediction/       # Training + batch inference scripts (write to predictions table)
├── simulator/        # Telemetry generator: fake containers on fixed routes (Phase 3)
├── data/             # Static reference data: ports.json with lat/lng (Phase 3)
└── frontend/         # React + Vite + Leaflet dashboard (Phase 5)
```

## Build phases

1. [x] Project scaffolding + folder structure + Git init
2. [ ] Database schema + connect backend
3. [ ] Telemetry simulator + POST /telemetry end to end
4. [ ] GET endpoints returning real data
5. [ ] Frontend map with live container data
6. [ ] Baseline (linear regression) prediction pipeline
7. [ ] Delay-risk coloring + alerts list
8. [ ] Better model, polish, deploy

## Local development (filled in as phases complete)

Backend: `cd backend`, create venv, `pip install -r requirements.txt`, `uvicorn app.main:app --reload`
Frontend: `cd frontend`, `npm install`, `npm run dev`
