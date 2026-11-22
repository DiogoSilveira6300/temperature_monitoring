from flask import Flask, request, jsonify
from datetime import datetime
import time
import logging
import psutil
import os
import json
import threading
import requests
import re

app = Flask(__name__)

with open("./config/registry.json") as config_file:
	config = json.load(config_file)

SERVICE_NAME = os.getenv("REGISTRY_SERVICE_NAME", config["service_name"])
HOST = os.getenv("REGISTRY_HOST", config["host"])
PORT = int(os.getenv("REGISTRY_PORT", config["port"]))
LOG_PATH = os.getenv("REGISTRY_LOG_PATH", config["log_path"])

RUN_HEALTH_CHECKS = os.getenv("REGISTRY_RUN_HEALTH_CHECKS", str(config.get("run_health_checks", "true"))).lower() == "true"
HEALTH_CHECK_INTERVAL = int(os.getenv("REGISTRY_HEALTH_CHECK_INTERVAL", config["health_check_interval"]))
HEALTH_CHECK_TIMEOUT = int(os.getenv("REGISTRY_HEALTH_CHECK_TIMEOUT", config.get("health_check_timeout", 5)))

PERFORM_LOAD_BALANCING = os.getenv("REGISTRY_PERFORM_LOAD_BALANCING", str(config.get("perform_load_balancing", "true"))).lower() == "true"


os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
handler = logging.FileHandler(LOG_PATH)
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(handler)

START_TIME = time.time()

process = psutil.Process(os.getpid())
process.cpu_percent()

registry = {}
registry_lock = threading.Lock()


# Endpoints -----------------------------------------------------------------------------------------
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


@app.route('/register', methods=['POST'])
def register():
	data = request.get_json()
	if not isinstance(data, dict):
		return jsonify({"error": "Request body must be a JSON object"}), 400

	service = data.get("service", data.get("name"))  # "service" preferred, "name" kept for backward compatibility
	url = data.get("url")
	role = data.get("role")

	if not service or not url:
		return jsonify({"error": "Missing name or url"}), 400
	if not check_service_name(service):
		return jsonify({"error": "Invalid service name"}), 400

	instance = {
		"url": url,
		"timestamp": datetime.utcnow().isoformat()
	}

	with registry_lock:
		upsert_instance(service, role, instance)
	
	return jsonify({"message": f"{service} registered"}), 200


@app.route('/unregister', methods=['DELETE'])
def unregister():
	data = request.get_json()
	if not isinstance(data, dict):
		return jsonify({"error": "Request body must be a JSON object"}), 400

	service = data.get("service", data.get("name"))  # "service" preferred, "name" kept for backward compatibility
	if not check_service_name(service):
		return jsonify({"error": "Invalid or missing service name"}), 400

	with registry_lock:
		if registry.pop(service, None) is not None:
			return jsonify({"message": f"{service} unregistered"}), 200
	return jsonify({"error": "Not found"}), 404


@app.route('/services', methods=['GET'])
def services():
	with registry_lock:
		return jsonify(registry)


@app.route('/services/<service>', methods=['GET'])
def get_service(service):
	service = pick_service(service) if check_service_name(service) else None
	if service:
		return jsonify(service)
	else:
		return jsonify({"error": "Not found"}), 404


# Confirm that the service name follows the expected pattern: <name>-<role>
def check_service_name(name):
	pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+$"
	return isinstance(name, str) and re.fullmatch(pattern, name) is not None


# Add or refresh an instance for a service; must be called while holding registry_lock
def upsert_instance(service, role, instance):
	if service not in registry:
		registry[service] = {"role": role, "instances": []}
	if role:
		registry[service]["role"] = role
	for existing in registry[service]["instances"]:
		if existing["url"] == instance["url"]:
			existing["timestamp"] = instance["timestamp"]
			break
	else:
		registry[service]["instances"].append(instance)


# Load balancing -----------------------------------------------------------------------------------

# Pick an instance of the named service with a round-robin strategy
def pick_service(name):
	with registry_lock:
		instances = registry.get(name, {}).get("instances", [])
		if not instances:
			return None
		instance = instances.pop(0)
		instances.append(instance)
		return instance


# Health checking ----------------------------------------------------------------------------------
def health_check():
	with registry_lock:
		services_snapshot = [
			(name, instance.copy())
			for name, entry in registry.items()
			for instance in entry["instances"]
		]
	for name, service in services_snapshot:
		try:
			response = requests.get(f"{service['url']}/health", timeout=HEALTH_CHECK_TIMEOUT)
			healthy = response.status_code == 200
		except requests.exceptions.RequestException:
			healthy = False
		except Exception as exception:
			app.logger.exception(f"Unexpected error checking {name}", exc_info=exception)
			continue
		if not healthy:
			with registry_lock:
				entry = registry.get(name)
				instances = entry["instances"] if entry else []
				remaining = [
					instance for instance in instances
					if (
						instance["url"] != service["url"]
						or instance["timestamp"] != service["timestamp"]
					)
				]
				if entry is not None:
					if remaining:
						entry["instances"] = remaining
					else:
						registry.pop(name, None)
			app.logger.warning(
				f"Service instance {service['url']} removed from registry due to failed health check"
			)


def run_health_checks():
	while True:
		health_check()
		time.sleep(HEALTH_CHECK_INTERVAL * 60)


if __name__ == '__main__':
	if RUN_HEALTH_CHECKS:
		threading.Thread(target=run_health_checks, daemon=True).start()
	app.run(host=HOST, port=PORT)
  