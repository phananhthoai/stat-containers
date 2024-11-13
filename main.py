from flask import Flask, Response
import docker
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
latest_metrics = ""
metrics_lock = threading.Lock()

def get_container_stats(container):
    ta = time.time()
    stat = container.stats(stream=False)
    cpu_delta = stat['cpu_stats']['cpu_usage']['total_usage'] - stat['precpu_stats']['cpu_usage']['total_usage']
    system_delta = stat['cpu_stats']['system_cpu_usage'] - stat['precpu_stats']['system_cpu_usage']

    cpu_count = stat['cpu_stats'].get('online_cpus', 1)
    cpu_percentage = (cpu_delta / system_delta) * cpu_count * 100.0 if system_delta > 0 else 0

    memory_usage = stat['memory_stats']['usage']
    memory_limit = stat['memory_stats']['limit']
    memory_percentage = (memory_usage / memory_limit) * 100.0 if memory_limit > 0 else 0
    result = {
        'name': container.name,
        'cpu_usage': cpu_percentage,
        'memory_usage': memory_percentage,
    }
    print(f'@@ container: {container.name} {time.time() - ta}')
    return result

def get_docker_stats():
    ta = time.time()
    client = docker.from_env()
    containers = client.containers.list()
    stats = []

    with ThreadPoolExecutor(max_workers=min(32, len(containers))) as executor:
        future_to_container = {executor.submit(get_container_stats, container): container for container in containers}
        for future in as_completed(future_to_container):
            stats.append(future.result())

    print(f'@@ all containers {time.time() - ta}')
    return stats


def create_metrics(stats):
    metrics = []
    for stat in stats:
        metrics.append(f'docker_cpu_usage{{container="{stat["name"]}"}} {stat["cpu_usage"]}')
        metrics.append(f'docker_memory_usage{{container="{stat["name"]}"}} {stat["memory_usage"]}')
    return '\n'.join(metrics)

def update_metrics():
    global latest_metrics
    while True:
        stats = get_docker_stats()
        new_metrics = create_metrics(stats)
        with metrics_lock:
            latest_metrics = new_metrics
        time.sleep(15) 

@app.route('/metrics')
def metrics():
    with metrics_lock:
        return Response(latest_metrics, mimetype='text/plain')


if __name__ == '__main__':
    update_thread = threading.Thread(target=update_metrics, daemon=True)
    update_thread.start()    
    app.run(host='0.0.0.0', port=9091)
    
