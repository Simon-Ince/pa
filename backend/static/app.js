/* PA Command Center — vanilla JS frontend: ambient dust/wireframe canvas,
 * SSE state sync, live clock + countdown ticking, panel rendering. */

(function ambientScene() {
  const canvas = document.getElementById("bg-canvas");
  const ctx = canvas.getContext("2d");
  let motes = [];
  let facets = [];

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const count = Math.floor((canvas.width * canvas.height) / 16000);
    motes = Array.from({ length: count }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      r: Math.random() * 1.1 + 0.3,
      speed: Math.random() * 0.06 + 0.01,
      drift: (Math.random() - 0.5) * 0.05,
      twinkle: Math.random() * Math.PI * 2,
    }));
    facets = Array.from({ length: 3 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      size: Math.random() * 70 + 60,
      angle: Math.random() * Math.PI * 2,
      spin: (Math.random() - 0.5) * 0.0006,
    }));
  }

  function drawFacet(f) {
    ctx.save();
    ctx.translate(f.x, f.y);
    ctx.rotate(f.angle);
    ctx.strokeStyle = "rgba(124, 141, 153, 0.14)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    const sides = 3;
    for (let i = 0; i <= sides; i++) {
      const a = (i / sides) * Math.PI * 2;
      const px = Math.cos(a) * f.size;
      const py = Math.sin(a) * f.size * 0.8;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
    ctx.restore();
  }

  function frame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const f of facets) {
      f.angle += f.spin;
      drawFacet(f);
    }

    for (const m of motes) {
      m.twinkle += 0.015;
      const alpha = 0.15 + Math.abs(Math.sin(m.twinkle)) * 0.25;
      ctx.beginPath();
      ctx.fillStyle = `rgba(159, 178, 186, ${alpha})`;
      ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
      ctx.fill();
      m.y += m.speed;
      m.x += m.drift;
      if (m.y > canvas.height) {
        m.y = 0;
        m.x = Math.random() * canvas.width;
      }
    }
    requestAnimationFrame(frame);
  }

  window.addEventListener("resize", resize);
  resize();
  frame();
})();

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

function fmtEventTime(iso, allDay) {
  if (allDay) return "all day";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function fmtCountdown(iso) {
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0 && diffMs > -60 * 60 * 1000) return "now";
  if (diffMs <= 0) return "";
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `starts in ${mins}m`;
  const hrs = Math.floor(mins / 60);
  const rem = mins % 60;
  return `starts in ${hrs}h ${rem}m`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

let latestState = null;

function renderSignal(gmail, triage) {
  const statusEl = document.getElementById("signal-status");
  const countEl = document.getElementById("signal-count");
  const listEl = document.getElementById("signal-list");
  const footerGmail = document.getElementById("footer-gmail");
  const footerTriage = document.getElementById("footer-triage");
  footerGmail.textContent = `inbox: ${timeAgo(gmail.last_updated)}`;
  footerTriage.textContent = `triage: ${timeAgo(triage.last_updated)}`;

  if (gmail.status === "unavailable" || gmail.status === "error") {
    statusEl.textContent = "Gmail unavailable — " + (gmail.error || "unknown error");
    statusEl.classList.add("error");
    countEl.textContent = "--";
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
    if (gmail.status === "pending" || !gmail.query) {
      countEl.textContent = gmail.status === "pending" ? "--" : String(gmail.unread_count ?? 0);
    } else {
      const encodedQuery = encodeURIComponent(gmail.query).replace(/%20/g, "+");
      const gmailUrl = `https://mail.google.com/mail/u/0/#search/${encodedQuery}`;
      countEl.innerHTML = `<a href="${escapeHtml(gmailUrl)}" target="_blank" rel="noopener">${String(gmail.unread_count ?? 0)}</a>`;
    }
  }

  if (triage.status === "error") {
    listEl.innerHTML = `<div class="empty-state">Triage snapshot error — ${escapeHtml(triage.error || "unknown error")}</div>`;
    return;
  }
  if (triage.status === "empty" || triage.status === "pending") {
    listEl.innerHTML = `<div class="empty-state">No triage snapshot yet. Waiting on the 8am/1pm cron.</div>`;
    return;
  }

  const items = triage.items || [];
  const staleTag = triage.stale
    ? `<span class="stale-flag">STALE</span>`
    : "";
  const meta = `<div class="triage-meta">Generated ${triage.generated_at ? new Date(triage.generated_at).toLocaleString() : "?"} · ${items.length} flagged${staleTag}</div>`;

  if (items.length === 0) {
    listEl.innerHTML = meta + `<div class="empty-state">Last run found nothing needing attention.</div>`;
    return;
  }

  listEl.innerHTML =
    meta +
    items
      .map((it) => {
        const urgency = (it.urgency || "").toLowerCase();
        const body = it.link
          ? `<a href="${escapeHtml(it.link)}" target="_blank" rel="noopener">${escapeHtml(it.summary || "")}</a>`
          : escapeHtml(it.summary || "");
        return `
      <div class="triage-item urgency-${escapeHtml(urgency)}">
        <div class="triage-source">${escapeHtml(it.source || "")}${urgency ? " · " + escapeHtml(urgency) : ""}</div>
        ${body}
      </div>`;
      })
      .join("");
}

function renderTasks(ticktick) {
  const statusEl = document.getElementById("tasks-status");
  const listEl = document.getElementById("tasks-list");
  const footer = document.getElementById("footer-tasks");
  footer.textContent = `tasks: ${timeAgo(ticktick.last_updated)}`;

  if (ticktick.status === "unavailable" || ticktick.status === "error") {
    statusEl.textContent = "TickTick unavailable — " + (ticktick.error || "unknown error");
    statusEl.classList.add("error");
    listEl.innerHTML = "";
    return;
  }
  statusEl.classList.remove("error");
  statusEl.textContent = ticktick.status === "pending" ? "loading…" : `${ticktick.items.length} open`;

  if (!ticktick.items || ticktick.items.length === 0) {
    listEl.innerHTML = ticktick.status === "pending" ? "" : `<div class="empty-state">No open tasks.</div>`;
    return;
  }

  const todayStr = new Date().toDateString();
  listEl.innerHTML = ticktick.items
    .map((t) => {
      let due = "";
      let overdueClass = "";
      if (t.due_date) {
        const d = new Date(t.due_date);
        const isOverdue = d.getTime() < Date.now() && d.toDateString() !== todayStr;
        overdueClass = isOverdue ? "overdue" : "";
        due = `<span class="task-due ${isOverdue ? "overdue-text" : ""}">${d.toLocaleDateString([], { month: "short", day: "numeric" })}</span>`;
      }
      const priority = t.priority ? `<span class="task-priority">P${t.priority}</span>` : "";
      const titleHtml = t.link
        ? `<a href="${escapeHtml(t.link)}" target="_blank" rel="noopener">${escapeHtml(t.title)}</a>`
        : escapeHtml(t.title);
      return `
      <div class="task-row ${overdueClass}">
        <div class="task-title">${titleHtml}</div>
        <div class="task-meta">${escapeHtml(t.project || "")} ${due} ${priority}</div>
      </div>`;
    })
    .join("");
}

const FOCUS_TAG_CLASS = { SIGNAL: "tag-signal", MEETING: "tag-meeting", TASK: "tag-task", NOTES: "tag-notes" };

function renderFocus(focus) {
  const statusEl = document.getElementById("focus-status");
  const listEl = document.getElementById("focus-list");

  if (focus.status === "error") {
    statusEl.textContent = "Focus computation error — " + (focus.error || "unknown error");
    statusEl.classList.add("error");
    listEl.innerHTML = "";
    return;
  }
  statusEl.classList.remove("error");
  statusEl.textContent = focus.status === "pending" ? "computing…" : "";

  const items = focus.items || [];
  if (items.length === 0) {
    listEl.innerHTML = `<div class="empty-state">Nothing urgent — clear to focus.</div>`;
    return;
  }

  listEl.innerHTML = items
    .map((it) => {
      const tagClass = FOCUS_TAG_CLASS[it.source] || "tag-signal";
      const body = it.link
        ? `<a href="${escapeHtml(it.link)}" target="_blank" rel="noopener" class="focus-text">${escapeHtml(it.text)}</a>`
        : `<span class="focus-text">${escapeHtml(it.text)}</span>`;
      return `
      <div class="focus-item">
        <span class="focus-tag ${tagClass}">${escapeHtml(it.source)}</span>
        ${body}
        ${it.detail ? `<span class="focus-detail">${escapeHtml(it.detail)}</span>` : ""}
      </div>`;
    })
    .join("");
}

function renderCalendar(calendar) {
  const statusEl = document.getElementById("calendar-status");
  const listEl = document.getElementById("calendar-list");
  const footer = document.getElementById("footer-calendar");
  footer.textContent = `calendar: ${timeAgo(calendar.last_updated)}`;

  if (calendar.status === "unavailable" || calendar.status === "error") {
    statusEl.textContent = "Calendar unavailable — " + (calendar.error || "unknown error");
    statusEl.classList.add("error");
    listEl.innerHTML = "";
    return;
  }
  statusEl.classList.remove("error");
  statusEl.textContent = calendar.status === "pending" ? "loading…" : `${calendar.items.length} events through tomorrow`;

  if (!calendar.items || calendar.items.length === 0) {
    listEl.innerHTML = calendar.status === "pending" ? "" : `<div class="empty-state">Nothing on the calendar through tomorrow.</div>`;
    return;
  }

  const now = Date.now();
  const nextIdx = calendar.items.findIndex((e) => !e.all_day && new Date(e.start).getTime() > now);

  listEl.innerHTML = calendar.items
    .map((e, i) => {
      const link = e.meet_link || e.html_link;
      return `
      <div class="event-row ${i === nextIdx ? "next-up" : ""}" data-start="${escapeHtml(e.start || "")}" data-allday="${e.all_day}">
        <span class="event-countdown" data-countdown></span>
        <div class="event-time">${fmtEventTime(e.start, e.all_day)}</div>
        <div class="event-title">${escapeHtml(e.title)}</div>
        <div class="event-meta">
          ${e.location ? escapeHtml(e.location) + " · " : ""}
          ${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener">${e.meet_link ? "join" : "open"}</a>` : ""}
        </div>
      </div>`;
    })
    .join("");
  tickCountdowns();
}

function tickCountdowns() {
  document.querySelectorAll(".event-row[data-start]").forEach((row) => {
    const start = row.getAttribute("data-start");
    const allDay = row.getAttribute("data-allday") === "true";
    const el = row.querySelector("[data-countdown]");
    if (!el) return;
    el.textContent = allDay || !start ? "" : fmtCountdown(start);
  });
}

const DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

function renderLoops(wn) {
  const statusEl = document.getElementById("loops-status");
  const listEl = document.getElementById("loops-list");
  const footer = document.getElementById("footer-loops");
  footer.textContent = `loops: ${timeAgo(wn.last_updated)}`;

  if (wn.status === "error") {
    statusEl.textContent = "Weekly note error — " + (wn.error || "unknown error");
    statusEl.classList.add("error");
    listEl.innerHTML = "";
    return;
  }
  statusEl.classList.remove("error");

  if (wn.status === "not_found") {
    statusEl.textContent = "no current-week note found";
    listEl.innerHTML = `<div class="empty-state">No Weekly Note found for week starting ${escapeHtml(wn.week_start || "")}.</div>`;
    return;
  }
  if (wn.status === "pending") {
    statusEl.textContent = "loading…";
    listEl.innerHTML = "";
    return;
  }

  const totalOpen = DAY_ORDER.reduce((n, d) => n + ((wn.days && wn.days[d]) || []).length, 0);
  statusEl.textContent = `${wn.note_file} · ${totalOpen} open`;

  if (totalOpen === 0) {
    listEl.innerHTML = `<div class="empty-state">No open items this week. Clean slate.</div>`;
    return;
  }

  listEl.innerHTML = DAY_ORDER.map((day) => {
    const items = (wn.days && wn.days[day]) || [];
    if (items.length === 0) return "";
    return `
      <div class="day-group">
        <div class="day-heading">${day}</div>
        ${items.map((it) => `<div class="loop-item"><span class="loop-checkbox">[ ]</span><span>${escapeHtml(it)}</span></div>`).join("")}
      </div>`;
  }).join("");
}

function render(state) {
  latestState = state;
  if (state.focus) renderFocus(state.focus);
  if (state.gmail) renderSignal(state.gmail, state.triage || { status: "pending" });
  if (state.calendar) renderCalendar(state.calendar);
  if (state.ticktick) renderTasks(state.ticktick);
  if (state.weekly_notes) renderLoops(state.weekly_notes);
}

setInterval(tickCountdowns, 1000);

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
