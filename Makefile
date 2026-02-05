.PHONY: cassandra-up cassandra-down cassandra-shell cassandra-init cassandra-status run install

install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

cassandra-up:
	docker compose up -d cassandra
	@echo "Waiting for Cassandra to be ready..."
	@sleep 30

cassandra-down:
	docker compose down

cassandra-shell:
	docker exec -it url-shortener-cassandra cqlsh

cassandra-init:
	docker exec -i url-shortener-cassandra cqlsh < cassandra/init/01-schema.cql
	@echo "Schema initialized successfully"

cassandra-status:
	docker exec url-shortener-cassandra nodetool status
