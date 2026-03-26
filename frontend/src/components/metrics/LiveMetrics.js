import React, { useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from "recharts";
import { getMetricsHistory, getCascadeEvents } from "../../utils/api";

const SERVICES = [
  "api-gateway", "user-service", "product-service",
  "order-service", "notification-service"
];

const SERVICE_COLORS = {
  "api-gateway": "#3b9eff",
  "user-service": "#22c55e",
  "product-service": "#f59e0b",
  "order-service": "#a78bfa",
  "notification-service": "#fb7185",
};

const GRAFANA_URL = process.env.REACT_APP_GRAFANA_URL || "http://localhost:13030";

function BlastRadiusMeter({ value = 0 }) {
  const clamped = Math.min(Math.max(value, 0), 100);
  const color = clamped > 70 ? "#ef4444" : clamped > 30 ? "#f59e0b" : "#22c55e";
  const circumference = 2 * Math.PI * 45;
  const dashOffset = circumference * (1 - clamped / 100);

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-32 h-32">
        <svg className="w-32 h-32 -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="45" fill="none" stroke="#0f2040" strokeWidth="8" />
          <circle
            cx="50" cy="50" r="45" fill="none"
            stroke={color} strokeWidth="8"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.8s ease, stroke 0.3s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-mono font-bold" style={{ color }}>
            {clamped.toFixed(0)}
          </span>
          <span className="text-xs text-slate-500 font-mono">/100</span>
        </div>
      </div>
      <span className="text-xs font-mono text-slate-400 mt-2">Blast Radius</span>
    </div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg p-3 text-xs font-mono shadow-xl">
      <div className="text-slate-400 mb-2">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="text-white">{typeof p.value === "number" ? p.value.toFixed(3) : p.value}</span>
        </div>
      ))}
    </div>
  );
}

export default function LiveMetrics({ health, chaos }) {
  const [errorData, setErrorData] = useState([]);
  const [latencyData, setLatencyData] = useState([]);
  const [cascades, setCascades] = useState([]);
  const [selectedView, setSelectedView] = useState("error_rate");

  // Build real-time chart data from health state
  useEffect(() => {
    const now = new Date().toLocaleTimeString();

    setErrorData((prev) => {
      const point = { time: now };
      SERVICES.forEach((svc) => {
        point[svc] = parseFloat(((health[svc]?.error_rate || 0) * 100).toFixed(2));
      });
      return [...prev.slice(-60), point];
    });

    setLatencyData((prev) => {
      const point = { time: now };
      SERVICES.forEach((svc) => {
        point[svc] = parseFloat((health[svc]?.avg_latency_ms || 0).toFixed(1));
      });
      return [...prev.slice(-60), point];
    });
  }, [health]);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await getCascadeEvents();
        setCascades(data.slice(0, 20));
      } catch (_) {}
    };
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const blastRadius = (() => {
    const rates = SERVICES.map((s) => health[s]?.error_rate || 0);
    const avg = rates.reduce((a, b) => a + b, 0) / rates.length;
    const affected = rates.filter((r) => r > 0.1).length;
    return Math.round((affected / SERVICES.length) * 50 + avg * 50);
  })();

  const chartData = selectedView === "error_rate" ? errorData : latencyData;
  const yLabel = selectedView === "error_rate" ? "Error %" : "Latency (ms)";

  return (
    <div className="space-y-6">
      {/* Top bar: blast radius + active faults */}
      <div className="flex items-center gap-6 bg-navy-900 border border-navy-700 rounded-xl p-5">
        <BlastRadiusMeter value={blastRadius} />
        <div className="flex-1">
          <h3 className="text-sm font-mono text-electric-400 uppercase tracking-widest mb-3">
            System Stress Overview
          </h3>
          <div className="grid grid-cols-5 gap-3">
            {SERVICES.map((svc) => {
              const h = health[svc] || {};
              const er = (h.error_rate || 0) * 100;
              const color =
                er > 50 ? "#ef4444" : er > 10 ? "#f59e0b" : "#22c55e";
              return (
                <div key={svc} className="text-center">
                  <div className="text-xs font-mono text-slate-500 mb-1 truncate">{svc.split("-")[0]}</div>
                  <div className="text-sm font-mono font-bold" style={{ color }}>
                    {er.toFixed(1)}%
                  </div>
                  <div className="text-xs text-slate-600 font-mono">
                    {(h.avg_latency_ms || 0).toFixed(0)}ms
                  </div>
                </div>
              );
            })}
          </div>
          {chaos?.active_experiments?.length > 0 && (
            <div className="mt-3 text-xs font-mono text-danger border border-danger/30 bg-danger/10 rounded px-2 py-1 inline-block">
              {chaos.active_experiments.length} chaos experiment(s) active
            </div>
          )}
        </div>
      </div>

      {/* Main chart */}
      <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-mono text-electric-400 uppercase tracking-widest">
            Real-Time Metrics
          </h3>
          <div className="flex gap-2">
            {["error_rate", "latency"].map((v) => (
              <button
                key={v}
                onClick={() => setSelectedView(v)}
                className={`px-3 py-1 rounded text-xs font-mono transition-all ${
                  selectedView === v
                    ? "bg-electric-500/20 text-electric-400 border border-electric-500/50"
                    : "text-slate-500 border border-navy-600 hover:border-slate-500"
                }`}
              >
                {v === "error_rate" ? "Error Rate" : "Latency"}
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#0f2040" />
            <XAxis
              dataKey="time"
              tick={{ fill: "#4a5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: "#4a5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
              label={{ value: yLabel, angle: -90, position: "insideLeft", fill: "#4a5568", fontSize: 10 }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 11, fontFamily: "JetBrains Mono", color: "#94a3b8" }}
            />
            {selectedView === "error_rate" && (
              <ReferenceLine y={10} stroke="#f59e0b40" strokeDasharray="4 4" label={{ value: "10% threshold", fill: "#f59e0b80", fontSize: 9 }} />
            )}
            {SERVICES.map((svc) => (
              <Line
                key={svc}
                type="monotone"
                dataKey={svc}
                stroke={SERVICE_COLORS[svc]}
                strokeWidth={1.5}
                dot={false}
                activeDot={{ r: 3 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Grafana iframe */}
      <div className="bg-navy-900 border border-navy-700 rounded-xl overflow-hidden">
        <div className="px-6 py-3 border-b border-navy-700 flex items-center justify-between">
          <h3 className="text-sm font-mono text-electric-400 uppercase tracking-widest">
            Grafana Dashboard
          </h3>
          <a
            href={GRAFANA_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-mono text-slate-500 hover:text-electric-400 transition-colors"
          >
            Open in Grafana
          </a>
        </div>
        <iframe
          src={`${GRAFANA_URL}/d/resilienceos-health/resilienceos-system-health-overview?orgId=1&refresh=5s&kiosk=tv`}
          title="Grafana Dashboard"
          className="w-full"
          style={{ height: 500, border: "none" }}
        />
      </div>

      {/* Cascade event log */}
      <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
        <h3 className="text-sm font-mono text-electric-400 uppercase tracking-widest mb-4">
          Cascade Detection Log
        </h3>
        {cascades.length === 0 ? (
          <div className="text-center py-6 text-slate-600 text-sm font-mono">
            No cascade events detected
          </div>
        ) : (
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {cascades.map((c) => (
              <div key={c.id} className="flex items-start gap-3 text-xs font-mono border-b border-navy-800 pb-2">
                <span className="text-slate-500 shrink-0">
                  {new Date(c.detected_at).toLocaleTimeString()}
                </span>
                <span className="text-danger shrink-0">{c.source_service}</span>
                <span className="text-slate-500">-&gt;</span>
                <span className="text-warning shrink-0">{c.affected_service}</span>
                <span className="text-slate-400 truncate">{c.impact_description}</span>
                <span className="text-slate-600 shrink-0">+{c.delay_seconds.toFixed(1)}s</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
