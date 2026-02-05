# Cassandra Setup

## Quick Start

```bash
# Start Cassandra
make cassandra-up

# Initialize schema
make cassandra-init

# Check cluster status
make cassandra-status

# Access CQL shell
make cassandra-shell
```

## Schema Design

### urls table
- **Partition Key**: `short_code` (ensures even distribution)
- **Purpose**: Primary lookup for redirects (read-heavy)
- **TTL**: 3 years default

### url_dedup table
- **Partition Key**: `url_hash` (SHA-256 of long_url)
- **Purpose**: Prevent duplicate URLs, return existing short_code

### Consistency Level
- **Writes**: QUORUM (2/3 nodes)
- **Reads**: ONE (low latency, eventual consistency acceptable)

## Production Considerations

- Deploy 3+ nodes per datacenter
- Use `NetworkTopologyStrategy` for multi-DC
- Monitor with `nodetool` and Prometheus exporters
- Tune `read_repair_chance` based on consistency needs
