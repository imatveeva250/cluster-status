"""cluster-status: live cluster numbers from Prometheus, through a fixed set of queries."""

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse

PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL", "http://kube-prometheus-stack-prometheus.monitoring.svc:9090"
)
CACHE_TTL = 15  # seconds; Prometheus is queried at most once per TTL, whatever the traffic
QUERY_TIMEOUT = 5  # seconds per query
STATIC_DIR = Path(__file__).parent / "static"

# The only PromQL this service ever runs. Visitors cannot send their own queries.
QUERIES = {
    "memory_percent": '100 * (1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes))',
    "cpu_percent": '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
    "disk_percent": '100 * (1 - sum(node_filesystem_avail_bytes{mountpoint="/"}) / sum(node_filesystem_size_bytes{mountpoint="/"}))',
    "pods_running": 'sum(kube_pod_status_phase{phase="Running"})',
    "uptime_seconds": 'time() - max(node_boot_time_seconds)',
    "endpoints_up": 'sum(publicendpoint_up)',
    "endpoints_total": 'count(publicendpoint_up)',
}

# Queries whose data may be missing without the whole status failing.
OPTIONAL = {"endpoints_up", "endpoints_total"}

log = logging.getLogger("cluster-status")

# No interactive API docs on a public site.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

_lock = threading.Lock()
_cache = {"status": None, "fetched_at": 0.0}


def query(promql: str) -> float:
    url = f"{PROMETHEUS_URL}/api/v1/query?" + urllib.parse.urlencode({"query": promql})
    with urllib.request.urlopen(url, timeout=QUERY_TIMEOUT) as resp:
        body = json.load(resp)
    result = body.get("data", {}).get("result", [])
    if body.get("status") != "success" or not result:
        raise ValueError("no data")
    return float(result[0]["value"][1])

def get_status() -> dict:
    with _lock:
        now = time.time()
        if _cache["status"] is not None and now - _cache["fetched_at"] < CACHE_TTL:
            return _cache["status"]
        metrics = {}
        for name, promql in QUERIES.items():
            try:
                metrics[name] = query(promql)
            except Exception as exc:
                if name in OPTIONAL:
                    log.info("optional query %s: %s", name, exc)
                    continue
                raise RuntimeError(f"{name}: {exc}") from exc
        status = {
            "metrics": metrics,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        }
        _cache["status"] = status
        _cache["fetched_at"] = now
        return status

@app.get("/api/status")
def api_status(response: Response) -> dict:
    try:
        status = get_status()
    except Exception as exc:
        log.warning("status: %s", exc)
        raise HTTPException(status_code=503, detail="metrics unavailable") from None
    response.headers["Cache-Control"] = "public, max-age=15"
    return status


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}

@app.api_route("/", methods=["GET", "HEAD"])
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
