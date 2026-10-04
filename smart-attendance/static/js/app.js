/* AttendIQ front-end: shared helpers + one init function per page */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons = () => window.lucide && lucide.createIcons();
const pages = {};
const COL = {primary:'#601D49', accent:'#BD5579', pink:'#EA9D9D', cream:'#FFEBB8', purple:'#AF719D'};

async function api(url, opt = {}) {
  const o = {headers: {'Content-Type': 'application/json'}, ...opt};
  if (o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);
  let r;
  try { r = await fetch(url, o); } catch (e) { throw new Error('Cannot reach the server. Is it still running?'); }
  let d = {}; try { d = await r.json(); } catch (e) {}
  if (r.status === 401) { location.href = '/login'; throw new Error('Please sign in again.'); }
  if (!r.ok) throw Object.assign(new Error(d.message || 'Something went wrong'), {data: d});
  return d;
}

function toast(msg, type = 'ok') {
  const t = document.createElement('div');
  t.className = 'toast ' + (type === 'ok' ? '' : type);
  t.innerHTML = `<i data-lucide="${type === 'ok' ? 'check-circle-2' : 'alert-triangle'}"></i><span>${esc(msg)}</span>`;
  $('#toasts').appendChild(t); icons();
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, 3800);
}

function modal(html, wide) {
  const o = document.createElement('div');
  o.className = 'overlay';
  o.innerHTML = `<div class="dialog ${wide ? 'wide' : ''}" role="dialog">${html}</div>`;
  const close = () => { o.remove(); document.removeEventListener('keydown', esc_); };
  const esc_ = e => e.key === 'Escape' && close();
  o.addEventListener('click', e => (e.target === o || e.target.closest('[data-close]')) && close());
  document.addEventListener('keydown', esc_);
  document.body.appendChild(o); icons();
  return {el: o.firstElementChild, close};
}

function confirmBox(title, text, okLabel = 'Delete') {
  return new Promise(res => {
    const m = modal(`<h3>${esc(title)}</h3><p style="color:var(--muted);font-size:14px">${esc(text)}</p>
      <div class="row"><button class="btn ghost" data-close>Cancel</button><button class="btn danger" id="ok">${esc(okLabel)}</button></div>`);
    m.el.parentElement.addEventListener('click', e => { if (e.target.id === 'ok' || e.target.closest('#ok')) { res(true); m.close(); } else if (e.target.closest('[data-close]') || e.target === m.el.parentElement) res(false); });
  });
}

function setLoading(btn, on, label) {
  btn.disabled = on;
  const s = $('span', btn);
  if (on) { btn._h = btn.innerHTML; btn.innerHTML = '<div class="spin"></div>'; }
  else if (btn._h) { btn.innerHTML = btn._h; icons(); }
}

const initials = n => n.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
const pill = s => `<span class="pill ${s.toLowerCase()}">${s}</span>`;
const t12 = s => { if (!s || s === '—') return '—'; const d = new Date(s.length > 8 ? s.replace(' ', 'T') : '1970-01-01T' + s); return d.toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}); };
const since = n => { const d = new Date(); d.setDate(d.getDate() - n + 1); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
const mmss = n => String(Math.floor(n / 60)).padStart(2, '0') + ':' + String(n % 60).padStart(2, '0');
const shortDate = d => new Date(d + 'T00:00').toLocaleDateString([], {day: 'numeric', month: 'short'});
const emptyState = (icon, title, text) => `<div class="empty"><i data-lucide="${icon}"></i><b>${title}</b>${text}</div>`;
const skeletonRows = n => Array.from({length: n}, () => '<div class="skeleton sk-row"></div>').join('');

function countUp(el, to, suffix = '') {
  el.classList.remove('skeleton');
  const t0 = performance.now();
  (function f(t) { const p = Math.min(1, (t - t0) / 700); el.textContent = Math.round(to * (1 - Math.pow(1 - p, 3))) + suffix; if (p < 1) requestAnimationFrame(f); })(t0);
}

/* ---------- charts ---------- */
const charts = {};
function drawChart(id, cfg) {
  const c = $('#' + id);
  if (!window.Chart) { c.parentElement.innerHTML = emptyState('wifi-off', 'Chart could not load', 'Connect to the internet and refresh.'); icons(); return; }
  charts[id]?.destroy();
  charts[id] = new Chart(c, cfg);
}
if (window.Chart) { Chart.defaults.color = '#c3a0b3'; Chart.defaults.font.family = 'Inter'; Chart.defaults.animation.duration = 900; }
const tip = {backgroundColor: '#2a0d20', borderColor: 'rgba(234,157,157,.3)', borderWidth: 1, titleColor: COL.cream, bodyColor: '#f7eaf0', padding: 10, cornerRadius: 10, displayColors: false};
const grid = {color: 'rgba(234,157,157,.08)'};
function lineChart(id, pts) {
  const ctx = $('#' + id).getContext('2d'), g = ctx.createLinearGradient(0, 0, 0, 260);
  g.addColorStop(0, 'rgba(189,85,121,.55)'); g.addColorStop(1, 'rgba(189,85,121,0)');
  drawChart(id, {type: 'line', data: {labels: pts.map(p => shortDate(p.date)), datasets: [{data: pts.map(p => p.pct), borderColor: COL.accent, backgroundColor: g, fill: true, tension: .4, borderWidth: 3, pointRadius: 4, pointBackgroundColor: COL.cream, pointBorderColor: COL.accent, pointHoverRadius: 7}]},
    options: {maintainAspectRatio: false, plugins: {legend: {display: false}, tooltip: {...tip, callbacks: {label: c => c.parsed.y + '% present'}}}, scales: {y: {min: 0, max: 100, grid, ticks: {callback: v => v + '%'}}, x: {grid: {display: false}}}}});
}
function donutChart(id, labels, data) {
  drawChart(id, {type: 'doughnut', data: {labels, datasets: [{data, backgroundColor: [COL.cream, COL.purple, COL.accent].slice(0, data.length), borderColor: '#1c0a16', borderWidth: 3, hoverOffset: 10}]},
    options: {maintainAspectRatio: false, cutout: '68%', plugins: {legend: {position: 'bottom', labels: {usePointStyle: true, padding: 16}}, tooltip: tip}}});
}
function barChart(id, labels, data) {
  drawChart(id, {type: 'bar', data: {labels, datasets: [{data, backgroundColor: COL.accent, hoverBackgroundColor: COL.cream, borderRadius: 8, maxBarThickness: 44}]},
    options: {maintainAspectRatio: false, plugins: {legend: {display: false}, tooltip: {...tip, callbacks: {label: c => c.parsed.y + '%'}}}, scales: {y: {min: 0, max: 100, grid, ticks: {callback: v => v + '%'}}, x: {grid: {display: false}}}}});
}

/* ---------- shell ---------- */
async function loadNotifications() {
  try {
    const list = await api('/api/notifications');
    $('#bell-n').style.display = list.length ? 'grid' : 'none'; $('#bell-n').textContent = list.length;
    $('#notif-list').innerHTML = list.length ? list.map(n => `<div class="note ${n.type}"><div class="dot"><i data-lucide="${n.type === 'low' ? 'trending-down' : n.type === 'warn' ? 'shield-alert' : n.type === 'qr' ? 'qr-code' : 'info'}"></i></div><div><b>${esc(n.title)}</b><small style="color:var(--text)">${esc(n.text)}</small>${n.time ? `<small>${t12(n.time)}</small>` : ''}</div></div>`).join('') : emptyState('bell-off', 'All clear', 'No alerts right now.');
    icons();
  } catch (e) {}
}

document.addEventListener('DOMContentLoaded', () => {
  if (localStorage.getItem('sb') === '1') document.body.classList.add('sb-collapsed');
  $('#collapse')?.addEventListener('click', () => { document.body.classList.toggle('sb-collapsed'); localStorage.setItem('sb', document.body.classList.contains('sb-collapsed') ? '1' : '0'); });
  $('#bell')?.addEventListener('click', e => { e.stopPropagation(); $('#notif').classList.toggle('open'); });
  document.addEventListener('click', e => { if (!e.target.closest('#notif')) $('#notif')?.classList.remove('open'); });
  icons(); loadNotifications(); setInterval(loadNotifications, 20000);
  (pages[document.body.dataset.page] || (() => {}))();
});

/* ---------- dashboard ---------- */
const actIcon = {success: 'check', qr: 'qr-code', warn: 'shield-alert', system: 'info', info: 'info'};
pages.dashboard = () => {
  let S, days = 7, qrAt = 0;
  const actHTML = a => a.length ? a.map(x => `<div class="feed-item ${x.kind}"><div class="dot"><i data-lucide="${actIcon[x.kind] || 'info'}"></i></div><span>${esc(x.message)}</span><small>${t12(x.created_at)}</small></div>`).join('') : emptyState('inbox', 'Nothing yet', 'Activity shows up here.');
  $('#activity').innerHTML = skeletonRows(5);
  function renderTrend() { const c = since(days); lineChart('trend', S.trend.filter(p => p.date >= c)); }
  function qrMini() {
    const q = S.qr, el = $('#qr-mini'); const left = q.state === 'active' ? Math.max(0, q.remaining - Math.floor((Date.now() - qrAt) / 1000)) : 0;
    if (q.state === 'none') el.innerHTML = emptyState('qr-code', 'No session yet', '<a class="btn primary sm" style="margin-top:12px" href="/qr">Generate QR</a>');
    else el.innerHTML = `<div class="mini-qr"><span class="status ${left > 0 ? 'active' : 'expired'}">${left > 0 ? 'QR ACTIVE' : 'QR EXPIRED'}</span><div><div class="timer" style="font-size:28px">${left > 0 ? mmss(left) : '00:00'}</div><div style="color:var(--muted);font-size:13px">${esc(q.subject)} · ${q.attendees.length} scanned</div></div></div><a class="btn ghost sm" style="margin-top:14px" href="/qr">${left > 0 ? 'Open session' : 'Start new session'}</a>`;
    icons();
  }
  async function load(first) {
    S = await api('/api/stats'); qrAt = Date.now();
    countUp($('#s-total'), S.total); countUp($('#s-present'), S.present); countUp($('#s-absent'), S.absent); countUp($('#s-pct'), S.pct, '%');
    $('#s-late').textContent = S.late ? `${S.late} of them arrived late` : 'On time so far';
    $('#s-low').textContent = S.low_count ? `${S.low_count} student${S.low_count > 1 ? 's' : ''} below the limit` : 'Everyone is above the limit';
    donutChart('donut', ['Present', 'Absent'], [S.present, S.absent]);
    if (first) renderTrend();
    qrMini();
    $('#absent-list').innerHTML = S.absent_list.length ? S.absent_list.slice(0, 8).map(s => `<div class="feed-item"><div class="mini-av">${initials(s.name)}</div><span><b>${esc(s.name)}</b><br><small style="margin:0;color:var(--muted)">${esc(s.student_id)} · ${esc(s.cls)}</small></span></div>`).join('') + (S.absent_list.length > 8 ? `<div class="empty" style="padding:12px">+ ${S.absent_list.length - 8} more</div>` : '') : emptyState('party-popper', 'Full attendance', 'Everyone is present today.');
    $('#activity').innerHTML = actHTML(await api('/api/activity')); icons();
  }
  $('#range').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; $$('#range button').forEach(x => x.classList.toggle('on', x === b)); days = +b.dataset.d; renderTrend(); });
  load(true).catch(e => toast(e.message, 'error'));
  setInterval(() => { if (S) { load(false).catch(() => {}); } }, 5000);
  setInterval(() => S && qrMini(), 1000);
};

/* ---------- QR page ---------- */
pages.qr = async () => {
  let cur = null, at = 0, lastToken = null, lastState = null;
  const CIRC = 339.29;
  const rem = () => cur && cur.state === 'active' ? Math.max(0, cur.remaining - Math.floor((Date.now() - at) / 1000)) : 0;
  const cfg = await api('/api/settings');
  $('#subject').innerHTML = cfg.subjects.map(s => `<option>${s}</option>`).join('');
  $('#minutes').value = [1, 2, 5, 10, 15, 30].includes(cfg.default_minutes) ? cfg.default_minutes : 5;

  async function sync() { cur = await api('/api/qr/current'); at = Date.now(); paint(); }
  function paint() {
    const st = $('#st'), box = $('#qrbox');
    if (!cur || cur.state === 'none') return;
    const r = rem(), active = cur.state === 'active' && r > 0;
    if (cur.token !== lastToken) { box.className = 'qr-img'; box.innerHTML = `<img alt="Attendance QR code" src="/api/qr/${cur.token}/image.png"><div class="over"><i data-lucide="timer-off" style="width:40px;height:40px"></i>QR EXPIRED</div>`; lastToken = cur.token; icons(); $('#link').value = cur.url; }
    box.classList.toggle('expired', !active);
    st.className = 'status ' + (active ? 'active' : 'expired'); st.textContent = active ? 'QR ACTIVE' : 'QR EXPIRED';
    $('#timer').textContent = active ? mmss(r) : '00:00';
    $('#meta').textContent = active ? `Expires in ${mmss(r)} · ${cur.subject} class` : `${cur.subject} session has ended. Regenerate to start again.`;
    $('#fg').style.strokeDashoffset = CIRC * (1 - (active ? r / cur.total : 0));
    $('#regen').style.display = 'inline-flex';
    if (lastState === 'active' && !active) toast('This QR code has expired.', 'warn');
    lastState = active ? 'active' : 'expired';
    $('#cnt').textContent = cur.attendees.length;
    $('#attendees').innerHTML = cur.attendees.length ? cur.attendees.map(a => `<div class="feed-item"><div class="mini-av">${initials(a.name)}</div><span><b>${esc(a.name)}</b><br><small style="margin:0;color:var(--muted)">${esc(a.student_id)}</small></span>${pill(a.status)}<small style="margin-left:10px">${t12(a.time)}</small></div>`).join('') : emptyState('hourglass', 'Waiting for students', 'Ask them to scan the code.');
    icons();
  }
  async function generate(btn) {
    setLoading(btn, true);
    try { await api('/api/qr/generate', {method: 'POST', body: {subject: $('#subject').value, minutes: $('#minutes').value}}); lastToken = null; await sync(); toast('QR code is ready. Students can scan now.'); }
    catch (e) { toast(e.message, 'error'); }
    setLoading(btn, false);
  }
  $('#gen').onclick = () => generate($('#gen'));
  $('#regen').onclick = () => generate($('#regen'));
  $('#stop').onclick = async () => {
    if (!cur || cur.state !== 'active') return toast('There is no active session to end.', 'warn');
    if (await confirmBox('End this session?', 'Students will no longer be able to mark attendance with this code.', 'End session')) { await api('/api/qr/stop', {method: 'POST'}); sync(); toast('Session ended.'); }
  };
  $('#copy').onclick = () => { const v = $('#link').value; if (!v) return toast('Generate a QR code first.', 'warn'); navigator.clipboard?.writeText(v).then(() => toast('Link copied.')).catch(() => { $('#link').select(); document.execCommand('copy'); toast('Link copied.'); }); };
  $('#attendees').innerHTML = emptyState('hourglass', 'No session yet', 'Generate a QR code to begin.');
  await sync();
  setInterval(() => { if (cur && cur.state === 'active') { if (rem() <= 0) sync(); else paint(); } }, 1000);
  setInterval(() => cur && cur.state === 'active' && sync().catch(() => {}), 4000);
};

/* ---------- students ---------- */
pages.students = () => {
  let list = [], page = 0; const PER = 8;
  const rowsEl = $('#rows');
  async function load() {
    rowsEl.innerHTML = `<tr><td colspan="6">${skeletonRows(5)}</td></tr>`;
    try { list = await api(`/api/students?q=${encodeURIComponent($('#q').value)}&cls=${encodeURIComponent($('#cls').value)}`); page = 0; render(); }
    catch (e) { rowsEl.innerHTML = `<tr><td colspan="6">${emptyState('wifi-off', 'Could not load students', esc(e.message))}</td></tr>`; icons(); }
  }
  function render() {
    const pages_ = Math.max(1, Math.ceil(list.length / PER)), slice = list.slice(page * PER, page * PER + PER);
    rowsEl.innerHTML = slice.length ? slice.map(s => `<tr class="click" data-id="${esc(s.student_id)}">
      <td data-l="ID">${esc(s.student_id)}</td><td data-l="Name"><div class="who"><div class="mini-av">${initials(s.name)}</div>${esc(s.name)}</div></td>
      <td data-l="Class">${esc(s.cls)}</td><td data-l="Attendance">${s.pct}%<span class="bar"><i style="width:${s.pct}%"></i></span></td>
      <td data-l="Today">${pill(s.today)}</td>
      <td data-l="Actions"><div class="acts"><button class="btn ghost sm" data-act="edit" title="Edit"><i data-lucide="pencil"></i></button><button class="btn danger sm" data-act="del" title="Delete"><i data-lucide="trash-2"></i></button></div></td></tr>`).join('')
      : `<tr><td colspan="6">${emptyState('user-search', 'No students found', 'Try a different search or add a new student.')}</td></tr>`;
    $('#info').textContent = list.length ? `Showing ${page * PER + 1}–${page * PER + slice.length} of ${list.length}` : '0 students';
    $('#prev').disabled = page === 0; $('#next').disabled = page >= pages_ - 1; icons();
  }
  function showPin(name, pin, title = 'New PIN') {
    modal(`<h3>${title}</h3><p style="color:var(--muted);font-size:14px">Give this PIN to <b style="color:var(--text)">${esc(name)}</b>. For safety it is shown only once.</p>
      <div class="big-pct" style="text-align:center;margin:22px 0;letter-spacing:.3em">${pin}</div><div class="row"><button class="btn primary" data-close>Done</button></div>`);
  }
  function downloadCSV(list) {
    const q = v => '"' + String(v).replace(/"/g, '""') + '"';
    const csv = ['Student ID,Name,Class,PIN', ...list.map(r => [q(r.student_id), q(r.name), q(r.cls), r.pin].join(','))].join('\r\n');
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv'})); a.download = 'student_pins.csv'; a.click();
  }
  function form(s) {
    const m = modal(`<h3>${s ? 'Edit student' : 'Add a student'}</h3><p style="color:var(--muted);font-size:14px;margin-bottom:18px">${s ? 'Update the details below.' : 'They can mark attendance once added.'}</p>
      <div class="form-grid"><div class="field"><label>Student ID</label><input id="f-id" value="${esc(s?.student_id || '')}" ${s ? 'disabled' : ''} placeholder="CS24025"></div>
      <div class="field"><label>Class</label><select id="f-cls">${['CSE-A', 'CSE-B', 'IT-A'].map(c => `<option ${s?.cls === c ? 'selected' : ''}>${c}</option>`).join('')}</select></div></div>
      <div class="field"><label>Full name</label><input id="f-name" value="${esc(s?.name || '')}" placeholder="e.g. Aarav Kumar"></div>
      <div class="row"><button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="f-save"><span>Save student</span></button></div>`);
    $('#f-save', m.el).onclick = async e => {
      const b = e.currentTarget, body = {student_id: $('#f-id', m.el).value, name: $('#f-name', m.el).value, cls: $('#f-cls', m.el).value};
      setLoading(b, true);
      try { const r = await api(s ? `/api/students/${s.student_id}` : '/api/students', {method: s ? 'PUT' : 'POST', body}); m.close(); toast(s ? 'Student updated.' : 'Student added.'); load(); if (!s) showPin(body.name, r.pin, 'Student added'); }
      catch (err) { toast(err.message, 'error'); setLoading(b, false); }
    };
  }
  async function detail(id) {
    const m = modal(`<div class="skeleton" style="height:300px"></div>`, true);
    try {
      const {student: s, trend, history} = await api('/api/students/' + id);
      m.el.innerHTML = `<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><div class="mini-av" style="width:56px;height:56px;font-size:20px;border-radius:16px">${initials(s.name)}</div>
        <div><h3 style="margin:0">${esc(s.name)}</h3><span style="color:var(--muted);font-size:13px">${esc(s.student_id)} · ${esc(s.cls)}</span></div>
        <div style="margin-left:auto;text-align:right"><div class="big-pct">${s.pct}%</div><span style="color:var(--muted);font-size:12px">overall attendance</span></div></div>
        <div class="mini-stats"><div><b>${s.present}</b><span>Present</span></div><div><b>${s.late}</b><span>Late</span></div><div><b>${s.absent}</b><span>Absent</span></div></div>
        <div class="chart-box sm"><canvas id="sd"></canvas></div>
        <h4 style="margin:18px 0 6px">Recent history</h4>
        <div class="feed">${history.map(h => `<div class="feed-item"><span><b>${esc(h.subject)}</b></span><small style="margin:0 0 0 auto">${shortDate(h.date)} · ${t12(h.time)}</small>${pill(h.status)}</div>`).join('') || emptyState('inbox', 'No records yet', '')}</div>
        <h4 style="margin:18px 0 8px">PIN and phone</h4>
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center"><span class="pill ${s.has_pin ? 'present' : 'absent'}">${s.has_pin ? 'PIN set' : 'No PIN yet'}</span><span class="pill ${s.device_linked ? 'present' : 'late'}">${s.device_linked ? 'Phone linked' : 'No phone linked'}</span>
          <button class="btn ghost sm" id="rp"><i data-lucide="key-round"></i>Reset PIN</button><button class="btn ghost sm" id="ul" ${s.device_linked ? '' : 'disabled'}><i data-lucide="smartphone"></i>Unlink phone</button></div>
        <div class="row"><button class="btn ghost" data-close>Close</button></div>`;
      lineChart('sd', trend); icons();
      $('#rp', m.el).onclick = async () => { if (await confirmBox('Reset PIN for ' + s.name + '?', 'The old PIN stops working and their linked phone is removed.', 'Reset PIN')) { const r = await api(`/api/students/${s.student_id}/reset-pin`, {method: 'POST'}); m.close(); load(); showPin(s.name, r.pin); } };
      $('#ul', m.el).onclick = async () => { await api(`/api/students/${s.student_id}/unlink-device`, {method: 'POST'}); m.close(); load(); toast('Phone unlinked. The next scan links a new one.'); };
    } catch (e) { m.close(); toast(e.message, 'error'); }
  }
  rowsEl.addEventListener('click', async e => {
    const tr = e.target.closest('tr[data-id]'); if (!tr) return;
    const s = list.find(x => x.student_id === tr.dataset.id), act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'edit') form(s);
    else if (act === 'del') { if (await confirmBox('Delete ' + s.name + '?', 'Their attendance records will also be removed. This cannot be undone.')) { await api('/api/students/' + s.student_id, {method: 'DELETE'}); toast('Student deleted.'); load(); } }
    else detail(s.student_id);
  });
  let t; $('#q').addEventListener('input', () => { clearTimeout(t); t = setTimeout(load, 250); });
  $('#cls').onchange = load; $('#add').onclick = () => form(null);
  $('#pins').onclick = async e => {
    const b = e.currentTarget; setLoading(b, true);
    try {
      const r = await api('/api/pins/generate', {method: 'POST'});
      if (!r.pins.length) toast('Everyone already has a PIN. Open a student to reset one.', 'warn');
      else { downloadCSV(r.pins); load(); modal(`<h3>PINs created</h3><p style="color:var(--muted);font-size:14px">student_pins.csv with ${r.pins.length} PIN${r.pins.length > 1 ? 's' : ''} was downloaded. Hand each student their own PIN and keep the file private. PINs are not shown again.</p><div class="row"><button class="btn primary" data-close>Done</button></div>`); }
    } catch (err) { toast(err.message, 'error'); }
    setLoading(b, false);
  };
  $('#prev').onclick = () => { page--; render(); }; $('#next').onclick = () => { page++; render(); };
  load();
};

/* ---------- attendance ---------- */
pages.attendance = async () => {
  const f = ['q', 'date', 'subject', 'sid', 'status'];
  const cfg = await api('/api/settings'), studs = await api('/api/students');
  $('#subject').innerHTML += cfg.subjects.map(s => `<option>${s}</option>`).join('');
  $('#sid').innerHTML += studs.map(s => `<option value="${esc(s.student_id)}">${esc(s.name)}</option>`).join('');
  const qs = () => f.map(k => `${k}=${encodeURIComponent($('#' + k).value)}`).join('&');
  async function load() {
    $('#export').href = '/api/attendance/export.csv?' + qs();
    $('#rows').innerHTML = `<tr><td colspan="6">${skeletonRows(6)}</td></tr>`;
    try {
      const r = await api('/api/attendance?' + qs());
      $('#rows').innerHTML = r.length ? r.map(x => `<tr><td data-l="Student"><div class="who"><div class="mini-av">${initials(x.name)}</div>${esc(x.name)}</div></td><td data-l="ID">${esc(x.student_id)}</td><td data-l="Date">${shortDate(x.date)}</td><td data-l="Time">${t12(x.time)}</td><td data-l="Subject">${esc(x.subject)}</td><td data-l="Status">${pill(x.status)}</td></tr>`).join('')
        : `<tr><td colspan="6">${emptyState('clipboard-x', 'No records match', 'Clear the filters to see everything.')}</td></tr>`;
      $('#info').textContent = r.length >= 400 ? 'Showing the latest 400 records. Use filters or export for more.' : `${r.length} record${r.length === 1 ? '' : 's'}`;
      icons();
    } catch (e) { $('#rows').innerHTML = `<tr><td colspan="6">${emptyState('wifi-off', 'Could not load records', esc(e.message))}</td></tr>`; icons(); }
  }
  let t; $('#q').addEventListener('input', () => { clearTimeout(t); t = setTimeout(load, 250); });
  ['date', 'subject', 'sid', 'status'].forEach(k => $('#' + k).onchange = load);
  $('#clear').onclick = () => { f.forEach(k => $('#' + k).value = ''); load(); };
  load();
};

/* ---------- analytics ---------- */
pages.analytics = async () => {
  try {
    const A = await api('/api/analytics'); let days = 7;
    const draw = () => { const c = since(days); lineChart('trend', A.trend.filter(p => p.date >= c)); };
    draw();
    $('#range').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; $$('#range button').forEach(x => x.classList.toggle('on', x === b)); days = +b.dataset.d; draw(); });
    donutChart('donut', ['Present', 'Late', 'Absent'], [A.status.Present || 0, A.status.Late || 0, A.status.Absent || 0]);
    barChart('weekly', A.weekly.map(w => w.day), A.weekly.map(w => w.pct));
    barChart('subjects', A.subjects.map(s => s.subject), A.subjects.map(s => s.pct));
  } catch (e) { toast(e.message, 'error'); }
};

/* ---------- reports ---------- */
pages.reports = async () => {
  const cfg = await api('/api/settings');
  $('#rsub').innerHTML += cfg.subjects.map(s => `<option>${s}</option>`).join('');
  $('#rsub').onchange = () => $('#dl').href = '/api/attendance/export.csv?subject=' + encodeURIComponent($('#rsub').value);
  try {
    const [S, studs] = await Promise.all([api('/api/stats'), api('/api/students')]);
    $('#sum').innerHTML = `<div><b>${S.total}</b><span>Students</span></div><div><b>${S.present}</b><span>Present</span></div><div><b>${S.pct}%</b><span>Attendance</span></div>`;
    const low = studs.filter(s => s.pct < cfg.low_threshold).sort((a, b) => a.pct - b.pct);
    $('#lowsub').textContent = `Below ${cfg.low_threshold}% attendance`;
    $('#low').innerHTML = low.length ? low.map(s => `<tr><td data-l="Student"><div class="who"><div class="mini-av">${initials(s.name)}</div>${esc(s.name)}</div></td><td data-l="Class">${esc(s.cls)}</td><td data-l="Present">${s.present + s.late}</td><td data-l="Absent">${s.absent}</td><td data-l="Attendance">${s.pct}%<span class="bar"><i style="width:${s.pct}%"></i></span></td></tr>`).join('')
      : `<tr><td colspan="5">${emptyState('party-popper', 'Great news', 'Every student is above the limit.')}</td></tr>`;
    icons();
  } catch (e) { toast(e.message, 'error'); }
};

/* ---------- settings ---------- */
pages.settings = async () => {
  const keys = ['late_after', 'low_threshold', 'default_minutes'];
  const cfg = await api('/api/settings'); keys.forEach(k => $('#' + k).value = cfg[k]);
  $('#save').onclick = async e => {
    const b = e.currentTarget; setLoading(b, true);
    try { await api('/api/settings', {method: 'POST', body: Object.fromEntries(keys.map(k => [k, $('#' + k).value]))}); toast('Settings saved.'); }
    catch (err) { toast(err.message, 'error'); }
    setLoading(b, false);
  };
  $('#pw').onclick = async e => {
    const b = e.currentTarget; setLoading(b, true);
    try { await api('/api/password', {method: 'POST', body: {current: $('#cur').value, new: $('#new').value}}); $('#cur').value = $('#new').value = ''; toast('Password updated.'); }
    catch (err) { toast(err.message, 'error'); }
    setLoading(b, false);
  };
};
