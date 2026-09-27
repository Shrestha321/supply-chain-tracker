import { useCallback, useEffect, useMemo, useState } from "react";
import { getContainer, getContainers, getRoutes, API_URL } from "./api.js";
import { isAlert } from "./config.js";
import MapView from "./components/MapView.jsx";
import AlertsList from "./components/AlertsList.jsx";
import ContainerPanel from "./components/ContainerPanel.jsx";
import "./App.css";

const REFRESH_MS = 5000; // spec section J: polling is enough at this scale

export default function App() {
  const [containers, setContainers] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  const refreshContainers = useCallback(async () => {
    try {
      setContainers(await getContainers());
      setError(null);
    } catch (err) {
      setError(`API unreachable at ${API_URL} — is the backend running? (${err.message})`);
    }
  }, []);

  // Initial load: routes once (static reference data), containers immediately.
  useEffect(() => {
    refreshContainers();
    getRoutes().then(setRoutes).catch(() => setRoutes([]));
  }, [refreshContainers]);

  // Polling loop.
  useEffect(() => {
    const timer = setInterval(refreshContainers, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refreshContainers]);

  // Keep the selected container's detail panel live: refetch whenever the
  // container list refreshes (every 5s) or the selection changes.
  useEffect(() => {
    let cancelled = false;
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    getContainer(selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedId, containers]);

  // Alerts = containers at/above the risk threshold, worst first.
  const alerts = useMemo(
    () =>
      containers
        .filter(isAlert)
        .sort((a, b) => b.delay_probability - a.delay_probability),
    [containers]
  );

  const activeCount = containers.filter((c) => c.status !== "delivered").length;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Container Tracker</h1>
        <span className="header-stats">
          {containers.length} containers · {activeCount} active · {routes.length} routes
        </span>
        {alerts.length > 0 && (
          <span className="header-alert" role="status">
            ⚠ {alerts.length} above delay-risk threshold
          </span>
        )}
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="app-layout">
        <AlertsList alerts={alerts} selectedId={selectedId} onSelect={setSelectedId} />
        <MapView
          containers={containers}
          routes={routes}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        <ContainerPanel detail={detail} onClose={() => setSelectedId(null)} />
      </main>
    </div>
  );
}
