# Temperature Monitoring System

A distributed microservices-based temperature monitoring system built with Flask and Python. The system collects temperature readings from multiple sensors and provides analytics and statistics.

## Architecture

The system consists of five main components:

- **Registry** (port 5050): Service discovery and registration
- **Ingestion** (port 5001): Entry point for sensor readings
- **Storage** (port 5002): SQLite database and statistics computation
- **Analytics** (port 5003): Public-facing gateway for queries
- **Exporter** (port 8000): Prometheus metrics exporter
- **Sensors & Runner**: Client scripts for collecting data

## Prerequisites

- Python 3.8+
- pip

## Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd temperature_monitoring
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Running the Services

Each service can be started independently. Open separate terminal windows for each:

```bash
# Terminal 1: Registry
python registry/registry.py

# Terminal 2: Storage
python storage/storage.py

# Terminal 3: Ingestion
python ingestion/ingestion.py

# Terminal 4: Analytics
python analytics/analytics.py

# Terminal 5: Exporter (optional)
python exporter/exporter.py

# Terminal 6: Sensors (optional)
python sensors/sensor.py
```

## API Endpoints

See [API.md](./API.md) for detailed endpoint documentation.

### Quick Examples

**Check service health:**
```bash
curl http://localhost:5002/health
```

**Store a temperature reading:**
```bash
curl -X POST http://localhost:5001/ingest \
  -H "Content-Type: application/json" \
  -d '{"device_id": "sensor_1", "temperature": 22.5}'
```

**Get average temperature:**
```bash
curl http://localhost:5003/average
```

**Get all sensor statistics:**
```bash
curl http://localhost:5003/stats/sensors
```

## Project Structure

```
temperature_monitoring/
├── registry/           # Service registry
├── ingestion/          # Data ingestion service
├── storage/            # Data storage and stats
├── analytics/          # Analytics gateway
├── exporter/           # Prometheus metrics
├── sensors/            # Sensor clients
├── requirements.txt    # Python dependencies
├── API.md             # API documentation
└── README.md          # This file
```

## Configuration

Each service has configuration in its respective `config/` directory. Settings can be overridden via environment variables.

## Development

- Install in development mode: `pip install -e .`
- Run tests: `pytest`
- Check logs in respective service directories

## License

[Add your license here]

## Author

[Add author information here]
