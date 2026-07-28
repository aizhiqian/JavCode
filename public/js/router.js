import { state } from "./state.js";

var routeHandlers = {};

export function setRoutes(handlers) {
  routeHandlers = handlers || {};
}

export function emptyFilter() {
  return { q: "", actress: "", tag: "" };
}

export function normalizePage(n) {
  var p = parseInt(n, 10);
  return !p || p < 1 ? 1 : p;
}

export function normalizeFilter(f) {
  f = f || {};
  return {
    q: f.q || "",
    actress: f.actress || "",
    tag: f.tag || "",
  };
}

/** Current catalog filter mirrored from app state. */
export function currentFilter() {
  return normalizeFilter(state.filter);
}

/**
 * Build a catalog route object.
 * - patch.filter: omit to keep current filter; null/empty object for home.
 * - patch.page: omit → 1 when filter is set explicitly, else keep catalogPage.
 */
export function catalogRoute(patch) {
  patch = patch || {};
  var filter =
    patch.filter !== undefined
      ? normalizeFilter(patch.filter)
      : currentFilter();
  var page;
  if (patch.page !== undefined) {
    page = normalizePage(patch.page);
  } else if (patch.filter !== undefined) {
    page = 1;
  } else {
    page = normalizePage(state.catalogPage);
  }
  return { view: "catalog", filter: filter, page: page };
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
      page: normalizePage(params.page),
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
  return { view: "catalog", filter: emptyFilter(), page: 1 };
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
    var page = normalizePage(route.page);
    if (page > 1) parts.push("page=" + page);
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

/**
 * Go to catalog.
 * @param {object|null|undefined} filter - filter fields, or null for empty home.
 * @param {object} [opts] - { page?, replace? }. page defaults to 1 when filter
 *   is provided (including null home); use catalogRoute / current page for keep.
 */
export function goCatalog(filter, opts) {
  opts = opts || {};
  var route;
  if (opts.page !== undefined) {
    route = catalogRoute({
      filter: filter === undefined ? undefined : filter || emptyFilter(),
      page: opts.page,
    });
  } else if (filter === undefined) {
    // goCatalog() — nav home
    route = catalogRoute({ filter: emptyFilter(), page: 1 });
  } else {
    // goCatalog(filter|null) — new filter, page 1
    route = catalogRoute({ filter: filter || emptyFilter(), page: 1 });
  }
  navigate(route, opts);
}

/** Stay on current filter; change page only (pager / restore). */
export function goCatalogPage(page, opts) {
  opts = opts || {};
  navigate(catalogRoute({ page: page }), opts);
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
