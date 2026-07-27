import { state, $ } from "./state.js";
import { api } from "./api.js";

export function showAuthGate(mode) {
  var gate = $("#authGate");
  var shell = $("#appShell");
  if (gate) gate.classList.remove("hidden");
  if (shell) shell.classList.add("hidden");
  var setup = $("#authSetup");
  var login = $("#authLogin");
  if (setup) setup.classList.toggle("hidden", mode !== "setup");
  if (login) login.classList.toggle("hidden", mode !== "login");
}

export function showAppShell() {
  var gate = $("#authGate");
  var shell = $("#appShell");
  if (gate) gate.classList.add("hidden");
  if (shell) shell.classList.remove("hidden");
}

export function refreshAuthStatus() {
  return api("/api/auth/status").then(function (data) {
    state.auth = {
      configured: !!(data && data.configured),
      authenticated: !!(data && data.authenticated),
      username: (data && (data.session_user || data.username)) || "",
    };
    return state.auth;
  });
}

export function setupAuthForms(enterApp) {
  var setupForm = $("#setupForm");
  if (setupForm) {
    setupForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var err = $("#setupError");
      var u = ($("#setupUsername") && $("#setupUsername").value) || "";
      var p = ($("#setupPassword") && $("#setupPassword").value) || "";
      var p2 = ($("#setupPassword2") && $("#setupPassword2").value) || "";
      if (p !== p2) {
        if (err) {
          err.hidden = false;
          err.textContent = "两次密码不一致";
        }
        return;
      }
      api("/api/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p }),
      }).then(function (data) {
        if (data.ok) {
          if (err) err.hidden = true;
          enterApp();
        } else if (err) {
          err.hidden = false;
          err.textContent = data.error || "初始化失败";
        }
      });
    });
  }
  var loginForm = $("#loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var err = $("#loginError");
      var u = ($("#loginUsername") && $("#loginUsername").value) || "";
      var p = ($("#loginPassword") && $("#loginPassword").value) || "";
      api("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p }),
      }).then(function (data) {
        if (data.ok) {
          if (err) err.hidden = true;
          enterApp();
        } else if (err) {
          err.hidden = false;
          err.textContent = data.error || "登录失败";
        }
      });
    });
  }
}
