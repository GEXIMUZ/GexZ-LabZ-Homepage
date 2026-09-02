#!/usr/bin/env python3
"""Small fail-closed snapshot service; all infrastructure data comes from the bridge."""
import json, os, re, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
MAX_HISTORY = 120
HISTORY = {"timestamps": [], "cpu": [], "ram": [], "net_rx": [], "net_tx": []}
SNAPSHOT = {"status": "unknown", "generated_at": None, "last_success": None, "age_seconds": None, "pve": {"cpu": None, "ram": None}, "net": {"rx_kbs": None, "tx_kbs": None, "ping_ms": None}, "adguard": {"queries": None, "blocked": None, "block_rate": None}, "docker": {"total": None, "running": None}, "sources": {}, "history": HISTORY}


def fetch(path):
    try:
        with urllib.request.urlopen(f"{os.environ.get('BRIDGE_URL', 'http://127.0.0.1:9097').rstrip('/')}/{path}", timeout=5) as response:
            return json.loads(response.read().decode()), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def ping():
    try:
        result = subprocess.run(["ping", "-c", "1", "-W", "2", os.environ.get("PING_TARGET", "one.one.one.one")], capture_output=True, text=True, timeout=4)
        match = re.search(r"time=([0-9.]+)\s*ms", result.stdout)
        return (round(float(match.group(1)), 1), None) if result.returncode == 0 and match else (None, "no reply")
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def poll():
    global SNAPSHOT
    last_success = None
    while True:
        now = int(time.time())
        overview, overview_error = fetch("overview")
        dns, dns_error = fetch("dns")
        network, network_error = fetch("network?range=1h")
        ping_ms, ping_error = ping()
        complete = bool(overview and overview.get("status") == "operational" and dns and dns.get("available") and network and network.get("available") and ping_ms is not None)
        if complete:
            last_success = now
        cpu = (overview or {}).get("cpu_pct")
        ram = (overview or {}).get("ram_pct")
        rx_values = (network or {}).get("rx_kbs") or []
        tx_values = (network or {}).get("tx_kbs") or []
        rx = rx_values[-1] if rx_values else None
        tx = tx_values[-1] if tx_values else None
        with LOCK:
            if all(value is not None for value in (cpu, ram, rx, tx)):
                for key, value in (("timestamps", time.strftime("%H:%M:%S")), ("cpu", cpu), ("ram", ram), ("net_rx", rx), ("net_tx", tx)):
                    HISTORY[key].append(value)
                    del HISTORY[key][:-MAX_HISTORY]
            SNAPSHOT = {
                "status": "operational" if complete else "degraded",
                "generated_at": now,
                "last_success": last_success,
                "age_seconds": now - last_success if last_success else None,
                "pve": {"cpu": cpu, "ram": ram},
                "net": {"rx_kbs": rx, "tx_kbs": tx, "ping_ms": ping_ms},
                "adguard": {key: (dns or {}).get(key) for key in ("queries", "blocked", "block_rate")},
                "docker": dict((overview or {}).get("docker") or {"total": None, "running": None}),
                "sources": {"overview": {"available": overview is not None, "error": overview_error}, "network": {"available": network is not None and network.get("available", False), "error": network_error}, "adguard": {"available": dns is not None and dns.get("available", False), "error": dns_error}, "wan_ping": {"available": ping_ms is not None, "error": ping_error}},
                "history": {key: list(value) for key, value in HISTORY.items()},
            }
        time.sleep(int(os.environ.get("TELEMETRY_POLL_SECONDS", "15")))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0].rstrip("/") not in ("", "/telemetry", "/api/telemetry"):
            self.send_response(404); self.end_headers(); return
        with LOCK: payload = json.dumps(SNAPSHOT).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_): return


if __name__ == "__main__":
    threading.Thread(target=poll, daemon=True).start()
    ThreadingHTTPServer((os.environ.get("TELEMETRY_BIND", "127.0.0.1"), int(os.environ.get("TELEMETRY_PORT", "9099"))), Handler).serve_forever()
