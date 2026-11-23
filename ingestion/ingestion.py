from flask import Flask, request, jsonify
import requests
import time

import psutil
import os
import json

app = Flask(__name__)

with open("./config/ingestion.json") as config_file:
    config = json.load(config_file)

SERVICE_URL = os.getenv("INGESTION_SERVICE_URL", config["service_url"])
ROLE = os.getenv("INGESTION_ROLE", config["role"])
REGISTRY_ENDPOINT = os.getenv("REGISTRY_ENDPOINT", config["registry_endpoint"])
REGISTRY_RETRIES = int(os.getenv("INGESTION_REGISTRY_RETRIES", config.get("registry_retries", 5)))
REGISTRY_RETRY_DELAY = float(os.getenv("INGESTION_REGISTRY_RETRY_DELAY", config.get("registry_retry_delay", 1)))
SERVICE_NAME = os.getenv("INGESTION_SERVICE_NAME", config["service_name"])
HOST = os.getenv("INGESTION_HOST", config["host"])
PORT = int(os.getenv("INGESTION_PORT", config["port"]))
START_TIME = time.time()

process = psutil.Process(os.getpid())
process.cpu_percent()  


@app.route('/health')
def health():
    return jsonify({
        "status": "up",
        "service": SERVICE_NAME,
        "timestamp": int(time.time()),
        "uptime": time.time() - START_TIME,
        "metrics": {
            "memory_usage": process.memory_info().rss / 1024 / 1024,  # MB
            "cpu_percent": process.cpu_percent(),  # Second call will return actual value
            "thread_count": len(process.threads()),
            "open_connections": len(process.connections())
        }
    })

def lookup_storage_url(retries=REGISTRY_RETRIES, delay=REGISTRY_RETRY_DELAY):
    """Query the registry for the storage service URL."""
    service_url = f"{REGISTRY_ENDPOINT.rstrip('/')}/services/storage-service"
    for attempt in range(retries):
        try:
            r = requests.get(service_url, timeout=2)
            r.raise_for_status()
            storage = r.json()
            if storage and "url" in storage:
                return storage["url"]
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"Storage lookup failed (attempt {attempt + 1}/{retries}): {e}")
        if attempt < retries - 1:
            time.sleep(delay)
    return None

@app.route('/ingest', methods=['POST'])
def ingest():
    data = request.get_json()
    print("Received:", data)
    
    storage_url = lookup_storage_url()
    if not storage_url:
        return jsonify({"error": "storage service not available"}), 503
    try:
        res = requests.post(f"{storage_url.rstrip('/')}/store", json=data)
        return jsonify({"stored": True}), res.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def register():
	requests.post(
        f"{REGISTRY_ENDPOINT.rstrip('/')}/register",
		json={
			"name": SERVICE_NAME,
			"url": SERVICE_URL,
			"role": ROLE
		}
	)


def wait_for_registry(retries=REGISTRY_RETRIES, delay=REGISTRY_RETRY_DELAY):
	"""Check that the registry is reachable; used to gate startup."""
	health_url = f"{REGISTRY_ENDPOINT.rstrip('/')}/health"
	for attempt in range(retries):
		try:
			r = requests.get(health_url, timeout=2)
			if r.status_code == 200:
				return True
		except Exception:
			pass
		time.sleep(delay)
	return False

if __name__ == '__main__':
    if not wait_for_registry():
        raise SystemExit(f"Registry not reachable at {REGISTRY_ENDPOINT}, aborting startup")
    register()
    app.run(host=HOST, port=PORT)
