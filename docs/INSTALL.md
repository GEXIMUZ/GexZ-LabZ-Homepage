# Installation

## 1. Install Homepage

Use an official Homepage image or installation method from [gethomepage.dev](https://gethomepage.dev/installation/). Set `HOMEPAGE_ALLOWED_HOSTS` to the exact hostname used to reach the dashboard; do not use `*` for a public deployment.

## 2. Install the public configuration

Copy the files from `config/` to Homepage's config directory. Copy `public/custom.css`, `public/custom.js`, and `public/images/` to the locations served as Homepage custom assets in your installation.

Keep a private environment file outside the checkout. Start from `.env.example`, replace all `YOUR_*` values, then restrict access:

```sh
sudo install -o homepage-telemetry -g homepage-telemetry -m 0600 .env /etc/gexz-labz-homepage.env
```

Pass the same variables to Homepage using your container, compose, or service configuration.

## 3. Install the optional collectors

Create an unprivileged service account and install the scripts:

```sh
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin homepage-telemetry
sudo install -d -o root -g root -m 0755 /opt/gexz-labz-homepage/scripts
sudo install -o root -g root -m 0755 scripts/*.py /opt/gexz-labz-homepage/scripts/
sudo install -o root -g root -m 0644 systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gexz-grafana-bridge gexz-media-collector gexz-telemetry-collector
```

The collectors are long-running services with internal polling loops, so systemd timers are not needed. Their intervals are set with `MEDIA_POLL_SECONDS` and `TELEMETRY_POLL_SECONDS`.

## 4. Route the APIs

Merge `docs/nginx-locations.conf.example` into the authenticated TLS virtual host that already serves Homepage, then reload nginx. Do not forward ports 9097–9099 from a router or container host.

## 5. Verify

Check each local endpoint before opening the dashboard:

```sh
curl --fail http://127.0.0.1:9097/overview
curl --fail http://127.0.0.1:9098/summary
curl --fail http://127.0.0.1:9099/api/telemetry
```

Unavailable optional sources should produce `available: false` or `N/A`, not fabricated healthy data.
