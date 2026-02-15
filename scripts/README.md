# Deployment & Setup Scripts

Automation scripts for deploying and configuring the URL Shortener service.

## Scripts

### Kubernetes Deployment

**k8s-deploy.sh** - Deploy to Kubernetes
```bash
./scripts/k8s-deploy.sh
# Or: make k8s-deploy
```

**k8s-access.sh** - Port forwarding for local access
```bash
./scripts/k8s-access.sh
```

**k8s-monitor.sh** - Monitor cluster status
```bash
./scripts/k8s-monitor.sh
```

### API Gateway

**kong-setup.sh** - Configure Kong API Gateway
```bash
./scripts/kong-setup.sh
# Or: make kong-setup
```

### SSL/HTTPS

**setup-https.sh** - HTTPS configuration
```bash
./scripts/setup-https.sh
```

## Usage

All scripts are executable and can be run directly or via Makefile commands.

```bash
# Make scripts executable (if needed)
chmod +x scripts/*.sh

# Run via Makefile
make k8s-deploy
make kong-setup

# Or run directly
./scripts/k8s-deploy.sh
```
