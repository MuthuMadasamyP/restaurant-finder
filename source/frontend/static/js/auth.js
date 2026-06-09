const API_BASE = `${window.location.origin}/api`;

let authMode = "signin";

const $ = (id) => document.getElementById(id);
const qsa = (selector, context = document) => Array.from(context.querySelectorAll(selector));

document.addEventListener("DOMContentLoaded", () => {
  if (localStorage.getItem("restaurantFinderAdminToken")) {
    window.location.replace("/admin/dashboard");
    return;
  }

  if (localStorage.getItem("restaurantFinderUserToken")) {
    window.location.replace("/app");
    return;
  }

  $("authForm").addEventListener("submit", handleAuthSubmit);
  $("authSwitchBtn").addEventListener("click", () => {
    setAuthMode(authMode === "signin" ? "signup" : "signin");
  });

  const loginMessage = sessionStorage.getItem("restaurantFinderLoginMessage");
  if (loginMessage) {
    sessionStorage.removeItem("restaurantFinderLoginMessage");
    showAuthAlert(`${loginMessage}. Please login again.`, "warning");
  }
});

function setAuthMode(mode) {
  authMode = mode;
  const isSignup = mode === "signup";
  $("nameGroup").hidden = !isSignup;
  $("authTitle").textContent = isSignup ? "Signup" : "Login";
  $("authSubmitBtn").textContent = isSignup ? "SIGNUP" : "LOGIN";
  $("authSwitchText").textContent = isSignup ? "Already registered?" : "New User?";
  $("authSwitchBtn").textContent = isSignup ? "Login" : "Signup";
  clearAuthAlert();
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const isSignup = authMode === "signup";
  const loginId = $("authEmail").value.trim();
  const payload = {
    email: loginId,
    password: $("authPassword").value,
  };
  if (isSignup) {
    payload.name = $("authName").value.trim();
  }

  try {
    const data = isSignup
      ? await submitAuthRequest("/auth/signup", payload)
      : await loginWithUserOrAdmin(loginId, payload.password);

    if (data.role === "admin") {
      localStorage.setItem("restaurantFinderAdminToken", data.access_token);
      localStorage.setItem("restaurantFinderAdminName", data.name);
      window.location.replace("/admin/dashboard");
      return;
    }

    localStorage.setItem("restaurantFinderUserToken", data.access_token);
    localStorage.setItem("restaurantFinderUserName", data.name);
    window.location.replace("/app");
  } catch (err) {
    showAuthAlert(err.message, "error");
  }
}

async function loginWithUserOrAdmin(loginId, password) {
  try {
    return await submitAuthRequest("/auth/login", { email: loginId, password });
  } catch (userErr) {
    try {
      return await submitAuthRequest("/admin/login", { username: loginId, password });
    } catch (adminErr) {
      throw new Error(adminErr.message || userErr.message || "Authentication failed");
    }
  }
}

async function submitAuthRequest(path, payload) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(formatAuthError(data.detail));
  return data;
}

function formatAuthError(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg || item.message || "Invalid login details")
      .join(". ");
  }
  return "Invalid username/email or password";
}

function showAuthAlert(message, type = "error") {
  const el = $("authAlert");
  el.className = `alert alert-${type} fade-in`;
  el.textContent = message;
  el.style.display = "flex";
}

function clearAuthAlert() {
  const el = $("authAlert");
  el.style.display = "none";
  el.textContent = "";
}
