/* =========================================================
   app.js  –  Dashboard / index page logic
   No frameworks. Vanilla JS only.
   ========================================================= */

// --- Navigation -----------------------------------------------------------

const navLinks = document.querySelectorAll('nav a[data-page]');
const pages    = document.querySelectorAll('.page');

function showPage(id) {
  pages.forEach(p => p.classList.remove('active'));
  navLinks.forEach(l => l.classList.remove('active'));
  const page = document.getElementById('page-' + id);
  if (page) page.classList.add('active');
  const link = document.querySelector(`nav a[data-page="${id}"]`);
  if (link) link.classList.add('active');
}

navLinks.forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const id = link.dataset.page;
    showPage(id);
    if (id === 'all-days')  loadAllDays();
    if (id === 'revision')  loadRevisionPage();
    if (id === 'dashboard') loadDashboard();
  });
});

// Handle hash in URL for nav links from day.html
window.addEventListener('load', () => {
  const hash = location.hash.replace('#', '');
  if (hash === 'all-days') { showPage('all-days'); loadAllDays(); }
  else if (hash === 'revision') { showPage('revision'); loadRevisionPage(); }
  else { loadDashboard(); }
});

// --- API helpers ----------------------------------------------------------

async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  return res.json();
}

// --- Toast ----------------------------------------------------------------

let toastTimer;
function toast(msg, type = 'ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show ' + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, 3500);
}

// --- Utility --------------------------------------------------------------

function fmtTime(secs) {
  if (!secs) return '—';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (h > 0) return `${h}h ${String(m).padStart(2,'0')}m`;
  return `${m}m`;
}

function fmtTimer(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return [h, m, s].map(v => String(v).padStart(2,'0')).join(':');
}

function badgeClass(status) {
  if (status === 'completed')  return 'badge-completed';
  if (status === 'in_progress') return 'badge-progress';
  return 'badge-notstarted';
}

function badgeText(status) {
  if (status === 'completed')   return 'Completed';
  if (status === 'in_progress') return 'In Progress';
  return 'Not Started';
}

function dayLabel(d) { return 'DAY ' + String(d).padStart(2, '0'); }

// --- Dashboard ------------------------------------------------------------

let dashboardLoaded = false;
let activeSessionInterval = null;
let cdTimerInterval       = null;

async function loadDashboard() {
  dashboardLoaded = true;
  const stats = await api('/api/stats');

  // Stat cards
  document.getElementById('s-completed').textContent = `${stats.completed} / 100`;
  document.getElementById('s-pct').textContent       = `${stats.pct}%`;
  document.getElementById('s-time').textContent      = stats.total_time;
  document.getElementById('s-topics').textContent    = stats.topic_count;
  document.getElementById('s-revision').textContent  = stats.needs_revision;

  // Progress bar
  document.getElementById('prog-text').textContent = `${stats.completed} / 100`;
  document.getElementById('prog-bar').style.width  = stats.pct + '%';
  document.getElementById('prog-blocks').textContent = buildBlocks(stats.completed);

  // Recent days
  const recentEl = document.getElementById('recent-list');
  if (stats.recent.length === 0) {
    recentEl.innerHTML = '<span class="muted">No completed days yet.</span>';
  } else {
    recentEl.innerHTML = stats.recent.map(r => `
      <div class="recent-item" style="cursor:pointer" onclick="openDay(${r.day_number})">
        <span class="rec-day">${dayLabel(r.day_number)}</span>
        <span class="rec-title">${r.title || '<em class="muted">No title</em>'}</span>
        <span class="rec-time">${fmtTime(r.day_secs)}</span>
      </div>`).join('');
  }

  // Revision queue (dashboard)
  const qEl = document.getElementById('revision-queue-dash');
  if (!stats.revision_queue.length) {
    qEl.innerHTML = '<span class="muted">Nothing in the revision queue.</span>';
  } else {
    qEl.innerHTML = stats.revision_queue.map(r => `
      <div class="revision-item">
        <span class="rev-day">${dayLabel(r.day_number)}</span>
        <span class="rev-title">${r.title || '—'}</span>
        <div class="rev-actions">
          <button class="btn btn-secondary btn-sm" onclick="openDay(${r.day_number})">Open Day</button>
          <button class="btn btn-success btn-sm" onclick="markRevised(${r.day_number})">Mark Revised</button>
        </div>
      </div>`).join('');
  }

  // Current day
  await loadCurrentDay();

  // Active session banner (any day)
  await checkGlobalActiveSession();
}

function buildBlocks(n) {
  const filled = Math.floor(n / 5);
  const partial = n % 5;
  let s = '';
  for (let i = 0; i < 20; i++) {
    if (i < filled) s += '█';
    else if (i === filled && partial > 0) s += '▒';
    else s += '░';
    if ((i + 1) % 10 === 0) s += ' ';
  }
  return s + ' ' + n + '%';
}

async function loadCurrentDay() {
  const all  = await api('/api/days');
  const next = all.find(d => d.status !== 'completed') || all[all.length - 1];
  if (!next) return;

  document.getElementById('current-loading').classList.add('hidden');
  document.getElementById('current-content').classList.remove('hidden');

  document.getElementById('cd-num').textContent   = dayLabel(next.day_number);
  document.getElementById('cd-title').textContent = next.title || '(No title yet)';

  const badge = document.getElementById('cd-badge');
  badge.textContent = badgeText(next.status);
  badge.className   = 'badge ' + badgeClass(next.status);

  document.getElementById('cd-open-btn').onclick = () => openDay(next.day_number);

  // Load the day detail to check for active session
  const day = await api(`/api/days/${next.day_number}`);

  const timerBtn = document.getElementById('cd-timer-btn');
  const timerDisplay = document.getElementById('cd-timer-display');

  if (day.active_session) {
    timerBtn.textContent = 'Stop Session';
    timerBtn.className   = 'btn btn-danger btn-sm';
    timerDisplay.classList.remove('hidden');

    clearInterval(cdTimerInterval);
    cdTimerInterval = setInterval(() => {
      const started = new Date(day.active_session.started_at.replace(' ', 'T'));
      const elapsed = Math.floor((Date.now() - started.getTime()) / 1000);
      timerDisplay.textContent = fmtTimer(elapsed);
    }, 1000);

    timerBtn.onclick = async () => {
      const res = await api(`/api/sessions/${day.active_session.id}/stop`, 'POST');
      if (res.error) return toast(res.error, 'err');
      clearInterval(cdTimerInterval);
      timerDisplay.classList.add('hidden');
      toast('Session stopped. ' + fmtTime(res.duration_seconds));
      loadDashboard();
    };
  } else {
    timerBtn.textContent = 'Start Study Session';
    timerBtn.className   = 'btn btn-success btn-sm';
    timerDisplay.classList.add('hidden');
    timerBtn.onclick = async () => {
      const res = await api(`/api/days/${next.day_number}/sessions/start`, 'POST');
      if (res.error) return toast(res.error, 'err');
      toast('Session started!');
      loadDashboard();
    };
  }
}

async function checkGlobalActiveSession() {
  const session = await api('/api/active-session');
  const banner  = document.getElementById('active-session-banner');
  if (!session || !session.id) {
    banner.classList.add('hidden');
    clearInterval(activeSessionInterval);
    return;
  }
  banner.classList.remove('hidden');
  document.getElementById('asb-day').textContent =
    `Day ${session.day_number} — started ${session.started_at}`;

  const stopBtn = document.getElementById('asb-stop-btn');
  stopBtn.onclick = async () => {
    const res = await api(`/api/sessions/${session.id}/stop`, 'POST');
    if (res.error) return toast(res.error, 'err');
    toast('Session stopped. ' + fmtTime(res.duration_seconds));
    loadDashboard();
  };

  clearInterval(activeSessionInterval);
  activeSessionInterval = setInterval(() => {
    const started = new Date(session.started_at.replace(' ', 'T'));
    const elapsed = Math.floor((Date.now() - started.getTime()) / 1000);
    document.getElementById('asb-timer').textContent = fmtTimer(elapsed);
  }, 1000);
}

// --- Open a day ----------------------------------------------------------

function openDay(n) {
  location.href = `/day.html?day=${n}`;
}

// --- All Days page -------------------------------------------------------

let allDaysCache = [];

async function loadAllDays() {
  allDaysCache = await api('/api/days');
  renderDaysGrid(allDaysCache);
}

let currentFilter = 'all';

function filterDays(f) {
  currentFilter = f;
  renderDaysGrid(allDaysCache);
}

function renderDaysGrid(days) {
  const grid = document.getElementById('days-grid');
  const filtered = currentFilter === 'all'
    ? days
    : days.filter(d => d.status === currentFilter);

  if (!filtered.length) {
    grid.innerHTML = '<span class="muted">No days match this filter.</span>';
    return;
  }

  grid.innerHTML = filtered.map(d => {
    const t    = fmtTime(d.total_secs);
    const rev  = d.needs_revision && !d.revised_at
      ? ' <span class="badge badge-revision" style="font-size:0.65rem">Rev</span>' : '';
    return `
    <div class="day-row" onclick="openDay(${d.day_number})">
      <span class="day-num">${String(d.day_number).padStart(2,'0')}</span>
      <span class="day-title">${d.title || '<span class="muted">No title</span>'}</span>
      ${rev}
      <span class="badge ${badgeClass(d.status)}" style="font-size:0.65rem;flex:none">
        ${badgeText(d.status)}
      </span>
      <span class="day-time">${d.total_secs > 0 ? t : ''}</span>
    </div>`;
  }).join('');
}

// --- Revision page -------------------------------------------------------

async function loadRevisionPage() {
  const stats = await api('/api/stats');
  const el    = document.getElementById('revision-list');
  if (!stats.revision_queue.length) {
    el.innerHTML = '<span class="muted">Nothing to revise.</span>';
    return;
  }
  el.innerHTML = stats.revision_queue.map(r => `
    <div class="revision-item">
      <span class="rev-day">${dayLabel(r.day_number)}</span>
      <span class="rev-title">
        <strong>${r.title || '—'}</strong>
        ${r.revision_notes ? `<br><span class="muted">${r.revision_notes}</span>` : ''}
      </span>
      <div class="rev-actions">
        <button class="btn btn-secondary btn-sm" onclick="openDay(${r.day_number})">Open Day</button>
        <button class="btn btn-success btn-sm"   onclick="markRevised(${r.day_number}, true)">Mark Revised</button>
      </div>
    </div>`).join('');
}

async function markRevised(dayNum, reload = false) {
  const res = await api(`/api/days/${dayNum}/revised`, 'POST');
  if (res.error) return toast(res.error, 'err');
  toast('Marked as revised.');
  if (reload) loadRevisionPage();
  else loadDashboard();
}

// --- Search ---------------------------------------------------------------

document.getElementById('search-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});

async function doSearch() {
  const q  = document.getElementById('search-input').value.trim();
  const el = document.getElementById('search-results');
  if (!q) { el.innerHTML = ''; return; }

  const results = await api(`/api/search?q=${encodeURIComponent(q)}`);
  if (!results.length) {
    el.innerHTML = '<span class="muted">No results found.</span>';
    return;
  }
  el.innerHTML = results.map(r => `
    <div class="search-result" onclick="openDay(${r.day_number})">
      <span class="text-accent" style="font-weight:600;min-width:60px">${dayLabel(r.day_number)}</span>
      <span style="flex:1">${r.title || '<em class="muted">No title</em>'}</span>
      <span class="badge ${badgeClass(r.status)}">${badgeText(r.status)}</span>
    </div>`).join('');
}

// --- Backup / Export -----------------------------------------------------

async function doBackup() {
  const res = await api('/api/backup', 'POST');
  if (res.error) return toast(res.error, 'err');
  toast('Backup saved: ' + res.file);
}

async function doExport() {
  const res = await api('/api/export', 'POST');
  if (res.error) return toast(res.error, 'err');
  toast('Exported: ' + res.file);
}
