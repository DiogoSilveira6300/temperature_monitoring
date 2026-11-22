import argparse
import requests
import time
import random


def lookup_ingest_url(registry_endpoint, retries=5, delay=1):
	"""Query the registry for the ingestion service URL and append /ingest if needed."""
	service_url = f"{registry_endpoint.rstrip('/')}/services/ingestion-service"
	for attempt in range(retries):
		try:
			r = requests.get(service_url, timeout=2)
			r.raise_for_status()
			ingest = r.json()
			if ingest and "url" in ingest:
				url = ingest["url"]
				# normalize to ingest endpoint if base url provided
				if not url.endswith("/ingest"):
					url = url.rstrip("/") + "/ingest"
				return url
		except Exception:
			pass
		time.sleep(delay)
	return None


def parse_args():
	p = argparse.ArgumentParser()
	p.add_argument("--device-id", required=True, help="Device ID to register and send from")
	p.add_argument("--send-interval", type=float, required=True, help="Seconds between temperature sends")
	p.add_argument("--registry-endpoint", required=True, help="Base URL of the registry service")
	p.add_argument("--role", default="sensor", help="Role to register with the registry")
	p.add_argument("--registry-retries", type=int, default=5, help="Number of retries when contacting the registry")
	p.add_argument("--registry-retry-delay", type=float, default=1, help="Seconds to wait between registry retries")
	return p.parse_args()


def wait_for_registry(registry_endpoint, retries=5, delay=1):
	"""Check that the registry is reachable; used to gate sensor startup."""
	health_url = f"{registry_endpoint.rstrip('/')}/health"
	for attempt in range(retries):
		try:
			r = requests.get(health_url, timeout=2)
			if r.status_code == 200:
				return True
		except Exception:
			pass
		time.sleep(delay)
	return False


def register(device_id, registry_endpoint, role="sensor", retries=5, delay=1):
	service_url = lookup_ingest_url(registry_endpoint, retries=retries, delay=delay)
	payload = {
		"name": device_id,
		"url": service_url or "",
		"role": role,
	}
	# try a few times to register (registry might not be up yet)
	register_url = f"{registry_endpoint.rstrip('/')}/register"
	for attempt in range(retries):
		try:
			requests.post(register_url, json=payload, timeout=2)
			print("Registered with registry:", payload)
			return
		except Exception:
			print(f"Registry not available, retrying ({attempt + 1}/{retries})")
			time.sleep(delay)
	print("Failed to register with registry")



def send_temp(device_id, send_interval, registry_endpoint, retries=5, delay=1):
	while True:
		temp = round(random.uniform(20.0, 30.0), 2)
		payload = {"device_id": device_id, "temperature": temp}
		try:
			service_url = lookup_ingest_url(registry_endpoint, retries=retries, delay=delay)
			if not service_url:
				print("No ingest service found in registry, skipping send")
			else:
				requests.post(service_url, json=payload)
			print("Sent:", payload)
		except Exception as e:
			print("Error sending temperature:", e)
		time.sleep(send_interval)


def run_sensor(device_id, send_interval, registry_endpoint, role="sensor", retries=5, delay=1):
	"""Run a single sensor loop: register then send temperatures forever."""
	register(device_id, registry_endpoint, role, retries=retries, delay=delay)
	send_temp(device_id, send_interval, registry_endpoint, retries=retries, delay=delay)


if __name__ == "__main__":
	# preserve programmatic API while allowing script usage
	args = parse_args()
	if not wait_for_registry(args.registry_endpoint, retries=args.registry_retries, delay=args.registry_retry_delay):
		raise SystemExit(f"Registry not reachable at {args.registry_endpoint}, aborting startup")
	run_sensor(args.device_id, args.send_interval, args.registry_endpoint, args.role, retries=args.registry_retries, delay=args.registry_retry_delay)
