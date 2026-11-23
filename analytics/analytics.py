from flask import Flask, jsonify, request
import requests
import time
from datetime import datetime
import logging

import psutil
import os
import json

app = Flask(__name__)

with open("./config/analytics.json") as config_file:
    config = json.load(config_file)

SERVICE_NAME = os.getenv("ANALYTICS_SERVICE_NAME", config["service_name"])
SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", config["service_url"])
ROLE = os.getenv("ANALYTICS_ROLE", config["role"])
REGISTRY_ENDPOINT = os.getenv("ANALYTICS_REGISTRY_ENDPOINT", config["registry_endpoint"])
REGISTRY_RETRIES = int(os.getenv("ANALYTICS_REGISTRY_RETRIES", config.get("registry_retries", 5)))
REGISTRY_RETRY_DELAY = float(os.getenv("ANALYTICS_REGISTRY_RETRY_DELAY", config.get("registry_retry_delay", 1)))
HOST = os.getenv("ANALYTICS_HOST", config["host"])
PORT = int(os.getenv("ANALYTICS_ANALYTICS_PORT", config["port"]))
LOG_PATH = os.getenv("ANALYTICS_LOG_PATH", config["log_path"])
START_TIME = time.time()

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
handler = logging.FileHandler(LOG_PATH)
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(handler)

process = psutil.Process(os.getpid())
process.cpu_percent()  


@app.after_request
def log_request_info(response):
    # Apache combined style:
    # %h %l %u [%t] "%r" %>s %b "%{Referer}i" "%{User-Agent}i"

    remote_addr = request.remote_addr or '-'
    ident = '-'          # we don't have identd, so '-'
    user = '-'           # no auth user, so '-'
    now = datetime.utcnow().strftime('%d/%b/%Y:%H:%M:%S +0000')
    request_line = f"{request.method} {request.full_path or request.path} {request.environ.get('SERVER_PROTOCOL', 'HTTP/1.1')}"
    status = response.status_code
    size = response.calculate_content_length() or '-'
    referer = request.headers.get('Referer', '-')
    user_agent = request.headers.get('User-Agent', '-')

    log_line = f'{remote_addr} {ident} {user} [{now}] "{request_line}" {status} {size} "{referer}" "{user_agent}"'

    app.logger.info(log_line)
    return response

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
        except Exception:
            pass
        time.sleep(delay)
    return None

def forward_to_storage(path):
    storage_url = lookup_storage_url()
    if not storage_url:
        return jsonify({"error": "storage service not available"}), 503
    try:
        res = requests.get(f"{storage_url.rstrip('/')}{path}")
        return res.json(), res.status_code
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

@app.route('/average', methods=['GET'])
def average_temp():
    return forward_to_storage('/average')

@app.route('/stats/sensors', methods=['GET'])
def sensor_stats():
    return forward_to_storage('/stats/sensors')

@app.route('/stats/sensors/<device_id>', methods=['GET'])
def sensor_stats_one(device_id):
    return forward_to_storage(f'/stats/sensors/{device_id}')

@app.route('/stats/sensors/<device_id>/<stat>', methods=['GET'])
def sensor_stat_one(device_id, stat):
    return forward_to_storage(f'/stats/sensors/{device_id}/{stat}')

@app.route('/stats/overall', methods=['GET'])
def overall_stats():
    return forward_to_storage('/stats/overall')

@app.route('/stats/overall/<stat>', methods=['GET'])
def overall_stat_one(stat):
    return forward_to_storage(f'/stats/overall/{stat}')

if __name__ == '__main__':
    if not wait_for_registry():
        raise SystemExit(f"Registry not reachable at {REGISTRY_ENDPOINT}, aborting startup")
    register()
    app.run(host=HOST, port=PORT)