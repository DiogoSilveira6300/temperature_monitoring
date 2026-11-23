# Temperature Monitoring System - Architecture Summary

## Overview

The Temperature Monitoring System is a distributed microservices architecture designed to collect, store, and analyze temperature readings from multiple sensors. The system follows a service-oriented design with service discovery, enabling independent deployment and scaling of components.

**Key Characteristics:**
- **Microservices Architecture**: Loosely coupled, independently deployable services
- **Service Discovery**: Central registry for dynamic service lookup
- **REST API**: All services communicate via HTTP/JSON (except the exporter which uses Prometheus metrics)
- **Modular Design**: Clear separation of concerns across ingestion, storage, analytics, and monitoring layers

---

## System Components

### 1. **Registry Service** (`registry.py`, Port 5050)
**Role**: Service Directory & Discovery

The Registry is the central hub of the system responsible for service registration and lookup.

**Responsibilities:**
- Maintains a directory of all available service instances
- Provides service discovery through REST API
- Implements health checking (optional, configurable)
- Supports load balancing across multiple instances of the same service (round-robin)
- Performs dynamic deregistration of unhealthy services

**Key Features:**
- Thread-safe registry storage with locking
- Support for service roles (e.g., "consumer", "sensor")
- Timestamps for tracking registration time
- Instance-level registration (supports multiple instances per service)

**API Endpoints:**
- `GET /health` - Service liveness and metrics
- `POST /register` - Register a new service instance
- `DELETE /unregister` - Remove all instances of a service
- `GET /services` - List all registered services
- `GET /services/<name>` - Get a single service instance (round-robin selection)

---

### 2. **Ingestion Service** (`ingestion.py`, Port 5001)
**Role**: Data Entry Point & Proxy

The Ingestion service is the primary entry point for temperature readings from sensors and acts as a proxy to the storage service.

**Responsibilities:**
- Receives temperature readings from sensors via HTTP
- Dynamically discovers the storage service through the registry
- Forwards readings to the storage service for persistence
- Handles service availability issues gracefully

**Key Features:**
- Automatic service discovery via registry lookup
- Retry logic for registry queries (configurable attempts and delays)
- Transparent proxying to storage
- Health endpoint for monitoring

**API Endpoints:**
- `GET /health` - Service liveness and metrics
- `POST /ingest` - Accept and forward temperature readings
  - Accepts: `{"device_id", "temperature"}`

**Data Flow:**
```
Sensor → Ingestion /ingest → Registry lookup storage → Storage /store
```

---

### 3. **Storage Service** (`storage.py`, Port 5002)
**Role**: Data Persistence & Statistics Computation

The Storage service is the system's single source of truth for temperature data, storing all readings in SQLite and computing on-demand statistics.

**Responsibilities:**
- Persist all temperature readings to SQLite database
- Compute temperature statistics (average, median, highest, lowest, latest)
- Provide per-sensor and aggregate statistics
- Support queries across different dimensions (all sensors, single sensor, specific statistics)

**Database Schema:**
```sql
CREATE TABLE temperatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    temperature REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

**Key Features:**
- Efficient statistics computation with filtering options
- Per-device and system-wide aggregations
- Automatic timestamp tracking
- Configurable SQLite database location

**API Endpoints:**
- `GET /health` - Service liveness and metrics
- `POST /store` - Persist a temperature reading
- `GET /average` - System average temperature
- `GET /stats/sensors` - All sensors, full statistics
- `GET /stats/sensors/<device_id>` - Single sensor, full statistics
- `GET /stats/sensors/<device_id>/<stat>` - Single sensor, specific statistic
- `GET /stats/overall` - Aggregate statistics across all sensors (with device attribution)
- `GET /stats/overall/<stat>` - Aggregate specific statistic across all sensors

**Statistics Computed:**
- `latest` - Most recent temperature reading
- `highest` - Maximum temperature recorded
- `lowest` - Minimum temperature recorded
- `average` - Mean of all temperatures
- `median` - Median temperature value

---

### 4. **Analytics Service** (`analytics.py`, Port 5003)
**Role**: Public-Facing Analytics Gateway

The Analytics service provides a public-facing API that proxies to the Storage service, acting as an abstraction layer for client applications.

**Responsibilities:**
- Expose statistics APIs to end users/applications
- Dynamically discover the storage service through registry
- Forward all queries transparently to storage
- Isolate clients from storage service implementation details

**Key Features:**
- Gateway pattern for loose coupling
- Service discovery integration
- Same API as storage for seamless querying
- Health monitoring capability

**API Endpoints:**
(Mirrors storage service endpoints)
- `GET /health` - Service liveness and metrics
- `GET /average`
- `GET /stats/sensors`
- `GET /stats/sensors/<device_id>`
- `GET /stats/sensors/<device_id>/<stat>`
- `GET /stats/overall`
- `GET /stats/overall/<stat>`

**Data Flow:**
```
Client → Analytics /stats/* → Registry lookup storage → Storage /stats/*
```

---

### 5. **Exporter Service** (`exporter.py`, Port 8000)
**Role**: Metrics Export & Monitoring

The Exporter periodically polls all service health endpoints and republishes the data as Prometheus metrics.

**Responsibilities:**
- Periodically query health endpoints of all services
- Aggregate health and resource usage data
- Export metrics in Prometheus text exposition format
- Monitor system-wide health and performance

**Key Features:**
- Prometheus-compatible metrics format
- Configurable polling interval
- Health status tracking (0 = down, 1 = up)
- Performance metrics collection (latency, resource usage)

**Prometheus Metrics Exposed:**
- `service_health` (gauge) - Service availability (0 or 1)
- `service_memory_mb` (gauge) - Memory usage
- `service_cpu_percent` (gauge) - CPU usage
- `service_thread_count` (gauge) - Active threads
- `service_open_connections` (gauge) - Open connections
- `service_uptime_seconds` (gauge) - Service uptime
- `service_request_latency_seconds` (histogram) - Request latency distribution

**Data Flow:**
```
Exporter → Polls /health endpoints of all services → Prometheus /metrics
```

---

### 6. **Sensor Clients** (`sensor.py`, `sensors_sim.py`)
**Role**: Data Collection

Sensor clients are standalone applications that generate temperature readings and submit them to the ingestion service.

**Responsibilities:**
- Generate or read temperature measurements
- Register with the registry to be discoverable
- Periodically send readings to the ingestion service
- Handle registry unavailability gracefully

**Key Features:**
- Dynamic registry-based discovery of ingestion service
- Configurable send intervals
- Automatic retry logic
- Simulated sensor support for testing (random temperature generation)

**Command-Line Interface:**
```bash
python sensor.py \
    --device-id <sensor_id> \
    --send-interval <seconds> \
    --registry-endpoint <registry_url> \
    [--role <role>] \
    [--registry-retries <n>] \
    [--registry-retry-delay <seconds>]
```

---

## Data Flow Architecture

### Complete Request Flow - From Sensor to Analytics Query

1. **Data Ingestion Path:**
   ```
   Sensor Client
       ↓
   Registry /services/ingestion-service (lookup)
       ↓
   Ingestion Service /ingest
       ↓
   Registry /services/storage-service (lookup)
       ↓
   Storage Service /store
       ↓
   SQLite Database
   ```

2. **Analytics Query Path:**
   ```
   Client Application
       ↓
   Analytics Service /stats/* (gateway)
       ↓
   Registry /services/storage-service (lookup)
       ↓
   Storage Service /stats/*
       ↓
   SQLite Database Query
   ```

3. **Service Discovery Path:**
   ```
   Service Startup
       ↓
   Registry /register (self-registration)
       ↓
   Registry stores instance metadata
   ```

4. **Monitoring Path:**
   ```
   Exporter (periodic loop)
       ↓
   Polls all services /health
       ↓
   Prometheus /metrics endpoint
       ↓
   Prometheus scraper or Grafana
   ```

---

## Deployment Architecture

### Service Dependencies

```
┌─────────────────────────────────────────┐
│          Sensor Clients                 │
│      (sensor.py, sensors_sim.py)        │
└──────────────┬──────────────────────────┘
               │
               ↓
        ┌──────────────┐
        │  Registry    │◄──── All services register/lookup
        │  (5050)      │
        └──┬────────┬──┘
           │        │
           ↓        ↓
    ┌──────────┐  ┌───────────┐
    │Ingestion │  │Analytics  │
    │ (5001)   │  │  (5003)   │
    └────┬─────┘  └─────┬─────┘
         │              │
         └──────┬───────┘
                ↓
         ┌──────────────┐
         │  Storage     │
         │  (5002)      │
         │  SQLite DB   │
         └──────────────┘
                ▲
                │ Polls /health
         ┌──────┴──────┐
         │  Exporter   │
         │  (8000)     │
         └─────────────┘
```

### Environment Configuration

Each service loads its configuration from a JSON file in a local `config/` directory:
- `registry.json` - Registry configuration
- `ingestion.json` - Ingestion service configuration
- `storage.json` - Storage service configuration
- `analytics.json` - Analytics service configuration
- `exporter.json` - Exporter configuration

Configuration can be overridden via environment variables (service-specific with prefixes like `REGISTRY_`, `STORAGE_`, etc.).

---

## Key Architectural Patterns

### 1. **Service Discovery Pattern**
- Each service registers itself with the registry on startup
- Services use registry to dynamically discover peer endpoints
- Enables loose coupling and dynamic reconfiguration

### 2. **Gateway Pattern**
- Analytics service acts as a gateway to Storage
- Abstracts storage implementation from clients
- Allows for future caching, rate limiting, or versioning

### 3. **Health Check Pattern**
- All services expose `/health` endpoint
- Exporter periodically polls health endpoints
- Enables distributed health monitoring

### 4. **Retry & Resilience**
- Services retry registry lookups on failure
- Configurable retry counts and delays
- Graceful error handling for unavailable services

### 5. **Separation of Concerns**
- Ingestion: handles incoming data
- Storage: manages persistence and computation
- Analytics: provides data access layer
- Exporter: handles observability

---

## Configuration & Customization

### Common Configuration Elements
- `service_name` - Identifier for the service
- `host` / `port` - Listening address
- `registry_endpoint` - Registry URL for discovery
- `registry_retries` / `registry_retry_delay` - Resilience settings
- `role` - Service role in the system (optional)
- `log_path` - Location for service logs

### Environment Variables
Services support environment variable overrides following the pattern:
- `{SERVICE_NAME}_{CONFIG_KEY}` (uppercase with underscores)
- Example: `STORAGE_PORT=5050` overrides storage port

---

## Scalability Considerations

### Horizontal Scaling
- Multiple instances of Ingestion, Analytics, or Storage can be deployed
- Registry supports load balancing via round-robin instance selection
- Each instance registers independently

### Vertical Scaling
- SQLite database can be replaced with a production database (PostgreSQL, MySQL)
- Storage queries are optimized to avoid unnecessary data loading
- Statistics are computed on-demand (can be optimized with caching)

### Monitoring & Observability
- Prometheus metrics export enables integration with monitoring stacks
- Per-service health checks for operational visibility
- Configurable logging for debugging

---

## Security Considerations

**Current Implementation:**
- No authentication/authorization (designed for internal use)
- No encryption for inter-service communication
- JSON configuration files stored locally

**Recommendations for Production:**
- Add API key or OAuth2 authentication
- Implement HTTPS for all inter-service communication
- Use secret management for sensitive configuration
- Implement rate limiting on public APIs
- Add input validation and sanitization

---

## Summary

The Temperature Monitoring System demonstrates a well-structured microservices architecture with clear separation of concerns, dynamic service discovery, and built-in observability. The registry-based service discovery pattern enables loose coupling and flexibility, while the gateway pattern (Analytics → Storage) provides a clean public interface. The system is designed for independent deployment and testing of components, with a straightforward data flow from sensors through ingestion and storage to analytics and monitoring layers.
