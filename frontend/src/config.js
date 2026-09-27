// Delay-risk thresholds and status palette (Phase 7).
//
// Colors are the dataviz skill's fixed status palette (never themed),
// validated for colorblind separation (worst adjacent CVD Delta E 11.3,
// target >= 8). The warning amber is intentionally below 3:1 contrast on
// light surfaces — the required relief: every use pairs the color with an
// icon AND a text label, never color alone.

export const RISK_ALERT_THRESHOLD = 0.7; // >= this: alerts list + red marker
export const RISK_WATCH_THRESHOLD = 0.4; // >= this: amber marker

export const RISK_LEVELS = [
  { key: "critical", label: "High risk", icon: "▲", color: "#d03b3b" },
  { key: "warning", label: "Watch", icon: "◆", color: "#fab219" },
  { key: "good", label: "On track", icon: "●", color: "#0ca30c" },
];

export const NO_PREDICTION_COLOR = "#898781"; // muted gray: "no prediction yet"

export function riskLevel(container) {
  const p = container?.delay_probability;
  if (p == null) return null;
  if (p >= RISK_ALERT_THRESHOLD) return RISK_LEVELS[0];
  if (p >= RISK_WATCH_THRESHOLD) return RISK_LEVELS[1];
  return RISK_LEVELS[2];
}

export function riskColor(container) {
  return riskLevel(container)?.color ?? NO_PREDICTION_COLOR;
}

export function isAlert(container) {
  return (
    container.delay_probability != null &&
    container.delay_probability >= RISK_ALERT_THRESHOLD
  );
}
