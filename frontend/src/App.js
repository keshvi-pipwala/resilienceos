import React, { useState } from "react";
import clsx from "clsx";
import { useHealthData } from "./hooks/useHealthData";
import ServiceTopology from "./components/topology/ServiceTopology";
import ServiceHealthCard from "./components/topology/ServiceHealthCard";
import ChaosLaboratory from "./components/chaos/ChaosLaboratory";
import LiveMetrics from "./components/metrics/LiveMetrics";
import PostMortemReports from "./components/postmortem/PostMortemReports";
import ArchitecturePage from "./components/architecture/ArchitecturePage";

const NAV_ITEMS = [
  { id: "observatory", label: "Observatory", shortLabel: "Observe" },
  { id: "chaos", label: "Chaos Lab", shortLabel: "Chaos" },
  { id: "metrics", label: "Live Metrics", shortLabel: "Metrics" },
  { id: "postmortems", label: "Post-Mortems", shortLabel: "PMs" },
  { id: "architecture", label: "Architecture", shortLabel: "Arch" },
];

function StatusDot({ status }) {
  const color =
    status === "healthy" ? "bg-success" :
    status === "degraded" ? "bg-warning" :
    status === "unhealthy" ? "bg-danger" : "bg-slate-600";
  return <span className={clsx("inline-block w-1.5 h-1.5 rounded-full", color)} />;
}

function SystemStatusBar({ health, connected, blastRadius, chaos }) {
  const statuses = Object.values(health).map((h) => h.status || "unknown");
  const unhealthyCount = statuses.filter((s) => s === "unhealthy" || s === "unreachable").length;
  const degradedCount = statuses.filter((s) => s === "degraded").length;
  const activeExperiments = chaos?.active_experiments?.length || 0;

  const overallStatus =
    unhealthyCount > 0 ? "INCIDENT" :
    degradedCount > 0 || activeExperiments > 0 ? "DEGRADED" :
    "NOMINAL";

  const statusColor =
    overallStatus === "INCIDENT" ? "text-danger border-danger/40 bg-danger/5" :
    overallStatus === "DEGRADED" ? "text-warning border-warning/40 bg-warning/5" :
    "text-success border-success/40 bg-success/5";

  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-navy-900 border-b border-navy-700">
      <div className="flex items-center gap-2">
        <div className={clsx("px-2 py-0.5 rounded border text-xs font-mono font-bold tracking-widest", statusColor)}>
          {overallStatus}
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs font-mono text-slate-500">
        {Object.entries(health).map(([name, h]) => (
          <div key={name} className="flex items-center gap-1">
            <StatusDot status={h.status} />
            <span className="hidden sm:inline">{name.split("-")[0]}</span>
          </div>
        ))}
      </div>
      {activeExperiments > 0 && (
        <div className="ml-auto flex items-center gap-1.5 text-xs font-mono text-danger border border-danger/30 bg-danger/10 px-2 py-0.5 rounded">
          <span className="w-1.5 h-1.5 bg-danger rounded-full animate-pulse inline-block" />
          {activeExperiments} experiment{activeExperiments > 1 ? "s" : ""} active
        </div>
      )}
      <div className={clsx("ml-auto text-xs font-mono", connected ? "text-success" : "text-slate-600")}>
        {connected ? "live" : "polling"}
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("observatory");
  const [selectedNode, setSelectedNode] = useState(null);
  const { health, chaos, connected, blastRadius } = useHealthData();

  const SERVICE_NAMES = [
    "api-gateway", "user-service", "product-service",
    "order-service", "notification-service"
  ];

  const activeFaults = chaos?.active_faults || {};

  return (
    <div className="min-h-screen bg-navy-950 text-slate-200 flex flex-col">
      {/* Top header */}
      <header className="flex items-center justify-between px-6 py-3 bg-navy-900 border-b border-navy-700">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 bg-electric-500/20 border border-electric-500/40 rounded flex items-center justify-center">
            <span className="text-electric-400 text-xs font-mono font-bold">R</span>
          </div>
          <div>
            <div className="text-sm font-mono font-semibold text-slate-200 tracking-tight">ResilienceOS</div>
            <div className="text-xs text-slate-500 font-mono">Distributed Systems Chaos Simulator</div>
          </div>
        </div>
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setPage(item.id)}
              className={clsx(
                "px-3 py-1.5 rounded text-xs font-mono transition-all duration-150",
                page === item.id
                  ? "bg-electric-500/20 text-electric-400 border border-electric-500/40"
                  : "text-slate-500 hover:text-slate-300 border border-transparent"
              )}
            >
              <span className="hidden sm:inline">{item.label}</span>
              <span className="sm:hidden">{item.shortLabel}</span>
            </button>
          ))}
        </nav>
      </header>

      {/* System status bar */}
      <SystemStatusBar
        health={health}
        connected={connected}
        blastRadius={blastRadius}
        chaos={chaos}
      />

      {/* Main content */}
      <main className="flex-1 px-4 sm:px-6 py-6 max-w-screen-2xl w-full mx-auto">
        {page === "observatory" && (
          <div className="space-y-6">
            <div>
              <h1 className="text-lg font-mono font-semibold text-slate-200 mb-0.5">System Observatory</h1>
              <p className="text-xs text-slate-500 font-mono">Real-time service topology and health monitoring</p>
            </div>

            {/* Topology graph */}
            <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest">
                  Service Dependency Graph
                </h2>
                <span className="text-xs font-mono text-slate-500">Click a node for details</span>
              </div>
              <ServiceTopology
                health={health}
                chaosActive={activeFaults}
                onNodeClick={setSelectedNode}
              />
            </div>

            {/* Selected node detail */}
            {selectedNode && health[selectedNode] && (
              <div className="bg-navy-900 border border-electric-500/30 rounded-xl p-5 animate-fade-in">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-mono text-electric-400">{selectedNode}</span>
                  <button
                    onClick={() => setSelectedNode(null)}
                    className="text-xs text-slate-500 hover:text-slate-300 font-mono"
                  >
                    dismiss
                  </button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
                  {[
                    ["Status", health[selectedNode]?.status || "unknown"],
                    ["Error Rate", `${((health[selectedNode]?.error_rate || 0) * 100).toFixed(2)}%`],
                    ["Avg Latency", `${(health[selectedNode]?.avg_latency_ms || 0).toFixed(1)}ms`],
                    ["P99 Latency", `${(health[selectedNode]?.p99_latency_ms || 0).toFixed(1)}ms`],
                    ["Requests", (health[selectedNode]?.request_count || 0).toLocaleString()],
                    ["Uptime", `${Math.floor((health[selectedNode]?.uptime_seconds || 0) / 60)}m`],
                    ["Chaos", health[selectedNode]?.chaos_enabled ? "ACTIVE" : "off"],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <div className="text-slate-600 mb-0.5">{label}</div>
                      <div className={clsx("font-semibold",
                        label === "Chaos" && value === "ACTIVE" ? "text-danger" :
                        label === "Status" && value !== "healthy" ? "text-warning" :
                        "text-slate-200"
                      )}>
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Service health cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
              {SERVICE_NAMES.map((name) => (
                <ServiceHealthCard
                  key={name}
                  name={name}
                  health={health[name]}
                  isActive={selectedNode === name}
                  onClick={() => setSelectedNode(selectedNode === name ? null : name)}
                />
              ))}
            </div>
          </div>
        )}

        {page === "chaos" && (
          <div className="space-y-4">
            <div>
              <h1 className="text-lg font-mono font-semibold text-slate-200 mb-0.5">Chaos Laboratory</h1>
              <p className="text-xs text-slate-500 font-mono">Inject faults, run scenarios, observe system behavior</p>
            </div>
            <ChaosLaboratory />
          </div>
        )}

        {page === "metrics" && (
          <div className="space-y-4">
            <div>
              <h1 className="text-lg font-mono font-semibold text-slate-200 mb-0.5">Live Metrics</h1>
              <p className="text-xs text-slate-500 font-mono">Real-time error rates, latency, and cascade detection</p>
            </div>
            <LiveMetrics health={health} chaos={chaos} />
          </div>
        )}

        {page === "postmortems" && (
          <div className="space-y-4">
            <div>
              <h1 className="text-lg font-mono font-semibold text-slate-200 mb-0.5">Post-Mortem Reports</h1>
              <p className="text-xs text-slate-500 font-mono">AI-generated incident analysis from chaos experiments</p>
            </div>
            <PostMortemReports />
          </div>
        )}

        {page === "architecture" && (
          <div className="space-y-4">
            <div>
              <h1 className="text-lg font-mono font-semibold text-slate-200 mb-0.5">Architecture</h1>
              <p className="text-xs text-slate-500 font-mono">System design, service topology, and skills demonstrated</p>
            </div>
            <ArchitecturePage />
          </div>
        )}
      </main>
    </div>
  );
}
