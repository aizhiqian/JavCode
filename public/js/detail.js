import { state, $, invalidateCatalog } from "./state.js";
import { api } from "./api.js";
import { goCatalog, showView } from "./router.js";
import {
  coverHtml,
  escapeAttr,
  escapeHtml,
  femaleNames,
  sourceLabel,
} from "./util.js";
import {
  getLibraryLabelItems,
  loadLibraryLabels,
} from "./label-library.js";
import { bindLabelSuggest } from "./label-suggest.js";

function sectionHeadHtml(title, kind, items) {
  var hasItems = items && items.length;
  return (
    '<div class="detail-section-head">' +
    "<h3>" +
    escapeHtml(title) +
    "</h3>" +
    '<button type="button" class="btn label-clear-btn" data-kind="' +
    escapeAttr(kind) +
    '"' +
    (hasItems ? "" : " disabled") +
    ' title="清除全部' +
    escapeAttr(title) +
    '">' +
    "清除全部" +
    "</button>" +
    "</div>"
  );
}

function labelEditorHtml(kind, items, placeholder) {
  var chips =
    items && items.length
      ? items
          .map(function (t) {
            return (
              '<span class="tag tag-editable">' +
              '<button type="button" class="tag-text" data-tag="' +
              escapeAttr(t) +
              '" title="点击筛选">' +
              escapeHtml(t) +
              "</button>" +
              '<button type="button" class="tag-remove" data-kind="' +
              escapeAttr(kind) +
              '" data-label="' +
              escapeAttr(t) +
              '" title="移除" aria-label="移除 ' +
              escapeAttr(t) +
              '">×</button>' +
              "</span>"
            );
          })
          .join("")
      : '<span class="muted detail-empty-labels">暂无，可在下方选择或新增</span>';
  return (
    '<div class="label-editor" data-kind="' +
    escapeAttr(kind) +
    '">' +
    '<div class="tag-cloud">' +
    chips +
    "</div>" +
    '<form class="label-add-form" data-kind="' +
    escapeAttr(kind) +
    '">' +
    '<div class="label-suggest-wrap">' +
    '<input type="text" class="label-add-input" maxlength="40" placeholder="' +
    escapeAttr(placeholder) +
    '" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" />' +
    '<ul class="label-suggest-list" role="listbox" hidden></ul>' +
    "</div>" +
    '<button type="submit" class="btn label-add-btn">添加</button>' +
    "</form>" +
    "</div>"
  );
}

function saveLabels(code, payload) {
  return api("/api/movies/" + encodeURIComponent(code) + "/labels", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(function (data) {
    if (!data.ok || !data.item) {
      window.alert("保存失败：" + (data.error || "未知错误"));
      return null;
    }
    return data.item;
  });
}

/**
 * Persist labels for one kind. Re-renders detail from the server item and
 * refreshes the shared library index so suggestions stay coherent.
 */
function applyLabels(code, kind, list, opts) {
  opts = opts || {};
  var body = kind === "categories" ? { categories: list } : { tags: list };
  var status = $("#labelSaveStatus");
  if (status) status.textContent = "保存中…";
  if (opts.btn) opts.btn.disabled = true;

  return saveLabels(code, body).then(function (item) {
    if (opts.btn) opts.btn.disabled = false;
    if (!item) {
      if (status) status.textContent = "";
      return null;
    }
    invalidateCatalog();
    if (status) status.textContent = "已保存";
    return loadLibraryLabels()
      .catch(function () {
        return state.labels;
      })
      .then(function () {
        renderDetail(item);
        return item;
      });
  });
}

function addLabelValue(code, kind, currentList, value, opts) {
  var raw = String(value || "").trim();
  if (!raw) return Promise.resolve(null);
  if (currentList.indexOf(raw) !== -1) return Promise.resolve(null);
  return applyLabels(code, kind, currentList.concat([raw]), opts);
}

function stat(label, value) {
  if (!value) return "";
  return (
    '<div class="stat"><span>' +
    escapeHtml(label) +
    "</span><strong>" +
    escapeHtml(value) +
    "</strong></div>"
  );
}

function sourceStat(m) {
  var label = sourceLabel(m && m.source);
  if (!label) return "";
  var valueHtml;
  if (m.source_url) {
    valueHtml =
      '<a class="source-link" href="' +
      escapeAttr(m.source_url) +
      '" target="_blank" rel="noopener noreferrer" title="打开源站">' +
      escapeHtml(label) +
      "</a>";
  } else {
    valueHtml = escapeHtml(label);
  }
  return (
    '<div class="stat"><span>来源</span><strong>' + valueHtml + "</strong></div>"
  );
}

function watchLinks(code) {
  var c = String(code || "").trim();
  if (!c) return [];
  var q = encodeURIComponent(c);
  return [
    {
      name: "MissAV",
      url: "https://missav.ws/cn/search/" + q,
      title: "在 MissAV 搜索并观看",
    },
    {
      name: "Jable",
      url: "https://jable.tv/search/" + q + "/",
      title: "在 Jable 搜索并观看",
    },
  ];
}

function watchStat(m) {
  var links = watchLinks(m && m.code);
  if (!links.length) return "";
  var valueHtml = links
    .map(function (link, i) {
      return (
        (i ? '<span class="watch-sep"> · </span>' : "") +
        '<a class="source-link" href="' +
        escapeAttr(link.url) +
        '" target="_blank" rel="noopener noreferrer" title="' +
        escapeAttr(link.title) +
        '">' +
        escapeHtml(link.name) +
        "</a>"
      );
    })
    .join("");
  return (
    '<div class="stat"><span>观看</span><strong class="watch-links">' +
    valueHtml +
    "</strong></div>"
  );
}

function deleteMovie(code, btn) {
  if (!code) return;
  if (!window.confirm("确定从收藏中删除 " + code + "？此操作不可撤销。")) {
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.textContent = "删除中…";
  }
  api("/api/movies/" + encodeURIComponent(code), { method: "DELETE" })
    .then(function (data) {
      if (data.ok) {
        state.selectedCode = null;
        invalidateCatalog();
        goCatalog(null, { replace: true });
        return;
      }
      window.alert("删除失败：" + (data.error || "未知错误"));
      if (btn) {
        btn.disabled = false;
        btn.textContent = "从收藏中删除";
      }
    })
    .catch(function (err) {
      window.alert("删除失败：" + err);
      if (btn) {
        btn.disabled = false;
        btn.textContent = "从收藏中删除";
      }
    });
}

export function renderDetail(m) {
  var root = $("#detailRoot");
  if (!root) return;
  var names = femaleNames(m);
  var categories = (m.categories || []).slice();
  var tags = (m.tags || []).slice();

  root.innerHTML =
    '<div class="detail-left">' +
    '<div class="detail-cover">' +
    coverHtml(m.cover_url, m.title, { link: true }) +
    "</div>" +
    '<div class="detail-meta">' +
    '<span class="detail-code">' +
    escapeHtml(m.code) +
    "</span>" +
    "<h1>" +
    escapeHtml(m.title || m.code) +
    "</h1>" +
    (m.title_original && m.title_original !== m.title
      ? '<p class="detail-original">原标题：' + escapeHtml(m.title_original) + "</p>"
      : "") +
    '<div class="detail-stats">' +
    stat("发行", m.release_date) +
    stat("片长", m.duration_minutes ? m.duration_minutes + " 分钟" : "") +
    stat("片商", m.studio) +
    stat("评分", m.score != null ? String(m.score) : "") +
    sourceStat(m) +
    watchStat(m) +
    "</div>" +
    "</div>" +
    "</div>" +
    '<div class="detail-hero">' +
    "<h3 style='margin:0 0 0.5rem;font-size:1rem'>女优</h3>" +
    '<div class="actress-chips">' +
    names
      .map(function (n) {
        return (
          '<button type="button" class="actress-chip" data-actress="' +
          escapeAttr(n) +
          '">' +
          escapeHtml(n) +
          "</button>"
        );
      })
      .join("") +
    "</div>" +
    sectionHeadHtml("分类", "categories", categories) +
    labelEditorHtml("categories", categories, "选择已有或输入新分类…") +
    sectionHeadHtml("标签", "tags", tags) +
    labelEditorHtml("tags", tags, "选择已有或输入新标签…") +
    '<p id="labelSaveStatus" class="label-save-status muted" aria-live="polite"></p>' +
    '<div class="detail-actions">' +
    '<button type="button" class="btn danger" id="deleteMovieBtn" data-code="' +
    escapeAttr(m.code) +
    '">从收藏中删除</button>' +
    "</div>" +
    "</div>";

  root.querySelectorAll("[data-actress]").forEach(function (el) {
    el.addEventListener("click", function () {
      goCatalog({ q: "", actress: el.getAttribute("data-actress") || "", tag: "" });
    });
  });
  root.querySelectorAll(".tag-text[data-tag]").forEach(function (el) {
    el.addEventListener("click", function () {
      goCatalog({ q: "", actress: "", tag: el.getAttribute("data-tag") || "" });
    });
  });
  root.querySelectorAll(".tag-remove").forEach(function (el) {
    el.addEventListener("click", function () {
      var kind = el.getAttribute("data-kind");
      var label = el.getAttribute("data-label");
      var current = kind === "categories" ? categories : tags;
      applyLabels(
        m.code,
        kind,
        current.filter(function (x) {
          return x !== label;
        })
      );
    });
  });
  root.querySelectorAll(".label-clear-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var kind = btn.getAttribute("data-kind");
      var title = kind === "categories" ? "分类" : "标签";
      var list = kind === "categories" ? categories : tags;
      if (!list.length) return;
      if (!window.confirm("确定清除本片的全部" + title + "？")) return;
      applyLabels(m.code, kind, [], { btn: btn });
    });
  });
  root.querySelectorAll(".label-add-form").forEach(function (form) {
    var kind = form.getAttribute("data-kind");
    var list = kind === "categories" ? categories : tags;
    var submitBtn = form.querySelector('button[type="submit"]');
    bindLabelSuggest(form, {
      getItems: function () {
        return getLibraryLabelItems(kind);
      },
      getExclude: function () {
        return list;
      },
      onPick: function (value) {
        addLabelValue(m.code, kind, list, value, { btn: submitBtn });
      },
    });
  });
  var delBtn = $("#deleteMovieBtn");
  if (delBtn) {
    delBtn.addEventListener("click", function () {
      deleteMovie(delBtn.getAttribute("data-code"), delBtn);
    });
  }
}

export function loadDetail(code) {
  if (!code) return;
  state.selectedCode = code;
  showView("detail");
  var root = $("#detailRoot");
  if (root) root.innerHTML = "<p class='muted'>加载中…</p>";
  Promise.all([
    api("/api/movies/" + encodeURIComponent(code)),
    loadLibraryLabels().catch(function () {
      return state.labels || { categories: [], tags: [] };
    }),
  ]).then(function (results) {
    var data = results[0];
    if (state.selectedCode !== code || state.view !== "detail") return;
    if (!data.ok || !data.item) {
      if (root) root.innerHTML = "<p class='form-status error'>未找到该条目</p>";
      return;
    }
    renderDetail(data.item);
  });
}

export function onDetail(route) {
  loadDetail(route.code);
}
