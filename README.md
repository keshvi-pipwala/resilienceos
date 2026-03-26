# ResilienceOS

**Distributed Systems Chaos & Recovery Simulator**

A production-grade chaos engineering platform that deploys a realistic microservices architecture, injects real failures into running services, observes how the system degrades in real time, and automatically generates structured AI-written post-mortem reports.

---

## Architecture

```
                          CLIENT / BROWSER
                                |
                         [React Dashboard]
                          port 3001 (nginx)
                                |
                       [Control Plane API]
                        port 9000 (FastAPI)
                       REST + WebSocket /ws/metrics
                                |
           ┌────────────────────┼─────────────────────┐
           |                    |                     |
    [API Gateway]         [Chaos Agent]         [Prometheus]
     port 8000              port 8010             port 9090
   circuit breaker         5 fault types          5s scrape
           |                    |                     |
    ┌──────┼──────┐             |               [Grafana]
    |      |      |             |               port 3000
[User] [Product] [Order]        |            2 dashboards
 8001    8002    8003            |
   |       |        |           |
   |    pub/sub   calls both    |
[PostgreSQL] [Redis]  [User + Product]
  port 5432  port 6379         |
                        [Notification]
                           port 8004
                        subscribes Redis
                               |
                         [PostgreSQL]
```

## Quick Start

### Prerequisites

- Docker 24+ with Docker Compose v2
- 8 GB RAM minimum
- Ports free: 3000, 3001, 5432, 6379, 8000-8004, 8010, 9000, 9090

### One-Command Startup

```bash
# 1. Clone and enter the repository
git clone https://github.com/yourname/resilienceos.git
cd resilienceos

# 2. Configure environment
cp .env.example .env
# Optional: add your Anthropic API key for AI post-mortems
# ANTHROPIC_API_KEY=sk-ant-...

# 3. Start everything
docker compose up --build

# Wait ~60 seconds for all services to initialize and seed data
```

### Access Points

| Service | URL | Notes |
|---|---|---|
| React Dashboard | http://localhost:3001 | Main UI — start here |
| Control Plane API | http://localhost:9000 | REST + WebSocket |
| Grafana | http://localhost:3000 | Pre-provisioned dashboards |
| Prometheus | http://localhost:9090 | Raw metrics |
| API Gateway | http://localhost:8000 | Microservices entry point |
| Chaos Agent | http://localhost:8010 | Direct chaos API |

---

## Demo Walkthrough

### 1. Start in System Observatory

Open http://localhost:3001. You'll see:
- D3.js force-directed service topology graph showing all 5 services
- Green status nodes — all healthy after seeding
- Service health cards with real error rates and latencies
- Live WebSocket connection indicator (top-right: "live")

### 2. Drive Some Traffic

```bash
python scripts/generate_load.py --base-url http://localhost:8000 --rps 5
```

Watch request counts and latency metrics populate in real time on the dashboard.

### 3. Run the Cascade Failure Scenario

Navigate to **Chaos Lab** and click **"Run Scenario"** next to "Cascade Failure".

What happens:
1. 80% error rate injected into `user-service`
2. Within ~10 seconds, `order-service` begins returning 503 errors (it calls user-service synchronously)
3. Within ~20 seconds, `api-gateway` error rate climbs past the 10% alerting threshold
4. Grafana fires an alert annotation on the error rate graph
5. After 40 seconds, the fault is removed and recovery begins
6. The cascade detection log records: `user-service → order-service` with propagation delay

Watch the D3.js topology: nodes turn yellow then red as the cascade propagates.

### 4. Generate an AI Post-Mortem

After the experiment completes:
1. Navigate to **Post-Mortems**
2. The completed experiment appears in the "Generate Post-Mortem" section
3. Click **Generate**
4. Claude analyzes the experiment metrics, cascade events, and blast radius
5. A structured post-mortem appears with: severity classification, incident timeline, root cause analysis, cascade analysis, action items, and resilience score

### 5. Try the Other Scenarios

**Slow Death**: Latency ramp from 100ms → 500ms on product-service. Watch how timeout cascade through order-service differs from hard error cascade.

**Split Brain**: Simultaneously partition order-service from both dependencies. Observe a service island — it's running but cannot serve any requests.

### 6. Manual Fault Injection

In **Chaos Lab → Fault Injection**:
- Select fault type, target service, parameters
- Click **Inject Fault**
- Monitor real-time in Observatory or Metrics view
- Use **EMERGENCY STOP** to terminate all faults instantly

---

## Services Reference

### API Gateway (port 8000)
- `GET /health` — service health with circuit breaker states
- `GET /metrics` — Prometheus text format
- `GET /status` — detailed status including all circuit breaker states
- `GET /api/users`, `/api/products`, `/api/orders` — proxied routes
- `POST /chaos/configure` — inject chaos via agent

### User Service (port 8001)
- `GET /users` — list all users (seeded: 20)
- `GET /users/{id}` — get user by ID
- `POST /users` — create user
- `GET /health`, `GET /metrics`

### Product Service (port 8002)
- `GET /products` — list products, optional `?category=Electronics`
- `GET /products/{id}` — publishes Redis view event on fetch
- `GET /health`, `GET /metrics`

### Order Service (port 8003)
- `POST /orders` — creates order, calls user-service + product-service
- `GET /orders`, `GET /orders/{id}`
- `GET /health` — includes `dependency_health` for user/product services
- `GET /metrics` — includes inter-service dependency success rates

### Notification Service (port 8004)
- Subscribes to Redis `order_events` and `product_events`
- `GET /notifications` — view logged notification events
- `GET /health`, `GET /metrics`

### Chaos Agent (port 8010)
- `POST /chaos/latency` — inject latency
- `POST /chaos/errors` — inject error rate
- `POST /chaos/partition` — simulate network partition
- `POST /chaos/resources` — simulate resource exhaustion
- `POST /chaos/kill` — kill service (100% errors for N seconds)
- `POST /chaos/scenario` — run named scenario: `cascade_failure`, `slow_death`, `split_brain`
- `POST /chaos/stop-all` — emergency stop
- `GET /chaos/active` — running experiments
- `GET /chaos/experiments` — experiment history

### Control Plane (port 9000)
- `GET /api/services/health` — all service health in one call
- `GET /api/chaos/experiments` — experiment history from DB
- `POST /api/postmortems/generate/{id}` — trigger AI post-mortem
- `GET /api/postmortems` — list all post-mortems
- `WS /ws/metrics` — real-time health updates every 3 seconds

---

## Kubernetes Deployment

Kubernetes manifests are in `/k8s/manifests.yaml`.

### Minikube Setup

```bash
# Start minikube with sufficient resources
minikube start --cpus 4 --memory 8192

# Build images into minikube's Docker daemon
eval $(minikube docker-env)
docker build -f Dockerfile.service -t resilienceos-service:latest .
docker build -f Dockerfile.frontend -t resilienceos-frontend:latest .

# Create namespace and deploy
kubectl create namespace resilienceos
kubectl apply -f k8s/manifests.yaml

# Verify all pods are running
kubectl get pods -n resilienceos

# Access via port-forward
kubectl port-forward -n resilienceos svc/frontend 3001:3001
kubectl port-forward -n resilienceos svc/control-plane 9000:9000
kubectl port-forward -n resilienceos svc/grafana 3000:3000
```

### NetworkPolicy for Real Partitions

The K8s manifests include `NetworkPolicy` resources that enable real network partition simulation (vs. the application-layer simulation used in Docker Compose):

```bash
# Apply network policies
kubectl apply -f k8s/manifests.yaml

# The chaos agent uses these policies to create real network partitions
# POST /chaos/partition will label pods and apply deny policies
```

---

## Database Schema

```sql
services              -- service registry with dependency map
chaos_experiments     -- experiment history with blast radius scores
experiment_metrics    -- per-service metric snapshots during experiments
cascade_events        -- detected cascade propagation events
post_mortems          -- AI-generated post-mortem reports (JSON)
notifications_log     -- async event processing log
users                 -- seeded user accounts (20)
products              -- seeded product catalog (50)
orders                -- seeded and live order records
```

---

## Configuration

All configuration is via environment variables. See `.env.example` for full documentation.

Key variables:

```bash
ANTHROPIC_API_KEY=        # Required for AI post-mortems (optional — stub fallback works)
DATABASE_URL=             # PostgreSQL connection string
REDIS_URL=                # Redis connection URL
```

---

## Skills Demonstrated

**Distributed Systems**
- Microservices architecture with realistic inter-service dependencies
- Cascade failure propagation through synchronous dependency chains
- Circuit breaker pattern implementation
- Network partition simulation

**Chaos Engineering**
- Five distinct fault injection types
- Named scenario automation with multi-step orchestration
- Blast radius measurement and scoring
- Cascade detection algorithms

**Observability**
- Prometheus metrics scraping from all services
- Grafana dashboard provisioning via configuration (no manual setup)
- Custom alerting rules with multi-threshold escalation
- Real-time WebSocket metric streaming

**Backend Engineering**
- FastAPI with async/await throughout
- SQLAlchemy 2.x with PostgreSQL
- Redis pub/sub for async inter-service events
- Docker Compose multi-service orchestration

**AI Integration**
- Claude API for structured post-mortem generation
- Engineered prompts that produce consistent JSON output
- Fallback stub generator for offline operation
- Context-rich prompt construction from live experiment data

**Frontend Engineering**
- React 18 with custom hooks for WebSocket state management
- D3.js force-directed topology graph with live updates
- Recharts time-series for real-time error rate and latency
- Dark-mode SRE tool aesthetic

---

## Project Structure

```
resilienceos/
├── services/
│   ├── shared.py                   # ChaosMiddleware, ServiceMetrics
│   ├── api_gateway/main.py         # Port 8000, circuit breaker
│   ├── user_service/main.py        # Port 8001, PostgreSQL
│   ├── product_service/main.py     # Port 8002, Redis pub/sub
│   ├── order_service/main.py       # Port 8003, cascade demo
│   └── notification_service/main.py # Port 8004, Redis sub
├── chaos_agent/main.py             # Port 8010, 5 fault types
├── control_plane/
│   ├── main.py                     # Port 9000, REST + WebSocket
│   └── postmortem.py               # Claude API integration
├── postgres/
│   ├── models.py                   # SQLAlchemy models
│   └── seed.py                     # Database seeding (50 products, 20 users)
├── frontend/
│   └── src/
│       ├── App.js                  # Routing + nav
│       ├── hooks/useHealthData.js  # WebSocket + polling hook
│       ├── utils/api.js            # Axios API client
│       └── components/
│           ├── topology/           # D3.js graph, health cards
│           ├── chaos/              # Fault injection UI
│           ├── metrics/            # Recharts, Grafana iframe
│           ├── postmortem/         # Post-mortem viewer
│           └── architecture/      # Static architecture page
├── prometheus/
│   ├── prometheus.yml              # Scrape config, 5s interval
│   └── alerts.yml                  # Error rate + latency alerts
├── grafana/
│   ├── provisioning/               # Auto-provisioned datasource + dashboard
│   └── dashboards/                 # System Health + Chaos Experiment dashboards
├── k8s/manifests.yaml              # Full Kubernetes deployment
├── scripts/generate_load.py        # Traffic generator
├── docker-compose.yml              # One-command startup
├── Dockerfile.service              # Python service image
├── Dockerfile.frontend             # React nginx image
├── requirements.txt                # Python dependencies
└── .env.example                    # Configuration template
```

---

## Running Tests

The integration test suite validates the full stack end-to-end.

### Prerequisites

Start the stack first:
```bash
docker compose up --build
```

### Install test dependencies

```bash
pip install pytest==8.1.1 pytest-asyncio==0.23.5 httpx==0.27.0
```

### Run all tests

```bash
# Full suite (53 tests across 13 classes)
pytest tests/test_integration.py -v

# Smoke tests only — health checks and seed data (fast, ~10s)
pytest tests/test_integration.py -v -m smoke

# A specific test class
pytest tests/test_integration.py::TestRealCascadeFailure -v

# A single test
pytest tests/test_integration.py::TestRealCascadeFailure::test_user_service_errors_cascade_to_order_service -v
```

### Test coverage

| Class | Tests | What it validates |
|---|---|---|
| TestServiceHealth | 7 | All 7 services return 200 with correct health shape |
| TestMetricsEndpoints | 3 | Prometheus /metrics format on 3 services |
| TestSeedData | 4 | 50 products, 20 users, 5 categories seeded |
| TestOrderCreation | 3 | Real inter-service order creation flow |
| TestLatencyInjection | 2 | Latency fault applied and cleared correctly |
| TestErrorRateInjection | 2 | Error rate fault affects request outcomes |
| TestRealCascadeFailure | 3 | **Core demo**: user-service errors propagate to order-service |
| TestChaosAgentAPI | 6 | All 5 fault types trigger correctly |
| TestControlPlaneAPI | 9 | REST endpoints, post-mortem CRUD, cascade events |
| TestChaosHeaders | 3 | Per-request X-Chaos-* headers work; health endpoint exempt |
| TestScenarioRunner | 4 | All 3 named scenarios start; invalid scenario returns 400 |
| TestAPIGatewayProxy | 4 | Gateway proxies all routes; circuit breakers visible |
| TestDataIntegrity | 3 | Price calculation, user CRUD, duplicate rejection |
