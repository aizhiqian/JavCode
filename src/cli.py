from __future__ import annotations

import argparse
import json
import sys

from .ai import AIClient, AIConfig
from .db import DEFAULT_SQLITE_PATH, open_database, resolve_db_location
from .enrich import enrich_code
from .env import load_project_env
from .fetchers import SourceFetcher
from .settings import SettingsStore, resolve_proxy_dict
from .store import CollectionStore

DEFAULT_DB = DEFAULT_SQLITE_PATH


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="个人 AV 收藏 — 番号检索与管理")
    p.add_argument(
        "--db",
        default=None,
        help="数据库位置：SQLite 路径，或 mysql:// / postgresql:// URL（默认 JAVCODE_DB 或 data/collection.db）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enrich", help="检索番号并写入收藏")
    e.add_argument("code", help="番号，如 SSIS-001")
    e.add_argument("--prefer", default="javdb", choices=["javdb", "javlibrary"])
    e.add_argument("--no-persist", action="store_true")
    e.add_argument("--no-ai", action="store_true", help="禁用 AI（仅 zhconv 简繁 + 规则分类）")

    sub.add_parser("ai-status", help="查看 AI API 配置状态")

    s = sub.add_parser("search", help="搜索收藏")
    s.add_argument("-q", "--query", default="")
    s.add_argument("--code", default="")
    s.add_argument("--actress", default="")
    s.add_argument("--tag", default="")

    sub.add_parser("list", help="列出全部收藏")
    sub.add_parser("actresses", help="女优索引")

    d = sub.add_parser("delete", help="删除一条")
    d.add_argument("code")

    return p


def main(argv: list[str] | None = None) -> int:
    load_project_env()
    args = build_parser().parse_args(argv)
    location = resolve_db_location(args.db)
    database = open_database(location)
    store = CollectionStore(database)
    settings = SettingsStore(database)
    proxies = resolve_proxy_dict(settings)

    if args.cmd == "ai-status":
        print(
            json.dumps(
                {"ok": True, "ai": AIConfig.resolve(settings).to_public_dict()},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.cmd == "enrich":
        ai_client = None if args.no_ai else AIClient.from_settings(settings, proxies=proxies)
        result = enrich_code(
            args.code,
            store=store,
            persist=not args.no_persist,
            prefer=args.prefer,
            fetcher=SourceFetcher(proxies=proxies),
            ai_client=ai_client,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ok else 1

    if args.cmd == "list":
        items = [e.to_dict() for e in store.list_all()]
        print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "search":
        found = store.search(
            code=args.code or None,
            actress=args.actress or None,
            tag=args.tag or None,
            query=args.query or None,
        )
        print(json.dumps({"count": len(found), "items": [e.to_dict() for e in found]}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "actresses":
        print(json.dumps({"items": store.actress_index()}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "delete":
        ok = store.delete(args.code)
        print(json.dumps({"ok": ok}))
        return 0 if ok else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
