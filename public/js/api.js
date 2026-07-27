var unauthorizedHandler = null;

export function onUnauthorized(fn) {
  unauthorizedHandler = fn;
}

export function api(path, opts) {
  opts = opts || {};
  if (!opts.credentials) opts.credentials = "same-origin";
  return fetch(path, opts).then(function (res) {
    return res.json().then(
      function (data) {
        data._httpStatus = res.status;
        if (
          res.status === 401 &&
          data &&
          (data.code === "unauthorized" || data.code === "setup_required")
        ) {
          if (unauthorizedHandler) {
            unauthorizedHandler(
              data.code === "setup_required" ? "setup" : "login"
            );
          }
        }
        return data;
      },
      function () {
        return { ok: false, error: "无效响应", _httpStatus: res.status };
      }
    );
  });
}
