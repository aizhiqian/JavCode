import { state, $, ACTRESS_PAGE_SIZE } from "./state.js";
import { api } from "./api.js";
import { goCatalog, showView } from "./router.js";
import { escapeAttr, escapeHtml, pageSlice, renderPager } from "./util.js";
import {
  bindSearchInput,
  countInitials,
  filterByPinyin,
  filterHintText,
  renderInitialBar,
} from "./pinyin-filter.js";

var actressSearchBound = false;

function setupActressFilters() {
  if (actressSearchBound) return;
  actressSearchBound = true;
  bindSearchInput($("#actressPinyinInput"), {
    onChange: function (value) {
      state.actressPinyinQ = value;
      state.actressPage = 1;
      renderActresses();
    },
  });
}

export function renderActresses() {
  var list = $("#actressList");
  var count = $("#actressCount");
  var pager = $("#actressPager");
  if (!list) return;

  var all = state.actresses || [];
  renderInitialBar($("#actressInitialBar"), {
    selected: state.actressInitial,
    counts: countInitials(all),
    total: all.length,
    unit: "位",
    allTitle: "全部女优",
    onSelect: function (letter) {
      state.actressInitial = letter;
      state.actressPage = 1;
      renderActresses();
    },
  });

  if (!all.length) {
    list.innerHTML = "<p class='muted'>暂无女优数据，请先添加影片。</p>";
    if (count) count.textContent = "点击名字查看她的收藏影片";
    if (pager) {
      pager.hidden = true;
      pager.innerHTML = "";
    }
    return;
  }

  var items = filterByPinyin(all, {
    letter: state.actressInitial,
    query: state.actressPinyinQ,
  });
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
    var hint = filterHintText(state.actressInitial, state.actressPinyinQ);
    count.textContent =
      (hint ? "筛选 " + slice.total + " / 共 " + all.length : "共 " + slice.total) +
      " 位" +
      hint +
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
  setupActressFilters();
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
