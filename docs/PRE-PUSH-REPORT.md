# Pre-push security report

Status: **prepared locally; not pushed**

## Sanitization performed

- Replaced every production credential in public configuration with `{{HOMEPAGE_VAR_*}}` references.
- Moved collector credentials and endpoints to environment variables documented in `.env.example`.
- Replaced all production domains, IP addresses, hostnames, account IDs, tunnel IDs, device IDs, personalized entity IDs, location coordinates, usernames, and filesystem paths.
- Removed the internal LAN endpoint drawer rather than publishing a sanitized topology clone.
- Removed logs, backups, archives, bytecode, generated files, live architecture notes, production service definitions, and unverified third-party wallpapers.
- Stripped metadata from the included logo and replaced the live screenshot with an SVG preview containing only invented values.
- Changed collector defaults to reserved `.example` hostnames, localhost-only bind addresses, TLS verification on, and unprivileged systemd services.

No production credential was rotated, revoked, or edited. Operational credential changes remain entirely with the owner.

## Public helper scripts

- `grafana_bridge.py`: Prometheus/Grafana, Docker proxy, DNS, storage, weather, and service health
- `media_collector.py`: Sonarr/Radarr/Bazarr/Prowlarr/Seerr/SABnzbd/Jellyfin/qBittorrent aggregation
- `telemetry_collector.py`: header health snapshot, WAN latency, and short in-memory history

All three bind to `127.0.0.1` by default. The public systemd examples run under `homepage-telemetry`; they do not run as root.

## Validation results

- YAML parsing: passed for all seven config files
- Python syntax compilation: passed for all three collectors
- JavaScript syntax check: passed
- systemd unit verification: passed; the sandbox emitted only permission-related lookup warnings
- image metadata check: PNG contains no profiles
- independent sensitive-value gate: **0 unapproved findings**
- keyword review: all remaining password/token/secret references are placeholders, environment lookups, documentation, or runtime authentication code
- git history: the sanitized release commit was placed on top of the repository's existing MIT-license-only initial commit; no sensitive history exists

The dedicated `gitleaks` executable was not available locally. The release was checked with two independent local methods instead: a custom multi-pattern scanner and a separate keyword/file review. Before any push, running gitleaks in a trusted local environment is still recommended as an additional defense-in-depth check.

## Known residual risks

- The inventory is based on the available current export, not a fresh read from the live host. A final live-to-public comparison is advisable if production changed after that export.
- API response data can itself contain media titles, container names, VM names, or disk models. Authentication around Homepage remains required even though the repository is sanitized.
- The CSS is intentionally kept close to the working production cascade. Only clearly sensitive/dead asset and drawer rules were removed; a broad visual refactor was avoided.
- The logo is a protected brand asset, not MIT-licensed.
- The public preview is illustrative, not a screenshot of the live dashboard.

## Gate before push

1. Review this report and the repository diff.
2. Optionally run gitleaks locally.
3. Confirm the target repository is the intended empty public repository.
4. Give explicit approval to push.

Until all four are satisfied, do not push.
