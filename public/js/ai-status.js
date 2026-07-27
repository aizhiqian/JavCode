import { $ } from "./state.js";
import { api } from "./api.js";

export function loadAiStatus() {
  var line = $("#aiStatusLine");
  var check = $("#useAiCheck");
  return api("/api/ai/status")
    .then(function (data) {
      var ai = (data && data.ai) || {};
      if (line) {
        if (ai.available) {
          line.className = "ai-status on";
          line.textContent =
            "AI 已就绪 · " +
            (ai.provider_hint || "API") +
            " · " +
            (ai.model || "");
        } else if (ai.configured && !ai.enabled) {
          line.className = "ai-status off";
          line.textContent = "AI Key 已配置但被 JAVCODE_AI_ENABLED 关闭";
        } else {
          line.className = "ai-status off";
          line.textContent = "AI 未配置（仅简繁转换 + 规则分类，无日→中翻译）";
          if (check) check.checked = false;
        }
      }
    })
    .catch(function () {
      if (line) {
        line.className = "ai-status off";
        line.textContent = "无法读取 AI 状态";
      }
    });
}
