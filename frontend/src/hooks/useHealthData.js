import { useState, useEffect, useRef, useCallback } from "react";
import { createMetricsSocket, getServicesHealth, getActiveChaos } from "../utils/api";

const SERVICE_NAMES = [
  "api-gateway",
  "user-service",
  "product-service",
  "order-service",
  "notification-service",
];

const defaultHealth = () =>
  Object.fromEntries(
    SERVICE_NAMES.map((n) => [n, { status: "unknown", error_rate: 0, avg_latency_ms: 0, request_count: 0 }])
  );

export function useHealthData() {
  const [health, setHealth] = useState(defaultHealth());
  const [chaos, setChaos] = useState({ active_experiments: [], active_faults: {} });
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const pollRef = useRef(null);

  const handleMessage = useCallback((data) => {
    if (data.type === "health_update") {
      setHealth((prev) => ({ ...prev, ...data.services }));
      if (data.chaos) setChaos(data.chaos);
      setConnected(true);
    }
  }, []);

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = createMetricsSocket(handleMessage, () => {
      setConnected(false);
      setTimeout(connectWs, 3000);
    });

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connectWs, 3000);
    };

    wsRef.current = ws;
  }, [handleMessage]);

  // Fallback polling when WS is unavailable
  const poll = useCallback(async () => {
    try {
      const [healthData, chaosData] = await Promise.all([
        getServicesHealth(),
        getActiveChaos(),
      ]);
      setHealth((prev) => ({ ...prev, ...healthData }));
      setChaos(chaosData);
    } catch (e) {
      // silently handle polling errors
    }
  }, []);

  useEffect(() => {
    connectWs();
    poll();
    pollRef.current = setInterval(poll, 3000);

    return () => {
      clearInterval(pollRef.current);
      wsRef.current?.close();
    };
  }, [connectWs, poll]);

  const blastRadius = (() => {
    const rates = Object.values(health).map((h) => h.error_rate || 0);
    const avg = rates.reduce((a, b) => a + b, 0) / rates.length;
    const affected = rates.filter((r) => r > 0.1).length;
    return Math.round((affected / SERVICE_NAMES.length) * 50 + avg * 50);
  })();

  return { health, chaos, connected, blastRadius };
}
