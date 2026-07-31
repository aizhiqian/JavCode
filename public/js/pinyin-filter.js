import { escapeAttr } from "./util.js";

/** A–Z letters used by pinyin initial bars. */
export var PINYIN_INITIALS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

export function initialOf(item) {
  var ini = String((item && item.initial) || "").toUpperCase();
  if (ini.length === 1 && ini >= "A" && ini <= "Z") return ini;
  return "#";
}

export function normalizePinyinQuery(q) {
  return String(q || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "");
}

/** Match name / pinyin / pinyin_key against a normalized query (empty = match all). */
export function matchesPinyinItem(item, q) {
  if (!q) return true;
  var name = String((item && item.name) || "").toLowerCase();
  var py = String((item && item.pinyin) || "")
    .toLowerCase()
    .replace(/\s+/g, "");
  var key = String((item && item.pinyin_key) || "").toLowerCase();
  return (
    name.indexOf(q) !== -1 || py.indexOf(q) !== -1 || key.indexOf(q) !== -1
  );
}

export function countInitials(items) {
  var counts = {};
  (items || []).forEach(function (item) {
    var ini = initialOf(item);
    counts[ini] = (counts[ini] || 0) + 1;
  });
  return counts;
}

/**
 * Filter items by initial letter + pinyin/name query.
 * @param {object[]} items
 * @param {{ letter?: string, query?: string }} opts
 */
export function filterByPinyin(items, opts) {
  opts = opts || {};
  var letter = opts.letter || "all";
  var q = normalizePinyinQuery(opts.query);
  return (items || []).filter(function (item) {
    if (letter !== "all" && initialOf(item) !== letter) return false;
    return matchesPinyinItem(item, q);
  });
}

/**
 * Build " · K · “q”" style hint from active filters.
 */
export function filterHintText(letter, query) {
  var hint = "";
  if (letter && letter !== "all") hint += " · " + letter;
  var q = String(query || "").trim();
  if (q) hint += " · “" + q + "”";
  return hint;
}

/**
 * Render A–Z / # / 全部 chip bar.
 * opts: { selected, counts, total, unit, allTitle, onSelect }
 */
export function renderInitialBar(bar, opts) {
  if (!bar) return;
  opts = opts || {};
  var counts = opts.counts || {};
  var total = opts.total || 0;
  var unit = opts.unit || "个";
  var selected = opts.selected || "all";
  var allTitle = opts.allTitle || "全部";
  var onSelect = opts.onSelect;
  var letters = ["all"].concat(PINYIN_INITIALS).concat(["#"]);

  bar.innerHTML = letters
    .map(function (L) {
      var label = L === "all" ? "全部" : L;
      var n = L === "all" ? total : counts[L] || 0;
      var active = selected === L ? " active" : "";
      var disabled = L !== "all" && n === 0 ? " disabled" : "";
      return (
        '<button type="button" class="initial-chip' +
        active +
        '" data-initial="' +
        L +
        '"' +
        disabled +
        ' title="' +
        escapeAttr(
          (L === "all" ? allTitle : "拼音首字母 " + L) +
            (n ? " · " + n + " " + unit : "")
        ) +
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
      if (typeof onSelect === "function") {
        onSelect(btn.getAttribute("data-initial") || "all");
      }
    });
  });
}

/**
 * Bind debounced search input. Caller must ensure this runs once per input.
 * opts: { delay?, onChange(value) }
 */
export function bindSearchInput(input, opts) {
  if (!input) return;
  opts = opts || {};
  var delay = opts.delay != null ? opts.delay : 160;
  var onChange = opts.onChange;
  var timer = null;

  function emit() {
    if (typeof onChange === "function") onChange(input.value || "");
  }

  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(emit, delay);
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      clearTimeout(timer);
      emit();
    }
  });
}
