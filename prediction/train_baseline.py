"""Train the BASELINE model (spec G: linear first to prove the pipeline,
fancier model only after — and only with sign-off, per spec L).

- predicted_delay_hours: LinearRegression on the four shared features.
- delay_probability: LogisticRegression — still a linear model, but it
  outputs a proper 0-1 probability via the sigmoid instead of a clipped
  regression value.

Reports honest held-out test metrics and saves both models (plus the
feature-order contract) to prediction/model_baseline.joblib.

Run:  backend\\.venv\\Scripts\\python.exe prediction\\train_baseline.py
"""

from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score, roc_auc_score
from sklearn.model_selection import train_test_split

from features import DELAY_THRESHOLD_HOURS, FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "training_voyages.csv"
MODEL_PATH = Path(__file__).resolve().parent / "model_baseline.joblib"


def main() -> None:
    if not DATA.exists():
        raise SystemExit(f"{DATA} not found — run prediction/make_dataset.py first")

    df = pd.read_csv(DATA)
    print(f"loaded {len(df)} voyages ({df['delayed'].mean():.1%} delayed > {DELAY_THRESHOLD_HOURS}h)")

    X = df[FEATURE_COLUMNS]
    y_hours = df["delay_hours"]
    y_delayed = df["delayed"]

    X_tr, X_te, h_tr, h_te, d_tr, d_te = train_test_split(
        X, y_hours, y_delayed,
        test_size=0.2, random_state=42, stratify=y_delayed,
    )

    hours_model = LinearRegression().fit(X_tr, h_tr)
    prob_model = LogisticRegression(max_iter=1000).fit(X_tr, d_tr)

    h_pred = hours_model.predict(X_te)
    d_proba = prob_model.predict_proba(X_te)[:, 1]
    d_pred = (d_proba >= 0.5).astype(int)

    print("\n--- held-out test metrics (baseline) ---")
    print(f"delay hours   MAE: {mean_absolute_error(h_te, h_pred):.2f} h   R2: {r2_score(h_te, h_pred):.3f}")
    print(f"delayed flag  accuracy: {accuracy_score(d_te, d_pred):.3f}   ROC-AUC: {roc_auc_score(d_te, d_proba):.3f}")

    print("\nhours-model coefficients (interpretability is the baseline's one advantage):")
    for name, coef in zip(FEATURE_COLUMNS, hours_model.coef_):
        print(f"  {name:>24}: {coef:+.4f}")

    joblib.dump(
        {
            "hours_model": hours_model,
            "prob_model": prob_model,
            "feature_columns": FEATURE_COLUMNS,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "n_rows": len(df),
        },
        MODEL_PATH,
    )
    print(f"\nsaved -> {MODEL_PATH}")


if __name__ == "__main__":
    main()
