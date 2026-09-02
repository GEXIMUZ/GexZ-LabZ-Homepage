#!/usr/bin/env python3
"""Source-scoped, fail-closed same-origin telemetry bridge."""
import base64, json, math, os, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROM = os.environ.get("PROMETHEUS_URL", "http://prometheus.internal.example:9090").rstrip("/")
GRAFANA = os.environ.get("GRAFANA_URL", "http://grafana.internal.example:3000").rstrip("/")
DOCKER = os.environ.get("DOCKER_PROXY_URL", "http://docker-proxy.internal.example:2375").rstrip("/")
SMART = os.environ.get("SMART_API_URL", "http://smart-api.internal.example:9633/api/disks")
ADGUARD_URL = os.environ.get("ADGUARD_URL", "http://adguard.internal.example").rstrip("/")
NPMPLUS_URL = os.environ.get("NPMPLUS_URL", "http://npmplus.internal.example:81").rstrip("/")
WEATHER_LATITUDE = os.environ.get("WEATHER_LATITUDE", "50.8503")
WEATHER_LONGITUDE = os.environ.get("WEATHER_LONGITUDE", "4.3517")
WEATHER_LOCATION = os.environ.get("WEATHER_LOCATION", "Your location")
STALE = int(os.environ.get("TELEMETRY_STALE_SECONDS", "90"))
Q = {
    "cpu": 'pve_cpu_usage_ratio{job="proxmox_pve",id="node/pve"} * 100',
    "ram": '100 * pve_memory_usage_bytes{job="proxmox_pve",id="node/pve"} / pve_memory_size_bytes{job="proxmox_pve",id="node/pve"}',
    "load": 'netdata_system_load_load_average{job="proxmox_netdata",dimension="load1"}',
    "storage": '100 * pve_disk_usage_bytes{job="proxmox_pve",id="node/pve"} / pve_disk_size_bytes{job="proxmox_pve",id="node/pve"}',
    "rx": 'netdata_system_net_kilobits_persec_average{job="proxmox_netdata",dimension="received"} / 8',
    "tx": 'abs(netdata_system_net_kilobits_persec_average{job="proxmox_netdata",dimension="sent"}) / 8',
}


def fetch(url, headers=None, timeout=5):
    try:
        request = urllib.request.Request(url, headers=headers or {"User-Agent": "GexZBridge/2.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode()), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def prom_url(path, query, extra=None):
    params = {"query": query}
    params.update(extra or {})
    return f"{PROM}/api/v1/{path}?{urllib.parse.urlencode(params)}"


def instant(query):
    data, error = fetch(prom_url("query", query))
    results = (data or {}).get("data", {}).get("result", [])
    if error or not results:
        return None, None, error or "no samples"
    try:
        timestamp, raw = results[0]["value"]
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("non-finite sample")
        return value, float(timestamp), None
    except Exception as exc:
        return None, None, f"invalid sample: {exc}"


def metric_map(query):
    data, _ = fetch(prom_url("query", query))
    mapped = {}
    for result in (data or {}).get("data", {}).get("result", []):
        try:
            mapped[result["metric"]["id"]] = float(result["value"][1])
        except (KeyError, TypeError, ValueError):
            continue
    return mapped


def history(query, hours, points=90):
    now = int(time.time())
    extra = {"start": now - hours * 3600, "end": now, "step": max(15, hours * 3600 // points)}
    data, error = fetch(prom_url("query_range", query, extra), timeout=8)
    results = (data or {}).get("data", {}).get("result", [])
    if error or not results:
        return {"timestamps": [], "values": [], "samples": 0, "available": False, "error": error or "no samples"}
    timestamps, values = [], []
    for timestamp, raw in results[0].get("values", []):
        try:
            value = float(raw)
            if math.isfinite(value):
                timestamps.append(time.strftime("%H:%M", time.localtime(float(timestamp))))
                values.append(round(value, 2))
        except (TypeError, ValueError):
            continue
    return {"timestamps": timestamps, "values": values, "samples": len(values), "available": bool(values), "error": None if values else "no valid samples"}


def source(value, timestamp, error):
    age = round(max(0, time.time() - timestamp), 1) if timestamp else None
    return {"available": value is not None, "fresh": value is not None and age is not None and age <= STALE, "age_seconds": age, "error": error}


def docker_details():
    containers, error = fetch(f"{DOCKER}/containers/json?all=1", timeout=4)
    if not isinstance(containers, list):
        return {"available": False, "total": None, "running": None, "healthy": None, "unhealthy": None, "starting": None, "containers": [], "error": error or "invalid response"}
    items, healthy, unhealthy, starting = [], 0, 0, 0
    for container in containers:
        state, status = container.get("State") or "unknown", container.get("Status") or ""
        health = "none"
        match = re.search(r"\((healthy|unhealthy|health: starting)\)", status)
        if match:
            health = "starting" if "starting" in match.group(1) else match.group(1)
        healthy += health == "healthy"
        unhealthy += health == "unhealthy"
        starting += health == "starting"
        name = (container.get("Names") or [container.get("Id", "unknown")[:12]])[0].lstrip("/")
        items.append({"name": name, "state": state, "health": health, "status": status})
    items.sort(key=lambda item: (item["state"] != "running", item["name"].lower()))
    return {"available": True, "total": len(items), "running": sum(i["state"] == "running" for i in items), "healthy": healthy, "unhealthy": unhealthy, "starting": starting, "containers": items, "error": None}


def proxmox_details():
    guests_data, error = fetch(prom_url("query", 'pve_guest_info{job="proxmox_pve"}'))
    up_data, up_error = fetch(prom_url("query", 'pve_up{job="proxmox_pve"}'))
    results = (guests_data or {}).get("data", {}).get("result", [])
    if error or up_error or not results:
        return {"available": False, "total": None, "running": None, "lxc": {"total": None, "running": None}, "vm": {"total": None, "running": None}, "top_guests": [], "error": error or up_error or "no guests"}
    up = {r.get("metric", {}).get("id"): float(r.get("value", [0, 0])[1]) for r in (up_data or {}).get("data", {}).get("result", [])}
    cpu = metric_map('pve_cpu_usage_ratio{job="proxmox_pve",id!="node/pve"}')
    used = metric_map('pve_memory_usage_bytes{job="proxmox_pve",id!="node/pve"}')
    size = metric_map('pve_memory_size_bytes{job="proxmox_pve",id!="node/pve"}')
    items = []
    for result in results:
        metric, gid = result.get("metric", {}), result.get("metric", {}).get("id", "")
        kind = metric.get("type", "lxc").upper()
        items.append({"id": gid, "name": metric.get("name") or gid, "type": kind, "running": up.get(gid) == 1, "cpu_pct": round(cpu[gid] * 100, 1) if gid in cpu else None, "mem_pct": round(100 * used[gid] / size[gid], 1) if gid in used and size.get(gid) else None})
    lxc = [item for item in items if item["type"] == "LXC"]
    vm = [item for item in items if item["type"] in ("QEMU", "VM")]
    top = sorted(items, key=lambda item: item["cpu_pct"] if item["cpu_pct"] is not None else -1, reverse=True)[:7]
    return {"available": True, "total": len(items), "running": sum(i["running"] for i in items), "lxc": {"total": len(lxc), "running": sum(i["running"] for i in lxc)}, "vm": {"total": len(vm), "running": sum(i["running"] for i in vm)}, "top_guests": top, "error": None}


def adguard_creds():
    return os.environ.get("ADGUARD_USERNAME"), os.environ.get("ADGUARD_PASSWORD")


def npmplus_health():
    try:
        request = urllib.request.Request(f"{NPMPLUS_URL}/api/tokens", headers={"User-Agent": "GexZBridge/2.0"}, method="GET")
        with urllib.request.urlopen(request, timeout=4) as response:
            reachable = response.status < 500
        return {"available": False, "reachable": reachable, "error": "widget authentication not configured"}
    except urllib.error.HTTPError as exc:
        return {"available": False, "reachable": exc.code in (400, 401, 403, 405, 429), "error": "widget authentication not configured"}
    except Exception as exc:
        return {"available": False, "reachable": False, "error": f"{type(exc).__name__}: {exc}"}


def npmplus_card():
    health = npmplus_health()
    return {
        "endpoint": urllib.parse.urlparse(NPMPLUS_URL).netloc,
        "api": "Reachable" if health["reachable"] else "Unavailable",
        "role": "In use",
    }


def dns_details():
    user, password = adguard_creds()
    if not user or not password:
        return {"available": False, "queries": None, "blocked": None, "block_rate": None, "avg_latency_ms": None, "error": "credentials unavailable"}
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    data, error = fetch(f"{ADGUARD_URL}/control/stats", {"Authorization": f"Basic {token}", "User-Agent": "GexZBridge/2.0"})
    queries, blocked = (data or {}).get("num_dns_queries"), (data or {}).get("num_blocked_filtering")
    valid = isinstance(queries, (int, float)) and isinstance(blocked, (int, float)) and queries >= 0
    latency = (data or {}).get("avg_processing_time")
    return {"available": valid, "queries": queries if valid else None, "blocked": blocked if valid else None, "block_rate": round(100 * blocked / queries, 1) if valid and queries else 0.0 if valid else None, "avg_latency_ms": round(latency * 1000, 2) if isinstance(latency, (int, float)) else None, "error": None if valid else error or "missing core fields"}


def weather_details():
    params = urllib.parse.urlencode({"latitude": WEATHER_LATITUDE, "longitude": WEATHER_LONGITUDE, "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code", "timezone": "Europe/Brussels"})
    data, error = fetch(f"https://api.open-meteo.com/v1/forecast?{params}", timeout=7)
    current, temp = (data or {}).get("current", {}), (data or {}).get("current", {}).get("temperature_2m")
    if not isinstance(temp, (int, float)):
        return {"available": False, "temp": None, "condition": None, "icon": "☁", "feels_like": None, "humidity": None, "location": WEATHER_LOCATION, "error": error or "missing temperature"}
    code, condition, icon = current.get("weather_code"), "Clear", "☀"
    if code in (1, 2, 3): condition, icon = "Partly cloudy", "⛅"
    elif code in (45, 48): condition, icon = "Fog", "🌫"
    elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82): condition, icon = "Rain", "🌧"
    elif code in (71, 73, 75, 77, 85, 86): condition, icon = "Snow", "❄"
    elif code in (95, 96, 99): condition, icon = "Thunderstorm", "⛈"
    return {"available": True, "temp": round(temp, 1), "condition": condition, "icon": icon, "feels_like": current.get("apparent_temperature"), "humidity": current.get("relative_humidity_2m"), "location": WEATHER_LOCATION, "error": None}


def disks_details():
    disks, error = fetch(SMART, timeout=5)
    if not isinstance(disks, list):
        return {"available": False, "summary": None, "disks": [], "error": error or "invalid response"}
    capacity, free = sum(d.get("capacity_bytes") or 0 for d in disks), sum(d.get("free_bytes") or 0 for d in disks)
    healthy = sum(d.get("healthy") == 1 for d in disks)
    return {"available": True, "summary": {"total_drives": len(disks), "healthy_count": healthy, "warning_count": len(disks) - healthy, "total_capacity_tb": round(capacity / 1024**4, 1), "total_free_tb": round(free / 1024**4, 1)}, "disks": disks, "error": None}


def overview():
    values, sources = {}, {}
    for key in ("cpu", "ram", "load", "storage"):
        value, timestamp, error = instant(Q[key])
        values[key] = round(value, 2 if key == "load" else 1) if value is not None else None
        sources[key] = source(value, timestamp, error)
    pve, docker, npmplus = proxmox_details(), docker_details(), npmplus_health()
    grafana, grafana_error = fetch(f"{GRAFANA}/api/health", timeout=4)
    core_ok = all(s["fresh"] for s in sources.values()) and pve["available"] and docker["available"] and (grafana or {}).get("database") == "ok"
    warnings = [] if npmplus["available"] else ["NPMPlus widget authentication unavailable"]
    return {"generated_at": int(time.time()), "status": "operational" if core_ok else "degraded", "health": "Operational" if core_ok else "Degraded", "warnings": warnings, "cpu_pct": values["cpu"], "ram_pct": values["ram"], "load_1m": values["load"], "storage_pct": values["storage"], "pve_lxc": pve["lxc"], "pve_vm": pve["vm"], "pve_guests": {"total": pve["total"], "running": pve["running"]}, "docker": {k: docker[k] for k in ("total", "running", "healthy", "unhealthy", "starting")}, "sources": {"prometheus": sources, "proxmox_inventory": {"available": pve["available"], "error": pve["error"]}, "docker_proxy": {"available": docker["available"], "error": docker["error"]}, "grafana": {"available": isinstance(grafana, dict), "database": (grafana or {}).get("database"), "error": grafana_error}, "npmplus_api": npmplus}}


def system_history(hours):
    cpu, ram, load = history(Q["cpu"], hours), history(Q["ram"], hours), history(Q["load"], hours)
    return {"range": f"{hours}h", "timestamps": cpu["timestamps"], "cpu": cpu["values"], "ram": ram["values"], "load": load["values"], "samples": cpu["samples"], "available": cpu["available"] and ram["available"], "sources": {"cpu": {"available": cpu["available"], "error": cpu["error"]}, "ram": {"available": ram["available"], "error": ram["error"]}, "load": {"available": load["available"], "error": load["error"]}}}


def network_history(hours):
    rx, tx = history(Q["rx"], hours), history(Q["tx"], hours)
    return {"range": f"{hours}h", "timestamps": rx["timestamps"], "rx_kbs": rx["values"], "tx_kbs": tx["values"], "samples": rx["samples"], "available": rx["available"] and tx["available"], "sources": {"rx": {"available": rx["available"], "error": rx["error"]}, "tx": {"available": tx["available"], "error": tx["error"]}}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        hours = {"1h": 1, "6h": 6, "24h": 24}.get(urllib.parse.parse_qs(parsed.query).get("range", ["1h"])[0], 1)
        if path.endswith("/overview"): result = overview()
        elif path.endswith("/system"): result = system_history(hours)
        elif path.endswith("/network"): result = network_history(hours)
        elif path.endswith("/proxmox"): result = proxmox_details()
        elif path.endswith("/docker"): result = docker_details()
        elif path.endswith("/dns"): result = dns_details()
        elif path.endswith("/npmplus"): result = npmplus_card()
        elif path.endswith("/weather"): result = weather_details()
        elif path.endswith("/storage_disks"): result = disks_details()
        elif path.endswith("/storage"):
            value, timestamp, error = instant(Q["storage"])
            result = {"available": value is not None, "usage_pct": round(value, 1) if value is not None else None, "mount": "node/pve", "source": source(value, timestamp, error)}
        else: result = {"status": "ok", "service": "grafana-bridge", "version": 2}
        payload = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_): return


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("BRIDGE_BIND", "127.0.0.1"), int(os.environ.get("BRIDGE_PORT", "9097"))), Handler).serve_forever()
