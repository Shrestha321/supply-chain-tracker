// Side panel for the selected container (spec section H): route, current
// status, predicted delay, temperature history chart, plus the Phase 7
// risk badge (icon + label + number — never color alone).

import { riskLevel } from "../config.js";
import TemperatureChart from "./TemperatureChart.jsx";

function fmtCoord(lat, lng) {
  if (lat == null || lng == null) return "—";
  return `${lat.toFixed(3)}, ${lng.toFixed(3)}`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function ContainerPanel({ detail, onClose }) {
  if (!detail) {
    return (
      <aside className="panel">
        <div className="panel-empty">
          <h2>No container selected</h2>
          <p>Click a marker on the map — or an alert — to see its route, status, predicted delay, and temperature history.</p>
        </div>
      </aside>
    );
  }

  const prediction = detail.latest_prediction;
  const level = riskLevel(detail);

  return (
    <aside className="panel">
      <div className="panel-header">
        <h2>{detail.name}</h2>
        <button className="close-btn" onClick={onClose} aria-label="Close panel">
          ✕
        </button>
      </div>

      {level && (
        <div className={`risk-badge risk-${level.key}`}>
          <span className="risk-icon" style={{ color: level.color }} aria-hidden="true">
            {level.icon}
          </span>
          <span>
            {level.label} · {Math.round(detail.delay_probability * 100)}% delay risk
          </span>
        </div>
      )}

      <dl className="panel-facts">
        <div>
          <dt>Status</dt>
          <dd>
            <span className={`status-badge status-${detail.status}`}>{detail.status}</span>
          </dd>
        </div>
        <div>
          <dt>Route</dt>
          <dd>
            {detail.origin_port} → {detail.destination_port}
          </dd>
        </div>
        <div>
          <dt>Position</dt>
          <dd>{fmtCoord(detail.current_lat, detail.current_lng)}</dd>
        </div>
        <div>
          <dt>Last updated</dt>
          <dd>{fmtTime(detail.last_updated)}</dd>
        </div>
        <div>
          <dt>Telemetry points</dt>
          <dd>{detail.telemetry.length} (most recent first)</dd>
        </div>
      </dl>

      <h3>Delay prediction</h3>
      {prediction ? (
        <dl className="panel-facts">
          <div>
            <dt>Predicted delay</dt>
            <dd>{prediction.predicted_delay_hours.toFixed(1)} h</dd>
          </div>
          <div>
            <dt>Delay probability</dt>
            <dd>{(prediction.delay_probability * 100).toFixed(0)}%</dd>
          </div>
          <div>
            <dt>Generated</dt>
            <dd>{fmtTime(prediction.generated_at)}</dd>
          </div>
        </dl>
      ) : (
        <p className="prediction-none">
          No prediction yet — the model pipeline (Phase 6) writes these periodically.
        </p>
      )}

      <h3>Temperature history</h3>
      <TemperatureChart telemetry={detail.telemetry} />
    </aside>
  );
}
