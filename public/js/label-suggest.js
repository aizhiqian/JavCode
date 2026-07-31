import { escapeAttr, escapeHtml } from "./util.js";
import { matchesPinyinItem, normalizePinyinQuery } from "./pinyin-filter.js";

/**
 * Rank + filter library label items for the suggestion dropdown.
 */
export function filterLabelSuggestions(items, query, exclude) {
  var q = normalizePinyinQuery(query);
  var excluded = exclude || [];
  var out = (items || []).filter(function (item) {
    if (!item || !item.name) return false;
    if (excluded.indexOf(item.name) !== -1) return false;
    return matchesPinyinItem(item, q);
  });
  out.sort(function (a, b) {
    return (
      (b.count || 0) - (a.count || 0) ||
      String(a.name).localeCompare(String(b.name), "zh")
    );
  });
  return out.slice(0, 12);
}

/**
 * Combobox for picking an existing library label or typing a new one.
 *
 * @param {HTMLFormElement} form  .label-add-form with input + .label-suggest-list
 * @param {object} opts
 *   getItems(): library items for this kind
 *   getExclude(): names already on the movie
 *   onPick(value): called with chosen string (may return Promise)
 */
export function bindLabelSuggest(form, opts) {
  opts = opts || {};
  var input = form.querySelector(".label-add-input");
  var listEl = form.querySelector(".label-suggest-list");
  if (!input || !listEl) return;

  var activeIndex = -1;
  var visible = [];

  function closeSuggest() {
    listEl.hidden = true;
    listEl.innerHTML = "";
    activeIndex = -1;
    visible = [];
    input.setAttribute("aria-expanded", "false");
  }

  function setActive(idx) {
    activeIndex = idx;
    listEl.querySelectorAll(".label-suggest-item").forEach(function (node, i) {
      if (i === activeIndex) node.classList.add("active");
      else node.classList.remove("active");
    });
  }

  function pickValue(value) {
    var raw = String(value || "").trim();
    closeSuggest();
    if (!raw) return;
    input.value = "";
    if (typeof opts.onPick === "function") opts.onPick(raw);
  }

  function renderSuggest() {
    var raw = (input.value || "").trim();
    var exclude =
      typeof opts.getExclude === "function" ? opts.getExclude() || [] : [];
    var items =
      typeof opts.getItems === "function" ? opts.getItems() || [] : [];
    var suggestions = filterLabelSuggestions(items, raw, exclude);
    var exactInLib = items.some(function (s) {
      return s && s.name === raw;
    });
    var alreadyOn = exclude.indexOf(raw) !== -1;
    var rows = [];

    if (raw && !exactInLib && !alreadyOn) {
      rows.push({ type: "new", name: raw, label: "新增「" + raw + "」" });
    }
    suggestions.forEach(function (s) {
      rows.push({
        type: "existing",
        name: s.name,
        label: s.name,
        count: s.count || 0,
      });
    });

    if (!rows.length) {
      closeSuggest();
      return;
    }

    visible = rows;
    activeIndex = 0;
    listEl.innerHTML = rows
      .map(function (row, i) {
        var extra =
          row.type === "existing" && row.count
            ? '<span class="label-suggest-count">' + row.count + "</span>"
            : "";
        var cls =
          "label-suggest-item" +
          (row.type === "new" ? " is-new" : "") +
          (i === activeIndex ? " active" : "");
        return (
          '<li class="' +
          cls +
          '" role="option" data-value="' +
          escapeAttr(row.name) +
          '">' +
          '<span class="label-suggest-text">' +
          escapeHtml(row.label) +
          "</span>" +
          extra +
          "</li>"
        );
      })
      .join("");
    listEl.hidden = false;
    input.setAttribute("aria-expanded", "true");

    listEl.querySelectorAll(".label-suggest-item").forEach(function (el) {
      el.addEventListener("mousedown", function (e) {
        e.preventDefault();
        pickValue(el.getAttribute("data-value") || "");
      });
    });
  }

  input.addEventListener("focus", renderSuggest);
  input.addEventListener("input", renderSuggest);
  input.addEventListener("blur", function () {
    setTimeout(closeSuggest, 120);
  });
  input.addEventListener("keydown", function (e) {
    if (listEl.hidden || !visible.length) {
      if (e.key === "Escape") closeSuggest();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive(Math.min(activeIndex + 1, visible.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(Math.max(activeIndex - 1, 0));
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeSuggest();
    } else if (e.key === "Enter" && activeIndex >= 0 && visible[activeIndex]) {
      e.preventDefault();
      pickValue(visible[activeIndex].name);
    }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var value = (input.value || "").trim();
    if (!value && activeIndex >= 0 && visible[activeIndex]) {
      value = visible[activeIndex].name;
    }
    if (!value) return;
    pickValue(value);
  });
}
