import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

// Colors by operational status for Phase 5. Phase 7 switches marker color
// to delay-risk (green/amber/red) driven by latest_prediction.
const STATUS_COLORS = {
  in_transit: "#2563eb",
  at_port: "#64748b",
  delayed: "#f59e0b",
  delivered: "#16a34a",
};
const FALLBACK_COLOR = "#334155";

export default function MapView({ containers, routes, selectedId, onSelect }) {
  return (
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

      {/* Route polylines: dashed gray so markers stay visually dominant. */}
      {routes.map((route) => (
        <Polyline
          key={route.id}
          positions={route.waypoints.map((w) => [w.lat, w.lng])}
          pathOptions={{ color: "#94a3b8", weight: 2, dashArray: "6 6", opacity: 0.75 }}
        />
      ))}

      {containers
        .filter((c) => c.current_lat != null && c.current_lng != null)
        .map((c) => (
          <CircleMarker
            key={c.id}
            center={[c.current_lat, c.current_lng]}
            radius={c.id === selectedId ? 10 : 7}
            pathOptions={{
              color: c.id === selectedId ? "#0f172a" : "#ffffff",
              weight: c.id === selectedId ? 2.5 : 1.5,
              fillColor: STATUS_COLORS[c.status] ?? FALLBACK_COLOR,
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
            </Popup>
          </CircleMarker>
        ))}
    </MapContainer>
  );
}
