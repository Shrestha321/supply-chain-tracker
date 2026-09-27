import { RISK_ALERT_THRESHOLD, riskLevel } from "../config.js";

// Alerts list (spec H/I): every container at or above the delay-risk
// threshold, worst first. v1 is in-dashboard only — no external
// notifications (the Resend email stretch goal hooks in here later).

export default function AlertsList({ alerts, selectedId, onSelect }) {
  return (
    <aside className="alerts" aria-label="Delay risk alerts">
      <h2 className="alerts-title">
        Alerts
        <span className={`alerts-count${alerts.length > 0 ? " active" : ""}`}>
          {alerts.length}
        </span>
      </h2>
      <p className="alerts-sub">
        At or above {Math.round(RISK_ALERT_THRESHOLD * 100)}% predicted delay risk
      </p>

      {alerts.length === 0 ? (
        <p className="alerts-empty">✓ No containers above the threshold right now.</p>
      ) : (
        <ul className="alerts-list">
          {alerts.map((c) => {
            const level = riskLevel(c);
            return (
              <li key={c.id}>
                <button
                  type="button"
                  className={`alert-row${c.id === selectedId ? " selected" : ""}`}
                  onClick={() => onSelect(c.id)}
                >
                  <span className="alert-icon" style={{ color: level.color }} aria-hidden="true">
                    {level.icon}
                  </span>
                  <span className="alert-body">
                    <span className="alert-name">{c.name}</span>
                    <span className="alert-route">
                      {c.origin_port} → {c.destination_port}
                    </span>
                    <span className="alert-meta">
                      {level.label} · {Math.round(c.delay_probability * 100)}% · ~
                      {(c.predicted_delay_hours ?? 0).toFixed(1)} h late
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
