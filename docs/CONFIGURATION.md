# Configuration reference

The repository uses two variable styles:

- `HOMEPAGE_VAR_*` values are substituted by Homepage inside YAML.
- collector variables are read directly by the Python services from `/etc/gexz-labz-homepage.env`.

## Homepage groups

`config/services.yaml` contains four groups. Remove any card you do not use, together with its unused variables. Never paste a token directly into YAML.

| Area | Main variables |
| --- | --- |
| Core | `HOME_ASSISTANT_*`, `AUTHENTIK_*`, `PROXMOX_*`, `UPTIME_KUMA_*` |
| Infrastructure | `CLOUDFLARE_*`, `ADGUARD_*`, `DOCKGE_*`, `NPMPLUS_*` |
| Media | `JELLYFIN_*`, `SEERR_*`, `QBITTORRENT_*`, `SABNZBD_*` |
| Quick launch | public URL variables for Bazarr, Grafana, Prowlarr, Radarr, Sonarr, and Frigate |

All example domains end in `.example`; replace them with your own internal DNS names or addresses in the private environment file.

## Custom Home Assistant entities

The included entity IDs are generic examples. Replace them in `config/services.yaml` with entities that are safe for your own private configuration. Entity names can reveal rooms, people, vehicles, and devices, so do not publish a personalized copy.

## Docker

`config/docker.yaml` points to a configurable proxy. Do not expose the Docker Engine on an unauthenticated TCP socket. A restricted read-only socket proxy should allow only the endpoints required for container listing and status.

## Weather

Homepage uses the OpenWeatherMap provider. The custom header uses Open-Meteo through the bridge. Both take coordinates from the environment; location text is generic until you set `WEATHER_LOCATION` privately.

## Optional integrations

The dashboard remains usable if collectors or individual source systems are absent. Remove unused cards and variables to reduce both attack surface and log noise.
