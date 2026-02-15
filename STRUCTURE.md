# Project Structure

```
url-shortner/
├── app/                      # Application code
│   ├── api/                  # API endpoints
│   ├── core/                 # Configuration & security
│   ├── db/                   # Database connections
│   ├── middleware/           # Rate limiting, security headers
│   ├── models/               # Pydantic schemas
│   └── services/             # Business logic
│
├── assets/                   # Postman collections & resources
├── cassandra/                # Database schema & init scripts
├── config/                   # Configuration files (blocklist, etc.)
├── docs/                     # Architecture & design docs
├── k8s/                      # Kubernetes manifests
├── monitoring/               # Prometheus & Grafana configs
├── scripts/                  # Deployment & setup scripts
├── ssl/                      # SSL/TLS configuration
├── tests/                    # Testing scripts
│
├── docker-compose.yml        # Docker Compose setup
├── Dockerfile                # Container image
├── Makefile                  # Build & run commands
├── requirements.txt          # Python dependencies
└── README.md                 # Main documentation
```

## Directory Purpose

| Directory | Purpose |
|-----------|---------|
| `app/` | FastAPI application source code |
| `assets/` | Postman collections, API documentation |
| `cassandra/` | Database schema and initialization |
| `config/` | Application configuration files |
| `docs/` | Architecture, design, security docs |
| `k8s/` | Kubernetes deployment manifests |
| `monitoring/` | Observability configuration |
| `scripts/` | Automation scripts for deployment |
| `ssl/` | SSL/TLS certificates and config |
| `tests/` | Integration and load testing |

## Key Files

- **Makefile** - Common commands (run, test, deploy)
- **docker-compose.yml** - Local development stack
- **Dockerfile** - Production container image
- **requirements.txt** - Python dependencies
- **.env.example** - Environment variables template
