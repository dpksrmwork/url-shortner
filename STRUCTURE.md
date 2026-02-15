# Project Structure

```
url-shortner/
├── app/                        # FastAPI application
│   ├── api/                    # API endpoints
│   ├── core/                   # Configuration & security
│   ├── db/                     # Database connections
│   ├── middleware/             # Rate limiting, security headers
│   ├── models/                 # Pydantic schemas
│   └── services/               # Business logic
│
├── cassandra/                  # Cassandra database
│   ├── init/                   # Schema initialization
│   └── README.md
│
├── k8s/                        # Kubernetes manifests
│   ├── 00-namespace.yaml
│   ├── 00-secrets.yaml
│   ├── 01-cassandra.yaml
│   ├── 02-kong-database.yaml
│   ├── 03-kong.yaml
│   ├── 04-api.yaml
│   ├── 05-prometheus.yaml
│   ├── 06-grafana.yaml
│   ├── 07-redis.yaml
│   └── README.md
│
├── monitoring/                 # Prometheus & Grafana
│   ├── prometheus.yml
│   ├── grafana-datasources.yml
│   ├── grafana-dashboard.json
│   └── README.md
│
├── scripts/                    # Deployment scripts
│   ├── k8s-deploy.sh
│   ├── k8s-access.sh
│   ├── k8s-monitor.sh
│   ├── kong-setup.sh
│   ├── setup-https.sh
│   └── README.md
│
├── tests/                      # Load testing
│   ├── test.sh
│   ├── latency-test.sh
│   ├── latency_test.py
│   └── README.md
│
├── assets/                     # Postman collection
│   ├── postman-collection.json
│   ├── postman-environment.json
│   └── POSTMAN.md
│
├── ssl/                        # SSL certificates
│   ├── certs/
│   ├── setup-ssl.sh
│   └── README.md
│
├── docs/                       # Documentation
│   ├── ARCHITECTURE.md         # System architecture
│   ├── SECURITY.md             # Security features
│   └── README.md
│
├── config/                     # Configuration files
│   └── blocklist.txt
│
├── docker-compose.yml          # Local development
├── Dockerfile                  # API container
├── Makefile                    # Common commands
├── requirements.txt            # Python dependencies
├── README.md                   # Project overview
└── DEPLOYMENT.md               # Deployment guide
```

## Key Directories

### `/app` - Application Code
Core FastAPI application with clean architecture:
- `api/` - HTTP endpoints
- `services/` - Business logic
- `db/` - Database clients
- `models/` - Data schemas

### `/k8s` - Kubernetes Deployment
Production-ready Kubernetes manifests for all services.

### `/monitoring` - Observability
Prometheus metrics collection and Grafana dashboards.

### `/scripts` - Automation
Deployment and setup automation scripts.

### `/tests` - Testing
Load testing and performance benchmarking tools.

### `/docs` - Documentation
Architecture, security, and design documentation.
