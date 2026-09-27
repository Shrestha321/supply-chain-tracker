# prediction/

Delay-prediction pipeline: trains on a synthetic voyage dataset and writes
`predicted_delay_hours` + `delay_probability` rows to the `predictions`
table. Deliberately NOT part of the API process (spec section G) — it's a
batch script, run on demand or on an interval.

All scripts run with the **backend venv** (shares DB/session code, one
Python environment):

```
C:\dev\supply-chain-tracker\backend\.venv\Scripts\python.exe <script>
```

## Pipeline order

1. `make_dataset.py` — samples ~3000 synthetic voyages from the seeded
   routes into `data/training_voyages.csv` using a known ground-truth
   delay process (weather drag + nonlinear port queue + noise).
2. `train_baseline.py` — LinearRegression (delay hours) + LogisticRegression
   (delay probability). Prints held-out MAE/R²/accuracy/ROC-AUC and saves
   `model_baseline.joblib` (gitignored — regenerate, don't commit binaries).
3. `run_predictions.py` — batch inference for every active container;
   appends rows (latest wins via the API). `--loop 300` reruns every 5 min
   (spec F's polling job without any infra).

## Shared code

`features.py` computes all four features (distance remaining, weather
severity, port congestion, avg transit hours) and is imported by BOTH
training-data generation and inference — training/serving skew is
impossible by construction. Weather and congestion are deterministic
mocks per (route, day) until Phase 8 swaps in OpenWeatherMap.

## Upgrading the model (Phase 8, needs sign-off per spec L)

Replace the two estimators in `train_baseline.py` with
RandomForest/XGBoost; `run_predictions.py` and the DB contract don't
change — that's the point of doing the baseline first.
