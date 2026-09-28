/* ------------------------------------------------------------------
 * views.js — page renderers (login, register, events, detail,
 *            organizer dashboard, notifications)
 * ------------------------------------------------------------------ */

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function toast(message, kind = "info") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast ${kind}`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), 3800);
}

const Views = {};

/* ------------------------- AUTH ------------------------- */
Views.login = () => ({
  html: `
    <div class="card auth-card">
      <h3>Sign in</h3>
      <p class="muted mb">Use one of the seeded demo accounts or your own.</p>
      <div id="err" class="notice error hidden"></div>
      <label>Email</label>
      <input id="email" type="email" placeholder="organizer@demo.com" value="organizer@demo.com" />
      <label>Password</label>
      <input id="password" type="password" placeholder="Password123" value="Password123" />
      <button id="submit" style="width:100%">Sign in</button>
      <p class="muted center mt">
        No account? <a href="#/register" style="color:var(--primary)">Register</a>
      </p>
    </div>`,
  mount() {
    const submit = async () => {
      const err = document.getElementById("err");
      err.classList.add("hidden");
      try {
        const { token, user } = await Api.login(
          document.getElementById("email").value,
          document.getElementById("password").value
        );
        Token.set(token); Session.set(user);
        toast(`Welcome back, ${user.full_name}!`, "success");
        location.hash = user.role === "ATTENDEE" ? "#/events" : "#/dashboard";
      } catch (e) {
        err.textContent = e.message;
        err.classList.remove("hidden");
      }
    };
    document.getElementById("submit").onclick = submit;
    document.getElementById("password").onkeydown = (e) => e.key === "Enter" && submit();
  },
});

Views.register = () => ({
  html: `
    <div class="card auth-card">
      <h3>Create account</h3>
      <div id="err" class="notice error hidden"></div>
      <label>Full name</label>
      <input id="full_name" placeholder="Ada Lovelace" />
      <label>Email</label>
      <input id="email" type="email" placeholder="ada@example.com" />
      <label>Password (min 8 chars)</label>
      <input id="password" type="password" placeholder="StrongPass123" />
      <label>Role</label>
      <select id="role">
        <option value="ATTENDEE">Attendee — RSVP to events</option>
        <option value="ORGANIZER">Organizer — create and manage events</option>
      </select>
      <button id="submit" style="width:100%">Create account</button>
      <p class="muted center mt">
        Already registered? <a href="#/login" style="color:var(--primary)">Sign in</a>
      </p>
    </div>`,
  mount() {
    document.getElementById("submit").onclick = async () => {
      const err = document.getElementById("err");
      err.classList.add("hidden");
      try {
        const payload = {
          full_name: document.getElementById("full_name").value,
          email: document.getElementById("email").value,
          password: document.getElementById("password").value,
          role: document.getElementById("role").value,
        };
        const { token, user } = await Api.register(payload);
        Token.set(token); Session.set(user);
        toast("Account created!", "success");
        location.hash = user.role === "ATTENDEE" ? "#/events" : "#/dashboard";
      } catch (e) {
        err.textContent = e.message;
        err.classList.remove("hidden");
      }
    };
  },
});

/* ------------------------- EVENTS ------------------------- */
Views.events = () => ({
  html: `
    <div class="row mb">
      <h2 style="flex:1">Discover Events</h2>
      <input id="search" placeholder="Search events…" style="max-width:280px;margin:0" />
    </div>
    <div id="list" class="grid cols-2"></div>`,
  async mount() {
    const render = async (q = "") => {
      const list = document.getElementById("list");
      list.innerHTML = `<p class="muted">Loading…</p>`;
      try {
        const { events } = await Api.listEvents(q ? `?q=${encodeURIComponent(q)}` : "");
        if (!events.length) { list.innerHTML = `<p class="muted">No events found.</p>`; return; }
        list.innerHTML = events.map(eventCard).join("");
      } catch (e) { list.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
    };
    document.getElementById("search").oninput = (e) => render(e.target.value);
    await render();
  },
});

function eventCard(ev) {
  const pct = ev.maximum_capacity ? Math.round((ev.going_count / ev.maximum_capacity) * 100) : 0;
  return `
    <div class="card event-card">
      <div class="row">
        <h3 style="flex:1">${esc(ev.event_name)}</h3>
        <span class="status-pill status-${ev.status}">${ev.status}</span>
      </div>
      <p class="muted">${esc((ev.description || "").slice(0, 140))}</p>
      <div class="meta">
        <span>📅 ${esc(ev.event_date)}</span>
        <span>⏰ ${esc(ev.start_time)}–${esc(ev.end_time)}</span>
        <span>📍 ${esc(ev.venue || "Online")}</span>
        <span>👤 ${esc(ev.organizer_name)}</span>
      </div>
      <div>
        <div class="row" style="justify-content:space-between">
          <span class="muted">${ev.going_count} / ${ev.maximum_capacity} going</span>
          <span class="muted">${pct}%</span>
        </div>
        <div class="bar"><div style="width:${Math.min(pct, 100)}%"></div></div>
      </div>
      <div class="btn-row">
        <button onclick="location.hash='#/events/${ev.event_id}'">View &amp; RSVP</button>
      </div>
    </div>`;
}

/* ------------------------- EVENT DETAIL ------------------------- */
Views.eventDetail = (eventId) => ({
  html: `<div id="detail"><p class="muted">Loading event…</p></div>`,
  async mount() {
    const container = document.getElementById("detail");
    let ev, counts, myStatus = null, announcements = [];

    async function load() {
      const [evRes, countsRes, annRes, myRes] = await Promise.all([
        Api.getEvent(eventId),
        Api.eventCounts(eventId),
        Api.announcements(eventId).catch(() => ({ announcements: [] })),
        Api.myRsvps().catch(() => ({ rsvps: [] })),
      ]);
      ev = evRes.event;
      counts = countsRes.counts;
      announcements = annRes.announcements || [];
      myStatus = (myRes.rsvps.find((r) => r.event_id === Number(eventId)) || {}).status || null;
      render();
    }

    function render() {
      const me = Session.get();
      const isOrganizer = me && ev.organizer_id === me.user_id;
      const pct = counts.capacity ? Math.round((counts.GOING / counts.capacity) * 100) : 0;

      container.innerHTML = `
        <div class="row mb">
          <h2 style="flex:1">${esc(ev.event_name)}</h2>
          <span class="status-pill status-${counts.event_status || ev.status}">
            ${counts.event_status || ev.status}
          </span>
        </div>

        <div class="grid cols-2">
          <div class="card">
            <h3>Details</h3>
            <p class="muted mb">${esc(ev.description || "No description provided.")}</p>
            <div class="meta" style="display:grid;gap:.45rem;font-size:.88rem">
              <span>📅 <b>${esc(ev.event_date)}</b></span>
              <span>⏰ <b>${esc(ev.start_time)} – ${esc(ev.end_time)}</b></span>
              <span>📍 <b>${esc(ev.venue || "Online")}</b></span>
              ${ev.online_link ? `<span>🔗 <a href="${esc(ev.online_link)}" target="_blank" rel="noopener" style="color:var(--primary)">Join link</a></span>` : ""}
              <span>👤 Organizer: <b>${esc(ev.organizer_name)}</b></span>
              ${ev.registration_deadline ? `<span>⏳ Register by <b>${esc(ev.registration_deadline)}</b></span>` : ""}
              <span>🎟️ Capacity: <b>${counts.capacity}</b></span>
            </div>
          </div>

          <div class="card">
            <h3>Live RSVP Counter <span id="conn" class="muted" style="font-size:.75rem"></span></h3>
            <div class="grid cols-3 mt">
              <div class="kpi going"><div class="value" id="c-going">${counts.GOING}</div><div class="label">Going</div></div>
              <div class="kpi maybe"><div class="value" id="c-maybe">${counts.MAYBE}</div><div class="label">Maybe</div></div>
              <div class="kpi notgoing"><div class="value" id="c-notgoing">${counts.NOT_GOING}</div><div class="label">Not Going</div></div>
            </div>
            <div class="bar mt"><div id="capbar" style="width:${Math.min(pct, 100)}%"></div></div>
            <p class="muted mt" id="cap-text">
              ${counts.GOING} of ${counts.capacity} seats filled (${pct}%) ·
              ${counts.available} available · ${counts.waitlist} waitlisted
            </p>

            ${
              me
                ? `<div class="btn-row mt">
                     <button data-status="GOING"     class="${myStatus === "GOING" ? "success" : "secondary"}">Going</button>
                     <button data-status="MAYBE"     class="${myStatus === "MAYBE" ? "success" : "secondary"}">Maybe</button>
                     <button data-status="NOT_GOING" class="${myStatus === "NOT_GOING" ? "success" : "secondary"}">Not Going</button>
                     <button id="clear-rsvp" class="secondary">Clear</button>
                   </div>
                   <p class="muted mt">Your current response: <b>${myStatus || "none"}</b></p>`
                : `<p class="notice info mt">Sign in to RSVP for this event.</p>`
            }
          </div>
        </div>

        ${
          isOrganizer
            ? `<div class="card mt">
                 <h3>Organizer tools</h3>
                 <div class="btn-row">
                   <button id="go-analytics" class="secondary">View analytics</button>
                   <button id="go-attendees" class="secondary">Attendee list</button>
                   <button id="cancel-event" class="danger">Cancel event</button>
                 </div>
               </div>`
            : ""
        }

        <div class="card mt">
          <h3>Announcements</h3>
          ${
            announcements.length
              ? announcements.map((a) => `
                  <div style="border-left:3px solid var(--primary);padding-left:.75rem;margin-bottom:.8rem">
                    <b>${esc(a.title)}</b>
                    <div class="muted" style="font-size:.78rem">${esc(a.created_at)}</div>
                    <p>${esc(a.message)}</p>
                  </div>`).join("")
              : `<p class="muted">No announcements yet.</p>`
          }
        </div>`;
      bind();
    }

    function updateCounts(newCounts, flash = true) {
      counts = newCounts;
      ["GOING", "MAYBE", "NOT_GOING"].forEach((key) => {
        const el = document.getElementById(`c-${key.toLowerCase().replace("_", "")}`);
        if (!el) return;
        if (el.textContent !== String(newCounts[key])) {
          el.textContent = newCounts[key];
          if (flash) { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
        }
      });
      const pct = newCounts.capacity ? Math.round((newCounts.GOING / newCounts.capacity) * 100) : 0;
      const bar = document.getElementById("capbar");
      const txt = document.getElementById("cap-text");
      if (bar) bar.style.width = `${Math.min(pct, 100)}%`;
      if (txt) txt.textContent =
        `${newCounts.GOING} of ${newCounts.capacity} seats filled (${pct}%) · ` +
        `${newCounts.available} available · ${newCounts.waitlist} waitlisted`;
    }

    function bind() {
      document.querySelectorAll("[data-status]").forEach((btn) => {
        btn.onclick = async () => {
          const status = btn.dataset.status;
          btn.disabled = true;
          try {
            const res = myStatus
              ? await Api.updateRsvp(eventId, status)
              : await Api.setRsvp(eventId, status);
            myStatus = res.status === "WAITLISTED" ? null : status;
            updateCounts(res.counts);
            toast(res.message || "Your RSVP has been recorded.",
                  res.waitlisted ? "info" : "success");
            render();
          } catch (e) { toast(e.message, "error"); }
          finally { btn.disabled = false; }
        };
      });

      const clear = document.getElementById("clear-rsvp");
      if (clear) clear.onclick = async () => {
        try {
          const res = await Api.cancelRsvp(eventId);
          myStatus = null; updateCounts(res.counts);
          toast("RSVP cancelled", "info"); render();
        } catch (e) { toast(e.message, "error"); }
      };

      const analyticsBtn = document.getElementById("go-analytics");
      if (analyticsBtn) analyticsBtn.onclick = () => { location.hash = `#/dashboard/${eventId}`; };

      const attendeesBtn = document.getElementById("go-attendees");
      if (attendeesBtn) attendeesBtn.onclick = showAttendees;

      const cancelBtn = document.getElementById("cancel-event");
      if (cancelBtn) cancelBtn.onclick = async () => {
        const reason = prompt("Reason for cancellation (optional):") || "";
        if (!confirm("Cancel this event? Attendees will be notified.")) return;
        try { await Api.cancelEvent(eventId, reason); toast("Event cancelled", "info"); load(); }
        catch (e) { toast(e.message, "error"); }
      };
    }

    async function showAttendees() {
      try {
        const { rsvps, waitlist } = await Api.eventRsvps(eventId);
        const rows = rsvps.map((r) =>
          `<tr><td>${esc(r.full_name)}</td><td>${esc(r.email)}</td>
               <td><span class="status-pill status-${r.status === "GOING" ? "PUBLISHED" : r.status === "MAYBE" ? "FULL" : "CANCELLED"}">${r.status}</span></td>
               <td>${esc(r.updated_at)}</td></tr>`).join("");
        const waitRows = waitlist.map((w) =>
          `<tr><td>${esc(w.full_name)}</td><td>${esc(w.email)}</td><td>${w.status}</td><td>${esc(w.joined_at)}</td></tr>`).join("");
        document.getElementById("detail").insertAdjacentHTML("beforeend", `
          <div class="card mt" id="attendee-panel">
            <h3>Attendees (${rsvps.length})</h3>
            <table><thead><tr><th>Name</th><th>Email</th><th>Status</th><th>Updated</th></tr></thead>
              <tbody>${rows || `<tr><td colspan="4" class="muted">No responses yet.</td></tr>`}</tbody></table>
            <h3 class="mt">Waitlist (${waitlist.length})</h3>
            <table><thead><tr><th>Name</th><th>Email</th><th>Status</th><th>Joined</th></tr></thead>
              <tbody>${waitRows || `<tr><td colspan="4" class="muted">Waitlist empty.</td></tr>`}</tbody></table>
          </div>`);
      } catch (e) { toast(e.message, "error"); }
    }

    await load();

    // ---- realtime subscription ----
    openRealtime(
      eventId,
      (payload) => {
        if (payload.type === "SNAPSHOT" || payload.type === "RSVP_UPDATED") {
          updateCounts(payload.counts);
        } else if (payload.type === "ANNOUNCEMENT") {
          toast(`📢 ${payload.title}`, "info");
          load();
        }
      },
      (connected) => {
        const el = document.getElementById("conn");
        if (el) el.textContent = connected ? "● live" : "○ reconnecting…";
      }
    );
  },
});

/* ------------------------- ORGANIZER DASHBOARD ------------------------- */
Views.dashboard = (focusEventId) => ({
  html: `
    <div class="row mb">
      <h2 style="flex:1">Organizer Dashboard</h2>
      <button id="new-event">+ New Event</button>
    </div>
    <div id="kpis" class="grid cols-4 mb"></div>
    <div id="chart-card" class="card mb hidden">
      <div class="row"><h3 id="chart-title" style="flex:1"></h3>
        <span id="chart-live" class="muted" style="font-size:.78rem"></span></div>
      <canvas id="chart" height="90"></canvas>
    </div>
    <div id="modal" class="hidden"></div>
    <div id="events" class="grid cols-2"></div>`,
  async mount() {
    let chart = null;

    async function refresh() {
      try {
        const { totals, events } = await Api.overview();
        document.getElementById("kpis").innerHTML = `
          ${kpi("Total Events", totals.total_events)}
          ${kpi("Published", totals.published)}
          ${kpi("Full", totals.full)}
          ${kpi("Cancelled", totals.cancelled)}
          ${kpi("Going", totals.going, "going")}
          ${kpi("Maybe", totals.maybe, "maybe")}
          ${kpi("Not Going", totals.not_going, "notgoing")}
          ${kpi("Waitlisted", totals.waitlist)}
          ${kpi("Total Responses", totals.responses)}
          ${kpi("Response Rate", totals.response_rate + "%")}
          ${kpi("Seats Filled", totals.going + "/" + totals.total_capacity)}
          ${kpi("Events Upcoming", totals.published + totals.full)}
        `;
        document.getElementById("events").innerHTML =
          events.map(organizerEventCard).join("") ||
          `<p class="muted">You have not created any events yet.</p>`;

        document.querySelectorAll("[data-manage]").forEach((btn) => {
          btn.onclick = () => focusEvent(btn.dataset.manage);
        });
        document.querySelectorAll("[data-analytics]").forEach((btn) => {
          btn.onclick = () => focusEvent(btn.dataset.analytics);
        });
      } catch (e) { toast(e.message, "error"); }
    }

    async function focusEvent(id) {
      try {
        const { analytics } = { analytics: await Api.eventAnalytics(id) };
        const a = analytics;
        document.getElementById("chart-card").classList.remove("hidden");
        document.getElementById("chart-title").textContent =
          `Live Analytics — ${a.event.event_name}`;
        document.getElementById("chart-live").textContent =
          `Response rate ${a.metrics.response_rate}% · Utilization ${a.metrics.capacity_utilization}% · Waitlist ${a.totals.waitlist}`;

        const ctx = document.getElementById("chart");
        if (chart) chart.destroy();
        chart = new Chart(ctx, {
          type: "bar",
          data: {
            labels: ["Going", "Maybe", "Not Going", "Available Seats", "Waitlist"],
            datasets: [{
              label: "RSVP Breakdown",
              data: [a.totals.going, a.totals.maybe, a.totals.not_going,
                     a.metrics.available_seats, a.totals.waitlist],
              backgroundColor: ["#22c55e", "#f59e0b", "#ef4444", "#38bdf8", "#a855f7"],
              borderRadius: 6,
            }],
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              y: { beginAtZero: true, ticks: { color: "#94a3b8" }, grid: { color: "#334155" } },
              x: { ticks: { color: "#94a3b8" }, grid: { display: false } },
            },
          },
        });

        // Subscribe to this event's live stream so the chart refreshes on every RSVP.
        openRealtime(id, () => focusEvent(id), () => {});
      } catch (e) { toast(e.message, "error"); }
    }

    document.getElementById("new-event").onclick = () => showCreateEventModal(refresh);

    await refresh();
    if (focusEventId) await focusEvent(focusEventId);
  },
});

function kpi(label, value, cls = "") {
  return `<div class="card kpi ${cls}"><div class="value">${value}</div><div class="label">${label}</div></div>`;
}

function organizerEventCard(ev) {
  const pct = ev.maximum_capacity ? Math.round((ev.going / ev.maximum_capacity) * 100) : 0;
  return `
    <div class="card event-card">
      <div class="row">
        <h3 style="flex:1">${esc(ev.event_name)}</h3>
        <span class="status-pill status-${ev.status}">${ev.status}</span>
      </div>
      <div class="meta">
        <span>📅 ${esc(ev.event_date)}</span>
        <span>🎟️ ${ev.maximum_capacity}</span>
      </div>
      <div class="row" style="justify-content:space-between">
        <span class="muted">Going ${ev.going} · Maybe ${ev.maybe} · Not going ${ev.not_going}</span>
        <span class="muted">${pct}%</span>
      </div>
      <div class="bar"><div style="width:${Math.min(pct, 100)}%"></div></div>
      <div class="btn-row">
        <button data-analytics="${ev.event_id}">Live analytics</button>
        <button data-manage="${ev.event_id}" class="secondary">Open event</button>
      </div>
    </div>`;
}

function showCreateEventModal(onCreated) {
  const modal = document.getElementById("modal");
  modal.classList.remove("hidden");
  modal.innerHTML = `
    <div class="card mt">
      <h3>Create Event</h3>
      <div id="create-err" class="notice error hidden"></div>
      <div class="grid cols-2">
        <div>
          <label>Event name *</label><input id="f-name" placeholder="Cloud Computing Workshop" />
          <label>Description</label><textarea id="f-desc" rows="3"></textarea>
          <label>Event type</label>
          <select id="f-type">
            <option>WORKSHOP</option><option>WEBINAR</option><option>CONFERENCE</option>
            <option>MEETUP</option><option>FEST</option><option>GENERAL</option>
          </select>
          <label>Venue</label><input id="f-venue" placeholder="Seminar Hall A" />
        </div>
        <div>
          <label>Date *</label><input id="f-date" type="date" />
          <label>Start time *</label><input id="f-start" type="time" value="10:00" />
          <label>End time *</label><input id="f-end" type="time" value="12:00" />
          <label>Maximum capacity *</label><input id="f-cap" type="number" min="1" value="100" />
          <label>Registration deadline</label><input id="f-deadline" type="datetime-local" />
          <label>Online link (optional)</label><input id="f-link" placeholder="https://meet.example.com/abc" />
        </div>
      </div>
      <div class="btn-row">
        <button id="f-save">Publish event</button>
        <button id="f-cancel" class="secondary">Cancel</button>
      </div>
    </div>`;

  document.getElementById("f-cancel").onclick = () => {
    modal.classList.add("hidden"); modal.innerHTML = "";
  };

  document.getElementById("f-save").onclick = async () => {
    const err = document.getElementById("create-err");
    err.classList.add("hidden");
    const payload = {
      event_name: document.getElementById("f-name").value,
      description: document.getElementById("f-desc").value,
      event_type: document.getElementById("f-type").value,
      event_date: document.getElementById("f-date").value,
      start_time: document.getElementById("f-start").value,
      end_time: document.getElementById("f-end").value,
      venue: document.getElementById("f-venue").value,
      online_link: document.getElementById("f-link").value,
      maximum_capacity: Number(document.getElementById("f-cap").value),
      registration_deadline: document.getElementById("f-deadline").value || null,
      status: "PUBLISHED",
    };
    try {
      await Api.createEvent(payload);
      toast("Event published!", "success");
      modal.classList.add("hidden"); modal.innerHTML = "";
      onCreated && onCreated();
    } catch (e) {
      err.textContent = e.message;
      err.classList.remove("hidden");
    }
  };
}

/* ------------------------- NOTIFICATIONS ------------------------- */
Views.notifications = () => ({
  html: `
    <div class="row mb">
      <h2 style="flex:1">Notifications</h2>
      <button id="read-all" class="secondary">Mark all read</button>
    </div>
    <div id="list" class="grid"></div>`,
  async mount() {
    async function load() {
      const { notifications } = await Api.notifications();
      const list = document.getElementById("list");
      list.innerHTML = notifications.length
        ? notifications.map((n) => `
            <div class="card" style="${n.read ? "opacity:.6" : "border-left:4px solid var(--primary)"}">
              <div class="row">
                <b style="flex:1">${esc(n.type.replace(/_/g, " "))}</b>
                <span class="muted" style="font-size:.75rem">${esc(n.created_at)}</span>
              </div>
              <p>${esc(n.message)}</p>
              ${n.event_name ? `<p class="muted" style="font-size:.8rem">Event: ${esc(n.event_name)}</p>` : ""}
              ${n.read ? "" : `<button class="secondary" data-read="${n.notification_id}">Mark read</button>`}
            </div>`).join("")
        : `<p class="muted">No notifications yet.</p>`;

      document.querySelectorAll("[data-read]").forEach((btn) => {
        btn.onclick = async () => {
          await Api.readNotification(btn.dataset.read);
          load(); refreshNotificationBadge();
        };
      });
    }
    document.getElementById("read-all").onclick = async () => {
      await Api.readAllNotifications(); load(); refreshNotificationBadge();
    };
    await load();
  },
});

/* ------------------------- helpers ------------------------- */
async function refreshNotificationBadge() {
  if (!Token.get()) return;
  try {
    const { unread } = await Api.notifications();
    const badge = document.getElementById("notif-badge");
    badge.textContent = unread;
    badge.classList.toggle("hidden", unread === 0);
  } catch { /* ignore */ }
}