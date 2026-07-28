from __future__ import annotations

import logging
import os
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

logger = logging.getLogger(__name__)

from .ai import AIClient, AIConfig
from .auth import (
    auth_status,
    is_authenticated,
    logout_user,
    try_login,
    try_setup,
)
from .enrich import EnrichResult, enrich_code
from .db import DEFAULT_SQLITE_PATH, open_database, resolve_db_location
from .env import ROOT, load_project_env, parse_bool
from .fetchers import SourceFetcher
from .models import MovieEntry
from .normalize import normalize_code
from .settings import (
    SettingsStore,
    proxy_public_status,
    resolve_proxy_dict,
    settings_public_view,
    update_settings_from_payload,
)
from .store import CollectionStore

PUBLIC = ROOT / "public"
DEFAULT_DB = DEFAULT_SQLITE_PATH


def create_app(
    db_path: str | Path | None = None,
    *,
    fetcher: SourceFetcher | None = None,
    ai_client: AIClient | None = None,
) -> Flask:
    app = Flask(__name__, static_folder=str(PUBLIC), static_url_path="")
    # JAVCODE_DB: SQLite path, or mysql:// / postgresql:// URL
    location = resolve_db_location(db_path)
    database = open_database(location)
    store = CollectionStore(database)
    settings = SettingsStore(database)
    settings.bootstrap_admin_from_env()
    app.secret_key = settings.ensure_secret_key()
    try:
        n = store.warm()
        logger.info("collection cache warmed (%s titles)", n)
    except Exception:
        logger.exception("collection cache warm failed; first page may hit the DB")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    app.config["STORE"] = store
    app.config["SETTINGS"] = settings
    app.config["DATABASE"] = database

    @app.teardown_appcontext
    def _release_db(_exc: object | None = None) -> None:
        # SQLite: close per request. MySQL/PG: no-op (shared long-lived conn).
        database.release_request()

    proxies = resolve_proxy_dict(settings)
    if ai_client is None:
        ai_client = AIClient.from_settings(settings, proxies=proxies)
    if fetcher is None:
        fetcher = SourceFetcher(proxies=proxies)
    app.config["FETCHER"] = fetcher
    app.config["AI_CLIENT"] = ai_client

    def _reload_runtime() -> None:
        s: SettingsStore = app.config["SETTINGS"]
        proxies_now = resolve_proxy_dict(s)
        app.config["AI_CLIENT"] = AIClient.from_settings(s, proxies=proxies_now)
        app.config["FETCHER"] = SourceFetcher(proxies=proxies_now)

    app.config["RELOAD_RUNTIME"] = _reload_runtime

    @app.before_request
    def _require_auth():
        path = request.path or ""
        if not path.startswith("/api/"):
            return None
        if path == "/api/health" or path.startswith("/api/auth/"):
            return None
        settings_local: SettingsStore = app.config["SETTINGS"]
        if not settings_local.is_admin_configured():
            return jsonify({"ok": False, "error": "管理员未初始化", "code": "setup_required"}), 401
        if not is_authenticated():
            return jsonify({"ok": False, "error": "未登录", "code": "unauthorized"}), 401
        return None

    @app.get("/")
    def index():
        return send_from_directory(PUBLIC, "index.html")

    @app.get("/api/health")
    def health():
        if not is_authenticated():
            return jsonify(
                {
                    "ok": True,
                    "version": "1.0.0",
                    "authenticated": False,
                    "configured": app.config["SETTINGS"].is_admin_configured(),
                }
            )
        db = app.config["DATABASE"]
        return jsonify(
            {
                "ok": True,
                "version": "1.0.0",
                "authenticated": True,
                "configured": True,
                "storage": {
                    "backend": db.backend,
                    "location": db.location,
                },
                "ai": _ai_public_status(app),
                "proxy": proxy_public_status(app.config["SETTINGS"]),
            }
        )

    @app.get("/api/auth/status")
    def api_auth_status():
        return jsonify({"ok": True, **auth_status(app.config["SETTINGS"])})

    @app.post("/api/auth/setup")
    def api_auth_setup():
        data = request.get_json(silent=True) or {}
        ok, err = try_setup(
            app.config["SETTINGS"],
            str(data.get("username") or ""),
            str(data.get("password") or ""),
        )
        if not ok:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True, **auth_status(app.config["SETTINGS"])})

    @app.post("/api/auth/login")
    def api_auth_login():
        data = request.get_json(silent=True) or {}
        ok, err = try_login(
            app.config["SETTINGS"],
            str(data.get("username") or ""),
            str(data.get("password") or ""),
        )
        if not ok:
            return jsonify({"ok": False, "error": err}), 401
        return jsonify({"ok": True, **auth_status(app.config["SETTINGS"])})

    @app.post("/api/auth/logout")
    def api_auth_logout():
        logout_user()
        return jsonify({"ok": True, **auth_status(app.config["SETTINGS"])})

    @app.get("/api/settings")
    def api_get_settings():
        return jsonify({"ok": True, **settings_public_view(app.config["SETTINGS"])})

    @app.put("/api/settings")
    def api_put_settings():
        data = request.get_json(silent=True) or {}
        view = update_settings_from_payload(app.config["SETTINGS"], data)
        app.config["RELOAD_RUNTIME"]()
        return jsonify({"ok": True, **view})

    @app.get("/api/ai/status")
    def ai_status():
        return jsonify({"ok": True, "ai": _ai_public_status(app)})

    @app.get("/api/movies")
    def list_movies():
        entries = _query_movies(app.config["STORE"], request.args)
        return jsonify({"ok": True, "count": len(entries), "items": [e.to_dict() for e in entries]})

    @app.get("/api/movies/<code>")
    def get_movie(code: str):
        store_local: CollectionStore = app.config["STORE"]
        entry = store_local.get_by_code(code)
        if not entry:
            return jsonify({"ok": False, "error": "未找到"}), 404
        return jsonify({"ok": True, "item": entry.to_dict()})

    @app.patch("/api/movies/<code>/labels")
    def update_movie_labels(code: str):
        store_local: CollectionStore = app.config["STORE"]
        code_n = normalize_code(code)
        if not code_n:
            return jsonify({"ok": False, "error": "无效番号"}), 400
        data = request.get_json(silent=True) or {}
        if "tags" not in data and "categories" not in data:
            return jsonify({"ok": False, "error": "需要 tags 和/或 categories"}), 400
        tags = data.get("tags") if "tags" in data else None
        categories = data.get("categories") if "categories" in data else None
        if tags is not None and not isinstance(tags, list):
            return jsonify({"ok": False, "error": "tags 须为数组"}), 400
        if categories is not None and not isinstance(categories, list):
            return jsonify({"ok": False, "error": "categories 须为数组"}), 400
        entry = store_local.update_labels(
            code_n,
            tags=[str(x) for x in tags] if tags is not None else None,
            categories=[str(x) for x in categories] if categories is not None else None,
        )
        if entry is None:
            return jsonify({"ok": False, "error": "未找到"}), 404
        return jsonify({"ok": True, "item": entry.to_dict()})

    @app.post("/api/enrich")
    def api_enrich():
        store_local: CollectionStore = app.config["STORE"]
        data = request.get_json(silent=True) or {}
        code_n = normalize_code(data.get("code") or "")
        if not code_n:
            empty = EnrichResult(ok=False, error="无效番号", log=["empty code"])
            return jsonify(empty.to_dict()), empty.http_status()

        want_ai = parse_bool(data.get("use_ai"), default=True)
        result = enrich_code(
            code_n,
            store=store_local,
            persist=bool(parse_bool(data.get("persist"), default=True)),
            fetcher=app.config["FETCHER"],
            prefer=data.get("prefer") or "javdb",
            ai_client=app.config["AI_CLIENT"] if want_ai else None,
        )
        return jsonify(result.to_dict()), result.http_status()

    @app.delete("/api/movies/<code>")
    def delete_movie(code: str):
        code_n = normalize_code(code)
        if not code_n:
            return jsonify({"ok": False, "error": "无效番号"}), 400
        ok = app.config["STORE"].delete(code_n)
        if not ok:
            return jsonify({"ok": False, "error": "未找到"}), 404
        return jsonify({"ok": True, "code": code_n})

    @app.get("/api/labels")
    def list_labels():
        return jsonify({"ok": True, **app.config["STORE"].label_index()})

    @app.get("/api/actresses")
    def list_actresses():
        return jsonify({"ok": True, "items": app.config["STORE"].actress_index()})

    return app


def _query_movies(store: CollectionStore, args) -> list[MovieEntry]:
    q = args.get("q")
    code = args.get("code")
    actress = args.get("actress")
    tag = args.get("tag")
    if q or code or actress or tag:
        return store.search(code=code, actress=actress, tag=tag, query=q)
    return store.list_all()


def _ai_public_status(app: Flask) -> dict:
    ai: AIClient | None = app.config.get("AI_CLIENT")
    if ai is None:
        return AIConfig.resolve(app.config.get("SETTINGS")).to_public_dict()
    return ai.config.to_public_dict()


def main() -> None:
    load_project_env()
    host = os.environ.get("JAVCODE_HOST", "0.0.0.0")
    port = int(os.environ.get("JAVCODE_PORT", "8765"))
    app = create_app()
    print(f"JavCode collection UI → http://{host}:{port}/")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
