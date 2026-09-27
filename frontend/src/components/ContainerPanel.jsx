// Side panel for the selected container (spec section H).
// Phase 5: snapshot basics + latest prediction when present.
// Phase 7 adds the temperature-history chart and risk badge.

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
          <p>Click a marker on the map to see its route, status, and predicted delay.</p>
        </div>
      </aside>
    );
  }

  const prediction = detail.latest_prediction;

  return (
    <aside className="panel">
      <div className="panel-header">
        <h2>{detail.name}</h2>
        <button className="close-btn" onClick={onClose} aria-label="Close panel">
          ✕
        </button>
      </div>

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

      {detail.telemetry.length > 0 && (
        <>
          <h3>Latest temperature</h3>
          <p className="prediction-none">
            {detail.telemetry[0].temperature != null
              ? `${detail.telemetry[0].temperature.toFixed(1)} °C at ${fmtTime(detail.telemetry[0].timestamp)}`
              : "no temperature reading"}
          </p>
        </>
      )}
    </aside>
  );
}
