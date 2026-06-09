const API_BASE = `${window.location.origin}/api`;
const REFRESH_INTERVAL_MS = 10000;
let adminToken = "";
let yearChart = null;
let activeChart = null;
let dailyUsersChart = null;
let adminRefreshTimer = null;
let currentDetailType = "users";
let currentArea = "Chennai";
let refreshInProgress = false;
let currentSettings = {
  daily_search_limit: 3,
  special_event_limit: 3,
  event_enabled: false,
  active_user_days: 30,
};

const $ = (id) => document.getElementById(id);
const qsa = (selector, context = document) => Array.from(context.querySelectorAll(selector));

document.addEventListener("DOMContentLoaded", () => {
  try {
    adminToken = localStorage.getItem("restaurantFinderAdminToken") || "";
    if (!adminToken) {
      window.location.replace("/login");
      return;
    }
    openAdminPortal();
    window.addEventListener("popstate", () => routeAdminPage({ replace: true }));
  } catch (err) {
    showAdminError(err.message || "Unable to load admin dashboard.");
  }
});

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`,
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      handleLogout();
      throw new Error("Please login again.");
    }
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

function handleLogout() {
  adminToken = "";
  localStorage.removeItem("restaurantFinderAdminToken");
  localStorage.removeItem("restaurantFinderAdminName");
  stopAdminAutoRefresh();
  window.location.replace("/login");
}

function openAdminPortal() {
  renderAdminPortal();
  bindAdminPortalEvents();
  routeAdminPage({ replace: true });
  startAdminAutoRefresh();
}

function renderAdminPortal() {
  $("adminMount").innerHTML = `
    <main id="adminApp" class="admin-shell">
      <aside class="sidebar">
        <a class="admin-brand" href="/admin">
          <span>RF</span>
          <strong>Restaurant Finder</strong>
        </a>
        <nav>
          <button class="nav-item" data-route="/admin/dashboard">Dashboard</button>
          <button class="nav-item" data-route="/admin/settings">Settings</button>
          <label class="city-select-label" for="topCities">Top cities</label>
          <select id="topCities" class="top-cities-select">
            <option value="">Select city</option>
            <option value="Chennai">Chennai</option>
            <option value="Madurai">Madurai</option>
            <option value="Coimbatore">Coimbatore</option>
          </select>
        </nav>
      </aside>

      <section class="admin-main">
        <header class="admin-topbar">
          <div>
            <p class="eyebrow">Administrator</p>
            <h1>Restaurant Finder Control Center</h1>
          </div>
          <button id="adminLogout" class="ghost-btn">Logout</button>
        </header>

        <div id="adminContent"></div>
      </section>
    </main>
  `;
}

function bindAdminPortalEvents() {
  $("adminLogout").addEventListener("click", handleLogout);
  qsa(".nav-item[data-route]").forEach((button) => {
    button.addEventListener("click", () => navigateAdmin(button.dataset.route));
  });

  $("topCities").addEventListener("change", (event) => {
    if (!event.target.value) return;
    navigateAdmin(`/admin/cities/${encodeURIComponent(event.target.value.toLowerCase())}`);
  });
}

function navigateAdmin(path) {
  if (window.location.pathname !== path) {
    window.history.pushState({}, "", path);
  }
  routeAdminPage();
}

function routeAdminPage({ replace = false } = {}) {
  const path = window.location.pathname.replace(/\/+$/, "") || "/admin";
  if (path === "/admin") {
    window.history.replaceState({}, "", "/admin/dashboard");
    return routeAdminPage({ replace: true });
  }

  if (path === "/admin/settings") {
    renderSettingsPage();
    setActiveRoute("/admin/settings");
    window.scrollTo(0, 0);
    return loadSettings().catch(showAdminError);
  }

  const cityMatch = path.match(/^\/admin\/cities\/([^/]+)$/);
  if (cityMatch) {
    const city = normalizeCity(decodeURIComponent(cityMatch[1]));
    renderAreaPage(city);
    setActiveRoute("");
    window.scrollTo(0, 0);
    return loadArea(city).catch(showAdminError);
  }

  renderDashboardPage();
  setActiveRoute("/admin/dashboard");
  window.scrollTo(0, 0);
  return loadDashboard().catch(showAdminError);
}

function setActiveRoute(route) {
  qsa(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.route === route);
  });
  if ($("topCities") && route) {
    $("topCities").value = "";
  }
}

function renderDashboardPage() {
  destroyCharts();
  $("adminContent").innerHTML = `
    <section id="dashboardPage" class="portal-section">
      <div class="summary-grid">
        <button class="summary-card" data-detail="users">
          <span>How Many Users</span>
          <strong id="totalUsers">0</strong>
        </button>
        <button class="summary-card" data-detail="feedback">
          <span>Feedback & Ratings</span>
          <strong id="totalFeedback">0</strong>
        </button>
        <button class="summary-card" data-detail="star-hotels">
          <span>Star Hotel Searches</span>
          <strong id="totalStarHotels">0</strong>
        </button>
      </div>

      <div class="analytics-grid">
        <article class="chart-panel">
          <h2>Month-wise Search Trends</h2>
          <canvas id="yearTrendChart"></canvas>
        </article>
        <article class="chart-panel">
          <h2>Daily Users</h2>
          <canvas id="dailyUsersChart"></canvas>
        </article>
        <article class="chart-panel">
          <h2>Active vs Inactive Users</h2>
          <canvas id="activeUsersChart"></canvas>
        </article>
        <article class="table-panel star-favourites-panel">
          <h2>Star Hotel Favourites</h2>
          <div class="table-wrap compact-table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>User Name</th>
                  <th>Hotel Name</th>
                  <th>Location</th>
                </tr>
              </thead>
              <tbody id="starHotelFavouritesBody"></tbody>
            </table>
          </div>
        </article>
      </div>

      <article id="dashboardDetailPanel" class="table-panel">
        <div class="table-heading">
          <h2 id="detailTitle">User Search Details</h2>
        </div>
        <div class="table-wrap">
          <table>
            <thead id="detailHead"></thead>
            <tbody id="detailBody"></tbody>
          </table>
        </div>
      </article>
    </section>
  `;

  qsa(".summary-card[data-detail]").forEach((card) => {
    card.addEventListener("click", async () => {
      try {
        await loadDetail(card.dataset.detail);
        scrollToDashboardDetail();
      } catch (err) {
        showAdminError(err.message);
      }
    });
  });
}

function renderSettingsPage() {
  destroyCharts();
  $("adminContent").innerHTML = `
    <section id="settingsPage" class="portal-section settings-layout">
      <article class="settings-panel">
        <h2>Login & Search Restrictions</h2>
        <div class="settings-metrics">
          <div>
            <span>Daily Limit</span>
            <strong id="settingsDailyMetric">0</strong>
          </div>
          <div>
            <span>Active Period</span>
            <strong id="settingsActiveMetric">0 days</strong>
          </div>
        </div>
        <form id="settingsForm" class="settings-form">
          <label for="dailyLimit">Daily Login Search Limit</label>
          <input id="dailyLimit" type="number" min="1" max="100" required />
          <label for="activeUserDays">Active User Period</label>
          <input id="activeUserDays" type="number" min="1" max="365" required />
          <button type="submit">Save Settings</button>
          <div id="settingsStatus" class="form-status" role="status" aria-live="polite"></div>
        </form>
      </article>
      <article class="table-panel settings-users-panel">
        <div class="table-heading">
          <h2>User Details</h2>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>User No</th>
                <th>Username</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="settingsUsersBody"></tbody>
          </table>
        </div>
      </article>
    </section>
  `;
  $("settingsForm").addEventListener("submit", saveSettings);
}

function renderAreaPage(area) {
  destroyCharts();
  $("adminContent").innerHTML = `
    <section id="areaPage" class="portal-section">
      <div class="area-header">
        <div>
          <p class="eyebrow">Area Analytics</p>
          <h2 id="areaTitle">${esc(area)}</h2>
        </div>
      </div>
      <div class="summary-grid">
        <article class="summary-card plain">
          <span>Total Area Users</span>
          <strong id="areaUsers">0</strong>
        </article>
        <article class="summary-card plain">
          <span>Total Search Count</span>
          <strong id="areaSearches">0</strong>
        </article>
        <article class="summary-card plain">
          <span>Star Hotel</span>
          <strong id="areaTopLocation">-</strong>
        </article>
      </div>
      <div class="area-tables">
        <article class="table-panel">
          <h2>Search Hotel</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Location</th><th>Search Count</th></tr></thead>
              <tbody id="areaLocationBody"></tbody>
            </table>
          </div>
        </article>
        <article class="table-panel">
          <h2>Most Favourite Restaurants</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Restaurant</th><th>Favourite Count</th></tr></thead>
              <tbody id="areaRestaurantBody"></tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  `;
  if ($("topCities")) $("topCities").value = area;
}

async function loadDashboard() {
  const [summary, analytics, starFavourites] = await Promise.all([
    api("/admin/summary"),
    api("/admin/analytics"),
    api("/admin/star-hotel-favourites"),
  ]);
  $("totalUsers").textContent = summary.users;
  $("totalFeedback").textContent = summary.feedback;
  $("totalStarHotels").textContent = summary.star_hotels;
  renderCharts(analytics);
  renderStarHotelFavourites(starFavourites);
  await loadDetail(currentDetailType);
}

async function loadSettings() {
  const [settings, users] = await Promise.all([api("/admin/settings"), api("/admin/users")]);
  currentSettings = settings;
  $("dailyLimit").value = settings.daily_search_limit;
  $("activeUserDays").value = settings.active_user_days;
  $("settingsDailyMetric").textContent = settings.daily_search_limit;
  $("settingsActiveMetric").textContent = `${settings.active_user_days} days`;
  renderSettingsUsers(users);
}

async function saveSettings(event) {
  event.preventDefault();
  $("settingsStatus").textContent = "";
  try {
    await api("/admin/settings", {
      method: "PUT",
      body: JSON.stringify({
        daily_search_limit: Number($("dailyLimit").value),
        special_event_limit: Number($("dailyLimit").value),
        event_enabled: false,
        active_user_days: Number($("activeUserDays").value),
      }),
    });
    $("settingsStatus").style.color = "var(--success)";
    $("settingsStatus").textContent = "Settings saved.";
  } catch (err) {
    $("settingsStatus").style.color = "var(--danger)";
    $("settingsStatus").textContent = err.message;
  }
}

function renderSettingsUsers(users) {
  const body = $("settingsUsersBody");
  if (!body) return;
  body.innerHTML = users.length
    ? users.map((user, index) => `
        <tr>
          <td>${index + 1}</td>
          <td>${esc(user.name)}</td>
          <td>
            <button class="delete-user-btn" type="button" data-user-id="${user.id}" data-user-name="${esc(user.name)}">
              Delete
            </button>
          </td>
        </tr>
      `).join("")
    : '<tr><td colspan="3">No users found.</td></tr>';

  qsa(".delete-user-btn", body).forEach((button) => {
    button.addEventListener("click", () => deleteUser(button));
  });
}

async function deleteUser(button) {
  const userId = button.dataset.userId;
  const userName = button.dataset.userName || "this user";
  if (!window.confirm(`Delete ${userName}? This removes their search history, feedback, and favourites.`)) {
    return;
  }

  button.disabled = true;
  button.textContent = "Deleting...";
  try {
    await api(`/admin/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
    await loadSettings();
  } catch (err) {
    button.disabled = false;
    button.textContent = "Delete";
    alert(err.message);
  }
}

async function loadDetail(type) {
  currentDetailType = type;
  const map = {
    users: {
      title: "User Search Details",
      path: "/admin/search-history",
      columns: ["User Name", "Search Location", "Radius", "Restaurants Requested", "Search Date & Time"],
      row: (item) => [item.user_name, item.search_location, `${item.radius} km`, item.restaurant_count, formatDate(item.searched_at)],
    },
    feedback: {
      title: "Feedback & Ratings",
      path: "/admin/feedback",
      columns: ["User Name", "Rating", "Feedback Message", "Submitted Date"],
      row: (item) => [item.user_name, item.rating, item.feedback, formatDate(item.created_at)],
    },
    "star-hotels": {
      title: "Star Hotel Searches",
      path: "/admin/star-hotels",
      columns: ["User Name", "Star Term", "Search Area", "Search Date"],
      row: (item) => [item.user_name, item.hotel_name, item.area, formatDate(item.created_at)],
    },
  };
  const config = map[type];
  const rows = await api(config.path);
  $("detailTitle").textContent = config.title;
  renderTable($("detailHead"), $("detailBody"), config.columns, rows.map(config.row));
}

async function loadArea(area) {
  currentArea = area;
  if ($("topCities")) $("topCities").value = area;

  const data = await api(`/admin/area/${encodeURIComponent(area)}`);
  $("areaTitle").textContent = data.area;
  $("areaUsers").textContent = data.total_users;
  $("areaSearches").textContent = data.total_search_count;
  $("areaTopLocation").textContent = data.star_hotel_count ?? 0;
  renderSimpleCountTable($("areaLocationBody"), data.most_searched_locations);
  renderSimpleCountTable($("areaRestaurantBody"), data.most_favourite_restaurants || []);
}

function showAdminError(message) {
  const mount = $("adminMount");
  if (!mount) return;
  mount.innerHTML = `<main class="admin-error">${esc(message)}</main>`;
}

function scrollToDashboardDetail() {
  const panel = $("dashboardDetailPanel");
  if (!panel) return;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function normalizeCity(value) {
  const city = String(value || "").toLowerCase();
  if (city === "madurai") return "Madurai";
  if (city === "coimbatore") return "Coimbatore";
  return "Chennai";
}

function startAdminAutoRefresh() {
  stopAdminAutoRefresh();
  adminRefreshTimer = window.setInterval(refreshVisibleAdminSection, REFRESH_INTERVAL_MS);
}

function stopAdminAutoRefresh() {
  if (adminRefreshTimer) {
    window.clearInterval(adminRefreshTimer);
    adminRefreshTimer = null;
  }
}

async function refreshVisibleAdminSection() {
  if (!adminToken || refreshInProgress || !$("adminApp")) return;
  refreshInProgress = true;
  try {
    const path = window.location.pathname.replace(/\/+$/, "");
    if (path === "/admin" || path === "/admin/dashboard") {
      await loadDashboard();
    } else if (path === "/admin/settings") {
      await loadSettings();
    } else if (path.startsWith("/admin/cities/")) {
      await loadArea(currentArea);
    }
  } catch (err) {
    console.error("Admin refresh failed:", err);
  } finally {
    refreshInProgress = false;
  }
}

function destroyCharts() {
  if (yearChart) {
    yearChart.destroy();
    yearChart = null;
  }
  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }
  if (dailyUsersChart) {
    dailyUsersChart.destroy();
    dailyUsersChart = null;
  }
}

function renderCharts(data) {
  const months = data.months || [];
  const monthCounts = months.map((month) => {
    const found = (data.searches_per_month || []).find((item) => item.month === month);
    return found ? found.count : 0;
  });

  if (yearChart) yearChart.destroy();
  yearChart = new Chart($("yearTrendChart"), {
    type: "line",
    data: {
      labels: months.map(formatMonthLabel),
      datasets: [
        { label: "All Searches", data: monthCounts, borderColor: "#176447", tension: 0.35 },
        { label: "Chennai", data: data.area_series.Chennai, borderColor: "#d9912b", tension: 0.35 },
        { label: "Madurai", data: data.area_series.Madurai, borderColor: "#1d6b9a", tension: 0.35 },
        { label: "Coimbatore", data: data.area_series.Coimbatore, borderColor: "#b54b35", tension: 0.35 },
      ],
    },
    options: { responsive: true, maintainAspectRatio: false },
  });

  if (activeChart) activeChart.destroy();
  if (dailyUsersChart) dailyUsersChart.destroy();

  dailyUsersChart = new Chart($("dailyUsersChart"), {
    type: "bar",
    data: {
      labels: data.daily_users.map((item) => formatShortDate(item.day)),
      datasets: [
        {
          label: "Users Created",
          data: data.daily_users.map((item) => item.count),
          backgroundColor: "#176447",
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
    },
  });

  const activeUsers = Number(data.active_users) || 0;
  const inactiveUsers = Number(data.inactive_users) || 0;
  const userTotal = activeUsers + inactiveUsers;
  activeChart = new Chart($("activeUsersChart"), {
    type: "pie",
    data: {
      labels: ["Active Users", "Inactive Users"],
      datasets: [{ data: [activeUsers, inactiveUsers], backgroundColor: ["#176447", "#d9912b"] }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            generateLabels(chart) {
              const dataset = chart.data.datasets[0];
              return chart.data.labels.map((label, index) => {
                const value = Number(dataset.data[index]) || 0;
                const pct = userTotal ? Math.round((value / userTotal) * 100) : 0;
                return {
                  text: `${label}: ${pct}%`,
                  fillStyle: dataset.backgroundColor[index],
                  strokeStyle: dataset.backgroundColor[index],
                  index,
                };
              });
            },
          },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const value = Number(context.raw) || 0;
              const pct = userTotal ? Math.round((value / userTotal) * 100) : 0;
              return `${context.label}: ${value} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

function formatShortDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
  });
}

function formatMonthLabel(value) {
  if (!value) return "-";
  return new Date(`${value}-01T00:00:00`).toLocaleDateString("en-IN", {
    month: "short",
    year: "numeric",
  });
}

function renderTable(head, body, columns, rows) {
  head.innerHTML = `<tr>${columns.map((column) => `<th>${esc(column)}</th>`).join("")}</tr>`;
  body.innerHTML = rows.length
    ? rows.map((row) => `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${columns.length}">No records found.</td></tr>`;
}

function renderSimpleCountTable(body, rows) {
  body.innerHTML = rows.length
    ? rows.map(([label, count]) => `<tr><td>${esc(label)}</td><td>${count}</td></tr>`).join("")
    : '<tr><td colspan="2">No records found.</td></tr>';
}

function renderStarHotelFavourites(rows) {
  const body = $("starHotelFavouritesBody");
  if (!body) return;
  body.innerHTML = rows.length
    ? rows.map((row) => `
        <tr>
          <td>${esc(row.user_name)}</td>
          <td>${esc(row.hotel_name)}</td>
          <td>${esc(row.location)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="3">No star hotel favourites found.</td></tr>';
}

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function esc(value) {
  return String(value ?? "-")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
