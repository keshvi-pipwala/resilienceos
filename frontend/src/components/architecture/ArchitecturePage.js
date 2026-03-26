import React from "react";

const SERVICES_INFO = [
  {
    name: "API Gateway",
    port: 8000,
    tech: "FastAPI",
    color: "#3b9eff",
    description: "Central entry point routing traffic to all downstream services. Implements circuit breaker logic per upstream. Exposes Prometheus metrics and chaos control headers.",
    dependencies: ["User Service", "Product Service", "Order Service"],
    skills: ["Circuit Breaker Pattern", "HTTP Reverse Proxy", "Request Routing"]
  },
  {
    name: "User Service",
    port: 8001,
    tech: "FastAPI + PostgreSQL",
    color: "#22c55e",
    description: "Manages user accounts and profile data backed by PostgreSQL. Primary target for cascade failure injection — when this service degrades, Order Service follows.",
    dependencies: ["PostgreSQL"],
    skills: ["SQLAlchemy ORM", "REST API Design", "Database Integration"]
  },
  {
    name: "Product Service",
    port: 8002,
    tech: "FastAPI + Redis",
    color: "#f59e0b",
    description: "Product catalog service seeded with 50 items across 5 categories. Publishes product view events to Redis pub/sub for downstream consumption by Notification Service.",
    dependencies: ["PostgreSQL", "Redis"],
    skills: ["Redis Pub/Sub", "Event-Driven Architecture", "Catalog Design"]
  },
  {
    name: "Order Service",
    port: 8003,
    tech: "FastAPI + Redis",
    color: "#a78bfa",
    description: "Order creation requires synchronous calls to both User Service and Product Service. This is the key cascade failure demonstration point — dependency failures propagate immediately.",
    dependencies: ["User Service", "Product Service", "PostgreSQL", "Redis"],
    skills: ["Synchronous Dependency Calls", "Cascade Failure Demonstration", "Event Publishing"]
  },
  {
    name: "Notification Service",
    port: 8004,
    tech: "FastAPI + Redis Sub",
    color: "#fb7185",
    description: "Async consumer of Redis pub/sub channels for order and product events. Simulates email/SMS delivery by logging to PostgreSQL. Demonstrates async service decoupling.",
    dependencies: ["Redis", "PostgreSQL"],
    skills: ["Async Message Consumer", "Redis Pub/Sub", "Event Processing"]
  },
];

const INFRA_INFO = [
  { name: "Prometheus", port: 9090, color: "#e8680a", description: "Scrapes /metrics from all 5 services every 5 seconds. Custom alerting rules for error rate and latency thresholds." },
  { name: "Grafana", port: 3000, color: "#f97316", description: "2 pre-provisioned dashboards: System Health Overview and Chaos Experiment View. Auto-refresh 5s, anonymous auth enabled." },
  { name: "PostgreSQL", port: 5432, color: "#336791", description: "Shared database for all services. Schema includes: users, products, orders, chaos_experiments, post_mortems, cascade_events." },
  { name: "Redis", port: 6379, color: "#dc382d", description: "Pub/sub channels: order_events, product_events. Used for async inter-service communication and event streaming." },
  { name: "Chaos Agent", port: 8010, color: "#ef4444", description: "5 fault types: latency, errors, partition, resources, kill. 3 named scenarios. Cascade detection. Blast radius scoring." },
  { name: "Control Plane", port: 9000, color: "#8b5cf6", description: "REST API + WebSocket server consumed by React frontend. Aggregates health data, manages post-mortems, proxies chaos commands." },
];

const SKILLS = [
  { category: "Distributed Systems", items: ["Microservices Architecture", "Service Dependency Graphs", "Cascade Failure Propagation", "Circuit Breaker Pattern", "Network Partition Simulation"] },
  { category: "Chaos Engineering", items: ["Fault Injection (5 types)", "Named Scenario Automation", "Blast Radius Measurement", "Cascade Detection Algorithms", "Recovery Time Measurement"] },
  { category: "Observability", items: ["Prometheus Metrics Scraping", "Grafana Dashboard Provisioning", "Custom Alerting Rules", "P99 Latency Tracking", "Real-Time WebSocket Streaming"] },
  { category: "Backend Engineering", items: ["FastAPI / Python Async", "SQLAlchemy ORM + PostgreSQL", "Redis Pub/Sub", "REST API Design", "Docker Compose Orchestration"] },
  { category: "AI Integration", items: ["Claude API Integration", "Prompt Engineering for JSON Output", "Structured Post-Mortem Generation", "Context-Aware Analysis", "SRE-Quality Report Generation"] },
  { category: "Frontend Engineering", items: ["React 18 + Hooks", "D3.js Force-Directed Graph", "Recharts Real-Time Time Series", "WebSocket Client", "Tailwind CSS Dark Theme"] },
];

export default function ArchitecturePage() {
  return (
    <div className="space-y-8">
      {/* ASCII Architecture Diagram */}
      <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
        <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-4">System Architecture</h2>
        <pre className="text-xs font-mono text-slate-400 leading-relaxed overflow-x-auto">
{`
                              CLIENT / BROWSER
                                    |
                             [React Dashboard]
                            port 3001 (frontend)
                                    |
                          [Control Plane API]
                           port 9000 (FastAPI)
                          REST + WebSocket /ws/metrics
                                    |
              ┌─────────────────────┼──────────────────────┐
              |                     |                      |
       [API Gateway]          [Chaos Agent]         [Prometheus]
        port 8000               port 8010             port 9090
      circuit breaker         5 fault types          scrapes all
              |                     |                  /metrics
    ┌─────────┼──────────┐          |
    |         |          |          |              [Grafana]
[User Svc] [Product Svc] [Order Svc]              port 3000
  port 8001   port 8002   port 8003           2 provisioned
    |            |           |               dashboards
    |         pub/sub     calls both
[PostgreSQL] [Redis]  [User + Product]
  port 5432  port 6379         |
                        [Notification Svc]
                           port 8004
                        subscribes to Redis
                               |
                         [PostgreSQL]
`}
        </pre>
      </div>

      {/* Service cards */}
      <div>
        <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-4">Microservices</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {SERVICES_INFO.map((svc) => (
            <div key={svc.name} className="bg-navy-900 border border-navy-700 rounded-xl p-5 card-hover">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="font-mono text-sm font-semibold" style={{ color: svc.color }}>
                    {svc.name}
                  </div>
                  <div className="text-xs text-slate-500 font-mono mt-0.5">:{svc.port} — {svc.tech}</div>
                </div>
                <div className="w-2 h-2 rounded-full mt-1" style={{ backgroundColor: svc.color }} />
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">{svc.description}</p>
              <div className="mb-2">
                <div className="text-xs text-slate-600 font-mono mb-1">Dependencies:</div>
                <div className="flex flex-wrap gap-1">
                  {svc.dependencies.map((d) => (
                    <span key={d} className="text-xs font-mono px-1.5 py-0.5 bg-navy-800 border border-navy-600 rounded text-slate-400">
                      {d}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-600 font-mono mb-1">Demonstrates:</div>
                <div className="flex flex-wrap gap-1">
                  {svc.skills.map((s) => (
                    <span key={s} className="text-xs font-mono px-1.5 py-0.5 rounded"
                      style={{ backgroundColor: svc.color + "15", color: svc.color, border: `1px solid ${svc.color}30` }}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Infrastructure */}
      <div>
        <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-4">Infrastructure</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {INFRA_INFO.map((infra) => (
            <div key={infra.name} className="bg-navy-900 border border-navy-700 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-2">
                <div className="font-mono text-sm font-semibold" style={{ color: infra.color }}>
                  {infra.name}
                </div>
                <span className="text-xs font-mono text-slate-500">:{infra.port}</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">{infra.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Skills Demonstrated */}
      <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
        <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-5">
          Skills Demonstrated
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {SKILLS.map((cat) => (
            <div key={cat.category}>
              <div className="text-xs font-mono text-slate-400 font-semibold mb-2 uppercase tracking-wide">
                {cat.category}
              </div>
              <ul className="space-y-1">
                {cat.items.map((item) => (
                  <li key={item} className="flex items-start gap-2 text-xs text-slate-500">
                    <span className="text-electric-500 mt-0.5 shrink-0">&bull;</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Stack summary */}
      <div className="bg-navy-900 border border-navy-700 rounded-xl p-6">
        <h2 className="text-xs font-mono text-electric-400 uppercase tracking-widest mb-4">Full Tech Stack</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
          {[
            ["Backend", "Python 3.11 + FastAPI"],
            ["Database", "PostgreSQL 15"],
            ["Cache / Queue", "Redis 7"],
            ["Metrics", "Prometheus + Grafana"],
            ["Orchestration", "Docker Compose + K8s"],
            ["Frontend", "React 18 + D3.js"],
            ["Charts", "Recharts"],
            ["AI", "Claude claude-sonnet-4-20250514"],
            ["Styling", "Tailwind CSS"],
            ["HTTP Client", "httpx (async)"],
            ["ORM", "SQLAlchemy 2"],
            ["Package Mgmt", "pip + npm"],
          ].map(([label, value]) => (
            <div key={label} className="bg-navy-800 border border-navy-700 rounded-lg p-3">
              <div className="text-slate-500 mb-0.5">{label}</div>
              <div className="text-slate-200">{value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
