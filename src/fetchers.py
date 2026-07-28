from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

import requests

from .models import MovieEntry
from .normalize import normalize_code
from .parsers import (
    ParseError,
    is_javlibrary_detail,
    parse_javdb_detail,
    parse_javdb_search,
    parse_javlibrary_detail,
    parse_javlibrary_search,
)

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
}


@dataclass
class FetchResult:
    ok: bool
    entry: MovieEntry | None = None
    error: str = ""
    source: str = ""
    url: str = ""


@dataclass
class _HttpPage:
    ok: bool
    html: str = ""
    error: str = ""
    url: str = ""


class SourceFetcher:
    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 20.0,
        get: Callable[..., requests.Response] | None = None,
        *,
        proxies: dict[str, str] | None = None,
    ) -> None:
        """HTTP client for JavDB / JavLibrary. Proxy is injected; never self-resolved.

        proxies=None or {} means direct (trust_env=False — ambient HTTP_PROXY ignored).
        Composition roots (cli/server) call resolve_proxy_dict and pass the result.
        """
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.headers.update(DEFAULT_HEADERS)
        resolved = dict(proxies) if proxies else {}
        if resolved:
            self.session.proxies.update(resolved)
        self.timeout = timeout
        self._get = get or self.session.get

    def _get_page(
        self,
        url: str,
        *,
        what: str,
        headers: dict[str, str] | None = None,
    ) -> _HttpPage:
        try:
            resp = self._get(url, timeout=self.timeout, headers=headers)
        except requests.RequestException as exc:
            msg = f"{what} network error: {exc}"
            logger.warning(msg)
            return _HttpPage(ok=False, error=msg, url=url)
        final_url = getattr(resp, "url", url) or url
        if resp.status_code != 200:
            msg = f"{what} HTTP {resp.status_code}"
            logger.warning(msg)
            return _HttpPage(ok=False, error=msg, url=final_url)
        return _HttpPage(ok=True, html=resp.text, url=final_url)

    def _fail(self, *, source: str, error: str, url: str = "") -> FetchResult:
        return FetchResult(ok=False, error=error, source=source, url=url)

    def _parse_detail(
        self,
        *,
        source: str,
        html: str,
        code: str,
        url: str,
        parse,
    ) -> FetchResult:
        try:
            entry = parse(html, code=code, source_url=url)
        except ParseError as exc:
            return self._fail(source=source, error=f"{source} parse failed: {exc}", url=url)
        return FetchResult(ok=True, entry=entry, source=source, url=url)

    def fetch_javdb(self, code: str) -> FetchResult:
        code_n = normalize_code(code)
        source = "javdb"
        search_url = f"https://javdb.com/search?q={quote(code_n)}&f=all"
        search = self._get_page(search_url, what="JavDB search")
        if not search.ok:
            return self._fail(source=source, error=search.error, url=search.url or search_url)

        try:
            path = parse_javdb_search(search.html, code_n)
        except ParseError as exc:
            return self._fail(source=source, error=str(exc), url=search.url)
        if not path:
            return self._fail(
                source=source,
                error=f"JavDB search: no result for {code_n}",
                url=search.url,
            )

        detail_url = f"https://javdb.com{path}"
        detail = self._get_page(
            detail_url,
            what="JavDB detail",
            headers={**DEFAULT_HEADERS, "Referer": search_url},
        )
        if not detail.ok:
            return self._fail(source=source, error=detail.error, url=detail.url or detail_url)
        return self._parse_detail(
            source=source,
            html=detail.html,
            code=code_n,
            url=detail.url or detail_url,
            parse=parse_javdb_detail,
        )

    def fetch_javlibrary(self, code: str) -> FetchResult:
        code_n = normalize_code(code)
        source = "javlibrary"
        search_url = f"https://www.javlibrary.com/cn/vl_searchbyid.php?keyword={quote(code_n)}"
        page = self._get_page(search_url, what="javlibrary")
        if not page.ok:
            return self._fail(source=source, error=page.error, url=page.url or search_url)

        html = page.html
        final_url = page.url or search_url
        if is_javlibrary_detail(html):
            return self._parse_detail(
                source=source,
                html=html,
                code=code_n,
                url=final_url,
                parse=parse_javlibrary_detail,
            )

        try:
            detail_url = parse_javlibrary_search(html, code_n)
        except ParseError as exc:
            return self._fail(source=source, error=str(exc), url=final_url)
        if not detail_url:
            return self._fail(
                source=source,
                error=f"javlibrary: no detail for {code_n}",
                url=final_url,
            )

        detail = self._get_page(detail_url, what="javlibrary detail")
        if not detail.ok:
            return self._fail(source=source, error=detail.error, url=detail.url or detail_url)
        return self._parse_detail(
            source=source,
            html=detail.html,
            code=code_n,
            url=detail.url or detail_url,
            parse=parse_javlibrary_detail,
        )

    def fetch(self, code: str, prefer: str = "javdb") -> FetchResult:
        order = ["javdb", "javlibrary"] if prefer == "javdb" else ["javlibrary", "javdb"]
        last: FetchResult | None = None
        for src in order:
            result = self.fetch_javdb(code) if src == "javdb" else self.fetch_javlibrary(code)
            if result.ok:
                return result
            last = result
            logger.info("source %s failed for %s: %s", src, code, result.error)
        return last or FetchResult(ok=False, error="No sources configured", source=prefer)
