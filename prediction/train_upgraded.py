"""Train the UPGRADED model (Phase 8, user-approved): RandomForest over the
baseline linear models.

Why RandomForest and not XGBoost: at 3k rows x 4 features the two are within
noise of each other; RF ships with scikit-learn (no new dependency, no extra
native-binary install step on Render), trains in seconds, and is robust to
feature scaling. XGBoost's edge appears at much larger datasets.

Same split and seed as train_baseline.py, so metrics are directly
comparable. Saves prediction/model_upgraded.joblib with the same bundle
contract as the baseline — run_predictions.py is model-agnostic.

Run:  backend\\.venv\\Scripts\\python.exe prediction\\train_upgraded.py
"""

from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score, roc_auc_score
from sklearn.model_selection import train_test_split

from features import DELAY_THRESHOLD_HOURS, FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "training_voyages.csv"
BASELINE_PATH = Path(__file__).resolve().parent / "model_baseline.joblib"
MODEL_PATH = Path(__file__).resolve().parent / "model_upgraded.joblib"


def main() -> None:
    if not DATA.exists():
        raise SystemExit(f"{DATA} not found — run prediction/make_dataset.py first")

    df = pd.read_csv(DATA)
    print(f"loaded {len(df)} voyages ({df['delayed'].mean():.1%} delayed > {DELAY_THRESHOLD_HOURS}h)")

    X = df[FEATURE_COLUMNS]
    y_hours = df["delay_hours"]
    y_delayed = df["delayed"]

    # Identical split to train_baseline.py -> apples-to-apples comparison.
    X_tr, X_te, h_tr, h_te, d_tr, d_te = train_test_split(
        X, y_hours, y_delayed,
        test_size=0.2, random_state=42, stratify=y_delayed,
    )

    hours_model = RandomForestRegressor(
        n_estimators=300, min_samples_leaf=2, random_state=42, n_jobs=-1
    ).fit(X_tr, h_tr)
    prob_model = RandomForestClassifier(
        n_estimators=300, min_samples_leaf=2, random_state=42, n_jobs=-1
    ).fit(X_tr, d_tr)

    h_pred = hours_model.predict(X_te)
    d_proba = prob_model.predict_proba(X_te)[:, 1]
    d_pred = (d_proba >= 0.5).astype(int)

    print("\n--- held-out test metrics: RandomForest (upgraded) ---")
    print(f"delay hours   MAE: {mean_absolute_error(h_te, h_pred):.2f} h   R2: {r2_score(h_te, h_pred):.3f}")
    print(f"delayed flag  accuracy: {accuracy_score(d_te, d_pred):.3f}   ROC-AUC: {roc_auc_score(d_te, d_proba):.3f}")

    if BASELINE_PATH.exists():
        base = joblib.load(BASELINE_PATH)
        bh = base["hours_model"].predict(X_te)
        bp = base["prob_model"].predict_proba(X_te)[:, 1]
        print("\n--- baseline (linear) on the SAME split, for comparison ---")
        print(f"delay hours   MAE: {mean_absolute_error(h_te, bh):.2f} h   R2: {r2_score(h_te, bh):.3f}")
        print(f"delayed flag  accuracy: {accuracy_score(d_te, (bp >= 0.5).astype(int)):.3f}   ROC-AUC: {roc_auc_score(d_te, bp):.3f}")

    # The nonlinear congestion-queue term should dominate importances —
    # that's the structure the linear baseline could not represent.
    print("\nRF feature importances (hours model):")
    for name, imp in sorted(
        zip(FEATURE_COLUMNS, hours_model.feature_importances_), key=lambda t: -t[1]
    ):
        print(f"  {name:>24}: {imp:.3f}")

    joblib.dump(
        {
            "hours_model": hours_model,
            "prob_model": prob_model,
            "feature_columns": FEATURE_COLUMNS,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "n_rows": len(df),
            "model_kind": "random_forest",
        },
        MODEL_PATH,
    )
    print(f"\nsaved -> {MODEL_PATH}")


if __name__ == "__main__":
    main()
