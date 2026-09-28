/* ------------------------------------------------------------------
 * api.js — thin REST client + local session storage
 * ------------------------------------------------------------------ */

const Token = {
  get: () => localStorage.getItem("cet.token"),
  set: (t) => localStorage.setItem("cet.token", t),
  clear: () => localStorage.removeItem("cet.token"),
};

const Session = {
  get: () => {
    try { return JSON.parse(localStorage.getItem("cet.user") || "null"); }
    catch { return null; }
  },
  set: (u) => localStorage.setItem("cet.user", JSON.stringify(u)),
  clear: () => localStorage.removeItem("cet.user"),
};

class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function request(path, { method = "GET", body = null, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && Token.get()) headers["Authorization"] = `Bearer ${Token.get()}`;

  const response = await fetch(path, {
    method,
    headers,
    body: body === null ? undefined : JSON.stringify(body),
  });

  const text = await response.text();
  let data = null;
  if (text) { try { data = JSON.parse(text); } catch { data = { raw: text }; } }

  if (!response.ok) {
    if (response.status === 401) { Token.clear(); Session.clear(); }
    const message = (data && (data.error || data.message)) || `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  return data;
}

const Api = {
  // ---- auth ----
  register: (payload) => request("/api/register", { method: "POST", body: payload, auth: false }),
  login: (email, password) =>
    request("/api/login", { method: "POST", body: { email, password }, auth: false }),
  logout: () => request("/api/logout", { method: "POST" }),
  me: () => request("/api/me"),

  // ---- events ----
  listEvents: (params = "") => request(`/api/events${params}`, { auth: false }),
  upcoming: () => request("/api/events/upcoming", { auth: false }),
  getEvent: (id) => request(`/api/events/${id}`),
  createEvent: (payload) => request("/api/events", { method: "POST", body: payload }),
  updateEvent: (id, payload) => request(`/api/events/${id}`, { method: "PUT", body: payload }),
  deleteEvent: (id) => request(`/api/events/${id}`, { method: "DELETE" }),
  cancelEvent: (id, reason) =>
    request(`/api/events/${id}/cancel`, { method: "POST", body: { reason } }),
  invite: (id, email) =>
    request(`/api/events/${id}/invite`, { method: "POST", body: { email } }),
  invites: (id) => request(`/api/events/${id}/invites`),

  // ---- rsvp ----
  setRsvp: (id, status) =>
    request(`/api/events/${id}/rsvp`, { method: "POST", body: { status } }),
  updateRsvp: (id, status) =>
    request(`/api/events/${id}/rsvp`, { method: "PUT", body: { status } }),
  cancelRsvp: (id) => request(`/api/events/${id}/rsvp`, { method: "DELETE" }),
  myRsvps: () => request("/api/rsvps/me"),
  eventCounts: (id) => request(`/api/events/${id}/counts`),
  eventRsvps: (id) => request(`/api/events/${id}/rsvps`),

  // ---- announcements / notifications / analytics ----
  announcements: (id) => request(`/api/events/${id}/announcements`),
  postAnnouncement: (id, title, message) =>
    request(`/api/events/${id}/announcements`, { method: "POST", body: { title, message } }),
  notifications: () => request("/api/notifications"),
  readNotification: (id) => request(`/api/notifications/${id}/read`, { method: "PUT" }),
  readAllNotifications: () => request("/api/notifications/read-all", { method: "PUT" }),
  eventAnalytics: (id) => request(`/api/events/${id}/analytics`),
  overview: () => request("/api/analytics/overview"),

  // ---- health ----
  health: () => request("/api/health", { auth: false }),
};