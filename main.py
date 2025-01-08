from flask import Flask, Response
import docker
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import logging

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Get stack environment variable
stacks = os.getenv('STACKS', 'all')

app = Flask(__name__)
latest_metrics = ""
metrics_lock = threading.Lock()

# Docker client initialization
client = docker.from_env()

def get_container_stats(container):
    try:
        ta = time.time()
        stat = container.stats(stream=False)

        # Safely retrieve CPU and memory stats
        cpu_delta = stat['cpu_stats']['cpu_usage']['total_usage'] - stat['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stat['cpu_stats'].get('system_cpu_usage', 0) - stat['precpu_stats'].get('system_cpu_usage', 0)
        cpu_count = stat['cpu_stats'].get('online_cpus', 1)
        cpu_percentage = (cpu_delta / system_delta) * cpu_count * 100.0 if system_delta > 0 else 0

        memory_usage = stat['memory_stats'].get('usage', 0)
        memory_limit = stat['memory_stats'].get('limit', 0)
        memory_percentage = (memory_usage / memory_limit) * 100.0 if memory_limit > 0 else 0

        result = {
            'name': container.name,
            'cpu_usage': round(cpu_percentage, 2),
            'memory_usage': round(memory_percentage, 2),
        }

        logging.info(f"Processed stats for container: {container.name} ({time.time() - ta:.2f}s)")
        return result
    except KeyError as e:
        logging.warning(f"Missing key in container stats for {container.name}: {e}")
    except Exception as e:
        logging.error(f"Error processing stats for container {container.name}: {e}")
    return None

def get_docker_stats():
    try:
        containers = client.containers.list()
        if stacks == 'all':
            regex_containers = containers
        elif ',' in stacks:
            stack_names = [stack.strip() for stack in stacks.split(',')]
            regex_containers = [
                item for item in containers
                if any(stack in item.attrs.get('Name', '') for stack in stack_names)
            ]
        else:
            regex_containers = [
                item for item in containers if stacks in item.attrs.get('Name', '')
            ]

        stats = []
        with ThreadPoolExecutor(max_workers=min(32, len(regex_containers))) as executor:
            future_to_container = {executor.submit(get_container_stats, container): container for container in regex_containers}
            for future in as_completed(future_to_container):
                result = future.result()
                if result:
                    stats.append(result)

        return stats
    except Exception as e:
        logging.error(f"Error getting Docker stats: {e}")
        return []

def create_metrics(stats):
    metrics = []
    for stat in stats:
        metrics.append(f'docker_cpu_usage{{container="{stat["name"]}"}} {stat["cpu_usage"]}')
        metrics.append(f'docker_memory_usage{{container="{stat["name"]}"}} {stat["memory_usage"]}')
    return '\n'.join(metrics)

def update_metrics():
    global latest_metrics
    while True:
        try:
            logging.info("Updating metrics...")
            stats = get_docker_stats()
            new_metrics = create_metrics(stats)
            with metrics_lock:
                latest_metrics = new_metrics
            logging.info("Metrics updated successfully.")
        except Exception as e:
            logging.error(f"Error updating metrics: {e}")
        time.sleep(30)

@app.route('/metrics')
def metrics():
    with metrics_lock:
        return Response(latest_metrics, mimetype='text/plain')

if __name__ == '__main__':
    update_thread = threading.Thread(target=update_metrics, daemon=True)
    update_thread.start()
    app.run(host='0.0.0.0', port=9091)

