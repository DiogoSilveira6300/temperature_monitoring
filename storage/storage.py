from flask import Flask, request, jsonify
import requests
import sqlite3
import statistics
import time
from datetime import datetime
import logging

import psutil
import os
import json

app = Flask(__name__)

with open("./config/storage.json") as config_file:
    config = json.load(config_file)

DB = os.getenv("STORAGE_DB", config["db"])
SERVICE_NAME = os.getenv("STORAGE_SERVICE_NAME", config["service_name"])
SERVICE_URL = os.getenv("STORAGE_SERVICE_URL", config["service_url"])
ROLE = os.getenv("STORAGE_ROLE", config["role"])
REGISTRY_ENDPOINT = os.getenv("REGISTRY_ENDPOINT", config["registry_endpoint"])
REGISTRY_RETRIES = int(os.getenv("STORAGE_REGISTRY_RETRIES", config.get("registry_retries", 5)))
REGISTRY_RETRY_DELAY = float(os.getenv("STORAGE_REGISTRY_RETRY_DELAY", config.get("registry_retry_delay", 1)))
HOST = os.getenv("STORAGE_HOST", config["host"])
PORT = int(os.getenv("STORAGE_PORT", config["port"]))
LOG_PATH = os.getenv("STORAGE_LOG_PATH", config["log_path"])
START_TIME = time.time()

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
handler = logging.FileHandler(LOG_PATH)
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(handler)

process = psutil.Process(os.getpid())
process.cpu_percent()  # First call to initialize CPU monitoring


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


def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS temperatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            temperature REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


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


def register():
    requests.post(
        f"{REGISTRY_ENDPOINT.rstrip('/')}/register",
        json={
            "name": SERVICE_NAME,
            "url": SERVICE_URL,
            "role": ROLE
        }
    )


@app.route('/store', methods=['POST'])
def store():
    data = request.get_json()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO temperatures (device_id, temperature) VALUES (?, ?)",
        (data["device_id"], data["temperature"])
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "stored"}), 200

@app.route('/average', methods=['GET'])
def average_temp():
	avg = _compute_single_stat("average")
	return jsonify({"average_temperature": avg})


def _compute_stats(device_id=None):
	conn = sqlite3.connect(DB)
	c = conn.cursor()
	if device_id:
		c.execute("SELECT temperature, device_id FROM temperatures WHERE device_id = ? ORDER BY id", (device_id,))
	else:
		c.execute("SELECT temperature, device_id FROM temperatures ORDER BY id")
	rows = c.fetchall()
	conn.close()
	if not rows:
		return None

	temperatures = [row[0] for row in rows]
	latest_temperature, _ = rows[-1]
	max_index = max(range(len(rows)), key=lambda i: rows[i][0])
	min_index = min(range(len(rows)), key=lambda i: rows[i][0])

	stats = {
		"latest": round(latest_temperature, 2),
		"highest": round(rows[max_index][0], 2),
		"lowest": round(rows[min_index][0], 2),
		"average": round(statistics.mean(temperatures), 2),
		"median": round(statistics.median(temperatures), 2),
	}
	# for the aggregate (all sensors) view, identify which sensor hit each extreme
	if device_id is None:
		stats["highest"] = {"temperature": round(rows[max_index][0], 2), "device_id": rows[max_index][1]}
		stats["lowest"] = {"temperature": round(rows[min_index][0], 2), "device_id": rows[min_index][1]}
	return stats


def _compute_single_stat(stat, device_id=None):
	"""Compute just one stat, querying only what that stat needs."""
	conn = sqlite3.connect(DB)
	c = conn.cursor()
	where_clause = "WHERE device_id = ?" if device_id else ""
	params = (device_id,) if device_id else ()

	if stat == "latest":
		c.execute(f"SELECT temperature FROM temperatures {where_clause} ORDER BY id DESC LIMIT 1", params)
		row = c.fetchone()
		conn.close()
		return round(row[0], 2) if row else None

	if stat == "average":
		c.execute(f"SELECT AVG(temperature) FROM temperatures {where_clause}", params)
		avg = c.fetchone()[0]
		conn.close()
		return round(avg, 2) if avg is not None else None

	if stat == "median":
		c.execute(f"SELECT temperature FROM temperatures {where_clause}", params)
		temperatures = [row[0] for row in c.fetchall()]
		conn.close()
		return round(statistics.median(temperatures), 2) if temperatures else None

	if stat in ("highest", "lowest"):
		order = "DESC" if stat == "highest" else "ASC"
		c.execute(f"SELECT temperature, device_id FROM temperatures {where_clause} ORDER BY temperature {order} LIMIT 1", params)
		row = c.fetchone()
		conn.close()
		if row is None:
			return None
		temperature, row_device_id = row
		if device_id is None:
			return {"temperature": round(temperature, 2), "device_id": row_device_id}
		return round(temperature, 2)

	conn.close()
	return None


@app.route('/stats/sensors', methods=['GET'])
def sensor_stats():
	conn = sqlite3.connect(DB)
	c = conn.cursor()
	c.execute("SELECT DISTINCT device_id FROM temperatures")
	device_ids = [row[0] for row in c.fetchall()]
	conn.close()

	return jsonify({device_id: _compute_stats(device_id) for device_id in device_ids})


@app.route('/stats/overall', methods=['GET'])
def overall_stats():
	stats = _compute_stats()
	if stats is None:
		return jsonify({"error": "No data"}), 404
	return jsonify(stats)


STAT_KEYS = {"latest", "highest", "lowest", "average", "median"}


@app.route('/stats/sensors/<device_id>', methods=['GET'])
def sensor_stats_one(device_id):
	stats = _compute_stats(device_id)
	if stats is None:
		return jsonify({"error": "No data for device"}), 404
	return jsonify(stats)


@app.route('/stats/sensors/<device_id>/<stat>', methods=['GET'])
def sensor_stat_one(device_id, stat):
	if stat not in STAT_KEYS:
		return jsonify({"error": f"Unknown stat '{stat}'"}), 400
	value = _compute_single_stat(stat, device_id)
	if value is None:
		return jsonify({"error": "No data for device"}), 404
	return jsonify({stat: value})


@app.route('/stats/overall/<stat>', methods=['GET'])
def overall_stat_one(stat):
	if stat not in STAT_KEYS:
		return jsonify({"error": f"Unknown stat '{stat}'"}), 400
	value = _compute_single_stat(stat)
	if value is None:
		return jsonify({"error": "No data"}), 404
	return jsonify({stat: value})


if __name__ == '__main__':
    if not wait_for_registry():
        raise SystemExit(f"Registry not reachable at {REGISTRY_ENDPOINT}, aborting startup")
    init_db()
    register()
    app.run(host=HOST, port=PORT)