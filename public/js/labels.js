import { state, $ } from "./state.js";
import { api } from "./api.js";
import { goCatalog, showView } from "./router.js";
import { escapeAttr, escapeHtml } from "./util.js";

function renderLabelCloud(container, emptyEl, items) {
  if (!container) return;
  if (!items || !items.length) {
    container.innerHTML = "";
    if (emptyEl) emptyEl.classList.remove("hidden");
    return;
  }
  if (emptyEl) emptyEl.classList.add("hidden");
  container.innerHTML = items
    .map(function (item) {
      return (
        '<button type="button" class="tag" data-tag="' +
        escapeAttr(item.name) +
        '">' +
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

export function loadLabels() {
  return api("/api/labels").then(function (data) {
    renderLabelCloud(
      $("#categoriesCloud"),
      $("#categoriesEmpty"),
      data.categories || []
    );
    renderLabelCloud($("#tagsCloud"), $("#tagsEmpty"), data.tags || []);
  });
}

export function onLabels() {
  state.selectedCode = null;
  showView("labels");
  loadLabels();
}
