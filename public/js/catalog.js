import { state, $, CATALOG_PAGE_SIZE } from "./state.js";
import { api } from "./api.js";
import { goCatalog, goDetail, navigate, showView } from "./router.js";
import {
  coverHtml,
  escapeAttr,
  escapeHtml,
  femaleNames,
  pageSlice,
  renderPager,
} from "./util.js";

export function loadMovies() {
  var params = new URLSearchParams();
  if (state.filter.q) params.set("q", state.filter.q);
  if (state.filter.actress) params.set("actress", state.filter.actress);
  if (state.filter.tag) params.set("tag", state.filter.tag);
  var qs = params.toString();
  return api("/api/movies" + (qs ? "?" + qs : "")).then(function (data) {
    state.movies = data.items || [];
    state.catalogPage = 1;
    renderCatalog();
    return data;
  });
}

export function renderCatalog() {
  var grid = $("#catalogGrid");
  var empty = $("#catalogEmpty");
  var count = $("#catalogCount");
  var title = $("#catalogTitle");
  var pager = $("#catalogPager");
  if (!grid) return;

  var label = "全部影片";
  if (state.filter.q) label = "搜索：" + state.filter.q;
  if (state.filter.actress) label = "女优：" + state.filter.actress;
  if (state.filter.tag) label = "标签：" + state.filter.tag;
  if (title) title.textContent = label;

  if (!state.movies.length) {
    grid.innerHTML = "";
    if (pager) {
      pager.hidden = true;
      pager.innerHTML = "";
    }
    if (count) count.textContent = "0 部";
    if (empty) {
      empty.classList.remove("hidden");
      var filtered = !!(state.filter.q || state.filter.actress || state.filter.tag);
      empty.innerHTML = filtered
        ? "<h3>没有匹配的影片</h3><p>试试其他关键词，或清除筛选。</p>"
        : "<h3>资料库还是空的</h3><p>添加一个番号开始收藏。</p>" +
          '<button type="button" class="btn primary" data-view="add">添加番号</button>';
      var addBtn = empty.querySelector("[data-view='add']");
      if (addBtn) {
        addBtn.addEventListener("click", function () {
          navigate({ view: "add" });
        });
      }
    }
    return;
  }
  if (empty) empty.classList.add("hidden");

  var slice = pageSlice(state.movies, state.catalogPage, CATALOG_PAGE_SIZE);
  state.catalogPage = slice.page;
  if (count) {
    count.textContent =
      slice.total +
      " 部" +
      (slice.totalPages > 1
        ? " · 第 " + slice.page + "/" + slice.totalPages + " 页"
        : "");
  }

  grid.innerHTML = slice.items
    .map(function (m) {
      var names = femaleNames(m).join(" · ");
      return (
        '<button type="button" class="movie-card" role="listitem" data-code="' +
        escapeAttr(m.code) +
        '">' +
        '<div class="cover">' +
        coverHtml(m.cover_url, m.title) +
        "</div>" +
        '<div class="card-meta">' +
        '<div class="card-code">' +
        escapeHtml(m.code) +
        "</div>" +
        '<div class="card-title">' +
        escapeHtml(m.title || m.title_original || m.code) +
        "</div>" +
        '<div class="card-actresses">' +
        escapeHtml(names) +
        "</div>" +
        "</div>" +
        "</button>"
      );
    })
    .join("");

  grid.querySelectorAll(".movie-card").forEach(function (card) {
    card.addEventListener("click", function () {
      goDetail(card.getAttribute("data-code"));
    });
  });

  renderPager(pager, slice, "部", function (page) {
    state.catalogPage = page;
    renderCatalog();
  });
}

export function setupSearch() {
  var input = $("#searchInput");
  if (!input) return;
  var timer = null;
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      goCatalog(
        { q: input.value.trim(), actress: "", tag: "" },
        { replace: true }
      );
    }, 220);
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      clearTimeout(timer);
      goCatalog({ q: input.value.trim(), actress: "", tag: "" });
    }
  });
}

export function onCatalog(route) {
  state.filter = {
    q: (route.filter && route.filter.q) || "",
    actress: (route.filter && route.filter.actress) || "",
    tag: (route.filter && route.filter.tag) || "",
  };
  state.selectedCode = null;
  state.catalogPage = 1;
  var input = $("#searchInput");
  if (input) {
    var display =
      state.filter.q || state.filter.actress || state.filter.tag || "";
    if (input.value !== display) input.value = display;
  }
  showView("catalog");
  loadMovies();
}
