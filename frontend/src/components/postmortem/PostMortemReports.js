import React, { useState, useEffect } from "react";
import clsx from "clsx";
import { getPostMortems, getPostMortem, generatePostMortem, getExperiments } from "../../utils/api";

function SeverityBadge({ severity }) {
  return (
    <span className={clsx(
      "inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono font-bold uppercase tracking-wider",
      `badge-${severity?.toLowerCase()}`
    )}>
      {severity}
    </span>
  );
}

function ResilienceGauge({ score }) {
  const color = score >= 70 ? "#22c55e" : score >= 40 ? "#f59e0b" : "#ef4444";
  const circumference = 2 * Math.PI * 40;
  const dashOffset = circumference * (1 - score / 100);
  return (
    <div className="flex flex-col items-center">
      <div className="relative w-24 h-24">
        <svg className="w-24 h-24 -rotate-90" viewBox="0 0 88 88">
          <circle cx="44" cy="44" r="40" fill="none" stroke="#0f2040" strokeWidth="7" />
          <circle
            cx="44" cy="44" r="40" fill="none"
            stroke={color} strokeWidth="7"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 1s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-mono font-bold" style={{ color }}>{score?.toFixed(0)}</span>
          <span className="text-xs text-slate-500 font-mono">/100</span>
        </div>
      </div>
      <span className="text-xs text-slate-500 font-mono mt-1">Resilience Score</span>
    </div>
  );
}

function TimelineItem({ item, index }) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className="w-2 h-2 rounded-full bg-electric-500 shrink-0 mt-1.5" />
        {index < 99 && <div className="w-px flex-1 bg-navy-700 mt-1" />}
      </div>
      <div className="pb-4">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs font-mono text-electric-400">{item.time}</span>
          <span className="text-xs font-mono text-slate-500 border border-navy-600 px-1.5 py-0.5 rounded">
            {item.service}
          </span>
        </div>
        <p className="text-sm text-slate-300">{item.event}</p>
      </div>
    </div>
  );
}

function PostMortemDetail({ pm, onBack }) {
  const report = pm.full_report || {};

  return (
    <div className="space-y-6 animate-fade-in">
      <button
        onClick={onBack}
        className="text-xs font-mono text-slate-500 hover:text-electric-400 transition-colors flex items-center gap-1"
      >
        &larr; Back to list
      </button>

      {/* Header */}
      <div className={clsx(
        "border rounded-xl p-6",
        pm.severity === "P0" ? "border-danger/40 bg-danger/5" :
        pm.severity === "P1" ? "border-orange-500/40 bg-orange-500/5" :
        pm.severity === "P2" ? "border-warning/40 bg-warning/5" :
        "border-success/40 bg-success/5"
      )}>
        <div className="flex items-start justify-between mb-3">
          <SeverityBadge severity={pm.severity} />
          <ResilienceGauge score={pm.resilience_score} />
        </div>
        <h1 className="text-xl font-mono font-semibold text-slate-100 mb-3">{pm.title}</h1>
        <p className="text-sm text-slate-400 leading-relaxed">{report.summary}</p>
        <div className="mt-3 text-xs font-mono text-slate-500">
          Generated {new Date(pm.generated_at).toLocaleString()}
        </div>
      </div>

      {/* Impact */}
      {report.impact && (
        <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
          <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-4">Impact</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-mono font-bold text-white">{report.impact.duration_minutes}m</div>
              <div className="text-xs text-slate-500 font-mono mt-1">Duration</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-mono font-bold text-warning">
                {report.impact.services_affected?.length || 0}
              </div>
              <div className="text-xs text-slate-500 font-mono mt-1">Services Affected</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-mono font-bold text-danger">
                {(report.impact.estimated_requests_impacted || 0).toLocaleString()}
              </div>
              <div className="text-xs text-slate-500 font-mono mt-1">Requests Impacted</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-mono font-bold text-electric-400">{pm.severity}</div>
              <div className="text-xs text-slate-500 font-mono mt-1">Severity</div>
            </div>
          </div>
          {report.impact.user_facing_impact && (
            <div className="mt-4 p-3 bg-navy-800 rounded-lg text-sm text-slate-300 border-l-2 border-warning">
              {report.impact.user_facing_impact}
            </div>
          )}
          {report.impact.services_affected?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {report.impact.services_affected.map((s) => (
                <span key={s} className="px-2 py-0.5 bg-navy-800 border border-navy-600 rounded text-xs font-mono text-slate-300">
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Timeline */}
      {report.timeline?.length > 0 && (
        <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
          <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-4">Incident Timeline</h2>
          <div>
            {report.timeline.map((item, i) => (
              <TimelineItem key={i} item={item} index={i} />
            ))}
          </div>
        </div>
      )}

      {/* Root Cause */}
      {report.root_cause && (
        <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
          <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-3">Root Cause</h2>
          <p className="text-sm text-slate-300 leading-relaxed font-mono bg-navy-800 p-4 rounded-lg border-l-2 border-electric-500">
            {report.root_cause}
          </p>
        </div>
      )}

      {/* Contributing Factors + Cascade Analysis */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {report.contributing_factors?.length > 0 && (
          <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
            <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-3">Contributing Factors</h2>
            <ul className="space-y-2">
              {report.contributing_factors.map((f, i) => (
                <li key={i} className="flex gap-2 text-sm text-slate-300">
                  <span className="text-warning shrink-0 font-mono">{i + 1}.</span>
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}

        {report.cascade_analysis && (
          <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
            <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-3">Cascade Analysis</h2>
            <p className="text-sm text-slate-300 leading-relaxed">{report.cascade_analysis}</p>
          </div>
        )}
      </div>

      {/* Detection + Recovery */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {report.detection_gap && (
          <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
            <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-3">Detection Gap</h2>
            <p className="text-sm text-slate-300 leading-relaxed">{report.detection_gap}</p>
          </div>
        )}
        {report.recovery_analysis && (
          <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
            <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-3">Recovery Analysis</h2>
            <p className="text-sm text-slate-300 leading-relaxed">{report.recovery_analysis}</p>
          </div>
        )}
      </div>

      {/* Action Items */}
      {report.action_items?.length > 0 && (
        <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
          <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-4">Action Items</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs font-mono text-slate-500 border-b border-navy-700">
                  <th className="text-left pb-2 pr-4">Priority</th>
                  <th className="text-left pb-2 pr-4">Action</th>
                  <th className="text-left pb-2 pr-4">Owner</th>
                  <th className="text-left pb-2">Deadline</th>
                </tr>
              </thead>
              <tbody>
                {report.action_items.map((item, i) => (
                  <tr key={i} className="border-b border-navy-800">
                    <td className="py-3 pr-4">
                      <SeverityBadge severity={item.priority} />
                    </td>
                    <td className="py-3 pr-4 text-slate-300">{item.action}</td>
                    <td className="py-3 pr-4 text-slate-400 font-mono text-xs">{item.owner}</td>
                    <td className="py-3 text-slate-400 font-mono text-xs">{item.deadline}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Lessons Learned */}
      {report.lessons_learned?.length > 0 && (
        <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
          <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-3">Lessons Learned</h2>
          <ul className="space-y-2">
            {report.lessons_learned.map((l, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-300">
                <span className="text-electric-400 font-mono shrink-0">&bull;</span>
                {l}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function PostMortemReports() {
  const [postmortems, setPostmortems] = useState([]);
  const [experiments, setExperiments] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [generating, setGenerating] = useState(null);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [pms, exps] = await Promise.all([getPostMortems(), getExperiments()]);
        setPostmortems(pms);
        setExperiments(exps.filter((e) => e.status === "completed" && !e.has_post_mortem));
      } catch (_) {}
    };
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const handleSelect = async (pm) => {
    try {
      const full = await getPostMortem(pm.id);
      setDetail(full);
    } catch (_) {
      setDetail(pm);
    }
  };

  const handleGenerate = async (expId) => {
    setGenerating(expId);
    try {
      await generatePostMortem(expId);
      setStatus("Post-mortem generation started. This may take 30-60 seconds.");
      setTimeout(async () => {
        const pms = await getPostMortems();
        setPostmortems(pms);
      }, 10000);
    } catch (e) {
      setStatus("Generation failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setGenerating(null);
    }
  };

  if (detail) {
    return <PostMortemDetail pm={detail} onBack={() => setDetail(null)} />;
  }

  return (
    <div className="space-y-6">
      {status && (
        <div className="px-4 py-3 rounded-lg text-sm font-mono bg-electric-500/10 border border-electric-500/30 text-electric-400 animate-fade-in">
          {status}
        </div>
      )}

      {/* Generate new post-mortem */}
      {experiments.length > 0 && (
        <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
          <h3 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-3">
            Generate Post-Mortem
          </h3>
          <p className="text-xs text-slate-500 mb-3">
            {experiments.length} completed experiment(s) without a post-mortem
          </p>
          <div className="space-y-2">
            {experiments.slice(0, 5).map((exp) => (
              <div key={exp.id} className="flex items-center justify-between bg-navy-800 rounded-lg p-3">
                <div>
                  <div className="text-xs font-mono text-slate-300">{exp.scenario_name}</div>
                  <div className="text-xs text-slate-500 font-mono mt-0.5">
                    Blast radius: {exp.blast_radius_score?.toFixed(1)}
                  </div>
                </div>
                <button
                  onClick={() => handleGenerate(exp.id)}
                  disabled={generating === exp.id}
                  className="px-3 py-1.5 bg-electric-500/15 border border-electric-500/40 rounded text-xs font-mono text-electric-400 hover:bg-electric-500/25 disabled:opacity-50 transition-all"
                >
                  {generating === exp.id ? "Generating..." : "Generate"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Post-mortem list */}
      <div className="bg-navy-900 border border-navy-700 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-navy-700">
          <h3 className="text-xs font-mono text-electric-400 uppercase tracking-widest">
            Post-Mortem Reports ({postmortems.length})
          </h3>
        </div>
        {postmortems.length === 0 ? (
          <div className="text-center py-12 text-slate-600 text-sm font-mono">
            No post-mortems generated yet. Run a chaos experiment and generate one.
          </div>
        ) : (
          <div className="divide-y divide-navy-800">
            {postmortems.map((pm) => (
              <div
                key={pm.id}
                onClick={() => handleSelect(pm)}
                className="px-6 py-4 cursor-pointer hover:bg-navy-800/60 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <SeverityBadge severity={pm.severity} />
                      {pm.services_affected?.slice(0, 3).map((s) => (
                        <span key={s} className="text-xs font-mono text-slate-500 bg-navy-800 px-1.5 py-0.5 rounded border border-navy-600">
                          {s}
                        </span>
                      ))}
                    </div>
                    <div className="text-sm font-mono text-slate-200 truncate">{pm.title}</div>
                    <div className="text-xs text-slate-500 mt-1 line-clamp-1">{pm.summary}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-lg font-mono font-bold" style={{
                      color: pm.resilience_score >= 70 ? "#22c55e" :
                             pm.resilience_score >= 40 ? "#f59e0b" : "#ef4444"
                    }}>
                      {pm.resilience_score?.toFixed(0)}
                    </div>
                    <div className="text-xs text-slate-500 font-mono">resilience</div>
                    <div className="text-xs text-slate-600 font-mono mt-1">
                      {new Date(pm.generated_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
