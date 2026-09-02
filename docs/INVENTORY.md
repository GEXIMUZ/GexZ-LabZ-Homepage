# Release inventory

This inventory is based on the available current Homepage export and its accompanying service definitions. It does not assert that unrelated files elsewhere on the live host were inspected.

## Included in the public release

| Area | Files | Reason |
| --- | --- | --- |
| Homepage configuration | `config/*.yaml` | Required to reproduce cards, widgets, layout, Docker proxy, and Proxmox integration |
| Theme and views | `public/custom.css`, `public/custom.js` | Required for the GexZ LabZ shell, Media view, and Analytics view |
| Brand asset | `public/images/gexz-3d.png` | Required by the header; metadata stripped and separately licensed |
| Collectors | `scripts/*.py` | Required for health, DNS, Docker, storage, media, and telemetry data |
| Service examples | `systemd/*.service` | Reproducible, unprivileged collector startup |
| Proxy example | `docs/nginx-locations.conf.example` | Routes same-origin API paths without exposing collector ports |
| Documentation | `README.md`, `docs/`, `SECURITY.md` | Installation, configuration, security, and data-source behavior |

## Excluded

| Source material | Classification | Reason |
| --- | --- | --- |
| real environment and credential values | secret | Never publish or commit |
| production `services.yaml`, `settings.yaml`, and widget values | sensitive source | Contained live tokens, account identifiers, internal URLs, location data, and personalized entity IDs |
| Homepage log files | production-only / generated | Large, volatile, and may contain hosts, errors, or request details |
| `.bak` files and configuration archives | backup | Duplicate sensitive history with no public runtime value |
| Python bytecode and caches | generated | Rebuilt automatically; may preserve source strings |
| telemetry source-of-truth document | sensitive architecture | Described the production topology and exact endpoints |
| LAN endpoint drawer | sensitive functionality | Exposed a convenient map of internal services and ports |
| production systemd unit for Homepage | deployment-specific | Ran as root and allowed all host headers; unsafe as a public example |
| third-party wallpapers | license unknown | Redistribution rights were not established |
| live screenshots | sensitive visual | Could expose service names, topology, users, titles, or status data |
| complete nginx configuration | host-specific | Contains unrelated host configuration; only scoped locations are reproduced |

No cronjobs or systemd timers were present in the available export. The three collector processes are daemons with internal polling intervals, so the public examples use services rather than timers. No generated JSON/status files are required; collector state is kept in memory.
