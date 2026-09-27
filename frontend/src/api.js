// Thin fetch wrapper around the backend API.
// VITE_API_URL lets the Vercel deployment point at the Render backend
// without a code change; defaults to the local dev server.

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

async function getJson(path) {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: HTTP ${res.status}`);
  }
  return res.json();
}

export const getContainers = () => getJson("/containers");
export const getRoutes = () => getJson("/routes");
export const getContainer = (id) => getJson(`/containers/${id}`);

// A prediction 404 means "none generated yet" — an expected state until
// Phase 6, so callers get null instead of an exception.
export async function getPrediction(containerId) {
  try {
    return await getJson(`/containers/${containerId}/prediction`);
  } catch {
    return null;
  }
}

export { API_URL };
