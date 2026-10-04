/* =========================================================
   day.js  –  Day Detail page logic
   No frameworks. Vanilla JS only.
   ========================================================= */

// --- State ---------------------------------------------------------------

let dayNum     = null;   // current day number from URL
let dayData    = null;   // full day object from API
let timerInterval = null;
let activeSessionId = null;
let difficulty    = 0;
let understanding = 0;

// --- Init ----------------------------------------------------------------

window.addEventListener('load', async () => {
  const params = new URLSearchParams(location.search);
  dayNum = parseInt(params.get('day'), 10);
  if (!dayNum || dayNum < 1 || dayNum > 100) {
    document.querySelector('main').innerHTML =
      '<p class="muted">Invalid day number.</p>';
    return;
  }
  await loadDay();
});

// --- API helpers ---------------------------------------------------------

async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  return res.json();
}

let toastTimer;
function toast(msg, type = 'ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show ' + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, 3500);
}

function fmtTime(secs) {
  if (!secs) return '0m';
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

function fmtDatetime(str) {
  if (!str) return '—';
  // str format: "YYYY-MM-DD HH:MM:SS"
  const [datePart, timePart] = str.split(' ');
  const [y, mo, d] = datePart.split('-');
  const [hh, mm] = timePart.split(':');
  const hour = parseInt(hh, 10);
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const h12  = ((hour % 12) || 12);
  return `${h12}:${mm} ${ampm}`;
}

function badgeClass(status) {
  if (status === 'completed')   return 'badge-completed';
  if (status === 'in_progress') return 'badge-progress';
  return 'badge-notstarted';
}

function badgeText(status) {
  if (status === 'completed')   return 'Completed';
  if (status === 'in_progress') return 'In Progress';
  return 'Not Started';
}

// --- Load day data -------------------------------------------------------

async function loadDay() {
  dayData = await api(`/api/days/${dayNum}`);
  if (dayData.error) {
    document.querySelector('main').innerHTML =
      `<p class="muted">${dayData.error}</p>`;
    return;
  }
  renderDay();
}

function renderDay() {
  const d = dayData;

  // Header
  document.title = `Day ${d.day_number} – Tracker`;
  document.getElementById('dh-label').textContent = `Day ${String(d.day_number).padStart(2,'0')}`;
  document.getElementById('dh-title-input').value = d.title || '';
  const badge = document.getElementById('dh-badge');
  badge.textContent = badgeText(d.status);
  badge.className   = 'badge ' + badgeClass(d.status);
  document.getElementById('dh-completion').textContent =
    d.completion_date ? `Completed: ${d.completion_date}` : '';

  // Description
  document.getElementById('desc-input').value = d.description || '';

  // Topics
  renderTopics();

  // Files
  renderFiles();

  // Reflection
  document.getElementById('confusion-input').value       = d.confusion_notes   || '';
  document.getElementById('revision-notes-input').value  = d.revision_notes    || '';
  document.getElementById('fav-input').value             = d.favorite_learning  || '';
  document.getElementById('needs-revision-chk').checked  = !!d.needs_revision;

  difficulty    = d.difficulty    || 0;
  understanding = d.understanding || 0;
  renderStars('stars-difficulty',    difficulty);
  renderStars('stars-understanding', understanding);

  // Timer & sessions
  renderSessions();

  // Status section
  renderStatusSection();

  // Day nav actions
  renderDayActions();
}

// --- Stars ---------------------------------------------------------------

function renderStars(containerId, value) {
  const el = document.getElementById(containerId);
  el.innerHTML = '';
  for (let i = 1; i <= 5; i++) {
    const span = document.createElement('span');
    span.className = 'star' + (i <= value ? ' active' : '');
    span.textContent = '★';
    span.dataset.val = i;
    span.onclick = () => handleStar(containerId, i);
    el.appendChild(span);
  }
}

function handleStar(containerId, val) {
  if (containerId === 'stars-difficulty')    difficulty    = val;
  if (containerId === 'stars-understanding') understanding = val;
  renderStars(containerId, val);
  saveReflection();
}

// --- Topics --------------------------------------------------------------

function renderTopics() {
  const list = document.getElementById('topics-list');
  if (!dayData.topics.length) {
    list.innerHTML = '<span class="muted" style="font-size:0.82rem">No topics yet.</span>';
    return;
  }
  list.innerHTML = dayData.topics.map(t => `
    <span class="chip">
      ${t.name}
      <button class="chip-remove" onclick="removeTopic(${t.id})" title="Remove">×</button>
    </span>`).join('');
}

async function addTopic() {
  const input = document.getElementById('topic-input');
  const name  = input.value.trim();
  if (!name) return;
  const res = await api(`/api/days/${dayNum}/topics/add`, 'POST', { name });
  if (res.error) return toast(res.error, 'err');
  input.value = '';
  dayData = await api(`/api/days/${dayNum}`);
  renderTopics();
  toast('Topic added.');
}

async function removeTopic(topicId) {
  const res = await api(`/api/days/${dayNum}/topics/${topicId}/remove`, 'POST');
  if (res.error) return toast(res.error, 'err');
  dayData = await api(`/api/days/${dayNum}`);
  renderTopics();
}

// --- Files ---------------------------------------------------------------

function renderFiles() {
  const el = document.getElementById('files-list');
  if (!dayData.files.length) {
    el.innerHTML = '<span class="muted" style="font-size:0.82rem">No files recorded yet.</span>';
    return;
  }
  el.innerHTML = dayData.files.map(f => `
    <div class="flex-between" style="padding:6px 0;border-bottom:1px solid var(--border);font-size:0.83rem">
      <div>
        <code style="color:var(--accent)">${f.file_path}</code>
        ${f.description ? `<div class="muted">${f.description}</div>` : ''}
      </div>
      <button class="btn btn-danger btn-sm" onclick="removeFile(${f.id})">Remove</button>
    </div>`).join('');
}

async function addFile() {
  const path = document.getElementById('file-path-input').value.trim();
  const desc = document.getElementById('file-desc-input').value.trim();
  if (!path) return toast('Please enter a file path.', 'err');
  const res = await api(`/api/days/${dayNum}/files/add`, 'POST',
    { file_path: path, description: desc });
  if (res.error) return toast(res.error, 'err');
  document.getElementById('file-path-input').value = '';
  document.getElementById('file-desc-input').value = '';
  dayData = await api(`/api/days/${dayNum}`);
  renderFiles();
  toast('File added.');
}

async function removeFile(fileId) {
  const res = await api(`/api/files/${fileId}/remove`, 'POST');
  if (res.error) return toast(res.error, 'err');
  dayData = await api(`/api/days/${dayNum}`);
  renderFiles();
}

async function scanFolder() {
  const res     = await api(`/api/days/${dayNum}/scan`);
  const scanEl  = document.getElementById('scan-results');
  scanEl.classList.remove('hidden');

  if (!res.exists) {
    scanEl.innerHTML =
      `<span class="muted">Folder <code>CODES/${res.folder}</code> not found.</span>`;
    return;
  }
  if (!res.files.length) {
    scanEl.innerHTML =
      `<span class="muted">No .py files found in <code>CODES/${res.folder}</code>.</span>`;
    return;
  }

  // Show checkboxes for each file found
  scanEl.innerHTML = `
    <div class="label mb-8">Found in CODES/${res.folder} — select files to add:</div>
    ${res.files.map(f => `
      <label style="display:flex;align-items:center;gap:8px;margin-bottom:6px;cursor:pointer">
        <input type="checkbox" class="scan-file-chk" value="${f}" />
        <code style="font-size:0.82rem;color:var(--text2)">${f}</code>
      </label>`).join('')}
    <button class="btn btn-secondary btn-sm mt-8" onclick="addScannedFiles()">Add Selected</button>
  `;
}

async function addScannedFiles() {
  const checks = document.querySelectorAll('.scan-file-chk:checked');
  if (!checks.length) return toast('No files selected.', 'err');
  let added = 0;
  for (const chk of checks) {
    const res = await api(`/api/days/${dayNum}/files/add`, 'POST',
      { file_path: chk.value, description: '' });
    if (!res.error) added++;
  }
  dayData = await api(`/api/days/${dayNum}`);
  renderFiles();
  document.getElementById('scan-results').classList.add('hidden');
  toast(`Added ${added} file(s).`);
}

// --- Save helpers --------------------------------------------------------

async function saveTitle() {
  const title = document.getElementById('dh-title-input').value.trim();
  const res = await api(`/api/days/${dayNum}/update`, 'POST', { title });
  if (res.error) return toast(res.error, 'err');
  dayData.title = title;  // keep in-memory state in sync
  toast('Title saved.');
}

async function saveDescription() {
  const description = document.getElementById('desc-input').value;
  await api(`/api/days/${dayNum}/update`, 'POST', { description });
}

async function saveReflection() {
  await api(`/api/days/${dayNum}/update`, 'POST', {
    difficulty:        difficulty,
    understanding:     understanding,
    confusion_notes:   document.getElementById('confusion-input').value,
    revision_notes:    document.getElementById('revision-notes-input').value,
    favorite_learning: document.getElementById('fav-input').value,
    needs_revision:    document.getElementById('needs-revision-chk').checked ? 1 : 0,
  });
}

// --- Timer ---------------------------------------------------------------

function renderSessions() {
  const d          = dayData;
  const timerStatus = document.getElementById('timer-status');
  const timerDisp  = document.getElementById('timer-display');
  const startBtn   = document.getElementById('start-btn');
  const stopBtn    = document.getElementById('stop-btn');

  // Clear any existing interval
  clearInterval(timerInterval);

  if (d.active_session) {
    activeSessionId = d.active_session.id;
    timerStatus.innerHTML =
      `<span class="text-warning">Session active since ${d.active_session.started_at.split(' ')[1]}</span>`;
    timerDisp.classList.remove('hidden');
    startBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');

    // Reconstruct elapsed time from stored started_at timestamp
    timerInterval = setInterval(() => {
      const started = new Date(d.active_session.started_at.replace(' ', 'T'));
      const elapsed = Math.floor((Date.now() - started.getTime()) / 1000);
      timerDisp.textContent = fmtTimer(elapsed);
    }, 1000);
  } else {
    activeSessionId = null;
    timerStatus.innerHTML = `<span class="muted">No active session.</span>`;
    timerDisp.classList.add('hidden');
    startBtn.classList.remove('hidden');
    stopBtn.classList.add('hidden');
  }

  // Past sessions
  const sessionList = document.getElementById('session-list');
  const done = d.sessions.filter(s => s.ended_at);
  if (!done.length) {
    sessionList.innerHTML = '';
    return;
  }
  sessionList.innerHTML = done.map((s, i) => `
    <div class="session-item">
      <span class="session-num">#${i + 1}</span>
      <span>${fmtDatetime(s.started_at)} → ${fmtDatetime(s.ended_at)}</span>
      <span style="margin-left:auto">${fmtTime(s.duration_seconds)}</span>
    </div>`).join('');

  if (d.total_secs) {
    sessionList.innerHTML +=
      `<div class="session-item" style="border-top:1px solid var(--border);padding-top:8px">
        <span class="muted">Total</span>
        <span style="margin-left:auto;font-weight:600">${fmtTime(d.total_secs)}</span>
      </div>`;
  }
}

async function startTimer() {
  const res = await api(`/api/days/${dayNum}/sessions/start`, 'POST');
  if (res.error) return toast(res.error, 'err');
  toast('Session started.');
  // Reload to get fresh data and reconstruct timer from DB timestamp
  dayData = await api(`/api/days/${dayNum}`);
  renderSessions();
}

async function stopTimer() {
  if (!activeSessionId) return;
  const res = await api(`/api/sessions/${activeSessionId}/stop`, 'POST');
  if (res.error) return toast(res.error, 'err');
  clearInterval(timerInterval);
  toast('Session stopped. Duration: ' + fmtTime(res.duration_seconds));
  dayData = await api(`/api/days/${dayNum}`);
  renderSessions();
}

// --- Status section -------------------------------------------------------

function renderStatusSection() {
  const el = document.getElementById('status-section');
  const d  = dayData;

  if (d.status === 'completed') {
    el.innerHTML = `
      <div class="badge badge-completed" style="margin-bottom:10px">Completed</div>
      <div class="muted" style="font-size:0.82rem">
        Completed on ${d.completion_date || '—'}
      </div>
      <button class="btn btn-secondary btn-sm mt-8"
              onclick="uncompleteDay()">Reopen Day</button>`;
  } else {
    el.innerHTML = `
      <button class="btn btn-primary w-full" onclick="completeDay()">
        Mark Day Complete
      </button>
      <div class="muted mt-8" style="font-size:0.75rem">
        Requires: description, at least one topic, and one code file.
      </div>`;
  }
}

async function completeDay() {
  const res = await api(`/api/days/${dayNum}/complete`, 'POST');
  if (res.error) return toast(res.error, 'err');
  toast(`Day ${dayNum} completed!`);
  dayData = await api(`/api/days/${dayNum}`);
  renderDay();
}

async function uncompleteDay() {
  const res = await api(`/api/days/${dayNum}/status`, 'POST', { status: 'in_progress' });
  if (res.error) return toast(res.error, 'err');
  toast('Day reopened.');
  dayData = await api(`/api/days/${dayNum}`);
  renderDay();
}

// --- Day navigation actions -----------------------------------------------

function renderDayActions() {
  const el = document.getElementById('day-actions');
  const prev = dayNum > 1   ? dayNum - 1 : null;
  const next = dayNum < 100 ? dayNum + 1 : null;
  el.innerHTML = `
    ${prev ? `<button class="btn btn-secondary btn-sm" onclick="location.href='/day.html?day=${prev}'">← Day ${prev}</button>` : ''}
    ${next ? `<button class="btn btn-secondary btn-sm" onclick="location.href='/day.html?day=${next}'">Day ${next} →</button>` : ''}
  `;
}
