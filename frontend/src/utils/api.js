import axios from "axios";

const BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:9000";
const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:9000";

const api = axios.create({ baseURL: BASE_URL, timeout: 15000 });

// Services
export const getServicesHealth = () => api.get("/api/services/health").then(r => r.data);
export const getServices = () => api.get("/api/services").then(r => r.data);

// Chaos
export const injectLatency = (payload) => api.post("/api/chaos/latency", payload).then(r => r.data);
export const injectErrors = (payload) => api.post("/api/chaos/errors", payload).then(r => r.data);
export const injectPartition = (payload) => api.post("/api/chaos/partition", payload).then(r => r.data);
export const injectResources = (payload) => api.post("/api/chaos/resources", payload).then(r => r.data);
export const killService = (payload) => api.post("/api/chaos/kill", payload).then(r => r.data);
export const runScenario = (scenario) => api.post("/api/chaos/scenario", { scenario }).then(r => r.data);
export const stopAll = () => api.post("/api/chaos/stop-all").then(r => r.data);
export const getActiveChaos = () => api.get("/api/chaos/active").then(r => r.data);
export const getExperiments = () => api.get("/api/chaos/experiments").then(r => r.data);
export const getExperiment = (id) => api.get(`/api/chaos/experiments/${id}`).then(r => r.data);

// Post-mortems
export const getPostMortems = () => api.get("/api/postmortems").then(r => r.data);
export const getPostMortem = (id) => api.get(`/api/postmortems/${id}`).then(r => r.data);
export const generatePostMortem = (experimentId) =>
  api.post(`/api/postmortems/generate/${experimentId}`).then(r => r.data);

// Metrics
export const getMetricsHistory = (service, limit = 100) =>
  api.get(`/api/metrics/history/${service}`, { params: { limit } }).then(r => r.data);
export const getCascadeEvents = () => api.get("/api/cascade/events").then(r => r.data);

// WebSocket factory
export const createMetricsSocket = (onMessage, onError) => {
  const ws = new WebSocket(`${WS_URL}/ws/metrics`);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch (err) {
      console.error("WS parse error:", err);
    }
  };
  ws.onerror = onError || console.error;
  ws.onclose = () => console.log("WS disconnected");
  return ws;
};

export default api;
