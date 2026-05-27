const POLL_MS = (window.JOLLY_POLL_SECONDS || 300) * 1000;
const REVIEW_POLL_MS = 2000;
const LS_THEME = 'jolly.theme';
const LS_FILTERS = 'jolly.filters';

let data = null;
let lastSyncedAt = null;
let lastCounts = {};

const filters = loadFilters();

document.addEventListener('DOMContentLoaded', () => {
  applyTheme(localStorage.getItem(LS_THEME) || 'dark');
  document.getElementById('theme-btn').addEventListener('click', toggleTheme);
  document.getElementById('refresh-btn').addEventListener('click', fetchDashboard);
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('modal').addEventListener('click', (e) => {
    if (e.target.id === 'modal') closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
  fetchDashboard();
  setInterval(fetchDashboard, POLL_MS);
  setInterval(updateSyncLabel, 30000);
});

/* ============================================================
   Theme
   ============================================================ */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = document.getElementById('theme-btn');
  if (btn) btn.textContent = theme === 'dark' ? '☾' : '☀';
  localStorage.setItem(LS_THEME, theme);
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme;
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

/* ============================================================
   Filters (per-section, persisted)
   ============================================================ */
function defaultFilters() {
  return {
    allTickets: { sources: { jira: true, linear: true } },
    myPrs: { hideDrafts: false },
    reviews: { hideDrafts: false },
  };
}

function loadFilters() {
  try {
    const stored = JSON.parse(localStorage.getItem(LS_FILTERS) || '{}');
    return { ...defaultFilters(), ...stored };
  } catch {
    return defaultFilters();
  }
}

function saveFilters() {
  localStorage.setItem(LS_FILTERS, JSON.stringify(filters));
}

/* ============================================================
   Data fetching
   ============================================================ */
async function fetchDashboard() {
  setSyncStatus('syncing…', 'is-syncing');
  try {
    const r = await fetch('/api/dashboard');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    data = await r.json();
    lastSyncedAt = new Date();
    renderAll();
    updateSyncLabel();
  } catch (e) {
    setSyncStatus(`sync failed: ${e.message}`, 'is-error');
  }
}

function setSyncStatus(text, statusClass) {
  const el = document.getElementById('sync-status');
  el.textContent = text;
  el.classList.remove('is-syncing', 'is-error');
  if (statusClass) el.classList.add(statusClass);
}

function updateSyncLabel() {
  if (!lastSyncedAt) return;
  const errs = data && data.errors ? Object.keys(data.errors) : [];
  const suffix = errs.length ? ` · ${errs.length} source error${errs.length > 1 ? 's' : ''}` : '';
  setSyncStatus(`synced ${timeAgo(lastSyncedAt)}${suffix}`, errs.length ? 'is-error' : '');
}

/* ============================================================
   Render
   ============================================================ */
function renderAll() {
  renderToday();
  renderMyPrs();
  renderReviews();
  renderWeek();
  renderAllTickets();
}

function updateCount(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  if (lastCounts[id] !== value) {
    el.classList.remove('bump');
    void el.offsetWidth;
    el.classList.add('bump');
    setTimeout(() => el.classList.remove('bump'), 320);
  }
  el.textContent = value;
  lastCounts[id] = value;
}

function renderToday() {
  const el = document.getElementById('today-list');
  const tickets = data.tickets.daily || [];
  const todayIso = todayDateIso();
  const events = ((data.calendar && data.calendar.events) || [])
    .filter((e) => e.startDate === todayIso)
    .slice()
    .sort((a, b) => {
      if (a.allDay !== b.allDay) return a.allDay ? -1 : 1;
      return (a.startTime || '').localeCompare(b.startTime || '');
    });
  const total = tickets.length + events.length;
  updateCount('today-count', total);
  if (!total) {
    el.innerHTML = '<div class="row-empty">nothing on the docket today. enjoy.</div>';
    return;
  }
  const eventTiles = events.map(renderEventTile).join('');
  const ticketTiles = tickets.map(renderTicketTile).join('');
  el.innerHTML = eventTiles + ticketTiles;
  attachTicketHandlers(el);
}

function todayDateIso() {
  const days = (data.calendar && data.calendar.days) || [];
  const found = days.find((d) => d.isToday);
  if (found) return found.date;
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function renderEventTile(e) {
  const time = e.allDay
    ? 'all day'
    : (e.startTime || '') + (e.endTime ? `–${e.endTime}` : '');
  const locationPill = e.location ? `<span class="pill">${escapeHtml(e.location)}</span>` : '';
  const link = e.link
    ? `<a class="tile-link" href="${escapeAttr(e.link)}" target="_blank" rel="noreferrer noopener">join →</a>`
    : '<span class="tile-sub"></span>';
  return `
    <div class="tile" data-kind="event" data-all-day="${e.allDay ? 'true' : 'false'}">
      <div class="tile-head">
        <span class="tile-tag">${e.allDay ? 'all-day' : 'meeting'}</span>
        <span class="tile-id">${escapeHtml(time)}</span>
      </div>
      <div class="tile-title">${escapeHtml(e.title || '(untitled)')}</div>
      <div class="tile-meta">${locationPill}</div>
      <div class="tile-foot">
        <span class="tile-sub"></span>
        ${link}
      </div>
    </div>
  `;
}

function renderTicketTile(t) {
  const statePill = `<span class="pill ${stateTypeClass(t.stateType)}">${escapeHtml(t.state || '')}</span>`;
  const priorityPill = t.priority ? `<span class="pill">${escapeHtml(t.priority)}</span>` : '';
  const cyclePill = t.cycle ? `<span class="pill">${escapeHtml(t.cycle)}</span>` : '';
  return `
    <div class="tile" data-kind="ticket" data-source="${t.source}" data-id="${escapeAttr(t.id)}" data-team="${escapeAttr(t.team || '')}">
      <div class="tile-head">
        <span class="tile-tag">${escapeHtml(t.source)}</span>
        <span class="tile-id">${escapeHtml(t.key)}</span>
      </div>
      <div class="tile-title"><a href="${escapeAttr(t.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(t.title)}</a></div>
      <div class="tile-meta">${statePill}${priorityPill}${cyclePill}</div>
      <div class="tile-foot">
        <span class="tile-sub"></span>
        <button class="transition-btn" type="button">move</button>
      </div>
    </div>
  `;
}

function renderAllTickets() {
  renderChips('all-tickets-chips', getTicketChipDefs(), () => {
    saveFilters();
    renderAllTickets();
  });
  const el = document.getElementById('all-tickets-list');
  const visible = data.tickets.all.filter((t) => filters.allTickets.sources[t.source]);
  updateCount('all-tickets-count', visible.length);
  if (!visible.length) {
    el.innerHTML = '<div class="empty">no tickets match current filters.</div>';
    return;
  }
  el.innerHTML = visible.map(renderTicketRow).join('');
  attachTicketHandlers(el);
}

function getTicketChipDefs() {
  const sources = data.sources || {};
  const counts = { jira: 0, linear: 0 };
  (data.tickets.all || []).forEach((t) => { counts[t.source] = (counts[t.source] || 0) + 1; });
  const defs = [];
  if (sources.jira) defs.push({
    key: 'jira',
    label: 'jira',
    count: counts.jira || 0,
    pressed: !!filters.allTickets.sources.jira,
    onToggle: () => { filters.allTickets.sources.jira = !filters.allTickets.sources.jira; },
  });
  if (sources.linear) defs.push({
    key: 'linear',
    label: 'linear',
    count: counts.linear || 0,
    pressed: !!filters.allTickets.sources.linear,
    onToggle: () => { filters.allTickets.sources.linear = !filters.allTickets.sources.linear; },
  });
  return defs;
}

function renderChips(containerId, defs, afterToggle) {
  const root = document.getElementById(containerId);
  if (!root) return;
  if (!defs.length) { root.innerHTML = ''; return; }
  root.innerHTML = defs.map((d) => `
    <button class="chip" type="button" data-filter="${escapeAttr(d.key)}" aria-pressed="${d.pressed}">
      <span class="chip-dot"></span>
      ${escapeHtml(d.label)}
      <span class="chip-count">${d.count}</span>
    </button>
  `).join('');
  root.querySelectorAll('.chip').forEach((btn, i) => {
    btn.addEventListener('click', () => {
      defs[i].onToggle();
      afterToggle();
    });
  });
}

function renderTicketRow(t) {
  const sourcePill = `<span class="pill ${t.source}"><span class="dot"></span>${t.source}</span>`;
  const statePill = `<span class="pill ${stateTypeClass(t.stateType)}">${escapeHtml(t.state || '')}</span>`;
  const cyclePill = t.cycle ? `<span class="pill">${escapeHtml(t.cycle)}</span>` : '';
  const priorityPill = t.priority ? `<span class="pill">${escapeHtml(t.priority)}</span>` : '';
  return `
    <div class="item" data-source="${t.source}" data-id="${escapeAttr(t.id)}" data-team="${escapeAttr(t.team || '')}">
      <div class="item-key">${escapeHtml(t.key)}</div>
      <div>
        <div class="item-title"><a href="${escapeAttr(t.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(t.title)}</a></div>
        <div class="item-meta">${sourcePill}${statePill}${cyclePill}${priorityPill}</div>
      </div>
      <div class="actions">
        <button class="transition-btn" type="button">move</button>
      </div>
    </div>
  `;
}

function stateTypeClass(t) {
  if (!t) return '';
  const v = String(t).toLowerCase();
  if (['started', 'inprogress', 'in-progress', 'indeterminate'].includes(v)) return 'warn';
  if (['completed', 'done'].includes(v)) return 'good';
  if (['canceled', 'cancelled'].includes(v)) return '';
  if (['backlog', 'unstarted', 'new', 'todo'].includes(v)) return 'info';
  return '';
}

function attachTicketHandlers(root) {
  root.querySelectorAll('.transition-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => openTransitionMenu(e.currentTarget));
  });
}

async function openTransitionMenu(btn) {
  const container = btn.closest('.tile, .item');
  const source = container.dataset.source;
  const id = container.dataset.id;
  const team = container.dataset.team;
  btn.disabled = true;
  btn.textContent = 'loading…';
  try {
    const params = source === 'linear' && team ? `?teamId=${encodeURIComponent(team)}` : '';
    const r = await fetch(`/api/tickets/${source}/${encodeURIComponent(id)}/transitions${params}`);
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${r.status}`);
    }
    const { transitions } = await r.json();
    if (!transitions || !transitions.length) {
      btn.disabled = false;
      btn.textContent = 'move';
      alert('no transitions available');
      return;
    }
    const select = document.createElement('select');
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '→ move to…';
    select.appendChild(placeholder);
    transitions.forEach((t) => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = source === 'jira'
        ? `${t.name}${t.to ? ` → ${t.to}` : ''}`
        : `${t.name} (${t.type})`;
      select.appendChild(opt);
    });
    btn.replaceWith(select);
    select.focus();
    select.addEventListener('change', () => applyTransition(select, source, id));
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'move';
    alert(`failed to load transitions: ${e.message}`);
  }
}

async function applyTransition(select, source, id) {
  if (!select.value) return;
  select.disabled = true;
  try {
    const r = await fetch(`/api/tickets/${source}/${encodeURIComponent(id)}/transition`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targetId: select.value }),
    });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${r.status}`);
    }
    await fetchDashboard();
  } catch (e) {
    alert(`transition failed: ${e.message}`);
    select.disabled = false;
  }
}

/* ============================================================
   Week
   ============================================================ */
function renderWeek() {
  const el = document.getElementById('week-grid');
  const cal = data.calendar || {};
  updateCount('week-count', (cal.events || []).length);
  if (!cal.enabled) {
    el.innerHTML = '<div class="calendar-unavailable">set <code>GCAL_ICS_URLS</code> in <code>.env</code> to enable. get the URL from Google Calendar → settings → "settings for my calendars" → your calendar → "integrate calendar" → "secret address in iCal format".</div>';
    return;
  }
  if (data.errors && data.errors.gcal) {
    el.innerHTML = `<p class="error">calendar error: ${escapeHtml(data.errors.gcal)}</p>`;
    return;
  }
  const days = cal.days || [];
  const eventsByDay = {};
  (cal.events || []).forEach((e) => {
    if (!eventsByDay[e.startDate]) eventsByDay[e.startDate] = [];
    eventsByDay[e.startDate].push(e);
  });
  el.innerHTML = `
    <div class="week">
      ${days.map((d) => renderDayColumn(d, eventsByDay[d.date] || [])).join('')}
    </div>
  `;
}

function renderDayColumn(day, events) {
  const dateLabel = formatMonthDay(day.date);
  const body = events.length
    ? events.map(renderEvent).join('')
    : '<div class="week-empty">nothing scheduled</div>';
  return `
    <div class="week-day ${day.isToday ? 'today' : ''}">
      <div class="week-day-head">
        <div class="week-day-label">${day.label}</div>
        <div class="week-day-date">${dateLabel}</div>
      </div>
      ${body}
    </div>
  `;
}

function renderEvent(e) {
  const time = e.allDay
    ? 'all day'
    : (e.startTime || '') + (e.endTime ? `–${e.endTime}` : '');
  const title = e.link
    ? `<a href="${escapeAttr(e.link)}" target="_blank" rel="noreferrer noopener">${escapeHtml(e.title || '(untitled)')}</a>`
    : escapeHtml(e.title || '(untitled)');
  return `
    <div class="event ${e.allDay ? 'all-day' : ''}">
      <div class="event-time">${escapeHtml(time)}</div>
      <div class="event-title">${title}</div>
    </div>
  `;
}

function formatMonthDay(iso) {
  const parts = iso.split('-');
  if (parts.length !== 3) return iso;
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[Number(parts[1]) - 1]} ${Number(parts[2])}`;
}

/* ============================================================
   PRs
   ============================================================ */
function renderMyPrs() {
  renderChips('my-prs-chips', getPrChipDefs(filters.myPrs), () => {
    saveFilters();
    renderMyPrs();
  });
  const el = document.getElementById('my-prs-list');
  const visible = (data.prs.mine || []).filter((pr) => prMatchesFilter(pr, filters.myPrs));
  updateCount('my-prs-count', visible.length);
  if (!visible.length) {
    el.innerHTML = '<div class="row-empty">nothing matches.</div>';
    return;
  }
  el.innerHTML = visible.map((pr) => renderPrTile(pr, false, 'pr')).join('');
  attachPrHandlers(el);
}

function renderReviews() {
  renderChips('reviews-chips', getPrChipDefs(filters.reviews), () => {
    saveFilters();
    renderReviews();
  });
  const el = document.getElementById('reviews-list');
  const visible = (data.prs.reviewRequests || []).filter((pr) => prMatchesFilter(pr, filters.reviews));
  updateCount('reviews-count', visible.length);
  if (!visible.length) {
    el.innerHTML = '<div class="row-empty">nothing matches.</div>';
    return;
  }
  el.innerHTML = visible.map((pr) => renderPrTile(pr, true, 'review')).join('');
  attachPrHandlers(el);
}

function renderPrTile(pr, showAuthor, kind) {
  const [owner, repo] = (pr.repo || '').split('/');
  const checks = pr.checks || {};
  const checkPill = checks.status && checks.status !== 'none'
    ? `<span class="pill ${checkClass(checks.status)}">${checks.status}${checks.total ? ` ${checks.passing}/${checks.total}` : ''}</span>`
    : '';
  const reviewPill = pr.reviewDecision
    ? `<span class="pill ${reviewClass(pr.reviewDecision)}">${escapeHtml(pr.reviewDecision.toLowerCase().replace(/_/g, ' '))}</span>`
    : '';
  const draftPill = pr.isDraft ? '<span class="pill">draft</span>' : '';
  const mergePill = pr.mergeable === 'CONFLICTING' ? '<span class="pill bad">conflicts</span>' : '';
  const subtitle = showAuthor && pr.author
    ? `by ${escapeHtml(pr.author)}`
    : escapeHtml(pr.repo || '');
  return `
    <div class="tile" data-kind="${kind}">
      <div class="tile-head">
        <span class="tile-tag">${kind === 'review' ? 'review' : 'pr'}</span>
        <span class="tile-id">${escapeHtml(pr.repo)}#${pr.number}</span>
      </div>
      <div class="tile-title"><a href="${escapeAttr(pr.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(pr.title)}</a></div>
      <div class="tile-meta">${draftPill}${checkPill}${reviewPill}${mergePill}</div>
      <div class="tile-foot">
        <span class="tile-sub">${subtitle}</span>
        <button class="review-btn" type="button"
          data-owner="${escapeAttr(owner)}"
          data-repo="${escapeAttr(repo)}"
          data-number="${pr.number}"
          data-title="${escapeAttr(pr.title)}"
          data-fullrepo="${escapeAttr(pr.repo)}">review</button>
      </div>
    </div>
  `;
}

function getPrChipDefs(state) {
  return [
    {
      key: 'drafts',
      label: 'hide drafts',
      count: '',
      pressed: !!state.hideDrafts,
      onToggle: () => { state.hideDrafts = !state.hideDrafts; },
    },
  ];
}

function prMatchesFilter(pr, state) {
  if (state.hideDrafts && pr.isDraft) return false;
  return true;
}

function checkClass(s) {
  if (s === 'passing') return 'good';
  if (s === 'failing') return 'bad';
  if (s === 'pending') return 'warn';
  return '';
}

function reviewClass(d) {
  if (d === 'APPROVED') return 'good';
  if (d === 'CHANGES_REQUESTED') return 'bad';
  return 'info';
}

function attachPrHandlers(root) {
  root.querySelectorAll('.review-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const b = e.currentTarget;
      startReview(b.dataset.owner, b.dataset.repo, b.dataset.number, b.dataset.title, b.dataset.fullrepo);
    });
  });
}

async function startReview(owner, repo, number, title, fullRepo) {
  openModal(
    `${fullRepo}#${number} · ${title}`,
    '<div class="review-status"><div class="spinner"></div><div>asking claude…</div></div>',
  );
  try {
    const r = await fetch(`/api/prs/${owner}/${repo}/${number}/review`, { method: 'POST' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const { jobId } = await r.json();
    pollReview(jobId);
  } catch (e) {
    setModalBody(`<p class="error">failed to start review: ${escapeHtml(e.message)}</p>`);
  }
}

async function pollReview(jobId) {
  try {
    const r = await fetch(`/api/reviews/${jobId}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const job = await r.json();
    if (job.status === 'done') {
      setModalBody(renderMarkdown(job.result || ''));
      return;
    }
    if (job.status === 'error') {
      setModalBody(`<p class="error">claude errored: ${escapeHtml(job.error || 'unknown')}</p>`);
      return;
    }
    setTimeout(() => pollReview(jobId), REVIEW_POLL_MS);
  } catch (e) {
    setModalBody(`<p class="error">poll failed: ${escapeHtml(e.message)}</p>`);
  }
}

/* ============================================================
   Modal
   ============================================================ */
function openModal(title, bodyHtml) {
  document.getElementById('modal-title').textContent = title;
  setModalBody(bodyHtml);
  document.getElementById('modal').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modal').classList.add('hidden');
}

function setModalBody(html) {
  document.getElementById('modal-body').innerHTML = html;
}

/* ============================================================
   Minimal markdown → HTML for Claude review output
   ============================================================ */
function renderMarkdown(src) {
  if (!src) return '<p class="empty">(no output)</p>';
  const codeBlocks = [];
  let text = src.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const i = codeBlocks.length;
    codeBlocks.push(`<pre><code>${code.replace(/^\n/, '')}</code></pre>`);
    return ` CODE${i} `;
  });
  text = text.replace(/^###### (.+)$/gm, '<h6>$1</h6>');
  text = text.replace(/^##### (.+)$/gm, '<h5>$1</h5>');
  text = text.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  text = text.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  text = text.replace(/(^|\n)((?:[-*] .+(?:\n|$))+)/g, (_, lead, block) => {
    const items = block.trim().split('\n').map((l) => `<li>${l.replace(/^[-*] /, '')}</li>`).join('');
    return `${lead}<ul>${items}</ul>`;
  });
  text = text.replace(/(^|\n)((?:\d+\. .+(?:\n|$))+)/g, (_, lead, block) => {
    const items = block.trim().split('\n').map((l) => `<li>${l.replace(/^\d+\. /, '')}</li>`).join('');
    return `${lead}<ol>${items}</ol>`;
  });
  text = text.split(/\n{2,}/).map((chunk) => {
    const trimmed = chunk.trim();
    if (!trimmed) return '';
    if (/^<(h\d|ul|ol|pre|p|blockquote)/.test(trimmed)) return trimmed;
    if (trimmed.startsWith(' CODE')) return trimmed;
    return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
  }).join('\n');
  text = text.replace(/ CODE(\d+) /g, (_, i) => codeBlocks[+i] || '');
  return text;
}

/* ============================================================
   Helpers
   ============================================================ */
function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

function timeAgo(d) {
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 10) return 'just now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}
