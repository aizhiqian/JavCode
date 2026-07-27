import { state, $, ACTRESS_INITIALS, ACTRESS_PAGE_SIZE } from "./state.js";
import { api } from "./api.js";
import { goCatalog, showView } from "./router.js";
import { escapeAttr, escapeHtml, pageSlice, renderPager } from "./util.js";

var actressFiltersBound = false;

function actressInitialOf(a) {
  var ini = String((a && a.initial) || "").toUpperCase();
  if (ini.length === 1 && ini >= "A" && ini <= "Z") return ini;
  return "#";
}

function filteredActresses() {
  var items = state.actresses || [];
  var letter = state.actressInitial || "all";
  var q = String(state.actressPinyinQ || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "");
  return items.filter(function (a) {
    if (letter !== "all" && actressInitialOf(a) !== letter) return false;
    if (!q) return true;
    var name = String(a.name || "").toLowerCase();
    var py = String(a.pinyin || "")
      .toLowerCase()
      .replace(/\s+/g, "");
    var key = String(a.pinyin_key || "").toLowerCase();
    return (
      name.indexOf(q) !== -1 ||
      py.indexOf(q) !== -1 ||
      key.indexOf(q) !== -1
    );
  });
}

function renderActressInitialBar(available) {
  var bar = $("#actressInitialBar");
  if (!bar) return;
  var counts = available || {};
  var letters = ["all"].concat(ACTRESS_INITIALS).concat(["#"]);
  bar.innerHTML = letters
    .map(function (L) {
      var label = L === "all" ? "全部" : L;
      var n = L === "all" ? state.actresses.length : counts[L] || 0;
      var active = state.actressInitial === L ? " active" : "";
      var disabled = L !== "all" && n === 0 ? " disabled" : "";
      return (
        '<button type="button" class="initial-chip' +
        active +
        '" data-initial="' +
        L +
        '"' +
        disabled +
        ' title="' +
        (L === "all" ? "全部女优" : "拼音首字母 " + L) +
        (n ? " · " + n + " 位" : "") +
        '">' +
        label +
        (L !== "all" && n ? '<span class="initial-n">' + n + "</span>" : "") +
        "</button>"
      );
    })
    .join("");
  bar.querySelectorAll("[data-initial]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      state.actressInitial = btn.getAttribute("data-initial") || "all";
      state.actressPage = 1;
      renderActresses();
    });
  });
}

function setupActressFilters() {
  var input = $("#actressPinyinInput");
  if (!input || actressFiltersBound) return;
  actressFiltersBound = true;
  var timer = null;
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      state.actressPinyinQ = input.value || "";
      state.actressPage = 1;
      renderActresses();
    }, 160);
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      clearTimeout(timer);
      state.actressPinyinQ = input.value || "";
      state.actressPage = 1;
      renderActresses();
    }
  });
}

export function renderActresses() {
  setupActressFilters();
  var list = $("#actressList");
  var count = $("#actressCount");
  var pager = $("#actressPager");
  if (!list) return;

  var all = state.actresses || [];
  var initialCounts = {};
  all.forEach(function (a) {
    var ini = actressInitialOf(a);
    initialCounts[ini] = (initialCounts[ini] || 0) + 1;
  });
  renderActressInitialBar(initialCounts);

  if (!all.length) {
    list.innerHTML = "<p class='muted'>暂无女优数据，请先添加影片。</p>";
    if (count) count.textContent = "点击名字查看她的收藏影片";
    if (pager) {
      pager.hidden = true;
      pager.innerHTML = "";
    }
    return;
  }

  var items = filteredActresses();
  if (!items.length) {
    list.innerHTML =
      "<p class='muted'>没有匹配的女优，试试其他拼音或首字母。</p>";
    if (count) {
      count.textContent =
        "筛选结果 0 / 共 " + all.length + " 位 · 点击名字查看收藏影片";
    }
    if (pager) {
      pager.hidden = true;
      pager.innerHTML = "";
    }
    return;
  }

  var slice = pageSlice(items, state.actressPage, ACTRESS_PAGE_SIZE);
  state.actressPage = slice.page;
  if (count) {
    var filterHint = "";
    if (state.actressInitial && state.actressInitial !== "all") {
      filterHint += " · " + state.actressInitial;
    }
    if (String(state.actressPinyinQ || "").trim()) {
      filterHint += " · “" + String(state.actressPinyinQ).trim() + "”";
    }
    count.textContent =
      (filterHint ? "筛选 " + slice.total + " / 共 " + all.length : "共 " + slice.total) +
      " 位" +
      filterHint +
      " · 点击名字查看收藏影片" +
      (slice.totalPages > 1
        ? " · 第 " + slice.page + "/" + slice.totalPages + " 页"
        : "");
  }

  list.innerHTML = slice.items
    .map(function (a) {
      var py = a.pinyin ? " · " + a.pinyin : "";
      return (
        '<button type="button" class="actress-tile" role="listitem" data-actress="' +
        escapeAttr(a.name) +
        '" title="' +
        escapeAttr(a.name) +
        py +
        " · " +
        (a.film_count || 0) +
        ' 部">' +
        '<span class="actress-tile-name">' +
        escapeHtml(a.name) +
        "</span>" +
        '<span class="actress-tile-count">' +
        (a.film_count || 0) +
        " 部" +
        (a.initial && a.initial !== "#"
          ? ' · <span class="actress-tile-initial">' +
            escapeHtml(a.initial) +
            "</span>"
          : "") +
        "</span>" +
        "</button>"
      );
    })
    .join("");

  list.querySelectorAll("[data-actress]").forEach(function (el) {
    el.addEventListener("click", function () {
      goCatalog({
        q: "",
        actress: el.getAttribute("data-actress") || "",
        tag: "",
      });
    });
  });

  renderPager(pager, slice, "位", function (page) {
    state.actressPage = page;
    renderActresses();
  });
}

export function loadActresses() {
  return api("/api/actresses").then(function (data) {
    state.actresses = data.items || [];
    state.actressPage = 1;
    renderActresses();
  });
}

export function onActresses() {
  state.selectedCode = null;
  showView("actresses");
  loadActresses();
}
