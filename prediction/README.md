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

1. `make_dataset.py` — samples synthetic voyages (default 3000, `--rows N`)
   from the seeded routes into `data/training_voyages.csv` using a known
   ground-truth delay process (weather drag + nonlinear port queue + noise).
2. `train_baseline.py` — LinearRegression (delay hours) + LogisticRegression
   (delay probability). Prints held-out MAE/R²/accuracy/ROC-AUC and saves
   `model_baseline.joblib` (gitignored — regenerate, don't commit binaries).
3. `train_upgraded.py` — RandomForest regressor + classifier on the SAME
   split/seed; prints a side-by-side comparison and saves
   `model_upgraded.joblib` (same bundle contract).
4. `run_predictions.py` — batch inference for every active container;
   appends rows (latest wins via the API). `--model auto|baseline|upgraded`
   (auto prefers the upgraded model when trained); `--loop 300` reruns every
   5 min (spec F's polling job without any infra).

## Shared code

`features.py` computes all four features (distance remaining, weather
severity, port congestion, avg transit hours) and is imported by BOTH
training-data generation and inference — training/serving skew is
impossible by construction. Weather and congestion are deterministic
mocks per (route, day) until Phase 8 swaps in OpenWeatherMap.

## Model upgrade — done (Phase 8), and the honest finding

RandomForest was chosen over XGBoost: at this data size they perform
within noise, RF needs no new dependency (ships with scikit-learn), and
no feature scaling. Measured on the identical held-out split, RF **ties**
the linear baseline (both MAE ≈ 2.4 h, R² ≈ 0.75): the synthetic ground
truth injects N(0, 3h) noise, so the theoretical MAE floor is ≈ 2.39 h and
both models sit on it — the nonlinear queue term (~1 h of curvature) is
buried under the noise. RF ships as the default anyway because its
inductive bias matches real port queueing (nonlinear tail risk) and it can
exploit real weather/AIS data when the mocks are swapped. Re-run both
trainers any time to reproduce the comparison; `--model baseline` A/Bs
against it in production.
