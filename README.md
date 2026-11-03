# cluster-status

The small public page at [status.matveeva.dev](https://status.matveeva.dev). It shows a few
live numbers from my Raspberry Pi cluster: memory, CPU, disk, running pods, how many of my
public endpoints are up, and how long the node has been running.

The cluster itself, and how this app is deployed there, lives in
[imatveeva250/pi-cluster](https://github.com/imatveeva250/pi-cluster).

## How it works

A FastAPI backend asks the cluster's Prometheus for seven numbers and hands them to a static
page as JSON. That's the whole app: `app.py` and `static/index.html`.

I wanted a public page without making Prometheus or Grafana public, so a few rules follow
from that:

- The queries are hardcoded in `app.py`. Visitors can't send their own, so the page can't be
  used to poke around the cluster or to load Prometheus with heavy queries.
- Results are cached for 15 seconds. However many people open the page, Prometheus gets at
  most one round of queries per 15 seconds.
- It only returns totals. No pod names, namespaces or anything else that identifies what runs
  where.
- The public endpoint numbers are optional. If that data is missing, the page shows "no data"
  for that row and the rest still works.

The page itself is plain HTML, CSS and a bit of JavaScript, with no external fonts or
scripts. The pixel-art board's activity light blinks faster when the CPU is busier, which
serves only entertainment purpose.

## Endpoints

- `/` is the page.
- `/api/status` returns the numbers as JSON, or a 503 if Prometheus can't be reached.
- `/healthz` is for Kubernetes probes. It doesn't touch Prometheus, so the pod stays up even
  when Prometheus is down, the page just says it has no reading.

## Running it locally

Prometheus is needed first. Then, a port-forward to the cluster:

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PROMETHEUS_URL=http://localhost:9090 uvicorn app:app --port 8080
```

Then open http://localhost:8080.

## Image and releases

Pushing a tag like `v0.2.2` makes GitHub Actions build an arm64 image on a native arm64
runner and push it to `ghcr.io/imatveeva250/cluster-status`. There's no `latest` tag on
purpose: the cluster always runs an exact version, and a release is a new tag here followed
by changing the image tag in pi-cluster.

The container runs as UID 10001 with a read-only root filesystem.

## License

MIT
