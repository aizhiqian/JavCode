export function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

export function femaleNames(entry) {
  return (entry.actresses || [])
    .filter(function (a) {
      return a.gender !== "male";
    })
    .map(function (a) {
      return a.name;
    });
}

export function sourceLabel(source) {
  var s = String(source || "").toLowerCase();
  if (s === "javdb") return "JavDB";
  if (s === "javlibrary") return "JavLibrary";
  return source ? String(source) : "";
}

export function coverHtml(url, alt, opts) {
  opts = opts || {};
  if (!url) return "";
  var img =
    '<img src="' +
    escapeAttr(url) +
    '" alt="' +
    escapeAttr(alt || "") +
    '" loading="lazy" />';
  if (opts.link) {
    return (
      '<a href="' +
      escapeAttr(url) +
      '" target="_blank" rel="noopener noreferrer" title="查看原图">' +
      img +
      "</a>"
    );
  }
  return img;
}

export function totalPages(count, pageSize) {
  return Math.max(1, Math.ceil((count || 0) / pageSize));
}

export function clampPage(page, count, pageSize) {
  var max = totalPages(count, pageSize);
  var p = parseInt(page, 10) || 1;
  if (p < 1) return 1;
  if (p > max) return max;
  return p;
}

export function pageSlice(items, page, pageSize) {
  var p = clampPage(page, items.length, pageSize);
  var start = (p - 1) * pageSize;
  return {
    page: p,
    totalPages: totalPages(items.length, pageSize),
    total: items.length,
    items: items.slice(start, start + pageSize),
    start: items.length ? start + 1 : 0,
    end: Math.min(start + pageSize, items.length),
  };
}

export function renderPager(el, slice, unit, onPage) {
  if (!el) return;
  if (!slice.total || slice.totalPages <= 1) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  el.hidden = false;
  el.innerHTML =
    '<button type="button" class="pager-btn" data-pager="prev"' +
    (slice.page <= 1 ? " disabled" : "") +
    ">上一页</button>" +
    '<span class="pager-info">' +
    "第 " +
    slice.page +
    " / " +
    slice.totalPages +
    " 页 · 显示 " +
    slice.start +
    "–" +
    slice.end +
    " / 共 " +
    slice.total +
    " " +
    unit +
    "</span>" +
    '<button type="button" class="pager-btn" data-pager="next"' +
    (slice.page >= slice.totalPages ? " disabled" : "") +
    ">下一页</button>";
  el.querySelectorAll("[data-pager]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var dir = btn.getAttribute("data-pager");
      if (dir === "prev") onPage(slice.page - 1);
      else if (dir === "next") onPage(slice.page + 1);
    });
  });
}
