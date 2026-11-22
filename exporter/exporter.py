from prometheus_client import start_http_server, Gauge, Counter, Histogram
import requests
import time

import json
import os

with open("./config/exporter.json") as config_file:
    config = json.load(config_file)
    
SERVICES = os.getenv("EXPORTER_SERVICES", config["services"])
PORT = int(os.getenv("EXPORTER_PORT", config["port"]))
INTERVAL = int(os.getenv("EXPORTER_INTERVAL", config["interval"]))

# Define metrics
health_gauge = Gauge('service_health', 
    'Service availability status', 
    ['service'])

latency_histogram = Histogram('service_request_latency_seconds',
    'Request latency in seconds',
    ['service'],
    buckets=[0.1, 0.2, 0.5, 1.0, 2.0, 5.0])

# System metrics from health endpoint
memory_gauge = Gauge('service_memory_mb', 
    'Service memory usage in MB', 
    ['service'])
cpu_gauge = Gauge('service_cpu_percent', 
    'Service CPU usage percentage', 
    ['service'])
thread_gauge = Gauge('service_thread_count', 
    'Service thread count', 
    ['service'])
connections_gauge = Gauge('service_open_connections',
    'Number of open connections',
    ['service'])
uptime_gauge = Gauge('service_uptime_seconds',
    'Service uptime in seconds',
    ['service'])

def check_service_health():
    for service in SERVICES:
        service_base = service.rstrip('/health')
        try:
            # Measure response time
            start_time = time.time()
            response = requests.get(service, timeout=5)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                metrics = data.get('metrics', {})
                
                # Update all gauges with data from health endpoint
                health_gauge.labels(service=service_base).set(1)
                memory_gauge.labels(service=service_base).set(metrics.get('memory_usage', 0))
                cpu_gauge.labels(service=service_base).set(metrics.get('cpu_percent', 0))
                thread_gauge.labels(service=service_base).set(metrics.get('thread_count', 0))
                connections_gauge.labels(service=service_base).set(metrics.get('open_connections', 0))
                uptime_gauge.labels(service=service_base).set(data.get('uptime', 0))
                
                # Record request latency
                latency_histogram.labels(service=service_base).observe(duration)
            else:
                health_gauge.labels(service=service_base).set(0)
        
        except requests.exceptions.RequestException:
            health_gauge.labels(service=service_base).set(0)

if __name__ == '__main__':
    start_http_server(PORT)
    print(f"Exporter started on port {PORT}")
    while True:
        check_service_health()
        time.sleep(INTERVAL)