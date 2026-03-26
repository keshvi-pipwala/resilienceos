import React, { useState, useEffect } from "react";
import clsx from "clsx";
import {
  injectLatency, injectErrors, injectPartition,
  injectResources, killService, runScenario, stopAll,
  getExperiments, getActiveChaos
} from "../../utils/api";

const SERVICES = [
  "api-gateway", "user-service", "product-service",
  "order-service", "notification-service"
];

const FAULT_TYPES = [
  { value: "latency", label: "Latency Injection" },
  { value: "errors", label: "Error Rate Injection" },
  { value: "partition", label: "Network Partition" },
  { value: "resources", label: "Resource Exhaustion" },
  { value: "kill", label: "Service Kill" },
];

const SCENARIOS = [
  {
    id: "cascade_failure",
    label: "Cascade Failure",
    description: "80% errors on user-service, observe cascade to order-service and api-gateway",
    duration: "~90s",
    severity: "high"
  },
  {
    id: "slow_death",
    label: "Slow Death",
    description: "Latency ramp from 100ms to 500ms on product-service, timeout cascade",
    duration: "~75s",
    severity: "medium"
  },
  {
    id: "split_brain",
    label: "Split Brain",
    description: "Partition order-service from all dependencies, observe isolation behavior",
    duration: "~60s",
    severity: "high"
  },
];

function ActiveExperimentCard({ exp }) {
  const pct = Math.min(
    (exp.elapsed_seconds / Math.max(exp.duration || 60, 1)) * 100,
    100
  );
  return (
    <div className="bg-navy-800 border border-danger/30 rounded-lg p-3 text-sm">
      <div className="flex items-start justify-between mb-2">
        <div className="font-mono text-danger text-xs uppercase tracking-wide">
          {exp.fault_type || exp.scenario || "running"}
        </div>
        <span className="font-mono text-xs text-slate-400">
          {Math.round(exp.remaining_seconds || 0)}s remaining
        </span>
      </div>
      <div className="text-xs text-slate-300 mb-2">{exp.target}</div>
      <div className="w-full bg-navy-900 rounded-full h-1">
        <div
          className="h-1 rounded-full bg-danger transition-all duration-1000"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function ChaosLaboratory() {
  const [faultType, setFaultType] = useState("latency");
  const [target, setTarget] = useState("user-service");
  const [target2, setTarget2] = useState("order-service");
  const [duration, setDuration] = useState(60);
  const [delayMs, setDelayMs] = useState(500);
  const [jitterMs, setJitterMs] = useState(100);
  const [errorRate, setErrorRate] = useState(0.5);
  const [intensity, setIntensity] = useState(0.7);
  const [resourceType, setResourceType] = useState("cpu");
  const [restartAfter, setRestartAfter] = useState(20);

  const [active, setActive] = useState({ active_experiments: [], active_faults: {} });
  const [experiments, setExperiments] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const poll = async () => {
      try {
        const [a, e] = await Promise.all([getActiveChaos(), getExperiments()]);
        setActive(a);
        setExperiments(e);
      } catch (_) {}
    };
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, []);

  const showStatus = (msg, type = "success") => {
    setStatus({ msg, type });
    setTimeout(() => setStatus(null), 4000);
  };

  const handleInject = async () => {
    setLoading(true);
    try {
      let result;
      if (faultType === "latency") {
        result = await injectLatency({ target, delay_ms: delayMs, jitter_ms: jitterMs, duration_seconds: duration });
      } else if (faultType === "errors") {
        result = await injectErrors({ target, error_rate: errorRate, duration_seconds: duration });
      } else if (faultType === "partition") {
        result = await injectPartition({ source: target, target: target2, duration_seconds: duration });
      } else if (faultType === "resources") {
        result = await injectResources({ target, type: resourceType, intensity, duration_seconds: duration });
      } else if (faultType === "kill") {
        result = await killService({ target, restart_after_seconds: restartAfter });
      }
      showStatus(`Fault injected — experiment #${result.experiment_id} started`);
    } catch (e) {
      showStatus(`Injection failed: ${e.response?.data?.detail || e.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleScenario = async (scenarioId) => {
    setLoading(true);
    try {
      const result = await runScenario(scenarioId);
      showStatus(`Scenario started — experiment #${result.experiment_id}`);
    } catch (e) {
      showStatus(`Scenario failed: ${e.response?.data?.detail || e.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleStopAll = async () => {
    setLoading(true);
    try {
      await stopAll();
      showStatus("All experiments stopped, faults cleared");
    } catch (e) {
      showStatus("Stop failed: " + e.message, "error");
    } finally {
      setLoading(false);
    }
  };

  const severityColors = { high: "text-danger", medium: "text-warning", low: "text-success" };

  return (
    <div className="space-y-6">
      {/* Status banner */}
      {status && (
        <div className={clsx(
          "px-4 py-3 rounded-lg text-sm font-mono border animate-fade-in",
          status.type === "error"
            ? "bg-danger/10 border-danger/30 text-danger"
            : "bg-success/10 border-success/30 text-success"
        )}>
          {status.msg}
        </div>
      )}

      {/* Emergency stop */}
      <button
        onClick={handleStopAll}
        disabled={loading}
        className="w-full py-3 bg-danger/15 border-2 border-danger/60 rounded-lg text-danger font-mono font-semibold text-sm uppercase tracking-wider hover:bg-danger/25 transition-all duration-150 disabled:opacity-50"
      >
        EMERGENCY STOP — Terminate All Chaos
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Manual fault injection */}
        <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
          <h3 className="text-sm font-mono text-electric-400 uppercase tracking-widest mb-4">
            Fault Injection
          </h3>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-slate-500 mb-1 font-mono">Fault Type</label>
              <select
                value={faultType}
                onChange={(e) => setFaultType(e.target.value)}
                className="w-full bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:border-electric-500 outline-none"
              >
                {FAULT_TYPES.map((f) => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-slate-500 mb-1 font-mono">
                {faultType === "partition" ? "Source Service" : "Target Service"}
              </label>
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                className="w-full bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:border-electric-500 outline-none"
              >
                {SERVICES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            {faultType === "partition" && (
              <div>
                <label className="block text-xs text-slate-500 mb-1 font-mono">Target Service</label>
                <select
                  value={target2}
                  onChange={(e) => setTarget2(e.target.value)}
                  className="w-full bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:border-electric-500 outline-none"
                >
                  {SERVICES.filter((s) => s !== target).map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            )}

            {faultType === "latency" && (
              <>
                <div>
                  <label className="block text-xs text-slate-500 mb-1 font-mono">
                    Delay: <span className="text-electric-400">{delayMs}ms</span>
                  </label>
                  <input type="range" min="50" max="5000" step="50"
                    value={delayMs} onChange={(e) => setDelayMs(+e.target.value)}
                    className="w-full accent-electric-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1 font-mono">
                    Jitter: <span className="text-electric-400">{jitterMs}ms</span>
                  </label>
                  <input type="range" min="0" max="1000" step="25"
                    value={jitterMs} onChange={(e) => setJitterMs(+e.target.value)}
                    className="w-full accent-electric-500"
                  />
                </div>
              </>
            )}

            {faultType === "errors" && (
              <div>
                <label className="block text-xs text-slate-500 mb-1 font-mono">
                  Error Rate: <span className="text-danger">{(errorRate * 100).toFixed(0)}%</span>
                </label>
                <input type="range" min="0.05" max="1.0" step="0.05"
                  value={errorRate} onChange={(e) => setErrorRate(+e.target.value)}
                  className="w-full accent-danger"
                />
              </div>
            )}

            {faultType === "resources" && (
              <>
                <div>
                  <label className="block text-xs text-slate-500 mb-1 font-mono">Resource Type</label>
                  <select
                    value={resourceType}
                    onChange={(e) => setResourceType(e.target.value)}
                    className="w-full bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:border-electric-500 outline-none"
                  >
                    <option value="cpu">CPU Pressure</option>
                    <option value="memory">Memory Pressure</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1 font-mono">
                    Intensity: <span className="text-warning">{(intensity * 100).toFixed(0)}%</span>
                  </label>
                  <input type="range" min="0.1" max="1.0" step="0.1"
                    value={intensity} onChange={(e) => setIntensity(+e.target.value)}
                    className="w-full accent-warning"
                  />
                </div>
              </>
            )}

            {faultType === "kill" && (
              <div>
                <label className="block text-xs text-slate-500 mb-1 font-mono">
                  Auto-restore after: <span className="text-electric-400">{restartAfter}s</span>
                </label>
                <input type="range" min="5" max="120" step="5"
                  value={restartAfter} onChange={(e) => setRestartAfter(+e.target.value)}
                  className="w-full accent-electric-500"
                />
              </div>
            )}

            {faultType !== "kill" && (
              <div>
                <label className="block text-xs text-slate-500 mb-1 font-mono">
                  Duration: <span className="text-electric-400">{duration}s</span>
                </label>
                <input type="range" min="10" max="300" step="10"
                  value={duration} onChange={(e) => setDuration(+e.target.value)}
                  className="w-full accent-electric-500"
                />
              </div>
            )}

            <button
              onClick={handleInject}
              disabled={loading}
              className="w-full py-2.5 bg-electric-500/15 border border-electric-500/50 rounded-lg text-electric-400 font-mono text-sm font-semibold hover:bg-electric-500/25 transition-all disabled:opacity-50"
            >
              {loading ? "Injecting..." : "Inject Fault"}
            </button>
          </div>
        </div>

        {/* Scenario launcher + active experiments */}
        <div className="space-y-4">
          <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
            <h3 className="text-sm font-mono text-electric-400 uppercase tracking-widest mb-4">
              Scenario Runner
            </h3>
            <div className="space-y-3">
              {SCENARIOS.map((s) => (
                <div key={s.id} className="bg-navy-800 border border-navy-600 rounded-lg p-4">
                  <div className="flex items-start justify-between mb-1.5">
                    <span className="text-sm font-mono text-slate-200 font-medium">{s.label}</span>
                    <span className={clsx("text-xs font-mono", severityColors[s.severity])}>
                      {s.severity}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mb-3">{s.description}</p>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-slate-500">{s.duration}</span>
                    <button
                      onClick={() => handleScenario(s.id)}
                      disabled={loading}
                      className="px-3 py-1.5 bg-navy-700 border border-navy-500 rounded text-xs font-mono text-electric-400 hover:border-electric-500/50 hover:bg-navy-600 transition-all disabled:opacity-50"
                    >
                      Run Scenario
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Active experiments */}
          {active.active_experiments?.length > 0 && (
            <div className="bg-navy-900 border border-navy-700 rounded-xl p-4">
              <h3 className="text-xs font-mono text-danger uppercase tracking-widest mb-3">
                Active Experiments ({active.active_experiments.length})
              </h3>
              <div className="space-y-2">
                {active.active_experiments.map((exp) => (
                  <ActiveExperimentCard key={exp.experiment_id} exp={exp} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Experiment history */}
      <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
        <h3 className="text-sm font-mono text-electric-400 uppercase tracking-widest mb-4">
          Experiment History
        </h3>
        {experiments.length === 0 ? (
          <div className="text-center py-8 text-slate-600 text-sm font-mono">
            No experiments recorded yet
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-slate-500 border-b border-navy-700">
                  <th className="text-left pb-2 pr-4">#</th>
                  <th className="text-left pb-2 pr-4">Scenario</th>
                  <th className="text-left pb-2 pr-4">Fault</th>
                  <th className="text-left pb-2 pr-4">Target</th>
                  <th className="text-left pb-2 pr-4">Status</th>
                  <th className="text-left pb-2 pr-4">Blast Radius</th>
                  <th className="text-left pb-2">Started</th>
                </tr>
              </thead>
              <tbody>
                {experiments.map((exp) => (
                  <tr key={exp.id} className="border-b border-navy-800 hover:bg-navy-800/50">
                    <td className="py-2 pr-4 text-slate-500">{exp.id}</td>
                    <td className="py-2 pr-4 text-slate-300 max-w-[200px] truncate">{exp.scenario_name}</td>
                    <td className="py-2 pr-4 text-electric-400">{exp.fault_type}</td>
                    <td className="py-2 pr-4 text-slate-400">{exp.target_service}</td>
                    <td className="py-2 pr-4">
                      <span className={clsx("px-1.5 py-0.5 rounded text-xs", {
                        "text-success bg-success/10": exp.status === "completed",
                        "text-danger bg-danger/10": exp.status === "running",
                        "text-slate-400 bg-slate-800": exp.status === "aborted",
                      })}>
                        {exp.status}
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      <span className={clsx({
                        "text-danger": exp.blast_radius_score > 70,
                        "text-warning": exp.blast_radius_score > 30,
                        "text-success": exp.blast_radius_score <= 30,
                      })}>
                        {exp.blast_radius_score?.toFixed(1) ?? "—"}
                      </span>
                    </td>
                    <td className="py-2 text-slate-500">
                      {new Date(exp.started_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
