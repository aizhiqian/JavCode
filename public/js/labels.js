import { state, $ } from "./state.js";
import { goCatalog, showView } from "./router.js";
import { escapeAttr, escapeHtml } from "./util.js";
import {
  bindSearchInput,
  countInitials,
  filterByPinyin,
  filterHintText,
  renderInitialBar,
} from "./pinyin-filter.js";
import { loadLibraryLabels } from "./label-library.js";

var labelSearchBound = false;

function setupLabelFilters() {
  if (labelSearchBound) return;
  labelSearchBound = true;
  bindSearchInput($("#labelPinyinInput"), {
    onChange: function (value) {
      state.labelPinyinQ = value;
      renderLabels();
    },
  });
}

function renderLabelCloud(container, emptyEl, items, emptyText) {
  if (!container) return;
  if (!items || !items.length) {
    container.innerHTML = "";
    if (emptyEl) {
      emptyEl.textContent = emptyText || "暂无";
      emptyEl.classList.remove("hidden");
    }
    return;
  }
  if (emptyEl) emptyEl.classList.add("hidden");
  container.innerHTML = items
    .map(function (item) {
      var py = item.pinyin ? " · " + item.pinyin : "";
      return (
        '<button type="button" class="tag" data-tag="' +
        escapeAttr(item.name) +
        '" title="' +
        escapeAttr(item.name) +
        py +
        " · " +
        (item.count || 0) +
        ' 部">' +
        escapeHtml(item.name) +
        '<span class="tag-count">' +
        item.count +
        "</span></button>"
      );
    })
    .join("");
  container.querySelectorAll("[data-tag]").forEach(function (el) {
    el.addEventListener("click", function () {
      goCatalog({ q: "", actress: "", tag: el.getAttribute("data-tag") || "" });
    });
  });
}

function updateLabelCount(shown, allTotal) {
  var countEl = $("#labelCount");
  if (!countEl) return;
  if (!allTotal) {
    countEl.textContent = "点击即可筛选收藏影片";
    return;
  }
  var hint = filterHintText(state.labelInitial, state.labelPinyinQ);
  if (hint) {
    countEl.textContent =
      "筛选 " +
      shown +
      " / 共 " +
      allTotal +
      " 个" +
      hint +
      " · 点击即可筛选收藏影片";
  } else {
    countEl.textContent = "共 " + allTotal + " 个 · 点击即可筛选收藏影片";
  }
}

export function renderLabels() {
  var cats = state.labels.categories || [];
  var tags = state.labels.tags || [];
  var all = cats.concat(tags);
  var filterOpts = {
    letter: state.labelInitial,
    query: state.labelPinyinQ,
  };

  renderInitialBar($("#labelInitialBar"), {
    selected: state.labelInitial,
    counts: countInitials(all),
    total: all.length,
    unit: "个",
    allTitle: "全部标签与分类",
    onSelect: function (letter) {
      state.labelInitial = letter;
      renderLabels();
    },
  });

  var filteredCats = filterByPinyin(cats, filterOpts);
  var filteredTags = filterByPinyin(tags, filterOpts);
  updateLabelCount(filteredCats.length + filteredTags.length, all.length);

  renderLabelCloud(
    $("#categoriesCloud"),
    $("#categoriesEmpty"),
    filteredCats,
    cats.length ? "没有匹配的分类" : "暂无分类"
  );
  renderLabelCloud(
    $("#tagsCloud"),
    $("#tagsEmpty"),
    filteredTags,
    tags.length ? "没有匹配的标签" : "暂无标签"
  );
}

export function loadLabels() {
  setupLabelFilters();
  return loadLibraryLabels().then(function () {
    renderLabels();
  });
}

export function onLabels() {
  state.selectedCode = null;
  showView("labels");
  loadLabels();
}
