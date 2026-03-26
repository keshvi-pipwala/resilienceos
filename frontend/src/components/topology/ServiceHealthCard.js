import React from "react";
import clsx from "clsx";

function StatusBadge({ status }) {
  const cls = clsx(
    "inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium uppercase tracking-wide",
    {
      "badge-healthy": status === "healthy",
      "badge-degraded": status === "degraded",
      "badge-unhealthy": status === "unhealthy",
      "badge-unreachable": !status || status === "unknown" || status === "unreachable",
    }
  );
  return <span className={cls}>{status || "unknown"}</span>;
}

function Gauge({ value, max = 100, colorClass = "text-electric-500" }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="w-full bg-navy-800 rounded-full h-1.5 mt-1">
      <div
        className={clsx("h-1.5 rounded-full transition-all duration-500", colorClass)}
        style={{ width: `${pct}%`, backgroundColor: "currentColor" }}
      />
    </div>
  );
}

export default function ServiceHealthCard({ name, health = {}, isActive, onClick }) {
  const errorPct = ((health.error_rate || 0) * 100).toFixed(1);
  const latency = (health.avg_latency_ms || 0).toFixed(0);
  const requests = health.request_count || 0;

  const errorColor =
    (health.error_rate || 0) > 0.5 ? "text-danger" :
    (health.error_rate || 0) > 0.1 ? "text-warning" :
    "text-success";

  const latencyColor =
    (health.avg_latency_ms || 0) > 1000 ? "text-danger" :
    (health.avg_latency_ms || 0) > 300 ? "text-warning" :
    "text-electric-400";

  return (
    <div
      onClick={onClick}
      className={clsx(
        "bg-navy-900 border rounded-lg p-4 cursor-pointer card-hover transition-all duration-200",
        isActive ? "border-electric-500 shadow-[0_0_15px_#3b9eff25]" : "border-navy-700"
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-sm font-mono text-slate-300 font-medium">{name}</div>
          <div className="mt-1">
            <StatusBadge status={health.status} />
          </div>
        </div>
        {health.chaos_enabled && (
          <span className="text-xs font-mono text-danger border border-danger/30 bg-danger/10 px-1.5 py-0.5 rounded">
            CHAOS
          </span>
        )}
      </div>

      <div className="space-y-2">
        <div>
          <div className="flex justify-between text-xs mb-0.5">
            <span className="text-slate-500">Error Rate</span>
            <span className={clsx("font-mono", errorColor)}>{errorPct}%</span>
          </div>
          <Gauge
            value={health.error_rate || 0}
            max={1}
            colorClass={(health.error_rate || 0) > 0.1 ? "text-danger" : "text-success"}
          />
        </div>

        <div>
          <div className="flex justify-between text-xs mb-0.5">
            <span className="text-slate-500">Avg Latency</span>
            <span className={clsx("font-mono", latencyColor)}>{latency}ms</span>
          </div>
          <Gauge
            value={health.avg_latency_ms || 0}
            max={2000}
            colorClass={(health.avg_latency_ms || 0) > 500 ? "text-warning" : "text-electric-500"}
          />
        </div>

        <div className="flex justify-between text-xs pt-1 border-t border-navy-700">
          <span className="text-slate-500">Requests</span>
          <span className="font-mono text-slate-300">{requests.toLocaleString()}</span>
        </div>

        {health.uptime_seconds !== undefined && (
          <div className="flex justify-between text-xs">
            <span className="text-slate-500">Uptime</span>
            <span className="font-mono text-slate-400">
              {Math.floor((health.uptime_seconds || 0) / 60)}m {Math.round((health.uptime_seconds || 0) % 60)}s
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
