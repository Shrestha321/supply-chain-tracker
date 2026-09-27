import { useMemo, useRef, useState } from "react";

// Single-series temperature history: time-trend job -> line chart. One
// series, so no legend box (the panel heading names it). Palette roles per
// the dataviz skill: series-1 blue #2a78d6, hairline grid #e1e0d9,
// axis/baseline #c3c2b7, muted labels #898781, ink #0b0b0b. Crosshair +
// tooltip ship by default; the <details> table is the accessible alternate
// view. Text wears ink tokens, never the series color.

const W = 320;
const H = 140;
const PAD = { top: 8, right: 8, bottom: 20, left: 30 };

const C = {
  series: "#2a78d6",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  muted: "#898781",
};

const fmtClock = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export default function TemperatureChart({ telemetry }) {
  // API returns telemetry newest-first; charts read oldest -> newest.
  const points = useMemo(
    () =>
      telemetry
        .filter((t) => t.temperature != null && t.timestamp)
        .map((t) => ({ time: new Date(t.timestamp).getTime(), temp: t.temperature }))
        .sort((a, b) => a.time - b.time)
        .slice(-200),
    [telemetry]
  );

  const [hoverIdx, setHoverIdx] = useState(null);
  const svgRef = useRef(null);

  const geom = useMemo(() => {
    if (points.length < 2) return null;
    const tMin = points[0].time;
    const tMax = points[points.length - 1].time;
    const temps = points.map((p) => p.temp);
    let yMin = Math.min(...temps);
    let yMax = Math.max(...temps);
    if (yMax - yMin < 1) {
      yMin -= 0.5;
      yMax += 0.5; // flat series: pad so the line isn't degenerate
    }
    const plotW = W - PAD.left - PAD.right;
    const plotH = H - PAD.top - PAD.bottom;
    const x = (t) => PAD.left + ((t - tMin) / (tMax - tMin || 1)) * plotW;
    const y = (v) => PAD.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    const path = points
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.time).toFixed(1)},${y(p.temp).toFixed(1)}`)
      .join(" ");
    return { x, y, path, tMin, tMax, plotW, yTicks: [yMin, (yMin + yMax) / 2, yMax] };
  }, [points]);

  if (!geom) {
    return <p className="chart-empty">Not enough temperature history yet (needs ≥ 2 readings).</p>;
  }

  function handleMove(e) {
    const rect = svgRef.current.getBoundingClientRect();
    // client px -> viewBox units (the SVG scales responsively)
    const mx = ((e.clientX - rect.left) / rect.width) * W;
    const ratio = Math.max(0, Math.min(1, (mx - PAD.left) / geom.plotW));
    setHoverIdx(Math.round(ratio * (points.length - 1)));
  }

  const hp = hoverIdx != null ? points[hoverIdx] : null;

  return (
    <div className="chart-wrap">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="temp-chart"
        role="img"
        aria-label={`Temperature history: ${points.length} readings from ${fmtClock(geom.tMin)} to ${fmtClock(geom.tMax)}, range ${Math.min(...points.map((p) => p.temp)).toFixed(1)} to ${Math.max(...points.map((p) => p.temp)).toFixed(1)} degrees Celsius`}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIdx(null)}
      >
        {geom.yTicks.map((v, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={geom.y(v)} y2={geom.y(v)} stroke={C.grid} strokeWidth={1} />
            <text x={PAD.left - 5} y={geom.y(v) + 3} textAnchor="end" fontSize={9} fill={C.muted}>
              {v.toFixed(1)}°
            </text>
          </g>
        ))}
        <line x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} stroke={C.axis} strokeWidth={1} />
        <text x={PAD.left} y={H - 6} fontSize={9} fill={C.muted}>{fmtClock(geom.tMin)}</text>
        <text x={W - PAD.right} y={H - 6} fontSize={9} fill={C.muted} textAnchor="end">{fmtClock(geom.tMax)}</text>

        <path d={geom.path} fill="none" stroke={C.series} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {hp && (
          <g>
            <line x1={geom.x(hp.time)} x2={geom.x(hp.time)} y1={PAD.top} y2={H - PAD.bottom} stroke={C.axis} strokeWidth={1} />
            <circle cx={geom.x(hp.time)} cy={geom.y(hp.temp)} r={4} fill={C.series} stroke="#ffffff" strokeWidth={2} />
          </g>
        )}
      </svg>

      {hp && (
        <div
          className="chart-tooltip"
          style={{
            left: `${(geom.x(hp.time) / W) * 100}%`,
            top: `${(geom.y(hp.temp) / H) * 100}%`,
          }}
        >
          <b>{hp.temp.toFixed(1)} °C</b>
          <span>{new Date(hp.time).toLocaleString()}</span>
        </div>
      )}

      <details className="chart-table">
        <summary>Show data (last 10 readings)</summary>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>°C</th>
            </tr>
          </thead>
          <tbody>
            {[...points].slice(-10).reverse().map((p, i) => (
              <tr key={i}>
                <td>{new Date(p.time).toLocaleString()}</td>
                <td>{p.temp.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
