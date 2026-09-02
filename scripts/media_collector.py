#!/usr/bin/env python3
import time
import json
import urllib.request
import urllib.error
import ssl
import os
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Lock

ssl_ctx = ssl.create_default_context()
if os.environ.get("ALLOW_INSECURE_TLS", "false").lower() == "true":
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

def service(name, default_url, key_name=None):
    prefix = name.upper()
    item = {"url": os.environ.get(f"{prefix}_URL", default_url).rstrip("/")}
    if key_name:
        item["key"] = os.environ.get(key_name, "")
    return item

CONFIG = {
    "sonarr": service("sonarr", "http://sonarr.internal.example:8989", "SONARR_API_KEY"),
    "radarr": service("radarr", "http://radarr.internal.example:7878", "RADARR_API_KEY"),
    "bazarr": service("bazarr", "http://bazarr.internal.example:6767", "BAZARR_API_KEY"),
    "prowlarr": service("prowlarr", "http://prowlarr.internal.example:9696", "PROWLARR_API_KEY"),
    "seerr": service("seerr", "http://seerr.internal.example:5055", "SEERR_API_KEY"),
    "sabnzbd": service("sabnzbd", "http://sabnzbd.internal.example:8080", "SABNZBD_API_KEY"),
    "jellyfin": {**service("jellyfin", "http://jellyfin.internal.example:8096", "JELLYFIN_API_KEY"), "user_id": os.environ.get("JELLYFIN_USER_ID", "")},
    "qbittorrent": {"url": os.environ.get("QBITTORRENT_URL", "http://qbittorrent.internal.example:8081").rstrip("/"), "user": os.environ.get("QBITTORRENT_USERNAME", ""), "pass": os.environ.get("QBITTORRENT_PASSWORD", "")},
}

data_lock = Lock()
last_success = None

cache_data = {
    "status": "unknown", "generated_at": None, "last_success": None, "age_seconds": None, "sources": {},
    "summary": {
        "requests": None,
        "downloading": None,
        "import_issues": None,
        "wanted": None,
        "missing_subs": None,
        "active_streams": None,
        "jellyfin": {
            "movies": None,
            "series": None,
            "episodes": None
        }
    },
    "calendar": [],
    "problems": {
        "sonarr": {"missing_count": None, "queue_warnings": None},
        "radarr": {"missing_count": None, "queue_warnings": None},
        "bazarr": {"wanted_episodes": None, "wanted_movies": None},
        "prowlarr": {"unhealthy": []},
        "qbittorrent": {"stalled": None, "errors": None},
        "sabnzbd": {"warnings": None, "status": None},
        "seerr": {"pending_count": None, "pending_requests": []}
    },
    "bazarr": {
        "wanted_episodes": None,
        "wanted_movies": None,
        "version": None,
        "languages": []
    },
    "download_engine": {
        "qbittorrent": {"available": False, "dl_speed": None, "up_speed": None, "active": None, "stalled": None, "torrents": []},
        "sabnzbd": {"available": False, "speed": None, "remaining_mb": None, "queue_count": None, "status": None}
    }
}

def fetch_json(url, headers=None, timeout=4):
    try:
        req = urllib.request.Request(url, headers=headers or {'User-Agent': 'MediaCollector/1.0'})
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None

def format_bytes(size):
    try:
        size = float(size)
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB/s"
    except Exception:
        return None

def poll_media():
    global cache_data, last_success
    while True:
        try:
            start_str = time.strftime("%Y-%m-%dT00:00:00Z")
            end_str = time.strftime("%Y-%m-%dT23:59:59Z", time.gmtime(time.time() + (14 * 86400)))
            start_day = start_str[:10]
            end_day = end_str[:10]

            # 1. Seerr Total Requests & Pending
            requests_raw = fetch_json(f"{CONFIG['seerr']['url']}/api/v1/request?take=100", {'X-Api-Key': CONFIG['seerr']['key']})
            seerr_ok = isinstance(requests_raw, dict)
            requests_data = requests_raw if seerr_ok else {}
            req_list = requests_data.get('results', []) if isinstance(requests_data, dict) else []
            total_requests = requests_data.get('pageInfo', {}).get('results', len(req_list)) if seerr_ok else None
            pending_requests = [r for r in req_list if isinstance(r, dict) and r.get('status') == 1]

            pending_formatted = []
            for pr in pending_requests[:5]:
                m_title = pr.get('media', {}).get('title') or pr.get('media', {}).get('name') or "Media Request"
                u_name = pr.get('requestedBy', {}).get('plexUsername') or pr.get('requestedBy', {}).get('email') or "User"
                pending_formatted.append({"title": m_title, "user": u_name, "type": pr.get('type', 'media')})

            # 2. Sonarr Missing & Queue
            s_missing_raw = fetch_json(f"{CONFIG['sonarr']['url']}/api/v3/wanted/missing?page=1&pageSize=1&apiKey={CONFIG['sonarr']['key']}")
            s_missing_data = s_missing_raw if isinstance(s_missing_raw, dict) else {}
            s_missing_count = s_missing_data.get('totalRecords') if isinstance(s_missing_data, dict) else None

            s_queue_raw = fetch_json(f"{CONFIG['sonarr']['url']}/api/v3/queue?apiKey={CONFIG['sonarr']['key']}")
            s_queue_data = s_queue_raw if isinstance(s_queue_raw, dict) else {}
            s_queue_records = s_queue_data.get('records', []) if isinstance(s_queue_data, dict) else []
            s_import_issues = sum(1 for r in s_queue_records if isinstance(r, dict) and (r.get('trackedDownloadStatus') == 'warning' or r.get('status') == 'completed'))

            s_cal = fetch_json(
                f"{CONFIG['sonarr']['url']}/api/v3/calendar?start={start_str}&end={end_str}"
                f"&includeSeries=true&includeEpisodeFile=true&apiKey={CONFIG['sonarr']['key']}"
            )
            sonarr_ok = isinstance(s_missing_raw, dict) and isinstance(s_queue_raw, dict) and isinstance(s_cal, list)
            if not isinstance(s_cal, list): s_cal = []

            # 3. Radarr Missing & Queue
            r_missing_raw = fetch_json(f"{CONFIG['radarr']['url']}/api/v3/wanted/missing?page=1&pageSize=1&apiKey={CONFIG['radarr']['key']}")
            r_missing_data = r_missing_raw if isinstance(r_missing_raw, dict) else {}
            r_missing_count = r_missing_data.get('totalRecords') if isinstance(r_missing_data, dict) else None

            r_queue_raw = fetch_json(f"{CONFIG['radarr']['url']}/api/v3/queue?apiKey={CONFIG['radarr']['key']}")
            r_queue_data = r_queue_raw if isinstance(r_queue_raw, dict) else {}
            r_queue_records = r_queue_data.get('records', []) if isinstance(r_queue_data, dict) else []
            r_import_issues = sum(1 for r in r_queue_records if isinstance(r, dict) and (r.get('trackedDownloadStatus') == 'warning' or r.get('status') == 'completed'))

            r_cal = fetch_json(
                f"{CONFIG['radarr']['url']}/api/v3/calendar?start={start_str}&end={end_str}"
                f"&apiKey={CONFIG['radarr']['key']}"
            )
            radarr_ok = isinstance(r_missing_raw, dict) and isinstance(r_queue_raw, dict) and isinstance(r_cal, list)
            if not isinstance(r_cal, list): r_cal = []

            # 4. Bazarr Wanted Subtitles
            b_episodes = fetch_json(f"{CONFIG['bazarr']['url']}/api/episodes/wanted?length=1", {'X-API-KEY': CONFIG['bazarr']['key']})
            b_movies = fetch_json(f"{CONFIG['bazarr']['url']}/api/movies/wanted?length=1", {'X-API-KEY': CONFIG['bazarr']['key']})
            b_langs_raw = fetch_json(f"{CONFIG['bazarr']['url']}/api/system/languages", {'X-API-KEY': CONFIG['bazarr']['key']})
            bazarr_ok = isinstance(b_episodes, dict) and isinstance(b_movies, dict) and isinstance(b_langs_raw, list)
            enabled_langs = [l.get('name') or l.get('code2') for l in b_langs_raw if isinstance(l, dict) and l.get('enabled')] if isinstance(b_langs_raw, list) else []
            b_wanted_ep = b_episodes.get('total') if isinstance(b_episodes, dict) else None
            b_wanted_mv = b_movies.get('total') if isinstance(b_movies, dict) else None

            # 5. Prowlarr Indexer Health
            p_indexers = fetch_json(f"{CONFIG['prowlarr']['url']}/api/v1/indexer", {'X-Api-Key': CONFIG['prowlarr']['key']})
            prowlarr_ok = isinstance(p_indexers, list)
            unhealthy_indexers = [i.get('name', 'Indexer') for i in p_indexers if isinstance(i, dict) and not i.get('enable')] if isinstance(p_indexers, list) else []

            # 6. qBittorrent Stats
            qbit_ok = False
            qbit_active = None
            qbit_stalled = None
            qbit_dl_speed = None
            qbit_up_speed = None
            torrent_list = []
            try:
                login_req = urllib.request.Request(f"{CONFIG['qbittorrent']['url']}/api/v2/auth/login",
                    data=urllib.parse.urlencode({'username': CONFIG['qbittorrent']['user'], 'password': CONFIG['qbittorrent']['pass']}).encode('utf-8'))
                with urllib.request.urlopen(login_req, timeout=3) as l_resp:
                    cookies = l_resp.headers.get('Set-Cookie')
                    qbit_cookie = cookies.split(';')[0] if cookies else None

                if qbit_cookie:
                    q_req = urllib.request.Request(f"{CONFIG['qbittorrent']['url']}/api/v2/sync/maindata", headers={'Cookie': qbit_cookie})
                    with urllib.request.urlopen(q_req, timeout=3) as q_resp:
                        q_data = json.loads(q_resp.read().decode('utf-8'))
                        server_state = q_data.get('server_state', {})
                        qbit_dl_speed = format_bytes(server_state.get('dl_info_speed', 0))
                        qbit_up_speed = format_bytes(server_state.get('up_info_speed', 0))

                        torrents = q_data.get('torrents', {})
                        qbit_active = 0
                        qbit_stalled = 0
                        qbit_ok = isinstance(torrents, dict)
                        for tid, tinfo in torrents.items():
                            st = tinfo.get('state', '')
                            if st in ['downloading', 'stalledDL', 'metaDL', 'allocating']:
                                qbit_active += 1
                            if 'stalled' in st.lower():
                                qbit_stalled += 1
                            if len(torrent_list) < 5:
                                torrent_list.append({
                                    "name": tinfo.get('name', 'Torrent'),
                                    "progress": round(tinfo.get('progress', 0) * 100, 1),
                                    "state": st,
                                    "speed": format_bytes(tinfo.get('dlspeed', 0))
                                })
            except Exception:
                pass

            # 7. SABnzbd Queue
            sab_data = fetch_json(f"{CONFIG['sabnzbd']['url']}/api?mode=queue&output=json&apikey={CONFIG['sabnzbd']['key']}")
            sab_ok = isinstance(sab_data, dict) and isinstance(sab_data.get('queue'), dict)
            if not sab_ok: sab_data = {}
            sab_q = sab_data.get('queue', {}) if isinstance(sab_data, dict) else {}
            sab_speed = sab_q.get('speed') if sab_ok else None
            sab_status = sab_q.get('status') if sab_ok else None
            sab_slots = len(sab_q.get('slots', [])) if sab_ok and isinstance(sab_q.get('slots'), list) else None
            sab_mbleft = sab_q.get('mbleft') if sab_ok else None

            # 8. Jellyfin Sessions & Counts
            j_counts = fetch_json(f"{CONFIG['jellyfin']['url']}/Items/Counts?api_key={CONFIG['jellyfin']['key']}")
            j_sessions = fetch_json(f"{CONFIG['jellyfin']['url']}/Sessions?api_key={CONFIG['jellyfin']['key']}")
            jellyfin_ok = isinstance(j_counts, dict) and isinstance(j_sessions, list)
            j_active_streams = None
            if isinstance(j_sessions, list):
                j_active_streams = len([s for s in j_sessions if isinstance(s, dict) and 'NowPlayingItem' in s])

            # Calculate Derived Summaries cleanly
            total_wanted = (s_missing_count or 0) + (r_missing_count or 0) if (s_missing_count is not None or r_missing_count is not None) else None
            total_subs = (b_wanted_ep or 0) + (b_wanted_mv or 0) if (b_wanted_ep is not None or b_wanted_mv is not None) else None
            total_import = s_import_issues + r_import_issues if sonarr_ok and radarr_ok else None
            total_downloading = qbit_active + sab_slots if qbit_ok and sab_ok else None
            sources = {"seerr": seerr_ok, "sonarr": sonarr_ok, "radarr": radarr_ok, "bazarr": bazarr_ok, "prowlarr": prowlarr_ok, "qbittorrent": qbit_ok, "sabnzbd": sab_ok, "jellyfin": jellyfin_ok}
            complete = all(sources.values())
            now = int(time.time())
            if complete: last_success = now

            calendar_combined = []
            if isinstance(s_cal, list):
                for item in s_cal[:10]:
                    if isinstance(item, dict):
                        series_t = item.get('series', {}).get('title', 'Series')
                        ep_t = item.get('title', '')
                        s_num = item.get('seasonNumber', 1)
                        e_num = item.get('episodeNumber', 1)
                        air_d = item.get('airDateUtc', start_str)
                        if not (start_day <= air_d[:10] <= end_day):
                            continue
                        calendar_combined.append({
                            "title": f"{series_t} - S{s_num:02d}E{e_num:02d}",
                            "sub_title": ep_t,
                            "type": "series",
                            "air_date": air_d[:10],
                            "monitored": item.get('monitored', True),
                            "has_file": item.get('hasFile', False)
                        })

            if isinstance(r_cal, list):
                for item in r_cal[:10]:
                    if isinstance(item, dict):
                        release_dates = [
                            item.get('digitalRelease'),
                            item.get('physicalRelease'),
                            item.get('inCinemas')
                        ]
                        release_d = next((d for d in release_dates if d and start_day <= d[:10] <= end_day), None)
                        if not release_d:
                            continue
                        calendar_combined.append({
                            "title": item.get('title', 'Movie'),
                            "sub_title": f"Movie ({item.get('year', 2026)})",
                            "type": "movie",
                            "air_date": release_d[:10],
                            "monitored": item.get('monitored', True),
                            "has_file": item.get('hasFile', False)
                        })

            calendar_combined.sort(key=lambda x: x['air_date'])

            with data_lock:
                cache_data = {
                    "status": "operational" if complete else "degraded",
                    "generated_at": now,
                    "last_success": last_success,
                    "age_seconds": now - last_success if last_success else None,
                    "sources": {name: {"available": available} for name, available in sources.items()},
                    "summary": {
                        "requests": total_requests,
                        "downloading": total_downloading,
                        "import_issues": total_import,
                        "wanted": total_wanted,
                        "missing_subs": total_subs,
                        "active_streams": j_active_streams,
                        "jellyfin": {
                            "movies": j_counts.get('MovieCount') if jellyfin_ok else None,
                            "series": j_counts.get('SeriesCount') if jellyfin_ok else None,
                            "episodes": j_counts.get('EpisodeCount') if jellyfin_ok else None
                        }
                    },
                    "calendar": calendar_combined[:14],
                    "problems": {
                        "sonarr": {"missing_count": s_missing_count, "queue_warnings": s_import_issues},
                        "radarr": {"missing_count": r_missing_count, "queue_warnings": r_import_issues},
                        "bazarr": {"wanted_episodes": b_wanted_ep, "wanted_movies": b_wanted_mv},
                        "prowlarr": {"available": prowlarr_ok, "total": len(p_indexers) if prowlarr_ok else None, "enabled": sum(bool(i.get('enable')) for i in p_indexers) if prowlarr_ok else None, "unhealthy": unhealthy_indexers if prowlarr_ok else None},
                        "qbittorrent": {"available": qbit_ok, "stalled": qbit_stalled, "errors": None},
                        "sabnzbd": {"available": sab_ok, "warnings": None, "status": sab_status},
                        "seerr": {"available": seerr_ok, "pending_count": len(pending_requests) if seerr_ok else None, "pending_requests": pending_formatted if seerr_ok else []}
                    },
                    "bazarr": {
                        "wanted_episodes": b_wanted_ep,
                        "wanted_movies": b_wanted_mv,
                        "version": None,
                        "languages": enabled_langs
                    },
                    "download_engine": {
                        "qbittorrent": {"available": qbit_ok, "dl_speed": qbit_dl_speed, "up_speed": qbit_up_speed, "active": qbit_active, "stalled": qbit_stalled, "torrents": torrent_list if qbit_ok else []},
                        "sabnzbd": {"available": sab_ok, "speed": sab_speed, "remaining_mb": f"{sab_mbleft} MB" if sab_mbleft is not None else None, "queue_count": sab_slots, "status": sab_status}
                    }
                }

        except Exception:
            pass

        time.sleep(int(os.environ.get("MEDIA_POLL_SECONDS", "15")))

class MediaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0].rstrip('/')
        with data_lock:
            if path in ['/api/media/summary', '/summary']:
                payload = json.dumps(cache_data['summary']).encode('utf-8')
            elif path in ['/api/media/calendar', '/calendar']:
                payload = json.dumps(cache_data['calendar']).encode('utf-8')
            elif path in ['/api/media/problems', '/problems']:
                payload = json.dumps(cache_data['problems']).encode('utf-8')
            elif path in ['/api/media/bazarr', '/bazarr']:
                payload = json.dumps(cache_data['bazarr']).encode('utf-8')
            elif path in ['/api/media/download-engine', '/download-engine']:
                payload = json.dumps(cache_data['download_engine']).encode('utf-8')
            else:
                payload = json.dumps(cache_data).encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return

def main():
    t = Thread(target=poll_media, daemon=True)
    t.start()
    server = HTTPServer((os.environ.get("MEDIA_BIND", "127.0.0.1"), int(os.environ.get("MEDIA_PORT", "9098"))), MediaHandler)
    print("Media collector started")
    server.serve_forever()

if __name__ == '__main__':
    main()
