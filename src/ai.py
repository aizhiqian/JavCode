from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

import requests

from .constants import DEFAULT_AI_BASE_URL, DEFAULT_AI_MODEL
from .env import parse_bool
from .labels import merge_labels, to_simplified
from .models import Actress, MovieEntry

if TYPE_CHECKING:
    from .settings import SettingsStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是日本成人影片元数据助手。根据给定的番号原始字段，输出严格 JSON（不要 markdown 代码块）：
{
  "title": "简体中文标题（自然通顺，不要番号前缀）",
  "actresses": [{"name": "简体常用译名", "name_original": "原文", "gender": "female|male"}],
  "tags": ["简体中文标签", ...],
  "categories": ["简体中文分类", ...]
}
规则：
1. 全部用户可见文字必须是简体中文（女优名用华语圈常用译名）。
2. tags/categories 从题材、玩法、人数、片商风格等归纳，简洁（每项 2–8 字），去重。
3. actresses 只能翻译输入里已有的演员（按 name_original/name 对应），禁止新增或替换成无关女优；男优 gender=male。
4. title 必须与原标题/演员一致，禁止换成其他作品或无关女优。
5. 只输出一个 JSON 对象。"""


@dataclass
class AIConfig:
    api_key: str = ""
    base_url: str = DEFAULT_AI_BASE_URL
    model: str = DEFAULT_AI_MODEL
    timeout: float = 60.0
    enabled: bool = True

    @property
    def available(self) -> bool:
        return bool(self.enabled and self.api_key.strip())

    @classmethod
    def resolve(cls, settings_store: "SettingsStore | None" = None) -> "AIConfig":
        from .settings import effective_ai_fields

        fields = effective_ai_fields(settings_store)
        key = fields["ai_api_key"].value.strip()
        base = (fields["ai_base_url"].value or DEFAULT_AI_BASE_URL).rstrip("/")
        model = fields["ai_model"].value or DEFAULT_AI_MODEL
        enabled_raw = fields["ai_enabled"].value
        enabled_flag = parse_bool(enabled_raw, default=None) if enabled_raw != "" else None
        enabled = bool(key) if enabled_flag is None else enabled_flag
        try:
            timeout = float(fields["ai_timeout"].value or "60")
        except (TypeError, ValueError):
            timeout = 60.0
        return cls(api_key=key, base_url=base, model=model, timeout=timeout, enabled=enabled)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "enabled": self.enabled,
            "configured": bool(self.api_key.strip()),
            "base_url": self.base_url,
            "model": self.model,
            "provider_hint": _provider_hint(self.base_url),
        }


def _provider_hint(base_url: str) -> str:
    u = (base_url or "").lower()
    if "x.ai" in u:
        return "xAI"
    if "openai.com" in u:
        return "OpenAI"
    if "deepseek" in u:
        return "DeepSeek"
    return "OpenAI-compatible"


def entry_to_ai_payload(entry: MovieEntry) -> dict[str, Any]:
    return {
        "code": entry.code,
        "title": entry.title,
        "title_original": entry.title_original,
        "actresses": [a.to_dict() for a in entry.actresses],
        "tags": list(entry.tags or []),
        "categories": list(entry.categories or []),
        "studio": entry.studio,
        "director": entry.director,
        "series": entry.series,
        "release_date": entry.release_date,
        "duration_minutes": entry.duration_minutes,
    }


def extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty AI response")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("AI JSON root must be object")
    return data


def _norm_key(s: str) -> str:
    return (s or "").strip().lower()


def _parse_ai_actress_item(item: Any) -> tuple[str, str, str] | None:
    if isinstance(item, str):
        raw = item.strip()
        if not raw:
            return None
        name = to_simplified(raw)
        return (name or raw, raw, "female")
    if isinstance(item, dict):
        name_o = str(item.get("name_original") or item.get("name") or "").strip()
        name = to_simplified(str(item.get("name") or name_o).strip())
        gender = str(item.get("gender") or "female").lower()
        if gender not in ("female", "male", "unknown"):
            gender = "female"
        if not (name or name_o):
            return None
        return (name or name_o, name_o or name, gender)
    return None


def merge_actress_translations(base: list[Actress], ai_raw: Any) -> list[Actress]:
    if not isinstance(ai_raw, list) or not ai_raw:
        return list(base)

    by_key: dict[str, tuple[str, str]] = {}
    for item in ai_raw:
        parsed = _parse_ai_actress_item(item)
        if not parsed:
            continue
        display, original, gender = parsed
        for key in (_norm_key(original), _norm_key(display)):
            if key and key not in by_key:
                by_key[key] = (display, gender)

    out: list[Actress] = []
    for a in base:
        orig = a.name_original or a.name
        hit = by_key.get(_norm_key(orig)) or by_key.get(_norm_key(a.name))
        if hit:
            display, gender = hit
            out.append(
                Actress(
                    name=display or a.name,
                    name_original=orig,
                    gender=gender if gender != "unknown" else a.gender,
                )
            )
        else:
            out.append(a)
    return out


def apply_ai_result(entry: MovieEntry, ai_data: dict[str, Any]) -> MovieEntry:
    title = to_simplified(str(ai_data.get("title") or "").strip()) or entry.title
    actresses = merge_actress_translations(entry.actresses, ai_data.get("actresses"))
    tags_ai = ai_data.get("tags") if isinstance(ai_data.get("tags"), list) else []
    cats_ai = ai_data.get("categories") if isinstance(ai_data.get("categories"), list) else []
    return entry.evolve(
        title=title,
        title_original=entry.title_original or entry.title,
        actresses=actresses,
        tags=merge_labels(entry.tags, [str(x) for x in tags_ai]),
        categories=merge_labels(entry.categories, [str(x) for x in cats_ai]),
        studio=to_simplified(entry.studio) if entry.studio else "",
        director=to_simplified(entry.director) if entry.director else "",
        series=to_simplified(entry.series) if entry.series else "",
    )


@dataclass
class AIMeta:
    used: bool = False
    error: str = ""
    provider: dict[str, Any] = field(default_factory=dict)


class AIClient:
    def __init__(
        self,
        config: AIConfig,
        *,
        post: Callable[..., requests.Response] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> None:
        """AI HTTP client. Proxy is injected; never self-resolved.

        proxies=None or {} means direct. Callers pass resolve_proxy_dict(...) from the root.
        """
        self.config = config
        self._proxies = dict(proxies) if proxies else {}
        self._post = post

    @classmethod
    def from_settings(
        cls,
        settings_store: "SettingsStore | None" = None,
        *,
        post: Callable[..., requests.Response] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> "AIClient":
        """Build from settings/env AI config. Proxy must be passed in (default direct)."""
        return cls(AIConfig.resolve(settings_store), post=post, proxies=proxies)

    @property
    def available(self) -> bool:
        return self.config.available

    def _http_post(self, url: str, **kwargs: Any) -> requests.Response:
        if self._post is not None:
            return self._post(url, **kwargs)
        # trust_env=False so empty proxies truly means direct (no ambient HTTP_PROXY).
        with requests.Session() as session:
            session.trust_env = False
            if self._proxies:
                session.proxies.update(self._proxies)
            return session.post(url, **kwargs)

    def chat_json(self, user_content: str) -> dict[str, Any]:
        if not self.config.available:
            raise RuntimeError("AI not configured (set JAVCODE_AI_API_KEY or XAI_API_KEY / OPENAI_API_KEY)")
        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.config.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        resp = self._http_post(
            url,
            headers=headers,
            json=body,
            timeout=self.config.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"AI API HTTP {resp.status_code}: {resp.text[:300]}")
        payload = resp.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected AI response shape: {payload!r}") from exc
        return extract_json_object(content)

    def enrich_metadata(self, entry: MovieEntry) -> MovieEntry:
        user = (
            "请将以下 AV 元数据翻译为简体中文，并补充合适的分类与标签。"
            "actresses 仅翻译已有演员，不要新增：\n"
            + json.dumps(entry_to_ai_payload(entry), ensure_ascii=False, indent=2)
        )
        return apply_ai_result(entry, self.chat_json(user))


def ai_enrich_entry(
    entry: MovieEntry,
    *,
    client: AIClient | None = None,
) -> tuple[MovieEntry, AIMeta]:
    meta = AIMeta(provider=client.config.to_public_dict() if client is not None else {})
    if client is None or not client.available:
        meta.error = "ai not configured"
        return entry, meta
    try:
        return client.enrich_metadata(entry), AIMeta(used=True, provider=meta.provider)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI enrich failed: %s", exc)
        meta.error = str(exc)
        return entry, meta
