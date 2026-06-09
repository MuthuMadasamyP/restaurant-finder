const API_BASE = window.location.protocol === "file:"
  ? "http://127.0.0.1:800/api"
  : `${window.location.origin}/api`;

let currentRestaurants = [];
let currentLocation = "";
let currentRadius = 5;
let currentMaxResults = 10;
let sortState = { col: null, dir: "asc" };
let selectedFeedbackRating = 0;
let userToken = localStorage.getItem("restaurantFinderUserToken") || "";
let currentUserName = localStorage.getItem("restaurantFinderUserName") || "";

const $ = (id) => document.getElementById(id);
const qsa = (selector, context = document) => Array.from(context.querySelectorAll(selector));

document.addEventListener("DOMContentLoaded", () => {
  if (!userToken) {
    window.location.replace("/login");
    return;
  }

  syncAuthUi();
  loadSearchHistory();

  if (typeof window.initSpeechInput === "function") {
    window.initSpeechInput({
      inputId: "locationInput",
      buttonId: "speechBtn",
      statusId: "speechStatus",
      lang: "en-IN",
    });
  }

  $("searchForm").addEventListener("submit", (event) => {
    event.preventDefault();
    handleSearch();
  });

  $("exportBtn").addEventListener("click", handleExport);
  $("clearBtn").addEventListener("click", clearResults);
  $("logoutBtn").addEventListener("click", handleUserLogout);
  $("refreshHistoryBtn").addEventListener("click", loadSearchHistory);

  // Add event listener for table search
  const tableSearchInput = $("tableSearchInput");
  if (tableSearchInput) {
    ["input", "keyup", "change", "search"].forEach((eventName) => {
      tableSearchInput.addEventListener(eventName, searchShortlistedHotel);
    });
  }

  qsa(".rating-option").forEach((button) => {
    button.addEventListener("click", () => selectFeedbackRating(Number(button.dataset.rating)));
  });

  const feedbackForm = $("feedbackForm");
  if (feedbackForm) {
    feedbackForm.addEventListener("submit", handleFeedbackSubmit);
  }

  const resultsBody = $("resultsBody");
  if (resultsBody) {
    resultsBody.addEventListener("click", handleFavouriteClick);
  }
});

async function handleSearch() {
  if (!userToken) {
    window.location.replace("/login");
    return;
  }

  const location = $("locationInput").value.trim();
  const radius = Number.parseFloat($("radiusSelect").value);
  const maxResults = clampCount(Number.parseInt($("countInput").value, 10));

  if (!location) {
    showAlert("Please enter a location, for example Chennai, India.", "error");
    $("locationInput").focus();
    return;
  }

  $("countInput").value = String(maxResults);
  clearAlert();
  hidePremiumPanel();
  clearResults({ keepAlert: true });
  currentRadius = radius;
  currentMaxResults = maxResults;
  showLoading(true);
  showAlert(`Search started for Top ${maxResults}. Larger shortlists can take a few minutes.`, "warning");

  try {
    const res = await fetch(`${API_BASE}/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${userToken}`,
      },
      body: JSON.stringify({
        location,
        radius_km: radius,
        max_results: maxResults,
      }),
      signal: timeoutSignal(300000),
    });

    if (!res.ok) {
      const err = await readApiError(res);
      if (res.status === 401 || res.status === 403) {
        handleAuthFailure(err.detail);
        return;
      }
      const error = new Error(err.detail || `HTTP ${res.status}`);
      error.status = res.status;
      throw error;
    }

    const data = await res.json();

    if (!data.success || !data.restaurants?.length) {
      showAlert(
        data.message || "No restaurants found. Try a broader location or larger radius.",
        "warning"
      );
      return;
    }

    currentRestaurants = data.restaurants;
    currentLocation = data.location;
    currentRadius = data.radius_km;
    renderResults(data);
    loadSearchHistory();
    showAlert(`Found ${data.total_found} restaurants near ${data.location}.`, "success");
  } catch (err) {
    if (err.name === "TimeoutError" || err.name === "AbortError") {
      showAlert("The search timed out. Try a smaller result count or a more specific location.", "error");
    } else if (err.status === 429) {
      showAlert(err.message, "warning");
      showPremiumPanel();
    } else {
      showAlert(`Search failed: ${err.message}`, "error");
    }
    console.error("Search error:", err);
  } finally {
    showLoading(false);
  }
}

async function readApiError(res) {
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    return {
      detail: `HTTP ${res.status}: The Render server stopped or timed out during scraping. Try 5 results first; if it repeats, Render free memory is too low for Google Maps scraping.`,
    };
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
  }

  const text = await res.text().catch(() => "");
  const detail = text
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 300);

  return {
    detail: detail || `HTTP ${res.status}: Render returned a non-JSON server error.`,
  };
}

function timeoutSignal(ms) {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(ms);
  }

  const controller = new AbortController();
  window.setTimeout(() => controller.abort(), ms);
  return controller.signal;
}

function clampCount(value) {
  if (!Number.isFinite(value)) return 10;
  return Math.max(1, Math.min(value, 100));
}

function renderResults(data) {
  $("resultsTitle").textContent = `Top ${currentMaxResults} Restaurants Near ${data.location}`;
  $("resultsBadge").textContent = `${data.total_found} found`;
  $("resultsMeta").textContent = `Within ${data.radius_km} km radius`;

  const tbody = $("resultsBody");
  tbody.innerHTML = "";

  data.restaurants.forEach((restaurant, index) => {
    const tr = document.createElement("tr");
    tr.className = "fade-in";
    tr.dataset.restaurantName = restaurant.name || "";
    tr.style.animationDelay = `${Math.min(index * 28, 420)}ms`;
    tr.innerHTML = `
      <td class="rank-col">${index + 1}</td>
      <td><span class="restaurant-name">${esc(restaurant.name)}</span></td>
      <td>${ratingBadge(restaurant.rating)}</td>
      <td>${esc(restaurant.category)}</td>
      <td>${esc(restaurant.address)}</td>
      <td>${phoneLink(restaurant.phone)}</td>
      <td>${websiteLink(restaurant.website)}</td>
      <td>
        <button type="button" class="favorite-btn" data-index="${index}">
          Favourite
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  $("resultsSection").style.display = "block";
  $("exportBtn").disabled = false;
  $("resultsSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadSearchHistory() {
  if (!userToken || !$("historyCards")) return;

  try {
    const res = await fetch(`${API_BASE}/search/history`, {
      headers: {
        Authorization: `Bearer ${userToken}`,
      },
    });
    const data = await res.json().catch(() => []);
    if (res.status === 401 || res.status === 403) {
      handleAuthFailure(data.detail);
      return;
    }
    if (!res.ok) throw new Error(data.detail || "Unable to load search history");
    renderSearchHistory(data);
  } catch (err) {
    $("historyCards").innerHTML = `<article class="history-empty">${esc(err.message)}</article>`;
  }
}

function renderSearchHistory(items) {
  const container = $("historyCards");
  if (!container) return;

  if (!items.length) {
    container.innerHTML = '<article class="history-empty">No search history yet.</article>';
    return;
  }

  const groups = items.reduce((acc, item) => {
    const date = item.searched_at ? new Date(item.searched_at) : new Date();
    const key = date.toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    if (!acc.has(key)) acc.set(key, []);
    acc.get(key).push({ ...item, date });
    return acc;
  }, new Map());

  container.innerHTML = Array.from(groups.entries()).map(([day, rows], index) => `
    <details class="history-card" ${index === 0 ? "open" : ""}>
      <summary class="history-card-header">
        <span class="history-day">${esc(day)}</span>
        <span class="history-summary-meta">
          <span class="history-count">${rows.length} ${rows.length === 1 ? "search" : "searches"}</span>
          <span class="history-chevron" aria-hidden="true">v</span>
        </span>
      </summary>
      <ul class="history-list">
        ${rows.map((row) => `
          <li class="history-item">
            <button type="button" class="history-search-btn" data-history-id="${row.id}">
              <span class="history-area">${esc(row.search_area)}</span>
              <span class="history-meta">
                <span>${esc(row.radius)} km radius</span>
                <span>${formatHistoryTime(row.date)}</span>
              </span>
            </button>
            <div id="historyRestaurants-${row.id}" class="history-restaurants" hidden></div>
          </li>
        `).join("")}
      </ul>
    </details>
  `).join("");

  qsa(".history-search-btn", container).forEach((button) => {
    button.addEventListener("click", () => toggleHistoryRestaurants(button.dataset.historyId, button));
  });
}

async function toggleHistoryRestaurants(historyId, button) {
  const panel = $(`historyRestaurants-${historyId}`);
  if (!panel) return;

  if (!panel.hidden) {
    panel.hidden = true;
    button.classList.remove("is-active");
    return;
  }

  qsa(".history-restaurants").forEach((item) => {
    item.hidden = true;
  });
  qsa(".history-search-btn").forEach((item) => item.classList.remove("is-active"));

  panel.hidden = false;
  button.classList.add("is-active");

  if (panel.dataset.loaded === "true") return;
  panel.innerHTML = '<div class="history-restaurants-empty">Loading restaurants. Old history may take a few minutes first time...</div>';

  try {
    const res = await fetch(`${API_BASE}/search/history/${encodeURIComponent(historyId)}/restaurants`, {
      headers: {
        Authorization: `Bearer ${userToken}`,
      },
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) {
      handleAuthFailure(data.detail);
      return;
    }
    if (!res.ok) throw new Error(data.detail || "Unable to load saved restaurants");

    renderHistoryRestaurants(panel, data.restaurants || []);
    panel.dataset.loaded = "true";
  } catch (err) {
    panel.innerHTML = `<div class="history-restaurants-empty">${esc(err.message)}</div>`;
  }
}

function renderHistoryRestaurants(panel, restaurants) {
  if (!restaurants.length) {
    panel.innerHTML = '<div class="history-restaurants-empty">No saved restaurants for this search.</div>';
    return;
  }

  panel.innerHTML = `
    <div class="history-restaurant-list">
      ${restaurants.map((restaurant) => `
        <article class="history-restaurant">
          <div>
            <strong>${esc(restaurant.rank)}. ${esc(restaurant.name)}</strong>
            <span>${esc(restaurant.category)}</span>
            <small>${esc(restaurant.address)}</small>
          </div>
          <div class="history-restaurant-meta">
            <span>${esc(restaurant.rating || "N/A")}</span>
            <span>${esc(restaurant.phone || "-")}</span>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function formatHistoryTime(date) {
  return date.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function handleUserLogout() {
  userToken = "";
  currentUserName = "";
  localStorage.removeItem("restaurantFinderUserToken");
  localStorage.removeItem("restaurantFinderUserName");
  window.location.replace("/login");
}

function handleAuthFailure(message = "Session expired") {
  userToken = "";
  currentUserName = "";
  localStorage.removeItem("restaurantFinderUserToken");
  localStorage.removeItem("restaurantFinderUserName");
  sessionStorage.setItem("restaurantFinderLoginMessage", message || "Please login again.");
  window.location.replace("/login");
}

function syncAuthUi() {
  $("userStatus").textContent = userToken ? currentUserName : "Guest";
  $("logoutBtn").hidden = !userToken;
}

function sortTable(colName) {
  if (sortState.col === colName) {
    sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
  } else {
    sortState.col = colName;
    sortState.dir = "desc";
  }

  const dir = sortState.dir;

  currentRestaurants = [...currentRestaurants].sort((a, b) => {
    const va = Number.parseFloat(a[colName]) || 0;
    const vb = Number.parseFloat(b[colName]) || 0;
    return dir === "asc" ? va - vb : vb - va;
  });

  qsa("thead th[data-col]").forEach((th) => {
    th.classList.remove("sorted");
    th.querySelector(".sort-icon").textContent = "Sort";
  });

  const activeHeader = document.querySelector(`th[data-col="${colName}"]`);
  if (activeHeader) {
    activeHeader.classList.add("sorted");
    activeHeader.querySelector(".sort-icon").textContent = dir === "asc" ? "Asc" : "Desc";
  }

  renderResults({
    location: currentLocation,
    radius_km: currentRadius,
    total_found: currentRestaurants.length,
    restaurants: currentRestaurants,
  });
}

async function handleExport() {
  if (!currentRestaurants.length) return;

  const btn = $("exportBtn");
  btn.disabled = true;
  btn.textContent = "Generating...";

  try {
    const res = await fetch(`${API_BASE}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        restaurants: currentRestaurants,
        location: currentLocation,
      }),
    });

    if (!res.ok) throw new Error(`Export failed: HTTP ${res.status}`);

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const ts = new Date().toISOString().slice(0, 10);
    link.href = url;
    link.download = `restaurants_${currentLocation.replace(/[\s,]+/g, "_")}_${ts}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    showAlert(`Excel file downloaded for "${currentLocation}".`, "success");
  } catch (err) {
    showAlert(`Export failed: ${err.message}`, "error");
    console.error("Export error:", err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Export Excel";
  }
}

function clearResults(options = {}) {
  currentRestaurants = [];
  currentLocation = "";
  sortState = { col: null, dir: "asc" };
  $("resultsSection").style.display = "none";
  $("resultsBody").innerHTML = "";
  $("exportBtn").disabled = true;
  const tableSearchInput = $("tableSearchInput");
  if (tableSearchInput) {
    tableSearchInput.value = "";
  }
  hideShortlistSearchAlert();
  if (!options.keepAlert) clearAlert();
}

function searchShortlistedHotel() {
  const input = $("tableSearchInput");
  const searchTerm = input ? input.value.toLowerCase().trim() : "";
  const rows = qsa("#resultsBody tr");

  if (!rows.length) {
    hideShortlistSearchAlert();
    return;
  }

  if (!searchTerm) {
    rows.forEach((row) => {
      row.style.display = "";
      row.classList.remove("shortlist-match");
    });
    $("resultsBadge").textContent = `${currentRestaurants.length} found`;
    hideShortlistSearchAlert();
    clearAlert();
    return;
  }

  let matchCount = 0;

  rows.forEach((row) => {
    const restaurantName = (row.dataset.restaurantName || "").toLowerCase();
    const isMatch = restaurantName.includes(searchTerm);
    row.classList.toggle("shortlist-match", isMatch);
    row.style.display = isMatch ? "" : "none";
    if (isMatch) {
      matchCount += 1;
    }
  });

  if (matchCount > 0) {
    $("resultsBadge").textContent = `${matchCount} shortlisted`;
    const hotelLabel = matchCount === 1 ? "hotel" : "hotels";
    showShortlistSearchAlert(`${matchCount} matching ${hotelLabel} found in shortlist.`, "success");
    clearAlert();
  } else {
    $("resultsBadge").textContent = "0 shortlisted";
    showShortlistSearchAlert("Hotel not found in this shortlist.", "error");
    showAlert("Hotel not found in this shortlist.", "error");
  }
}

function showShortlistSearchAlert(message, type = "error") {
  const el = $("shortlistSearchAlert");
  if (!el) return;
  el.className = `shortlist-search-alert shortlist-search-alert-${type}`;
  el.textContent = message;
  el.style.display = "inline-flex";
}

function hideShortlistSearchAlert() {
  const el = $("shortlistSearchAlert");
  if (!el) return;
  el.style.display = "none";
  el.textContent = "";
}

function selectFeedbackRating(rating) {
  selectedFeedbackRating = rating;
  $("feedbackRating").value = String(rating);

  qsa(".rating-option").forEach((button) => {
    const buttonRating = Number(button.dataset.rating);
    const isSelected = buttonRating <= rating;
    button.classList.toggle("is-selected", isSelected);
    button.setAttribute("aria-pressed", String(buttonRating === rating));
  });

  showFeedbackStatus(`Rated ${rating} out of 5.`, "success");
}

function handleFeedbackSubmit(event) {
  event.preventDefault();

  if (!userToken) {
    showFeedbackStatus("Please sign in before submitting feedback.", "error");
    return;
  }

  const rating = selectedFeedbackRating;
  const comment = $("feedbackComment").value.trim();

  if (!rating) {
    showFeedbackStatus("Please select a rating before submitting.", "error");
    return;
  }

  if (!comment) {
    showFeedbackStatus("Please enter your feedback message.", "error");
    $("feedbackComment").focus();
    return;
  }

  submitFeedback(rating, comment);
}

async function submitFeedback(rating, comment) {
  try {
    const res = await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${userToken}`,
      },
      body: JSON.stringify({ rating, feedback: comment }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) {
      handleAuthFailure(data.detail);
      return;
    }
    if (!res.ok) throw new Error(data.detail || "Feedback submit failed");

    $("feedbackForm").reset();
    selectedFeedbackRating = 0;
    $("feedbackRating").value = "";
    qsa(".rating-option").forEach((button) => {
      button.classList.remove("is-selected");
      button.setAttribute("aria-pressed", "false");
    });

    showFeedbackStatus("Thank you. Your feedback was submitted.", "success");
  } catch (err) {
    showFeedbackStatus(err.message, "error");
  }
}

async function handleFavouriteClick(event) {
  const button = event.target.closest(".favorite-btn");
  if (!button) return;

  if (!userToken) {
    showAlert("Please sign in before adding a favourite restaurant.", "error");
    return;
  }

  const restaurant = currentRestaurants[Number(button.dataset.index)];
  if (!restaurant) return;

  button.disabled = true;
  button.textContent = "Saving...";

  try {
    const res = await fetch(`${API_BASE}/favorite-restaurant`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${userToken}`,
      },
      body: JSON.stringify({
        restaurant_name: restaurant.name,
        search_area: currentLocation,
        rating: restaurant.rating,
        category: restaurant.category,
        address: restaurant.address,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) {
      handleAuthFailure(data.detail);
      return;
    }
    if (!res.ok) throw new Error(data.detail || "Favourite save failed");

    await saveStarHotelFavourite(restaurant);
    button.textContent = "Saved";
    button.classList.add("is-saved");
    showAlert(data.message || "Favourite restaurant saved.", "success");
  } catch (err) {
    button.disabled = false;
    button.textContent = "Favourite";
    showAlert(err.message, "error");
  }
}

async function saveStarHotelFavourite(restaurant) {
  if (!isStarHotelSearch(currentLocation)) return;

  const res = await fetch(`${API_BASE}/star-hotels`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${userToken}`,
    },
    body: JSON.stringify({
      hotel_name: restaurant.name || "Unknown hotel",
      area: currentLocation,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 || res.status === 403) {
    handleAuthFailure(data.detail);
    return;
  }
  if (!res.ok) throw new Error(data.detail || "Star hotel favourite save failed");
}

function isStarHotelSearch(value) {
  return /\b([1-7])\s*-?\s*star(?:\s+hotel|\s+hotels)?\b/i.test(value || "");
}

function showFeedbackStatus(message, type = "success") {
  const el = $("feedbackStatus");
  if (!el) return;
  el.className = `feedback-status feedback-status-${type}`;
  el.textContent = message;
}

function showLoading(show) {
  $("loadingSection").style.display = show ? "block" : "none";
  $("searchBtn").disabled = show;
  $("searchBtn").textContent = show ? "Searching..." : "Find Restaurants";
  $("loadingSub").textContent = show
    ? `Retrieving up to ${currentMaxResults} restaurants. Larger result sets can take a few minutes.`
    : "Keep this page open while the shortlist is built.";
}

function showAlert(message, type = "error") {
  const el = $("alertBox");
  el.className = `alert alert-${type} fade-in`;
  el.textContent = message;
  el.style.display = "flex";
}

function showPremiumPanel() {
  const panel = $("premiumPanel");
  if (!panel) return;
  panel.hidden = false;
}

function hidePremiumPanel() {
  const panel = $("premiumPanel");
  if (!panel) return;
  panel.hidden = true;
}

function clearAlert() {
  const el = $("alertBox");
  el.style.display = "none";
  el.textContent = "";
}

function esc(value) {
  if (!value || value === "N/A") return `<span class="na-text">-</span>`;
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function ratingBadge(rating) {
  if (!rating || rating === "N/A") {
    return `<span class="rating-badge rating-na">N/A</span>`;
  }

  const num = Number.parseFloat(rating);
  let cls = "rating-na";
  if (!Number.isNaN(num)) {
    if (num >= 4.0) cls = "rating-high";
    else if (num >= 3.0) cls = "rating-medium";
    else cls = "rating-low";
  }

  return `<span class="rating-badge ${cls}">${esc(rating)}</span>`;
}

function phoneLink(phone) {
  if (!phone || phone === "N/A") return `<span class="na-text">-</span>`;
  const clean = phone.replace(/[^\d+\-\s()]/g, "");
  return `<a href="tel:${esc(clean)}">${esc(phone)}</a>`;
}

function websiteLink(website) {
  if (!website || website === "N/A") return `<span class="na-text">-</span>`;

  const safeUrl = esc(website);
  let label = website;
  try {
    label = new URL(website).hostname.replace(/^www\./, "");
  } catch {
    label = website;
  }

  return `<a class="website-link" href="${safeUrl}" target="_blank" rel="noopener noreferrer" title="${safeUrl}">${esc(label)}</a>`;
}
