# Health and status collectors

## Grafana bridge

`scripts/grafana_bridge.py` listens on `127.0.0.1:9097` and serves:

| Path | Source |
| --- | --- |
| `/overview` | Prometheus, Grafana, Proxmox metrics, Docker proxy |
| `/system` and `/network` | Prometheus range queries |
| `/proxmox` | Prometheus PVE exporter metrics |
| `/docker` | restricted Docker proxy |
| `/dns` | AdGuard Home stats with basic authentication |
| `/storage_disks` | a user-supplied SMART JSON API |
| `/weather` | Open-Meteo |

It stores no history and returns unavailable values when a source fails. `TELEMETRY_STALE_SECONDS` controls freshness checks.

## Media collector

`scripts/media_collector.py` listens on `127.0.0.1:9098`. Every `MEDIA_POLL_SECONDS` it queries the configured Sonarr, Radarr, Bazarr, Prowlarr, Seerr, SABnzbd, Jellyfin, and qBittorrent APIs. Results are held only in memory.

TLS certificates are verified by default. `ALLOW_INSECURE_TLS=true` exists only for isolated testing and should not be used in a release deployment; install your private CA instead.

## Telemetry collector

`scripts/telemetry_collector.py` listens on `127.0.0.1:9099`. It combines bridge data with a WAN ping and retains at most 120 in-memory samples. The default poll interval is 15 seconds.

## Failure behavior

Collectors fail closed: missing or invalid responses produce `N/A`, `available: false`, or a degraded state. They do not turn failed requests into zeroes or healthy values.

## systemd

The examples run under the unprivileged `homepage-telemetry` account with a read-only filesystem view, protected home directories, and private temporary storage. They are daemons, not one-shot jobs, so no timers are installed.
