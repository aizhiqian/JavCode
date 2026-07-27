import { state, $ } from "./state.js";
import { api, onUnauthorized } from "./api.js";
import {
  applyRoute,
  buildHash,
  currentHash,
  goCatalog,
  navigate,
  parseRoute,
  setRoutes,
  setupHistory,
} from "./router.js";
import {
  refreshAuthStatus,
  setupAuthForms,
  showAppShell,
  showAuthGate,
} from "./auth.js";
import { onCatalog, setupSearch } from "./catalog.js";
import { onDetail } from "./detail.js";
import { onLabels } from "./labels.js";
import { onActresses } from "./actresses.js";
import { onAdd, setupEnrich } from "./add.js";
import { onSettings, setupSettings } from "./settings.js";
import { loadAiStatus } from "./ai-status.js";

setRoutes({
  catalog: onCatalog,
  detail: onDetail,
  labels: onLabels,
  actresses: onActresses,
  add: onAdd,
  settings: onSettings,
});

onUnauthorized(function (mode) {
  if (!state.appReady) return;
  state.auth.authenticated = false;
  showAuthGate(mode);
});

function setupNav() {
  document.querySelectorAll("[data-view]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var v = btn.getAttribute("data-view");
      if (v === "catalog") goCatalog();
      else if (v) navigate({ view: v });
    });
  });
  var logoutBtn = $("#logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", function () {
      api("/api/auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }).then(function () {
        state.auth.authenticated = false;
        showAuthGate("login");
      });
    });
  }
  var back = $("#backToCatalog");
  if (back) {
    back.addEventListener("click", function () {
      if (history.state && history.state.javcode) {
        history.back();
      } else {
        goCatalog(null, { replace: true });
      }
    });
  }
  var brand = $("#brandHome");
  if (brand) {
    brand.addEventListener("click", function () {
      goCatalog();
    });
  }
}

function enterApp() {
  state.appReady = true;
  state.auth.authenticated = true;
  showAppShell();
  loadAiStatus();
  var route = parseRoute(currentHash());
  if (!window.location.hash || window.location.hash === "#") {
    history.replaceState({ javcode: true }, "", buildHash(route));
  }
  applyRoute(route);
}

function init() {
  setupHistory();
  setupNav();
  setupSearch();
  setupEnrich();
  setupSettings();
  setupAuthForms(enterApp);
  refreshAuthStatus()
    .then(function (auth) {
      if (!auth.configured) {
        showAuthGate("setup");
        return;
      }
      if (!auth.authenticated) {
        var loginUser = $("#loginUsername");
        if (loginUser && auth.username) loginUser.value = auth.username;
        showAuthGate("login");
        return;
      }
      enterApp();
    })
    .catch(function () {
      showAuthGate("login");
    });
}

init();
