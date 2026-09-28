/* ------------------------------------------------------------------
 * app.js — hash router, navigation, session bootstrap
 * ------------------------------------------------------------------ */

const ROUTES = [
  { pattern: /^#\/login$/,          view: () => Views.login(),        public: true },
  { pattern: /^#\/register$/,       view: () => Views.register(),     public: true },
  { pattern: /^#\/events$/,         view: () => Views.events(),       public: false },
  { pattern: /^#\/events\/(\d+)$/,  view: (m) => Views.eventDetail(m[1]), public: false },
  { pattern: /^#\/dashboard$/,      view: () => Views.dashboard(),    public: false, roles: ["ORGANIZER", "ADMIN"] },
  { pattern: /^#\/dashboard\/(\d+)$/, view: (m) => Views.dashboard(m[1]), public: false, roles: ["ORGANIZER", "ADMIN"] },
  { pattern: /^#\/notifications$/,  view: () => Views.notifications(), public: false },
];

function renderNav() {
  const user = Session.get();
  const nav = document.getElementById("nav");
  const whoami = document.getElementById("whoami");

  if (!user) {
    nav.innerHTML = `<a href="#/login">Sign in</a><a href="#/register">Register</a>`;
    whoami.textContent = "guest";
    document.getElementById("notif-btn").classList.add("hidden");
    return;
  }

  const links = [`<a href="#/events">Events</a>`];
  if (user.role !== "ATTENDEE") links.push(`<a href="#/dashboard">Dashboard</a>`);
  links.push(`<a href="#/notifications">Notifications</a>`);
  links.push(`<a href="#" id="logout">Logout</a>`);
  nav.innerHTML = links.join("");
  whoami.textContent = `${user.full_name} · ${user.role}`;
  document.getElementById("notif-btn").classList.remove("hidden");

  document.getElementById("logout").onclick = async (e) => {
    e.preventDefault();
    try { await Api.logout(); } catch { /* token may already be invalid */ }
    Token.clear(); Session.clear();
    closeRealtime();
    toast("Signed out", "info");
    location.hash = "#/login";
  };
}

async function router() {
  closeRealtime();
  const hash = location.hash || "#/events";
  const user = Session.get();

  for (const route of ROUTES) {
    const match = hash.match(route.pattern);
    if (!match) continue;

    if (!route.public && !user) { location.hash = "#/login"; return; }
    if (route.roles && user && !route.roles.includes(user.role)) {
      toast("You do not have permission to view that page.", "error");
      location.hash = "#/events"; return;
    }

    const app = document.getElementById("app");
    const { html, mount } = route.view(match);
    app.innerHTML = html;
    try { await mount(); }
    catch (e) { app.innerHTML = `<div class="notice error">${esc(e.message)}</div>`; }
    renderNav();
    return;
  }

  location.hash = user ? "#/events" : "#/login";
}

window.addEventListener("hashchange", router);
window.addEventListener("DOMContentLoaded", async () => {
  // Validate any stored token before rendering protected pages.
  if (Token.get()) {
    try {
      const { user } = await Api.me();
      Session.set(user);
    } catch {
      Token.clear(); Session.clear();
    }
  }
  renderNav();
  router();
  refreshNotificationBadge();
  setInterval(refreshNotificationBadge, 30000);
});

document.getElementById("notif-btn").onclick = () => { location.hash = "#/notifications"; };