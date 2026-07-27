import { state } from "./state.js";

var routeHandlers = {};

export function setRoutes(handlers) {
  routeHandlers = handlers || {};
}

export function emptyFilter() {
  return { q: "", actress: "", tag: "" };
}

export function showView(name) {
  state.view = name;
  document.querySelectorAll(".view").forEach(function (el) {
    el.classList.toggle("active", el.id === "view-" + name);
  });
  document.querySelectorAll(".nav-link").forEach(function (btn) {
    btn.classList.toggle("active", btn.getAttribute("data-view") === name);
  });
}

export function currentHash() {
  var h = window.location.hash || "";
  if (!h || h === "#") return "#/";
  if (h.charAt(1) !== "/") return "#/" + h.slice(1);
  return h;
}

export function parseRoute(hash) {
  var raw = String(hash || "#/").replace(/^#/, "");
  if (!raw || raw.charAt(0) !== "/") raw = "/" + raw;
  var qIdx = raw.indexOf("?");
  var path = qIdx >= 0 ? raw.slice(0, qIdx) : raw;
  var query = qIdx >= 0 ? raw.slice(qIdx + 1) : "";
  path = path.replace(/\/+$/, "") || "/";

  var params = {};
  if (query) {
    query.split("&").forEach(function (pair) {
      if (!pair) return;
      var kv = pair.split("=");
      var k = decodeURIComponent(kv[0] || "");
      var v = decodeURIComponent((kv[1] || "").replace(/\+/g, " "));
      if (k) params[k] = v;
    });
  }

  if (path === "/" || path === "/catalog") {
    return {
      view: "catalog",
      filter: {
        q: params.q || "",
        actress: params.actress || "",
        tag: params.tag || "",
      },
    };
  }
  if (path.indexOf("/movie/") === 0) {
    var code = decodeURIComponent(path.slice("/movie/".length));
    if (code) return { view: "detail", code: code };
  }
  if (path === "/labels") return { view: "labels" };
  if (path === "/actresses") return { view: "actresses" };
  if (path === "/add") return { view: "add" };
  if (path === "/settings") return { view: "settings" };
  return { view: "catalog", filter: emptyFilter() };
}

export function buildHash(route) {
  if (!route || !route.view) return "#/";
  if (route.view === "detail" && route.code) {
    return "#/movie/" + encodeURIComponent(route.code);
  }
  if (route.view === "catalog") {
    var f = route.filter || {};
    var parts = [];
    if (f.actress) parts.push("actress=" + encodeURIComponent(f.actress));
    else if (f.tag) parts.push("tag=" + encodeURIComponent(f.tag));
    else if (f.q) parts.push("q=" + encodeURIComponent(f.q));
    return "#/" + (parts.length ? "?" + parts.join("&") : "");
  }
  if (route.view === "labels") return "#/labels";
  if (route.view === "actresses") return "#/actresses";
  if (route.view === "add") return "#/add";
  if (route.view === "settings") return "#/settings";
  return "#/";
}

export function applyRoute(route) {
  if (!route) route = parseRoute(currentHash());
  var handler = routeHandlers[route.view];
  if (handler) {
    handler(route);
    return;
  }
  goCatalog(null, { replace: true });
}

export function navigate(route, opts) {
  opts = opts || {};
  var next = buildHash(route);
  var cur = currentHash();
  if (opts.replace) {
    if (cur !== next) {
      history.replaceState({ javcode: true }, "", next);
    }
    applyRoute(route);
    return;
  }
  if (cur === next) {
    applyRoute(route);
    return;
  }
  history.pushState({ javcode: true }, "", next);
  applyRoute(route);
}

export function goCatalog(filter, opts) {
  navigate({ view: "catalog", filter: filter || emptyFilter() }, opts);
}

export function goDetail(code, opts) {
  if (!code) return;
  navigate({ view: "detail", code: code }, opts);
}

export function setupHistory() {
  window.addEventListener("popstate", function () {
    if (!state.appReady) return;
    applyRoute(parseRoute(currentHash()));
  });
}
