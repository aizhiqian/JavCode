import { state, $ } from "./state.js";
import { api } from "./api.js";
import { showView } from "./router.js";
import { loadAiStatus } from "./ai-status.js";

export function loadSettings() {
  var status = $("#settingsStatus");
  return api("/api/settings").then(function (data) {
    if (!data.ok) {
      if (status) {
        status.className = "form-status error";
        status.textContent = data.error || "无法加载设置";
      }
      return;
    }
    var fields = data.fields || {};
    function val(key) {
      return fields[key] && fields[key].value != null ? fields[key].value : "";
    }
    var map = {
      setAiKey: "ai_api_key",
      setAiBase: "ai_base_url",
      setAiModel: "ai_model",
      setAiEnabled: "ai_enabled",
      setAiTimeout: "ai_timeout",
      setProxy: "proxy",
    };
    Object.keys(map).forEach(function (id) {
      var el = $("#" + id);
      if (el) el.value = val(map[id]);
    });
    var user = $("#setAdminUser");
    if (user) user.value = data.admin_username || "";
    var pass = $("#setAdminPass");
    if (pass) pass.value = "";
    if (status) {
      status.className = "form-status";
      status.textContent = "";
    }
  });
}

export function setupSettings() {
  var form = $("#settingsForm");
  if (!form) return;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var status = $("#settingsStatus");
    var btn = $("#settingsSaveBtn");
    var body = {
      ai_api_key: ($("#setAiKey") && $("#setAiKey").value) || "",
      ai_base_url: ($("#setAiBase") && $("#setAiBase").value) || "",
      ai_model: ($("#setAiModel") && $("#setAiModel").value) || "",
      ai_enabled: ($("#setAiEnabled") && $("#setAiEnabled").value) || "",
      ai_timeout: ($("#setAiTimeout") && $("#setAiTimeout").value) || "",
      proxy: ($("#setProxy") && $("#setProxy").value) || "",
      admin_username: ($("#setAdminUser") && $("#setAdminUser").value) || "",
    };
    var newPass = ($("#setAdminPass") && $("#setAdminPass").value) || "";
    if (newPass) body.admin_password = newPass;
    if (btn) btn.disabled = true;
    api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (data) {
        if (data.ok) {
          if (status) {
            status.className = "form-status ok";
            status.textContent = "已保存（优先于 .env，已热更新）";
          }
          loadSettings();
          loadAiStatus();
        } else {
          if (status) {
            status.className = "form-status error";
            status.textContent = data.error || "保存失败";
          }
        }
      })
      .catch(function (err) {
        if (status) {
          status.className = "form-status error";
          status.textContent = String(err);
        }
      })
      .then(function () {
        if (btn) btn.disabled = false;
      });
  });
  var clearBtn = $("#settingsClearOverrides");
  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      if (!window.confirm("清除全部设置覆盖并回退到 .env？")) return;
      var status = $("#settingsStatus");
      api("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ai_api_key: "",
          ai_base_url: "",
          ai_model: "",
          ai_enabled: "",
          ai_timeout: "",
          proxy: "",
        }),
      }).then(function (data) {
        if (data.ok) {
          if (status) {
            status.className = "form-status ok";
            status.textContent = "已清除覆盖，回退 .env";
          }
          loadSettings();
          loadAiStatus();
        }
      });
    });
  }
}

export function onSettings() {
  state.selectedCode = null;
  showView("settings");
  loadSettings();
}
