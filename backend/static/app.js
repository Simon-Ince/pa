/* PA Command Center — vanilla JS frontend: SSE state sync, live clock +
 * countdown ticking, panel rendering. */

function fmtClock(d) {
  return d.toLocaleTimeString([], { hour12: false });
}

(function clock() {
  const el = document.getElementById("clock");
  function tick() {
    el.textContent = fmtClock(new Date());
  }
  tick();
  setInterval(tick, 1000);
})();

function timeAgo(iso) {
  if (!iso) return "never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diffMs / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

function parseIso(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

function localDateKeyFromDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function eventDateKey(ev) {
  if (!ev || !ev.start) return "";
  if (ev.all_day) return String(ev.start).slice(0, 10);
  const d = parseIso(ev.start);
  return d ? localDateKeyFromDate(d) : "";
}

function fmtEventTime(iso, allDay) {
  if (allDay) return "all day";
  const d = parseIso(iso);
  if (!d) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function fmtTimeRange(start, end, allDay) {
  if (allDay) return "all day";
  const s = fmtEventTime(start, false);
  if (!end) return s;
  const e = fmtEventTime(end, false);
  return e && e !== s ? `${s}–${e}` : s;
}

function fmtCountdown(startIso, endIso, allDay) {
  if (allDay || !startIso) return "";
  const start = parseIso(startIso);
  if (!start) return "";
  const end = parseIso(endIso);
  const now = Date.now();
  const startMs = start.getTime();
  const endMs = end ? end.getTime() : null;

  if (endMs && now >= startMs && now < endMs) {
    const mins = Math.floor((endMs - now) / 60000);
    if (mins < 1) return "ends now";
    if (mins < 60) return `ends in ${mins}m`;
    const hrs = Math.floor(mins / 60);
    const rem = mins % 60;
    return `ends in ${hrs}h ${rem}m`;
  }
  if (now >= startMs) return "";

  const mins = Math.floor((startMs - now) / 60000);
  if (mins < 60) return `starts in ${mins}m`;
  const hrs = Math.floor(mins / 60);
  const rem = mins % 60;
  return `starts in ${hrs}h ${rem}m`;
}

function eventIsInProgress(ev, nowMs) {
  if (!ev || ev.all_day || !ev.start) return false;
  const start = parseIso(ev.start);
  if (!start) return false;
  const end = parseIso(ev.end);
  const startMs = start.getTime();
  const endMs = end ? end.getTime() : null;
  if (endMs) return nowMs >= startMs && nowMs < endMs;
  return false;
}

function eventsOverlap(a, b) {
  if (!a || !b || a.all_day || b.all_day) return false;
  const aStart = parseIso(a.start);
  const bStart = parseIso(b.start);
  if (!aStart || !bStart) return false;
  const aEnd = parseIso(a.end);
  const bEnd = parseIso(b.end);
  const aEndMs = aEnd ? aEnd.getTime() : aStart.getTime();
  const bEndMs = bEnd ? bEnd.getTime() : bStart.getTime();
  return aStart.getTime() < bEndMs && bStart.getTime() < aEndMs;
}

function clusterEvents(events) {
  const allDay = [];
  const timed = [];
  for (const ev of events) {
    if (ev.all_day) allDay.push(ev);
    else timed.push(ev);
  }
  const clusters = allDay.map((e) => [e]);
  const used = new Set();
  for (let i = 0; i < timed.length; i++) {
    if (used.has(i)) continue;
    const cluster = [timed[i]];
    used.add(i);
    let changed = true;
    while (changed) {
      changed = false;
      for (let j = 0; j < timed.length; j++) {
        if (used.has(j)) continue;
        if (cluster.some((e) => eventsOverlap(e, timed[j]))) {
          cluster.push(timed[j]);
          used.add(j);
          changed = true;
        }
      }
    }
    clusters.push(cluster);
  }
  clusters.sort((a, b) => {
    const as = parseIso(a[0].start);
    const bs = parseIso(b[0].start);
    return (as ? as.getTime() : 0) - (bs ? bs.getTime() : 0);
  });
  return clusters;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

let latestState = null;

const htmlCache = new WeakMap();

function setHtml(el, html) {
  if (!el) return false;
  if (htmlCache.get(el) === html) return false;
  const top = el.scrollTop;
  el.innerHTML = html;
  htmlCache.set(el, html);
  el.scrollTop = top;
  return true;
}

function gmailHashSearchUrl(query) {
  const q = String(query || "")
    .trim()
    .replace(/[#%&]/g, " ")
    .replace(/\s+/g, "+");
  return `https://mail.google.com/mail/u/0/?fs=1#search/${q}`;
}

function renderSignalCount(gmail) {
  const countEl = document.getElementById("signal-count");
  if (gmail.status === "unavailable" || gmail.status === "error" || gmail.status === "pending" || !gmail.query) {
    setHtml(countEl, gmail.status === "pending" ? "--" : String(gmail.unread_count ?? "--"));
    return;
  }
  setHtml(
    countEl,
    `<a href="${escapeHtml(gmailHashSearchUrl(gmail.query))}" rel="opener">${String(gmail.unread_count ?? 0)}</a>`
  );
}

function renderSignal(gmail, triage) {
  const statusEl = document.getElementById("signal-status");
  const listEl = document.getElementById("signal-list");
  const footerGmail = document.getElementById("footer-gmail");
  const footerTriage = document.getElementById("footer-triage");
  footerGmail.textContent = `inbox: ${timeAgo(gmail.last_updated)}`;
  footerTriage.textContent = `triage: ${timeAgo(triage.generated_at || triage.last_updated)}`;

  renderSignalCount(gmail);

  if (gmail.status === "unavailable" || gmail.status === "error") {
    statusEl.textContent = "Gmail unavailable — " + (gmail.error || "unknown error");
    statusEl.classList.add("error");
  } else {
    statusEl.classList.remove("error");
    const windowLabel =
      gmail.count_window === "since_last_triage"
        ? "since last triage"
        : gmail.count_window === "fallback_3d"
        ? "last 3 days (fallback)"
        : "";
    statusEl.textContent =
      gmail.status === "pending" ? "loading…" : `untriaged / unread — ${windowLabel}`;
  }

  if (triage.status === "error") {
    setHtml(listEl, `<div class="empty-state">Triage snapshot error — ${escapeHtml(triage.error || "unknown error")}</div>`);
    return;
  }
  if (triage.status === "empty" || triage.status === "pending") {
    setHtml(listEl, `<div class="empty-state">No triage snapshot yet. Waiting on the 8am/1pm cron.</div>`);
    return;
  }

  const items = triage.items || [];
  const staleTag = triage.stale ? `<span class="stale-flag">STALE</span>` : "";
  const meta = `<div class="triage-meta">Generated ${triage.generated_at ? new Date(triage.generated_at).toLocaleString() : "?"} · ${items.length} flagged${staleTag}</div>`;

  if (items.length === 0) {
    setHtml(listEl, meta + `<div class="empty-state">Last run found nothing needing attention.</div>`);
    return;
  }

  setHtml(
    listEl,
    meta +
    items
      .map((it) => {
        const urgency = (it.urgency || "").toLowerCase();
        const href = typeof it.link === "string" && it.link ? it.link : "";
        const urgencyBadge = urgency
          ? `<span class="urgency-badge urgency-${escapeHtml(urgency)}">${escapeHtml(urgency)}</span>`
          : "";
        const inner = `
        <div class="triage-tags">
          <span class="triage-source">${escapeHtml(it.source || "")}</span>
          ${urgencyBadge}
        </div>
        <span class="triage-summary">${escapeHtml(it.summary || "")}</span>`;
        const cls = `triage-item urgency-${escapeHtml(urgency)}${href ? " triage-item-link" : ""}`;
        return href
          ? `<a class="${cls}" href="${escapeHtml(href)}" rel="opener">${inner}</a>`
          : `<div class="${cls}">${inner}</div>`;
      })
      .join("")
  );
}

function isOverdueTask(t, todayStr) {
  if (!t.due_date) return false;
  const d = parseIso(t.due_date);
  if (!d) return false;
  return d.getTime() < Date.now() && d.toDateString() !== todayStr;
}

function isDueTodayTask(t, todayStr) {
  if (!t.due_date) return false;
  const d = parseIso(t.due_date);
  if (!d) return false;
  return d.toDateString() === todayStr;
}

function renderTaskRow(t, overdue) {
  let due = "";
  if (t.due_date) {
    const d = parseIso(t.due_date);
    if (d) {
      due = `<span class="task-due ${overdue ? "overdue-text" : ""}">${d.toLocaleDateString([], { month: "short", day: "numeric" })}</span>`;
    }
  }
  const priority = t.priority ? `<span class="task-priority">P${t.priority}</span>` : "";
  const titleHtml = t.link
    ? `<a href="${escapeHtml(t.link)}" target="_blank" rel="noopener">${escapeHtml(t.title)}</a>`
    : escapeHtml(t.title);
  const note = t.note_link
    ? `<a class="task-note" href="${escapeHtml(t.note_link)}">note</a>`
    : "";
  return `
      <div class="task-row ${overdue ? "overdue" : ""}">
        <div class="task-title">${titleHtml}</div>
        <div class="task-meta">${escapeHtml(t.project || "")} ${due} ${priority} ${note}</div>
      </div>`;
}

function renderTasks(ticktick) {
  const statusEl = document.getElementById("tasks-status");
  const listEl = document.getElementById("tasks-list");
  const footer = document.getElementById("footer-tasks");
  footer.textContent = `tasks: ${timeAgo(ticktick.last_updated)}`;

  if (ticktick.status === "unavailable" || ticktick.status === "error") {
    statusEl.textContent = "TickTick unavailable — " + (ticktick.error || "unknown error");
    statusEl.classList.add("error");
    setHtml(listEl, "");
    return;
  }
  statusEl.classList.remove("error");
  const items = ticktick.items || [];
  const openCount = ticktick.open_count ?? items.length;
  statusEl.textContent = ticktick.status === "pending" ? "loading…" : `${openCount} open`;

  if (ticktick.status === "pending") {
    setHtml(listEl, "");
    return;
  }
  if (items.length === 0 && !(ticktick.later_count > 0)) {
    setHtml(listEl, `<div class="empty-state">No open tasks.</div>`);
    return;
  }

  const todayStr = new Date().toDateString();
  const overdue = items.filter((t) => isOverdueTask(t, todayStr));
  const today = items.filter((t) => isDueTodayTask(t, todayStr));
  const leftover = items.filter((t) => !isOverdueTask(t, todayStr) && !isDueTodayTask(t, todayStr));

  let html = "";
  if (overdue.length) {
    html += `<div class="list-group-label">Overdue</div>`;
    html += overdue.map((t) => renderTaskRow(t, true)).join("");
  }
  if (today.length) {
    html += `<div class="list-group-label">Today</div>`;
    html += today.map((t) => renderTaskRow(t, false)).join("");
  }
  if (leftover.length) {
    html += leftover.map((t) => renderTaskRow(t, false)).join("");
  }
  if (ticktick.more_count > 0) {
    html += `<div class="later-count">+${ticktick.more_count} more</div>`;
  }
  if (ticktick.later_count > 0) {
    html += `<div class="later-count">+${ticktick.later_count} later</div>`;
  }
  if (!html) {
    html = `<div class="empty-state">Nothing due today.</div>`;
    if (ticktick.later_count > 0) {
      html += `<div class="later-count">+${ticktick.later_count} later</div>`;
    }
  }
  setHtml(listEl, html);
}

const FOCUS_TAG_CLASS = { SIGNAL: "tag-signal", MEETING: "tag-meeting", TASK: "tag-task" };
const FOCUS_RANK_CLASS = ["rank-yellow", "rank-blue", "rank-red"];

function renderFocus(focus) {
  const statusEl = document.getElementById("focus-status");
  const listEl = document.getElementById("focus-list");

  if (focus.status === "error") {
    statusEl.textContent = "Focus computation error — " + (focus.error || "unknown error");
    statusEl.classList.add("error");
    setHtml(listEl, "");
    return;
  }
  statusEl.classList.remove("error");
  statusEl.textContent = focus.status === "pending" ? "computing…" : "";

  const items = focus.items || [];
  if (items.length === 0) {
    setHtml(listEl, `<div class="empty-state">Nothing urgent — clear to focus.</div>`);
    return;
  }

  setHtml(
    listEl,
    items
    .map((it, i) => {
      const tagClass = FOCUS_TAG_CLASS[it.source] || "tag-signal";
      const rankClass = FOCUS_RANK_CLASS[i % FOCUS_RANK_CLASS.length];
      const body = it.link
        ? `<a href="${escapeHtml(it.link)}" rel="opener" class="focus-text">${escapeHtml(it.text)}</a>`
        : `<span class="focus-text">${escapeHtml(it.text)}</span>`;
      return `
      <div class="focus-item">
        <span class="focus-rank ${rankClass}">${i + 1}</span>
        <span class="focus-tag ${tagClass}">${escapeHtml(it.source)}</span>
        ${body}
        ${it.detail ? `<span class="focus-detail">${escapeHtml(it.detail)}</span>` : ""}
      </div>`;
    })
    .join("")
  );
}

function renderEventCard(e, extraClass) {
  const link = e.meet_link || e.html_link;
  return `
      <div class="event-row ${extraClass || ""}" data-start="${escapeHtml(e.start || "")}" data-end="${escapeHtml(e.end || "")}" data-allday="${e.all_day}">
        <span class="event-countdown" data-countdown></span>
        <div class="event-time">${fmtTimeRange(e.start, e.end, e.all_day)}</div>
        <div class="event-title">${escapeHtml(e.title)}</div>
        <div class="event-meta">
          ${e.location ? escapeHtml(e.location) + " · " : ""}
          ${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener">${e.meet_link ? "join" : "open"}</a>` : ""}
        </div>
      </div>`;
}

function renderCluster(cluster, nowMs, highlightNow, nextEvent) {
  const inProgress = cluster.some((e) => eventIsInProgress(e, nowMs));
  const isNext = !highlightNow && nextEvent && cluster.includes(nextEvent);
  const stateClass = [inProgress ? "now" : "", isNext ? "next-up" : ""].filter(Boolean).join(" ");

  if (cluster.length === 1) {
    return renderEventCard(cluster[0], stateClass);
  }

  const lanes = cluster.map((e) => renderEventCard(e, "")).join("");
  return `
    <div class="overlap-cluster ${stateClass}">
      <span class="overlap-badge">overlap</span>
      <div class="overlap-lanes">${lanes}</div>
    </div>`;
}

function renderDaySection(label, events, nowMs, highlightNow, nextEvent) {
  if (!events.length) return "";
  const clusters = clusterEvents(events);
  const body = clusters.map((c) => renderCluster(c, nowMs, highlightNow, nextEvent)).join("");
  return `<div class="day-label">${escapeHtml(label)}</div>${body}`;
}

function renderCalendar(calendar) {
  const statusEl = document.getElementById("calendar-status");
  const listEl = document.getElementById("calendar-list");
  const footer = document.getElementById("footer-calendar");
  footer.textContent = `calendar: ${timeAgo(calendar.last_updated)}`;

  if (calendar.status === "unavailable" || calendar.status === "error") {
    statusEl.textContent = "Calendar unavailable — " + (calendar.error || "unknown error");
    statusEl.classList.add("error");
    setHtml(listEl, "");
    return;
  }
  statusEl.classList.remove("error");
  const items = calendar.items || [];
  statusEl.textContent = calendar.status === "pending" ? "loading…" : `${items.length} events through tomorrow`;

  if (!items.length) {
    setHtml(listEl, calendar.status === "pending" ? "" : `<div class="empty-state">Nothing on the calendar through tomorrow.</div>`);
    return;
  }

  const now = new Date();
  const nowMs = now.getTime();
  const todayKey = localDateKeyFromDate(now);
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowKey = localDateKeyFromDate(tomorrow);

  const todayItems = items.filter((e) => eventDateKey(e) === todayKey);
  const tomorrowItems = items.filter((e) => eventDateKey(e) === tomorrowKey);
  const otherItems = items.filter((e) => {
    const k = eventDateKey(e);
    return k !== todayKey && k !== tomorrowKey;
  });

  const anyInProgress = items.some((e) => eventIsInProgress(e, nowMs));
  const nextUpcoming = items.find((e) => {
    if (e.all_day) return false;
    const start = parseIso(e.start);
    return start && start.getTime() > nowMs;
  });

  let html = "";
  html += renderDaySection("Today", todayItems, nowMs, anyInProgress, nextUpcoming);
  html += renderDaySection("Tomorrow", tomorrowItems, nowMs, anyInProgress, nextUpcoming);
  if (otherItems.length) {
    html += renderDaySection("Later", otherItems, nowMs, anyInProgress, nextUpcoming);
  }
  setHtml(listEl, html);
  tickCountdowns();
}

function tickCountdowns() {
  document.querySelectorAll(".event-row[data-start]").forEach((row) => {
    const start = row.getAttribute("data-start");
    const end = row.getAttribute("data-end");
    const allDay = row.getAttribute("data-allday") === "true";
    const el = row.querySelector("[data-countdown]");
    if (!el) return;
    el.textContent = fmtCountdown(start, end, allDay);
  });
}

function render(state) {
  latestState = state;
  if (state.focus) renderFocus(state.focus);
  if (state.gmail) renderSignal(state.gmail, state.triage || { status: "pending" });
  if (state.calendar) renderCalendar(state.calendar);
  if (state.ticktick) renderTasks(state.ticktick);
}

function tickFooters() {
  if (!latestState) return;
  const gmail = latestState.gmail || {};
  const triage = latestState.triage || {};
  const calendar = latestState.calendar || {};
  const ticktick = latestState.ticktick || {};
  const fg = document.getElementById("footer-gmail");
  const ft = document.getElementById("footer-triage");
  const fc = document.getElementById("footer-calendar");
  const fk = document.getElementById("footer-tasks");
  if (fg) fg.textContent = `inbox: ${timeAgo(gmail.last_updated)}`;
  if (ft) ft.textContent = `triage: ${timeAgo(triage.generated_at || triage.last_updated)}`;
  if (fc) fc.textContent = `calendar: ${timeAgo(calendar.last_updated)}`;
  if (fk) fk.textContent = `tasks: ${timeAgo(ticktick.last_updated)}`;
}

setInterval(() => {
  tickCountdowns();
  tickFooters();
}, 1000);

function setConnStatus(status) {
  const dot = document.getElementById("conn-dot");
  const label = document.getElementById("conn-label");
  const flag = document.getElementById("footer-reconnect");
  dot.className = "dot " + (status === "connected" ? "green" : "amber");
  label.textContent = status === "connected" ? "connected" : "reconnecting";
  flag.classList.toggle("hidden", status === "connected");
}

function connect() {
  const es = new EventSource("/api/stream");

  es.addEventListener("open", () => setConnStatus("connected"));
  es.addEventListener("error", () => setConnStatus("reconnecting"));

  es.addEventListener("state", (evt) => {
    setConnStatus("connected");
    try {
      const data = JSON.parse(evt.data);
      render(data);
    } catch (e) {
      console.error("bad state payload", e);
    }
  });

  es.addEventListener("heartbeat", () => setConnStatus("connected"));
}

// Bootstrap from /api/state immediately so first paint doesn't wait on SSE,
// then switch to the live stream for push updates.
fetch("/api/state")
  .then((r) => r.json())
  .then(render)
  .catch(() => {})
  .finally(connect);

document.addEventListener("click", (event) => {
  const a = event.target.closest("a[href*='mail.google.com']");
  if (!a || event.button !== 0) return;
  event.preventDefault();
  const url = a.href;
  const tab = window.open("about:blank", "_blank");
  if (tab) {
    tab.location.replace(url);
  } else {
    window.location.href = url;
  }
});

const THEME_KEY = "pa-theme";

function currentTheme() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch (e) {}
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch (e) {}
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
  }
}

(function initTheme() {
  applyTheme(currentTheme());
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  });
})();
