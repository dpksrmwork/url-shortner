.PHONY: cassandra-up cassandra-down cassandra-shell cassandra-init cassandra-status run install docker-build docker-up docker-down kong-setup k8s-deploy k8s-clean

install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-ssl:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8443 --ssl-keyfile=ssl/certs/key.pem --ssl-certfile=ssl/certs/cert.pem

generate-cert:
	mkdir -p ssl/certs
	openssl req -x509 -newkey rsa:4096 -nodes -keyout ssl/certs/key.pem -out ssl/certs/cert.pem -days 365 -subj "/CN=localhost"

ssl-setup:
	./ssl/setup-ssl.sh

# Docker commands
docker-build:
	docker compose build

docker-up:
	docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 45

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

kong-setup:
	./scripts/kong-setup.sh

# Kubernetes commands
k8s-deploy:
	./scripts/k8s-deploy.sh

k8s-clean:
	kubectl delete namespace url-shortener

k8s-access:
	./scripts/k8s-access.sh

k8s-monitor:
	./scripts/k8s-monitor.sh

# Cassandra commands
cassandra-up:
	docker compose up -d cassandra
	@echo "Waiting for Cassandra to be ready..."
	@sleep 30

cassandra-down:
	docker compose down

cassandra-shell:
	docker exec -it cassandra cqlsh

cassandra-init:
	docker exec -i cassandra cqlsh < cassandra/init/01-schema.cql
	@echo "Schema initialized successfully"

cassandra-status:
	docker exec cassandra nodetool status
