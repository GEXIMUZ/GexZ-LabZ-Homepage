(function () {
  'use strict';

  const state = { view: 'home', range: '1h', started: false, mediaRenderBusy: false, timers: [] };
  const $ = (id) => document.getElementById(id);
  const val = (value, suffix = '') => value === null || value === undefined || Number.isNaN(value) ? 'N/A' : `${value}${suffix}`;
  const safe = (value) => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  async function api(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${response.status} ${url}`);
    return response.json();
  }
  function setText(id, text) { const node = $(id); if (node) node.textContent = text; }

  function injectHeader() {
    const container = document.querySelector('.container');
    if (!container || $('header-command-deck')) return;
    document.querySelectorAll('div.container > header, header.container').forEach(node => node.style.display = 'none');
    const stockSearch = document.querySelector('#search-container');
    if (stockSearch) {
      const bar = stockSearch.closest('.flex.items-center.justify-between') || stockSearch.parentElement?.parentElement;
      if (bar) bar.style.display = 'none';
    }
    const deck = document.createElement('div');
    deck.id = 'header-command-deck';
    deck.innerHTML = `
      <div class="hdr-row-top">
        <div class="hdr-brand">
          <img class="hdr-brand-logo" src="/images/gexz-3d.png" alt="GexZ logo">
          <div><div class="hdr-brand-title">GexZ LabZ</div><div class="hdr-brand-sub">self-hosted infrastructure</div></div>
        </div>
        <div class="hdr-search-box">
          <span class="hdr-search-icon">⌕</span>
          <input id="hdr-search-input" class="hdr-search-input" autocomplete="off" placeholder="Search services, nodes, tools…">
          <span class="hdr-search-kbd">/</span>
          <div id="hdr-search-dropdown" role="listbox" hidden></div>
        </div>
        <div class="hdr-time-weather"><span id="hdr-date-time">--</span><span class="hdr-sep">·</span><span id="hdr-weather" title="Open-Meteo · your location">☁ N/A</span></div>
      </div>
      <div class="hdr-row-bottom"><div class="hdr-telemetry-strip">
        <div class="hdr-signal"><span class="hdr-signal-lbl">PVE CPU</span><span id="hdr-val-cpu" class="hdr-signal-val">N/A</span></div><span class="hdr-sep">·</span>
        <div class="hdr-signal"><span class="hdr-signal-lbl">PVE RAM</span><span id="hdr-val-ram" class="hdr-signal-val">N/A</span></div><span class="hdr-sep">·</span>
        <div class="hdr-signal"><span class="hdr-signal-lbl">WAN</span><span id="hdr-val-ping" class="hdr-signal-val">N/A</span></div><span class="hdr-sep">·</span>
        <div class="hdr-signal"><span class="hdr-signal-lbl">DOCKER</span><span id="hdr-val-containers" class="hdr-signal-val">N/A</span></div><span class="hdr-sep">·</span>
        <div class="hdr-signal"><span class="hdr-signal-lbl">DNS BLOCKED</span><span id="hdr-val-dns" class="hdr-signal-val">N/A</span></div><span class="hdr-sep">·</span>
        <div class="hdr-signal hdr-health"><span id="hdr-status-dot">●</span><span id="hdr-status-text" class="hdr-signal-val">Unknown</span></div>
      </div></div>`;
    container.insertBefore(deck, container.firstChild);
    updateClock();
  }

  function updateClock() {
    const node = $('hdr-date-time'); if (!node) return;
    node.textContent = new Intl.DateTimeFormat('en-GB', { weekday:'short', day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }).format(new Date()).replace(',', ' ·');
  }

  async function fetchWeather() {
    try {
      const data = await api('/api/grafana/weather');
      if (!data.available || typeof data.temp !== 'number') throw new Error('weather unavailable');
      setText('hdr-weather', `${data.icon || '☁'} ${data.temp}°C`);
      $('hdr-weather').title = `${data.location} · ${data.condition} · feels like ${val(data.feels_like, '°C')} · humidity ${val(data.humidity, '%')}`;
    } catch (_) { setText('hdr-weather', '☁ N/A'); }
  }

  function setupSearch() {
    const input = $('hdr-search-input'), dropdown = $('hdr-search-dropdown');
    if (!input || !dropdown || input.dataset.bound) return;
    input.dataset.bound = '1';
    let selected = -1, results = [];
    const catalog = () => {
      const found = new Map();
      document.querySelectorAll('a[href]').forEach(anchor => {
        const href = anchor.href;
        const name = (anchor.querySelector('.service-title, h3, h2')?.textContent || anchor.textContent || '').replace(/\s+/g, ' ').trim();
        if (!name || /\.(png|svg|jpe?g|webp)$/i.test(name) || name.toLowerCase() === 'logo' || !/^https?:/.test(href) || href === location.href) return;
        const key = href.replace(/\/$/, '').toLowerCase();
        if (!found.has(key)) found.set(key, { name, url: href, hint: new URL(href).hostname });
      });
      return [...found.values()];
    };
    function draw() {
      const q = input.value.trim().toLowerCase();
      if (!q) { dropdown.hidden = true; dropdown.innerHTML = ''; selected = -1; return; }
      results = catalog().filter(item => `${item.name} ${item.url}`.toLowerCase().includes(q)).slice(0, 8);
      dropdown.innerHTML = results.length ? results.map((item, index) => `<button type="button" class="hdr-search-item${index === selected ? ' selected' : ''}" data-index="${index}"><span><strong>${safe(item.name)}</strong><small>${safe(item.hint)}</small></span><em>↗</em></button>`).join('') : '<div class="hdr-search-empty">No matching service</div>';
      dropdown.hidden = false;
    }
    function open(index) { const item = results[index]; if (item) { window.open(item.url, '_blank', 'noopener'); input.value = ''; draw(); } }
    input.addEventListener('input', () => { selected = -1; draw(); });
    input.addEventListener('focus', draw);
    input.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' && results.length) { event.preventDefault(); selected = (selected + 1) % results.length; draw(); }
      else if (event.key === 'ArrowUp' && results.length) { event.preventDefault(); selected = (selected - 1 + results.length) % results.length; draw(); }
      else if (event.key === 'Enter' && results.length) { event.preventDefault(); open(selected >= 0 ? selected : 0); }
      else if (event.key === 'Escape') { input.value = ''; input.blur(); draw(); }
    });
    dropdown.addEventListener('click', event => { const button = event.target.closest('[data-index]'); if (button) open(Number(button.dataset.index)); });
    document.addEventListener('click', event => { if (!event.target.closest('.hdr-search-box')) dropdown.hidden = true; });
    document.addEventListener('keydown', event => {
      if ((event.key === '/' && !/INPUT|TEXTAREA/.test(document.activeElement?.tagName)) || (event.ctrlKey && event.key.toLowerCase() === 'k')) { event.preventDefault(); input.focus(); input.select(); }
    });
  }

  function setupTabs() {
    const tabs = $('myTab'); if (!tabs) return;
    tabs.innerHTML = ['Home','Media','Analytics'].map(name => `<li role="presentation"><button id="tab-btn-${name.toLowerCase()}" type="button" role="tab" data-view="${name.toLowerCase()}">${name}</button></li>`).join('');
    tabs.querySelectorAll('button').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
    setView(state.view);
  }

  function setView(view) {
    if (!['home','media','analytics'].includes(view)) return;
    state.view = view;
    document.querySelectorAll('#myTab button').forEach(button => {
      const active = button.dataset.view === view;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    const media = $('gexz-media-view'), analytics = $('noc-telemetry-container');
    const home = document.querySelectorAll('.container > section, .container > div:not(#header-command-deck):not(#information-widgets):not(#gexz-media-view):not(#noc-telemetry-container)');
    home.forEach(node => node.style.display = view === 'home' ? '' : 'none');
    if (media) media.style.display = view === 'media' ? 'block' : 'none';
    if (analytics) analytics.style.display = view === 'analytics' ? 'block' : 'none';
    if (view === 'media') renderMedia();
    if (view === 'analytics') renderAnalytics();
  }
  window.gexzSetView = setView;

  async function pollHeader() {
    try {
      const [overview, telemetry, dns] = await Promise.all([api('/api/grafana/overview'), api('/api/telemetry'), api('/api/grafana/dns')]);
      setText('hdr-val-cpu', val(overview.cpu_pct, '%')); setText('hdr-val-ram', val(overview.ram_pct, '%'));
      setText('hdr-val-containers', overview.docker && overview.docker.running !== null ? `${overview.docker.running}/${overview.docker.total}` : 'N/A');
      setText('hdr-val-ping', val(telemetry.net?.ping_ms, 'ms')); setText('hdr-val-dns', val(dns.block_rate, '%'));
      const good = overview.status === 'operational'; setText('hdr-status-text', good ? 'Operational' : 'Degraded');
      $('hdr-status-dot')?.classList.toggle('ok', good); $('hdr-status-text')?.classList.toggle('ok', good);
    } catch (_) { setText('hdr-status-text', 'Degraded'); $('hdr-status-dot')?.classList.remove('ok'); $('hdr-status-text')?.classList.remove('ok'); }
  }

  function ensureView(id) {
    let node = $(id); if (!node) { node = document.createElement('div'); node.id = id; (document.querySelector('.container') || document.body).appendChild(node); }
    node.style.display = 'block'; return node;
  }

  function metricCards(items) { return `<div class="lux-metrics">${items.map(([label,value,id]) => `<div class="lux-metric"><span>${label}</span><strong${id ? ` id="${id}"` : ''}>${value}</strong></div>`).join('')}</div>`; }

  async function renderMedia() {
    if (state.mediaRenderBusy) return;
    state.mediaRenderBusy = true;
    const root = ensureView('gexz-media-view');
    root.innerHTML = `<div class="lux-view-head"><div><small>MEDIA AUTOMATION</small><h2>Pipeline control room</h2></div><span id="media-source-state" class="lux-state">Checking sources…</span></div>
      ${metricCards([['Requests','N/A','m-req'],['Downloading','N/A','m-dl'],['Import issues','N/A','m-imp'],['Wanted','N/A','m-wnt'],['Missing subs','N/A','m-sub'],['Active streams','N/A','m-stm']])}
      <div class="lux-pipeline" id="media-pipeline"><span>Seerr</span><i>→</i><span>Sonarr / Radarr</span><i>→</i><span>Prowlarr</span><i>→</i><span>qBit / SAB</span><i>→</i><span>Import</span><i>→</i><span>Bazarr</span><i>→</i><span>Jellyfin</span></div>
      <section class="lux-panel lux-calendar"><header><h3>Release calendar</h3><small>Next 14 days · Sonarr & Radarr</small></header><div id="media-calendar" class="calendar-grid"><div class="lux-empty">Loading…</div></div></section>
      <div class="lux-grid two-one"><section class="lux-panel"><header><h3>Needs attention</h3></header><div id="media-problems" class="lux-list"><div class="lux-empty">Loading…</div></div></section><section class="lux-panel"><header><h3>Bazarr subtitles</h3></header><div id="media-bazarr" class="lux-list"><div class="lux-empty">Loading…</div></div></section></div>
      <div class="lux-grid thirds"><section class="lux-panel"><header><h3>qBittorrent</h3><small id="qbit-speed">N/A</small></header><div id="qbit-list" class="lux-list"></div></section><section class="lux-panel"><header><h3>SABnzbd</h3><small id="sab-speed">N/A</small></header><div id="sab-list" class="lux-list"></div></section><section class="lux-panel"><header><h3>Requests & indexers</h3></header><div id="request-indexer" class="lux-list"></div></section></div>
      <section class="lux-panel jelly-row"><header><h3>Jellyfin library</h3></header><div id="jellyfin-library" class="jelly-stats"></div></section>`;
    try {
      const [summary, calendar, problems, bazarr, downloads] = await Promise.all([api('/api/media/summary'),api('/api/media/calendar'),api('/api/media/problems'),api('/api/media/bazarr'),api('/api/media/download-engine')]);
      [['m-req',summary.requests],['m-dl',summary.downloading],['m-imp',summary.import_issues],['m-wnt',summary.wanted],['m-sub',summary.missing_subs],['m-stm',summary.active_streams]].forEach(([id,value]) => setText(id,val(value)));
      const allAvailable = [summary.requests,summary.downloading,summary.import_issues,summary.wanted,summary.missing_subs,summary.active_streams].every(v => v !== null && v !== undefined);
      setText('media-source-state', allAvailable ? 'Live collector data' : 'Degraded · missing source data'); $('media-source-state')?.classList.toggle('ok', allAvailable);
      $('media-calendar').innerHTML = Array.isArray(calendar) && calendar.length ? calendar.slice(0,7).map(item => `<article><time>${safe(item.air_date)}</time><strong>${safe(item.title)}</strong><small>${safe(item.sub_title || item.type)}</small></article>`).join('') : '<div class="lux-empty">No scheduled releases, or calendar source unavailable.</div>';
      const issues = [];
      if (problems.sonarr?.missing_count > 0) issues.push(['Sonarr missing episodes',problems.sonarr.missing_count]);
      if (problems.radarr?.missing_count > 0) issues.push(['Radarr missing movies',problems.radarr.missing_count]);
      const subtitleBacklog = problems.bazarr?.wanted_episodes != null && problems.bazarr?.wanted_movies != null ? problems.bazarr.wanted_episodes + problems.bazarr.wanted_movies : null;
      if (subtitleBacklog > 0) issues.push(['Subtitle backlog',subtitleBacklog]);
      if (problems.seerr?.pending_count > 0) issues.push(['Pending requests',problems.seerr.pending_count]);
      $('media-problems').innerHTML = issues.length ? issues.map(([name,count]) => `<div><span>${safe(name)}</span><strong class="warn">${count}</strong></div>`).join('') : allAvailable ? '<div class="lux-empty ok-text">No active warnings.</div>' : '<div class="lux-empty">Unable to confirm: one or more core sources are missing.</div>';
      $('media-bazarr').innerHTML = `<div><span>Episode subtitles wanted</span><strong>${val(bazarr.wanted_episodes)}</strong></div><div><span>Movie subtitles wanted</span><strong>${val(bazarr.wanted_movies)}</strong></div><div><span>Languages</span><strong>${bazarr.languages?.length ? safe(bazarr.languages.join(', ')) : 'N/A'}</strong></div>`;
      const q = downloads.qbittorrent || {}; setText('qbit-speed', q.available ? `DL ${val(q.dl_speed)} · UL ${val(q.up_speed)}` : 'Source unavailable');
      $('qbit-list').innerHTML = q.available ? (q.torrents?.length ? q.torrents.slice(0,4).map(t => `<div class="queue-item"><span>${safe(t.name)}</span><strong>${val(t.progress,'%')}</strong><div><i style="width:${Math.min(100,Math.max(0,t.progress || 0))}%"></i></div></div>`).join('') : '<div class="lux-empty">Queue idle.</div>') : '<div class="lux-empty">Source unavailable.</div>';
      const sab = downloads.sabnzbd || {}; setText('sab-speed', sab.available ? `DL ${val(sab.speed)}` : 'Source unavailable'); $('sab-list').innerHTML = `<div><span>Status</span><strong>${sab.available ? safe(sab.status) : 'N/A'}</strong></div><div><span>Queue</span><strong>${val(sab.queue_count)}</strong></div><div><span>Remaining</span><strong>${val(sab.remaining_mb)}</strong></div>`;
      const prow = problems.prowlarr || {}; $('request-indexer').innerHTML = `<div><span>Pending requests</span><strong>${val(problems.seerr?.pending_count)}</strong></div><div><span>Prowlarr indexers</span><strong>${prow.available ? `${prow.enabled}/${prow.total} enabled` : 'N/A'}</strong></div><div><span>Unhealthy</span><strong class="${prow.unhealthy?.length ? 'warn' : ''}">${prow.available ? prow.unhealthy.length : 'N/A'}</strong></div>`;
      const jelly = summary.jellyfin || {}; $('jellyfin-library').innerHTML = [['Movies',jelly.movies],['Series',jelly.series],['Episodes',jelly.episodes],['Active streams',summary.active_streams]].map(([name,value]) => `<div><span>${name}</span><strong>${val(value)}</strong></div>`).join('');
    } catch (error) { setText('media-source-state','Degraded · collector unavailable'); root.querySelectorAll('.lux-empty').forEach(n => n.textContent = 'Source unavailable.'); }
    finally { state.mediaRenderBusy = false; }
  }

  function chart(timestamps, first, second, colors=['#c7ffdd','#a7aaad'], percent=false) {
    if (!timestamps?.length || !first?.length) return '<div class="chart-empty">No verified samples.</div>';
    const width=600,height=190,pad=24, usable=height-pad*2;
    const values=[...first,...(second||[])].filter(Number.isFinite); const max=percent ? 100 : Math.max(1,...values)*1.1;
    const points = series => series.map((v,i) => `${pad+i*(width-pad*2)/Math.max(1,series.length-1)},${height-pad-(Number(v)/max)*usable}`).join(' ');
    return `<svg viewBox="0 0 ${width} ${height}" aria-label="telemetry chart"><line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}"/><polyline points="${points(first)}" style="stroke:${colors[0]}"/>${second?.length ? `<polyline points="${points(second)}" style="stroke:${colors[1]}"/>` : ''}</svg>`;
  }

  async function renderAnalytics() {
    const root = ensureView('noc-telemetry-container');
    root.innerHTML = `<div class="lux-view-head"><div><small>OBSERVABILITY</small><h2>Infrastructure analytics</h2></div><div class="view-actions"><div class="range-switch">${['1h','6h','24h'].map(r=>`<button data-range="${r}" class="${r===state.range?'active':''}">${r}</button>`).join('')}</div><a href="https://service.example.com" target="_blank">Open Grafana ↗</a></div></div>
      ${metricCards([['CPU','N/A','noc-cpu'],['RAM','N/A','noc-ram'],['1m load','N/A','noc-load'],['VM / LXC','N/A','noc-pve'],['Docker','N/A','noc-docker'],['Storage','N/A','noc-storage'],['Health','Unknown','noc-health']])}
      <div class="lux-grid charts"><section class="lux-panel"><header><h3>CPU & RAM utilization</h3><small id="sys-current">N/A</small></header><div id="system-chart" class="chart-box"></div></section><section class="lux-panel"><header><h3>Network throughput</h3><small id="net-current">N/A</small></header><div id="network-chart" class="chart-box"></div></section></div>
      <div class="lux-grid thirds"><section class="lux-panel"><header><h3>Proxmox guests</h3><small>Top consumers</small></header><div id="pve-list" class="lux-list"></div></section><section class="lux-panel"><header><h3>Docker stack</h3><small>Restricted socket proxy</small></header><div id="docker-list" class="container-grid"></div></section><section class="lux-panel"><header><h3>Storage & DNS</h3></header><div id="system-summary" class="lux-list"></div></section></div><section id="disk-section" class="lux-panel disk-section"><header><h3>Physical disk health</h3><small id="disk-summary">Checking source…</small></header><div id="disk-grid" class="disk-grid"></div></section>`;
    root.querySelectorAll('[data-range]').forEach(button => button.addEventListener('click', () => { state.range=button.dataset.range; renderAnalytics(); }));
    try {
      const [overview, system, network, pve, docker, dns, disks] = await Promise.all([api('/api/grafana/overview'),api(`/api/grafana/system?range=${state.range}`),api(`/api/grafana/network?range=${state.range}`),api('/api/grafana/proxmox'),api('/api/grafana/docker'),api('/api/grafana/dns'),api('/api/grafana/storage_disks')]);
      setText('noc-cpu',val(overview.cpu_pct,'%')); setText('noc-ram',val(overview.ram_pct,'%')); setText('noc-load',val(overview.load_1m));
      setText('noc-pve',overview.pve_vm?.running != null && overview.pve_lxc?.running != null ? `${overview.pve_vm.running}/${overview.pve_vm.total} · ${overview.pve_lxc.running}/${overview.pve_lxc.total}` : 'N/A');
      setText('noc-docker',overview.docker?.running != null ? `${overview.docker.running}/${overview.docker.total}` : 'N/A'); setText('noc-storage',val(overview.storage_pct,'%')); setText('noc-health',overview.status === 'operational' ? 'Operational' : 'Degraded'); $('noc-health')?.classList.toggle('ok-text',overview.status==='operational');
      $('system-chart').innerHTML=chart(system.timestamps,system.cpu,system.ram,undefined,true); setText('sys-current',`CPU ${val(system.cpu?.at(-1),'%')} · RAM ${val(system.ram?.at(-1),'%')}`);
      $('network-chart').innerHTML=chart(network.timestamps,network.rx_kbs,network.tx_kbs); setText('net-current',`RX ${val(network.rx_kbs?.at(-1),' KB/s')} · TX ${val(network.tx_kbs?.at(-1),' KB/s')}`);
      $('pve-list').innerHTML=pve.available ? pve.top_guests.map(g=>`<div><span><b>${safe(g.name)}</b><small>${safe(g.type)} · ${g.running?'running':'stopped'}</small></span><strong>CPU ${val(g.cpu_pct,'%')} · RAM ${val(g.mem_pct,'%')}</strong></div>`).join('') : '<div class="lux-empty">Source unavailable.</div>';
      $('docker-list').innerHTML=docker.available ? docker.containers.slice(0,10).map(c=>`<div><span>${safe(c.name)}</span><strong class="${c.state==='running'&&c.health!=='unhealthy'?'ok-text':'warn'}">${safe(c.state)}${c.health!=='none'?` · ${safe(c.health)}`:''}</strong></div>`).join('') : '<div class="lux-empty">Source unavailable.</div>';
      const npmApi = overview.sources?.npmplus_api;
      $('system-summary').innerHTML=`<div><span>AdGuard queries</span><strong>${val(dns.queries?.toLocaleString())}</strong></div><div><span>Blocked</span><strong>${val(dns.block_rate,'%')} · ${val(dns.blocked?.toLocaleString())}</strong></div><div><span>DNS latency</span><strong>${val(dns.avg_latency_ms,' ms')}</strong></div><div><span>Docker health</span><strong>${docker.available ? `${docker.healthy} healthy · ${docker.unhealthy} unhealthy` : 'N/A'}</strong></div><div><span>NPMPlus API</span><strong class="${npmApi?.available?'ok-text':'warn'}">${npmApi?.available?'Authenticated':npmApi?.reachable?'Reachable · auth N/A':'Unavailable'}</strong></div>`;
      if (!disks.available) { setText('disk-summary','Source unavailable'); $('disk-grid').innerHTML='<div class="lux-empty">No verified SMART data.</div>'; }
      else { setText('disk-summary',`${disks.summary.healthy_count}/${disks.summary.total_drives} healthy · ${disks.summary.total_free_tb} TB free`); $('disk-grid').innerHTML=disks.disks.map(d=>`<article><div><span>${safe((d.type||'disk').toUpperCase())}</span><strong class="${d.healthy===1?'ok-text':'warn'}">${d.healthy===1?'GOOD':'WARNING'}</strong></div><h4>${safe(d.name)}</h4><small>${safe(d.model || 'N/A')}</small><dl><dt>Usage</dt><dd>${val(d.usage_pct,'%')}</dd><dt>Temp</dt><dd>${val(d.temp_c,'°C')}</dd><dt>Hours</dt><dd>${val(d.power_hours?.toLocaleString(),'h')}</dd></dl></article>`).join(''); }
    } catch (_) { setText('noc-health','Degraded'); root.querySelectorAll('.chart-box').forEach(node=>node.innerHTML='<div class="chart-empty">Source unavailable.</div>'); }
  }

  function init() {
    if (state.started) return; state.started = true;
    injectHeader(); setupSearch(); setupTabs(); pollHeader(); fetchWeather();
    state.timers.push(
      setInterval(updateClock,1000),
      setInterval(pollHeader,15000),
      setInterval(fetchWeather,600000),
      setInterval(() => { if (state.view === 'media') renderMedia(); },15000)
    );
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true}); else init();
})();
