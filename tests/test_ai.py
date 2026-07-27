from __future__ import annotations

import json
from unittest.mock import MagicMock

from src.ai import (
    AIClient,
    AIConfig,
    ai_enrich_entry,
    apply_ai_result,
    extract_json_object,
    merge_labels,
)
from src.enrich import enrich_from_html, post_process
from src.models import Actress, MovieEntry
from src.parsers import parse_javdb_detail
from tests.sample_html import JAVDB_DETAIL_SSIS, JAVDB_DETAIL_STARS


def test_extract_json_object_plain_and_fenced():
    assert extract_json_object('{"title": "甲"}')["title"] == "甲"
    fenced = '```json\n{"title": "乙", "tags": ["剧情"]}\n```'
    assert extract_json_object(fenced)["tags"] == ["剧情"]


def test_apply_ai_result_merges_zh_fields():
    base = MovieEntry(
        code="SSIS-001",
        title="日文原题残留",
        title_original="origin JP",
        actresses=[
            Actress(name="葵つかさ", name_original="葵つかさ", gender="female"),
            Actress(name="乙白さやか", name_original="乙白さやか", gender="female"),
        ],
        tags=["美乳"],
        categories=["S1"],
    )
    ai = {
        "title": "禁欲后与室友的三日出轨",
        "actresses": [
            {"name": "葵司", "name_original": "葵つかさ", "gender": "female"},
            {"name": "乙白沙也加", "name_original": "乙白さやか", "gender": "female"},
        ],
        "tags": ["NTR", "共演", "美乳"],
        "categories": ["剧情向", "S1"],
    }
    out = apply_ai_result(base, ai)
    assert out.title == "禁欲后与室友的三日出轨"
    assert "三上" not in out.title
    names = [a.name for a in out.actresses]
    assert "葵司" in names and "乙白沙也加" in names
    assert "NTR" in out.tags or "共演" in out.tags
    assert "美乳" in out.tags
    assert out.title_original == "origin JP"


def test_apply_ai_result_does_not_invent_cast():
    from src.ai import merge_actress_translations

    base = [
        Actress(name="葵つかさ", name_original="葵つかさ", gender="female"),
    ]
    ai_raw = [
        {"name": "葵司", "name_original": "葵つかさ", "gender": "female"},
        {"name": "三上悠亚", "name_original": "三上悠亜", "gender": "female"},
    ]
    merged = merge_actress_translations(base, ai_raw)
    assert len(merged) == 1
    assert merged[0].name == "葵司"
    assert merged[0].name_original == "葵つかさ"
    assert all("三上" not in a.name for a in merged)


def test_ai_client_enrich_metadata_uses_chat_completions():
    ai_json = {
        "title": "温泉一日甜蜜共浴",
        "actresses": [{"name": "飞鸟铃", "name_original": "飛鳥りん", "gender": "female"}],
        "tags": ["温泉", "主观视角"],
        "categories": ["SOD作品"],
    }
    response_body = {
        "choices": [{"message": {"content": json.dumps(ai_json, ensure_ascii=False)}}]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response_body
    mock_resp.text = json.dumps(response_body)

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"].startswith("Bearer test-key")
        assert json["model"] == "test-model"
        return mock_resp

    client = AIClient(
        AIConfig(api_key="test-key", base_url="https://example.test/v1", model="test-model"),
        post=fake_post,
    )
    entry = MovieEntry(
        code="STARS-001",
        title="raw",
        title_original="飛鳥りん 温泉",
        actresses=[Actress(name="飛鳥りん", name_original="飛鳥りん")],
        tags=["溫泉"],
    )
    out = client.enrich_metadata(entry)
    assert out.title == "温泉一日甜蜜共浴"
    assert out.actresses[0].name == "飞鸟铃"
    assert "温泉" in out.tags or "主观视角" in out.tags


def test_ai_enrich_entry_skips_without_key():
    entry = MovieEntry(code="X-1", title="t", actresses=[Actress(name="a")], tags=["b"])
    client = AIClient(AIConfig(api_key="", enabled=True))
    out, meta = ai_enrich_entry(entry, client=client)
    assert meta.used is False
    assert out is entry or out.title == entry.title


def test_ai_enrich_entry_skips_without_client():
    entry = MovieEntry(code="X-1", title="t", actresses=[Actress(name="a")], tags=["b"])
    out, meta = ai_enrich_entry(entry, client=None)
    assert meta.used is False
    assert out is entry
    assert meta.error == "ai not configured"


def test_ai_enrich_entry_failure_falls_back():
    def boom_post(*args, **kwargs):
        raise ConnectionError("network down")

    client = AIClient(
        AIConfig(api_key="k", base_url="https://example.test/v1", model="m"),
        post=boom_post,
    )
    entry = MovieEntry(code="X-1", title="保留", actresses=[Actress(name="甲")], tags=["剧情"])
    out, meta = ai_enrich_entry(entry, client=client)
    assert meta.used is False
    assert meta.error
    assert out.title == "保留"


def test_post_process_with_mock_ai():
    raw = parse_javdb_detail(JAVDB_DETAIL_SSIS, code="SSIS-001")
    ai_payload = {
        "title": "禁欲一个月后与女友室友的三日出轨",
        "actresses": [
            {"name": "葵司", "name_original": "葵つかさ", "gender": "female"},
            {"name": "乙白沙也加", "name_original": "乙白さやか", "gender": "female"},
        ],
        "tags": ["出轨", "共演", "美乳", "NTR"],
        "categories": ["剧情", "S1作品"],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(ai_payload, ensure_ascii=False)}}]
    }

    client = AIClient(
        AIConfig(api_key="k", base_url="https://example.test/v1", model="m"),
        post=lambda *a, **k: mock_resp,
    )
    entry, meta = post_process(raw, ai_client=client)
    assert meta.used is True
    assert "禁欲" in entry.title or "出轨" in entry.title
    assert "三上" not in entry.title
    assert any(a.name == "葵司" for a in entry.actresses)
    assert entry.tags


def test_enrich_from_html_ai_flag_in_result(tmp_path):
    ai_payload = {
        "title": "飞鸟铃毕业温泉一日十二发",
        "actresses": [{"name": "飞鸟铃", "name_original": "飛鳥りん", "gender": "female"}],
        "tags": ["温泉", "主观", "甜蜜"],
        "categories": ["SOD star"],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(ai_payload, ensure_ascii=False)}}]
    }
    client = AIClient(
        AIConfig(api_key="k", base_url="https://example.test/v1", model="m"),
        post=lambda *a, **k: mock_resp,
    )
    from src.store import CollectionStore

    store = CollectionStore(tmp_path / "ai.db")
    result = enrich_from_html(
        JAVDB_DETAIL_STARS,
        "STARS-001",
        source="javdb",
        store=store,
        persist=True,
        ai_client=client,
    )
    assert result.ok
    assert result.ai_used is True
    assert "飞鸟" in result.entry.title or "温泉" in result.entry.title


def test_api_boundary_maps_use_ai_to_client(tmp_path):
    from src.server import create_app
    from src.fetchers import FetchResult
    from src.parsers import parse_javdb_detail

    calls = {"n": 0}

    def tracking_post(*a, **k):
        calls["n"] += 1
        raise AssertionError("AI should not be called when use_ai=false")

    class FakeFetcher:
        def fetch(self, code, prefer="javdb"):
            entry = parse_javdb_detail(JAVDB_DETAIL_SSIS, code=code)
            return FetchResult(ok=True, entry=entry, source="javdb", url="https://javdb.com/v/x")

    client_ai = AIClient(
        AIConfig(api_key="secret-key", base_url="https://x.test/v1", model="g"),
        post=tracking_post,
    )
    app = create_app(db_path=tmp_path / "s.db", ai_client=client_ai, fetcher=FakeFetcher())  # type: ignore[arg-type]
    c = app.test_client()
    c.post("/api/auth/setup", json={"username": "admin", "password": "testpass"})
    r = c.get("/api/ai/status")
    body = r.get_json()
    assert body["ok"] is True
    assert body["ai"]["available"] is True
    assert body["ai"]["configured"] is True
    assert "secret-key" not in json.dumps(body)

    r = c.get("/api/health")
    assert "ai" in r.get_json()

    r = c.post(
        "/api/enrich",
        json={"code": "SSIS-001", "use_ai": False, "persist": True},
    )
    data = r.get_json()
    assert data["ok"] is True
    assert data["ai_used"] is False
    assert calls["n"] == 0


def test_merge_labels_dedup():
    assert merge_labels(["美乳", "剧情"], ["美乳", "NTR"]) == ["美乳", "剧情", "NTR"]


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("JAVCODE_AI_API_KEY", "abc")
    monkeypatch.setenv("JAVCODE_AI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("JAVCODE_AI_MODEL", "gpt-4o-mini")
    cfg = AIConfig.from_env()
    assert cfg.available
    assert cfg.model == "gpt-4o-mini"
    assert "openai.com" in cfg.base_url
    monkeypatch.setenv("JAVCODE_AI_ENABLED", "0")
    cfg2 = AIConfig.from_env()
    assert cfg2.available is False
