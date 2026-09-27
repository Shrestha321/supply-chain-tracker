import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import {
  NO_PREDICTION_COLOR,
  RISK_ALERT_THRESHOLD,
  RISK_LEVELS,
  RISK_WATCH_THRESHOLD,
  riskColor,
  riskLevel,
} from "../config.js";

// Phase 7: marker color = delay risk (green/amber/red from the validated
// status palette); gray when no prediction exists yet. The legend labels
// every color, and popups repeat risk as text — color never carries
// meaning alone.

export default function MapView({ containers, routes, selectedId, onSelect }) {
  return (
    <div className="map-wrap">
      <MapContainer
        center={[22, 30]}
        zoom={3}
        minZoom={2}
        worldCopyJump
        className="map"
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Route polylines: dashed gray so risk-colored markers dominate. */}
        {routes.map((route) => (
          <Polyline
            key={route.id}
            positions={route.waypoints.map((w) => [w.lat, w.lng])}
            pathOptions={{ color: "#94a3b8", weight: 2, dashArray: "6 6", opacity: 0.75 }}
          />
        ))}

        {containers
          .filter((c) => c.current_lat != null && c.current_lng != null)
          .map((c) => {
            const level = riskLevel(c);
            return (
              <CircleMarker
                key={c.id}
                center={[c.current_lat, c.current_lng]}
                radius={c.id === selectedId ? 10 : 7}
                pathOptions={{
                  color: c.id === selectedId ? "#0f172a" : "#ffffff",
                  weight: c.id === selectedId ? 2.5 : 1.5,
                  fillColor: riskColor(c),
                  fillOpacity: 0.95,
                }}
                eventHandlers={{ click: () => onSelect(c.id) }}
              >
                <Popup>
                  <b>{c.name}</b>
                  <br />
                  {c.origin_port} → {c.destination_port}
                  <br />
                  status: {c.status}
                  <br />
                  {level
                    ? `risk: ${level.icon} ${level.label} · ${Math.round(
                        c.delay_probability * 100
                      )}% · ~${(c.predicted_delay_hours ?? 0).toFixed(0)} h late`
                    : "risk: no prediction yet"}
                </Popup>
              </CircleMarker>
            );
          })}
      </MapContainer>

      <div className="map-legend" aria-label="Delay risk legend">
        <span className="legend-title">Delay risk</span>
        {RISK_LEVELS.map((l) => (
          <span key={l.key} className="legend-item">
            <span className="legend-swatch" style={{ background: l.color }} aria-hidden="true" />
            <span aria-hidden="true">{l.icon}</span> {l.label}
          </span>
        ))}
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: NO_PREDICTION_COLOR }} aria-hidden="true" />
          ○ No prediction
        </span>
        <span className="legend-thresholds">
          alert ≥ {Math.round(RISK_ALERT_THRESHOLD * 100)}% · watch ≥ {Math.round(RISK_WATCH_THRESHOLD * 100)}%
        </span>
      </div>
    </div>
  );
}
