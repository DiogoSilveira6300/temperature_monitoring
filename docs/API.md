# API Documentation

All services expose JSON over HTTP via Flask, except `exporter`, which exposes Prometheus text metrics. Default ports come from each service's `config/*.json` file (overridable via environment variables).

## Registry (`registry.py`, default port 5050)

Service directory: other services register themselves here so peers can discover their URLs.

| Method | Path | Body | Response | Description |
|---|---|---|---|---|
| GET | `/health` | — | `{status, service, timestamp, uptime, metrics}` | Liveness and resource usage. |
| POST | `/register` | `{"service", "url", "role"?}` (`"name"` accepted as a deprecated alias for `"service"`) | `{"message": "<service> registered"}` (400 if `service`/`url` missing) | Registers a service instance; repeated registrations for the same service and URL update that instance. |
| DELETE | `/unregister` | `{"service"}` (`"name"` accepted as a deprecated alias) | `{"message": "<service> unregistered"}` (404 if not found) | Removes all instances registered under that service. |
| GET | `/services` | — | `{name: {role, instances: [{url, timestamp}, ...]}, ...}` | Lists registered services grouped by name. |
| GET | `/services/<name>` | — | `{url, timestamp}` (404 if not found) | Selects an instance for the named service using round-robin. |

## Ingestion (`ingestion.py`, default port 5001)

Entry point for sensor readings; registers itself with the registry as a `consumer`, then forwards stored data to `storage`.

| Method | Path | Body | Response | Description |
|---|---|---|---|---|
| GET | `/health` | — | `{status, service, timestamp, uptime, metrics}` | Liveness and resource usage. |
| POST | `/ingest` | `{"device_id", "temperature"}` | `{"stored": true}` (proxies storage's status code; 500 on error) | Forwards a reading to storage's `/store`. |

## Storage (`storage.py`, default port 5002)

Owns the SQLite database of temperature readings and computes statistics.

| Method | Path | Body | Response | Description |
|---|---|---|---|---|
| GET | `/health` | — | `{status, service, timestamp, uptime, metrics}` | Liveness and resource usage. |
| POST | `/store` | `{"device_id", "temperature"}` | `{"status": "stored"}` | Persists a reading. |
| GET | `/average` | — | `{"average_temperature": <float or null>}` | Average temperature across all sensors. |
| GET | `/stats/sensors` | — | `{device_id: {latest, highest, lowest, average, median}, ...}` | Full stats for every sensor. |
| GET | `/stats/sensors/<device_id>` | — | `{latest, highest, lowest, average, median}` (404 if no data) | Full stats for one sensor. |
| GET | `/stats/sensors/<device_id>/<stat>` | — | `{<stat>: <value>}` (400 if unknown stat, 404 if no data) | Single stat for one sensor. |
| GET | `/stats/overall` | — | `{latest, highest: {temperature, device_id}, lowest: {temperature, device_id}, average, median}` (404 if no data) | Full stats across all sensors; `highest`/`lowest` include which sensor produced them. |
| GET | `/stats/overall/<stat>` | — | `{<stat>: <value>}` (400 if unknown stat, 404 if no data) | Single stat across all sensors. |

Valid `<stat>` values: `latest`, `highest`, `lowest`, `average`, `median`.

## Analytics (`analytics.py`, default port 5003)

Public-facing gateway that registers itself with the registry as a `consumer`, then forwards all analytics queries to `storage`.

| Method | Path | Body | Response | Description |
|---|---|---|---|---|
| GET | `/health` | — | `{status, service, timestamp, uptime, metrics}` | Liveness and resource usage. |
| GET | `/average` | — | `{"average_temperature": <float or null>}` | Forwards to storage's `/average`. |
| GET | `/stats/sensors` | — | Same as storage's `/stats/sensors` | Forwards to storage. |
| GET | `/stats/sensors/<device_id>` | — | Same as storage's `/stats/sensors/<device_id>` | Forwards to storage. |
| GET | `/stats/sensors/<device_id>/<stat>` | — | Same as storage's `/stats/sensors/<device_id>/<stat>` | Forwards to storage. |
| GET | `/stats/overall` | — | Same as storage's `/stats/overall` | Forwards to storage. |
| GET | `/stats/overall/<stat>` | — | Same as storage's `/stats/overall/<stat>` | Forwards to storage. |

## Exporter (`exporter.py`, default port 8000)

Polls each service's `/health` endpoint and republishes the data as Prometheus metrics; not a Flask app.

| Method | Path | Response | Description |
|---|---|---|---|
| GET | `/metrics` | Prometheus text exposition format | `service_health`, `service_memory_mb`, `service_cpu_percent`, `service_thread_count`, `service_open_connections`, `service_uptime_seconds`, `service_request_latency_seconds` gauges/histogram, labeled by `service`. |

## Sensor / Runner (no HTTP server)

`sensor.py` and `runner.py` are clients, not servers: they call the registry's `/register` and `/services` endpoints and ingestion's `/ingest` endpoint (via the URL discovered in the registry), but do not expose any endpoints themselves.
