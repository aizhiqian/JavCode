from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .ai import AIClient, AIMeta, ai_enrich_entry
from .classify import classify
from .fetchers import FetchResult, SourceFetcher
from .models import MovieEntry
from .normalize import normalize_code
from .parsers import ParseError, parse_javdb_detail, parse_javlibrary_detail
from .store import CollectionStore
from .translate import ensure_zh_fields, normalize_entry

logger = logging.getLogger(__name__)


@dataclass
class EnrichResult:
    ok: bool
    entry: MovieEntry | None = None
    error: str = ""
    source: str = ""
    url: str = ""
    persisted: bool = False
    live: bool = True
    ai_used: bool = False
    ai_error: str = ""
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "entry": self.entry.to_dict() if self.entry else None,
            "error": self.error,
            "source": self.source,
            "url": self.url,
            "persisted": self.persisted,
            "live": self.live,
            "ai_used": self.ai_used,
            "ai_error": self.ai_error,
            "log": list(self.log),
        }

    def http_status(self) -> int:
        if self.ok:
            return 200
        if self.error == "无效番号":
            return 400
        if self.entry is not None:
            return 422
        return 502


def post_process(
    raw: MovieEntry,
    *,
    ai_client: AIClient | None = None,
) -> tuple[MovieEntry, AIMeta]:
    normalized = normalize_entry(raw)
    polished, ai_meta = ai_enrich_entry(normalized, client=ai_client)
    return classify(polished), ai_meta


def _finalize(
    raw: MovieEntry,
    *,
    logs: list[str],
    source: str,
    url: str,
    live: bool,
    store: CollectionStore | None,
    persist: bool,
    ai_client: AIClient | None,
) -> EnrichResult:
    entry, ai_meta = post_process(raw, ai_client=ai_client)
    logs.append(
        f"post title={entry.title!r} actresses={[a.name for a in entry.actresses]} tags={entry.tags[:8]}"
    )
    logs.append(f"ai used={ai_meta.used} error={ai_meta.error!r}")
    if not ensure_zh_fields(entry):
        return EnrichResult(
            ok=False,
            error="缺少标题/女优/标签",
            entry=entry,
            source=source,
            url=url,
            live=live,
            ai_used=ai_meta.used,
            ai_error=ai_meta.error,
            log=logs,
        )

    persisted = False
    if persist and store is not None:
        entry = store.upsert(entry)
        persisted = True
        logs.append(f"persisted id={entry.id}")

    return EnrichResult(
        ok=True,
        entry=entry,
        source=source,
        url=url or entry.source_url,
        persisted=persisted,
        live=live,
        ai_used=ai_meta.used,
        ai_error=ai_meta.error,
        log=logs,
    )


def enrich_from_html(
    html: str,
    code: str,
    *,
    source: str = "javdb",
    source_url: str = "",
    store: CollectionStore | None = None,
    persist: bool = False,
    ai_client: AIClient | None = None,
) -> EnrichResult:
    logs: list[str] = []
    code_n = normalize_code(code)
    logs.append(f"enrich_from_html code={code_n} source={source}")
    try:
        if source == "javlibrary":
            raw = parse_javlibrary_detail(html, code=code_n, source_url=source_url)
        else:
            raw = parse_javdb_detail(html, code=code_n, source_url=source_url)
    except ParseError as exc:
        return EnrichResult(
            ok=False,
            error=str(exc),
            source=source,
            url=source_url,
            live=False,
            log=logs + [f"parse error: {exc}"],
        )

    return _finalize(
        raw,
        logs=logs,
        source=source,
        url=source_url,
        live=False,
        store=store,
        persist=persist,
        ai_client=ai_client,
    )


def enrich_code(
    code: str,
    *,
    store: CollectionStore | None = None,
    persist: bool = True,
    fetcher: SourceFetcher | None = None,
    prefer: str = "javdb",
    ai_client: AIClient | None = None,
) -> EnrichResult:
    logs: list[str] = []
    code_n = normalize_code(code)
    if not code_n:
        return EnrichResult(ok=False, error="无效番号", log=["empty code"])

    logs.append(f"enrich_code {code_n} prefer={prefer}")
    fetcher = fetcher or SourceFetcher()
    live: FetchResult = fetcher.fetch(code_n, prefer=prefer)
    logs.append(f"live result ok={live.ok} source={live.source} error={live.error!r} url={live.url}")

    if live.ok and live.entry is not None:
        return _finalize(
            live.entry,
            logs=logs,
            source=live.source,
            url=live.url,
            live=True,
            store=store,
            persist=persist,
            ai_client=ai_client,
        )

    err = live.error or "live fetch failed"
    logger.warning("enrich failed for %s: %s", code_n, err)
    return EnrichResult(
        ok=False,
        error=err,
        source=live.source,
        url=live.url,
        live=True,
        log=logs,
    )
