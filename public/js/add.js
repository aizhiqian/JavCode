import { state, $ } from "./state.js";
import { api } from "./api.js";
import { goDetail, showView } from "./router.js";
import { loadMovies } from "./catalog.js";
import { coverHtml, escapeHtml, sourceLabel } from "./util.js";

export function setupEnrich() {
  var form = $("#enrichForm");
  if (!form) return;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var code = ($("#codeInput") && $("#codeInput").value) || "";
    var prefer = ($("#preferSelect") && $("#preferSelect").value) || "javdb";
    var useAi = !!( $("#useAiCheck") && $("#useAiCheck").checked );
    var btn = $("#enrichBtn");
    var status = $("#enrichStatus");
    var preview = $("#enrichPreview");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "检索中…";
    }
    if (status) {
      status.className = "form-status";
      status.textContent =
        "正在从网络数据库检索 " +
        code +
        (useAi ? "，并尝试 AI 翻译/分类…" : " …");
    }
    if (preview) preview.innerHTML = "";

    api("/api/enrich", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: code,
        prefer: prefer,
        persist: true,
        use_ai: useAi,
      }),
    })
      .then(function (data) {
        if (data.ok && data.entry) {
          if (status) {
            status.className = "form-status ok";
            status.textContent =
              "已收藏 " +
              data.entry.code +
              (data.ai_used ? " · AI 已增强" : data.ai_error ? " · AI 未用（" + data.ai_error + "）" : "") +
              " · " +
              sourceLabel(data.source || (data.entry && data.entry.source) || "");
          }
          if (preview) {
            preview.innerHTML =
              '<button type="button" class="movie-card" id="previewCard" style="max-width:200px">' +
              '<div class="cover">' +
              coverHtml(data.entry.cover_url, data.entry.title) +
              "</div>" +
              '<div class="card-meta"><div class="card-code">' +
              escapeHtml(data.entry.code) +
              '</div><div class="card-title">' +
              escapeHtml(data.entry.title) +
              "</div></div></button>";
            var pc = $("#previewCard");
            if (pc) {
              pc.addEventListener("click", function () {
                goDetail(data.entry.code);
              });
            }
          }
          loadMovies();
        } else {
          if (status) {
            status.className = "form-status error";
            status.textContent =
              "检索失败：" + (data.error || "未知错误") + "（未写入虚假成功记录）";
          }
        }
      })
      .catch(function (err) {
        if (status) {
          status.className = "form-status error";
          status.textContent = "请求错误：" + err;
        }
      })
      .then(function () {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "检索并收藏";
        }
      });
  });
}

export function onAdd() {
  state.selectedCode = null;
  showView("add");
}
