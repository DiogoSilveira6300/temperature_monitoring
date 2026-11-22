import json
import os
import threading

import sensor

with open("./config/sensors.json") as config_file:
	config = json.load(config_file)

REGISTRY_ENDPOINT = config["registry_endpoint"]
DEVICES = config["devices"]
REGISTRY_RETRIES = int(os.getenv("SENSOR_REGISTRY_RETRIES", config.get("registry_retries", 5)))
REGISTRY_RETRY_DELAY = float(os.getenv("SENSOR_REGISTRY_RETRY_DELAY", config.get("registry_retry_delay", 1)))


def run_sensors():
	threads = []
	for device in DEVICES:
		t = threading.Thread(
			target=sensor.run_sensor,
			args=(device["device_id"], device["send_interval"], REGISTRY_ENDPOINT, device.get("role", "sensor")),
			kwargs={"retries": REGISTRY_RETRIES, "delay": REGISTRY_RETRY_DELAY},
			daemon=True,
		)
		t.start()
		threads.append(t)
		print(f"Started {device['device_id']}")
	return threads


if __name__ == "__main__":
	if not sensor.wait_for_registry(REGISTRY_ENDPOINT, retries=REGISTRY_RETRIES, delay=REGISTRY_RETRY_DELAY):
		raise SystemExit(f"Registry not reachable at {REGISTRY_ENDPOINT}, aborting startup")
	threads = run_sensors()
	try:
		for t in threads:
			t.join()
	except KeyboardInterrupt:
		print("Stopping sensors...")
