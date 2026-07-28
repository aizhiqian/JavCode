from __future__ import annotations

import pytest

from src.classify import classify
from src.enrich import enrich_code, enrich_from_html
from src.env import ROOT
from src.models import Actress, MovieEntry
from src.normalize import normalize_code
from src.media import normalize_cover_url
from src.parsers import (
    ParseError,
    parse_javdb_detail,
    parse_javdb_search,
    parse_javlibrary_detail,
)
from src.relationships import actress_index, name_pinyin_meta
from src.search import label_index, search_library
from src.store import CollectionStore
from src.translate import ensure_zh_fields, normalize_entry, to_simplified
from tests.sample_html import (
    JAVDB_DETAIL_SSIS,
    JAVDB_DETAIL_STARS,
    JAVDB_SEARCH_SSIS,
    JAVLIBRARY_DETAIL_SSIS,
)


def test_normalize_code_variants():
    assert normalize_code("ssis001") == "SSIS-001"
    assert normalize_code("SSIS-001") == "SSIS-001"
    assert normalize_code("  ssis 001 ") == "SSIS-001"


def test_normalize_cover_url_upgrades_known_thumbs():
    assert (
        normalize_cover_url("https://c0.jdbstatic.com/thumbs/zy/ZY5eq.jpg")
        == "https://c0.jdbstatic.com/covers/zy/ZY5eq.jpg"
    )
    assert normalize_cover_url("//c0.jdbstatic.com/thumbs/ab/Abc.jpg").startswith("https:")
    assert "/covers/" in normalize_cover_url("//c0.jdbstatic.com/thumbs/ab/Abc.jpg")
    assert (
        normalize_cover_url("https://pics.dmm.co.jp/digital/video/ssis001/ssis001ps.jpg")
        == "https://pics.dmm.co.jp/digital/video/ssis001/ssis001pl.jpg"
    )
    assert normalize_cover_url("https://example.com/cover_s.jpg") == "https://example.com/cover_b.jpg"
    assert normalize_cover_url("https://c0.jdbstatic.com/covers/zy/ZY5eq.jpg").endswith(
        "/covers/zy/ZY5eq.jpg"
    )
    assert normalize_cover_url("") == ""


def test_parse_javdb_prefers_full_cover_over_thumb():
    entry = parse_javdb_detail(JAVDB_DETAIL_SSIS, code="SSIS-001")
    assert entry.cover_url == "https://c0.jdbstatic.com/covers/zy/ZY5eq.jpg"
    assert "/thumbs/" not in entry.cover_url


def test_store_upgrades_thumb_cover_on_write_and_legacy_read(tmp_path):
    store = CollectionStore(tmp_path / "t.db")
    store.upsert(
        MovieEntry(
            code="SSIS-001",
            title="t",
            cover_url="https://c0.jdbstatic.com/thumbs/zy/ZY5eq.jpg",
            source="javdb",
        )
    )
    got = store.get_by_code("SSIS-001")
    assert got is not None
    assert got.cover_url == "https://c0.jdbstatic.com/covers/zy/ZY5eq.jpg"

    # Legacy row written before canonicalize-on-write still upgrades on read.
    import sqlite3

    with sqlite3.connect(str(tmp_path / "t.db")) as conn:
        conn.execute(
            "UPDATE movies SET cover_url = ? WHERE code = ?",
            ("https://c0.jdbstatic.com/thumbs/zy/ZY5eq.jpg", "SSIS-001"),
        )
    legacy = store.get_by_code("SSIS-001")
    assert legacy is not None
    assert legacy.cover_url == "https://c0.jdbstatic.com/covers/zy/ZY5eq.jpg"


def test_parse_javdb_detail_multi_actress():
    entry = parse_javdb_detail(JAVDB_DETAIL_SSIS, code="SSIS-001", source_url="https://javdb.com/v/ZY5eq")
    assert entry.code == "SSIS-001"
    assert entry.title or entry.title_original
    females = [a for a in entry.actresses if a.gender != "male"]
    assert len(females) >= 2
    names = {a.name for a in females}
    assert "葵つかさ" in names
    assert "乙白さやか" in names
    assert len(entry.tags) >= 2
    assert entry.cover_url.startswith("http")
    assert entry.source == "javdb"
    assert "三上" not in entry.title
    assert "三上" not in (entry.title_original or "")
    assert "禁欲" in entry.title or "禁欲" in entry.title_original


def test_parse_javdb_search_finds_detail_path():
    path = parse_javdb_search(JAVDB_SEARCH_SSIS, "SSIS-001")
    assert path and path.startswith("/v/")


def test_parse_javdb_stars():
    entry = parse_javdb_detail(JAVDB_DETAIL_STARS, code="STARS-001")
    assert entry.code == "STARS-001"
    assert any("飛鳥" in a.name or "飞鸟" in a.name for a in entry.actresses) or entry.actresses
    assert entry.tags


def test_parse_javlibrary():
    entry = parse_javlibrary_detail(JAVLIBRARY_DETAIL_SSIS, code="SSIS-001")
    assert entry.code == "SSIS-001"
    assert entry.title
    assert len(entry.actresses) >= 2
    assert entry.tags
    assert entry.source == "javlibrary"


def test_parse_blocked_page_fails_honestly():
    blocked = "<html><title>Just a moment...</title><div id='cf-browser-verification'></div></html>"
    with pytest.raises(ParseError):
        parse_javlibrary_detail(blocked, code="SSIS-001")


def test_normalize_and_classify_keep_source_and_rules():
    raw = parse_javdb_detail(JAVDB_DETAIL_SSIS, code="SSIS-001")
    zh = normalize_entry(raw)
    classified = classify(zh)
    assert ensure_zh_fields(classified)
    names = [a.name for a in classified.actresses if a.gender != "male"]
    assert names
    assert any(a.name_original for a in classified.actresses)
    assert classified.tags or classified.categories
    assert "多女优" in classified.tags or "共演" in classified.tags
    assert classified.studio
    assert classified.code == "SSIS-001"


def test_enrich_from_html_pipeline_persists(tmp_path):
    store = CollectionStore(tmp_path / "t.db")
    result = enrich_from_html(
        JAVDB_DETAIL_SSIS,
        "SSIS-001",
        source="javdb",
        source_url="https://javdb.com/v/ZY5eq",
        store=store,
        persist=True,
    )
    assert result.ok, result.error
    assert result.entry is not None
    assert result.persisted
    assert result.entry.title
    assert result.entry.actresses
    assert result.entry.tags
    assert "三上" not in result.entry.title
    polluted = search_library(store.list_all(), query="三上悠亚")
    assert all(e.code != "SSIS-001" for e in polluted)
    cast_needle = next(
        (a.name_original or a.name for a in result.entry.actresses if a.gender != "male"),
        "",
    )
    assert cast_needle
    by_actress = search_library(store.list_all(), actress=cast_needle)
    assert any(e.code == "SSIS-001" for e in by_actress)
    saved = store.get_by_code("SSIS-001")
    assert saved is not None
    assert saved.title == result.entry.title


def test_resolve_javdb_titles_unit():
    from src.parsers import resolve_javdb_titles, title_consistent_with_origin_or_cast

    origin = "一ヶ月間の禁欲の果てに彼女のルームメイト2人と浮気SEXだけに没頭した彼女不在の3日間。 葵つかさ 乙白さやか"
    wrong = "刺激您五感的三上悠亞頂級自慰協助 讓腦袋充滿快感的6個療癒勃起場景"
    cast = ["葵つかさ", "乙白さやか"]
    assert not title_consistent_with_origin_or_cast(wrong, origin, cast)
    title, orig = resolve_javdb_titles(wrong, origin, cast)
    assert title == origin
    assert orig == origin
    assert "三上" not in title

    stars_origin = "飛鳥りん 卒業 日帰りで12発射精しちゃうヤリまくりイチャイチャ温泉旅行"
    stars_current = "幹翻12砲甜蜜溫泉一日遊 飛鳥鈴"
    assert title_consistent_with_origin_or_cast(stars_current, stars_origin, ["飛鳥りん"])
    t2, o2 = resolve_javdb_titles(stars_current, stars_origin, ["飛鳥りん"])
    assert t2 == stars_current
    assert o2 == stars_origin


def test_enrich_stars_and_search_filter(tmp_path):
    store = CollectionStore(tmp_path / "lib.db")
    r1 = enrich_from_html(
        JAVDB_DETAIL_SSIS,
        "SSIS-001",
        source="javdb",
        store=store,
        persist=True,
    )
    r2 = enrich_from_html(
        JAVDB_DETAIL_STARS,
        "STARS-001",
        source="javdb",
        store=store,
        persist=True,
    )
    assert r1.ok and r2.ok
    lib = store.list_all()
    assert len(lib) >= 2

    by_code = search_library(lib, code="SSIS-001")
    assert len(by_code) == 1
    assert by_code[0].code == "SSIS-001"

    actress_name = r1.entry.actress_names()[0]
    by_actress = search_library(lib, actress=actress_name)
    assert len(by_actress) >= 1

    tag = (r2.entry.tags or r2.entry.categories or [None])[0]
    assert tag
    by_tag = search_library(lib, tag=tag)
    assert len(by_tag) >= 1

    by_q = search_library(lib, query="STARS")
    assert any(e.code == "STARS-001" for e in by_q)


def test_label_index_aggregates_tags_and_categories():
    entries = [
        MovieEntry(code="A-1", title="一", tags=["美乳", "剧情"], categories=["单体作品"]),
        MovieEntry(code="B-2", title="二", tags=["美乳"], categories=["共演"]),
        MovieEntry(code="C-3", title="三", tags=["美乳", "NTR"], categories=["单体作品"]),
    ]
    idx = label_index(entries)
    tags = {item["name"]: item for item in idx["tags"]}
    cats = {item["name"]: item for item in idx["categories"]}
    assert tags["美乳"]["count"] == 3
    assert set(tags["美乳"]["codes"]) == {"A-1", "B-2", "C-3"}
    assert tags["剧情"]["count"] == 1
    assert cats["单体作品"]["count"] == 2
    assert cats["共演"]["count"] == 1
    assert idx["tags"][0]["name"] == "美乳"


def test_name_pinyin_meta_initials():
    kui = name_pinyin_meta("葵司")
    assert kui["initial"] == "K"
    assert "kui" in kui["pinyin_key"]
    san = name_pinyin_meta("三上悠亚")
    assert san["initial"] == "S"
    assert name_pinyin_meta("Yua Mikami")["initial"] == "Y"
    assert name_pinyin_meta("***")["initial"] == "#"
    items = actress_index(
        [
            MovieEntry(
                code="T-1",
                title="t",
                actresses=[Actress(name="飞鸟铃", name_original="飛鳥りん")],
                tags=["x"],
            )
        ]
    )
    assert items[0]["initial"] == "F"
    assert "fei" in items[0]["pinyin_key"]
    assert "partners" not in items[0]


def test_enrich_live_path_no_false_success_on_bad_fetcher(tmp_path):
    class BoomFetcher:
        def fetch(self, code, prefer="javdb"):
            from src.fetchers import FetchResult

            return FetchResult(ok=False, error="simulated network block", source="javdb", url="https://javdb.com/x")

    store = CollectionStore(tmp_path / "fail.db")
    result = enrich_code(
        "SSIS-001",
        store=store,
        persist=True,
        fetcher=BoomFetcher(),  # type: ignore[arg-type]
    )
    assert result.ok is False
    assert result.error
    assert store.get_by_code("SSIS-001") is None


def test_to_simplified_traditional_only():
    assert "温泉" in to_simplified("溫泉")
    assert to_simplified("單體作品") == "单体作品"
    assert to_simplified("葵つかさ") == "葵つかさ"


def test_ui_static_structure():
    public = ROOT / "public"
    html = (public / "index.html").read_text(encoding="utf-8")
    css_dir = public / "css"
    js_dir = public / "js"
    css = "\n".join(p.read_text(encoding="utf-8") for p in sorted(css_dir.glob("*.css")))
    js = "\n".join(p.read_text(encoding="utf-8") for p in sorted(js_dir.glob("*.js")))
    app_js = (js_dir / "app.js").read_text(encoding="utf-8")
    router_js = (js_dir / "router.js").read_text(encoding="utf-8")

    expected_js = [
        "app.js",
        "router.js",
        "state.js",
        "api.js",
        "util.js",
        "auth.js",
        "ai-status.js",
        "catalog.js",
        "detail.js",
        "labels.js",
        "actresses.js",
        "add.js",
        "settings.js",
    ]
    for name in expected_js:
        assert (js_dir / name).is_file(), f"missing public/js/{name}"

    expected_css = [
        "base.css",
        "layout.css",
        "components.css",
        "catalog.css",
        "detail.css",
        "labels.css",
        "actresses.css",
        "forms.css",
        "auth.css",
    ]
    for name in expected_css:
        assert (css_dir / name).is_file(), f"missing public/css/{name}"
        assert f'href="css/{name}"' in html, f"index.html missing link for {name}"

    assert 'id="catalogGrid"' in html
    assert 'id="catalogPager"' in html
    assert 'id="actressPager"' in html
    assert 'id="actressPinyinInput"' in html
    assert 'id="actressInitialBar"' in html
    assert 'id="view-detail"' in html
    assert 'id="searchInput"' in html
    assert 'id="enrichForm"' in html
    assert 'type="module" src="js/app.js"' in html
    assert "女优与共演" not in html

    assert "card-grid" in css
    assert "actress-grid" in css
    assert "initial-bar" in css
    assert "detail-layout" in css
    assert "hero-banner" in css
    assert ".movie-card" in (css_dir / "components.css").read_text(encoding="utf-8")
    assert ".pager" in (css_dir / "components.css").read_text(encoding="utf-8")
    assert ".form-status" in (css_dir / "components.css").read_text(encoding="utf-8")
    assert ".tag-cloud" in (css_dir / "components.css").read_text(encoding="utf-8")

    assert "CATALOG_PAGE_SIZE" in js
    assert "ACTRESS_PAGE_SIZE" in js
    assert "actressPinyinQ" in js
    assert "共演：" not in js
    assert "fixture" not in js.lower()
    assert "/api/enrich" in js
    assert "/api/movies" in js
    assert "/api/relationships" not in js
    assert "registerRoute" not in js
    assert "export function setRoutes" in router_js
    assert "export function goCatalog" in router_js
    assert "export function goDetail" in router_js
    assert "setRoutes({" in app_js
    for handler in (
        "onCatalog",
        "onDetail",
        "onLabels",
        "onActresses",
        "onAdd",
        "onSettings",
    ):
        assert handler in app_js, f"app.js must wire {handler}"
    assert 'from "./ai-status.js"' in app_js
    assert 'from "./catalog.js"' not in (js_dir / "detail.js").read_text(encoding="utf-8")
    assert 'from "./catalog.js"' not in (js_dir / "labels.js").read_text(encoding="utf-8")
    assert 'from "./catalog.js"' not in (js_dir / "actresses.js").read_text(
        encoding="utf-8"
    )
    assert 'from "./add.js"' not in (js_dir / "settings.js").read_text(encoding="utf-8")
    assert "from \"./state.js\"" not in (js_dir / "api.js").read_text(encoding="utf-8")


def test_flask_api_search_and_labels(tmp_path):
    from src.server import create_app

    db = tmp_path / "api.db"
    app = create_app(db_path=db)
    client = app.test_client()
    client.post("/api/auth/setup", json={"username": "admin", "password": "testpass"})

    store = app.config["STORE"]
    enrich_from_html(JAVDB_DETAIL_SSIS, "SSIS-001", source="javdb", store=store, persist=True)
    enrich_from_html(JAVDB_DETAIL_STARS, "STARS-001", source="javdb", store=store, persist=True)

    r = client.get("/api/movies")
    assert r.status_code == 200
    body = r.get_json()
    assert body["count"] >= 2

    r = client.get("/api/movies?code=SSIS-001")
    assert r.get_json()["count"] == 1

    actress = store.get_by_code("SSIS-001").actress_names()[0]
    r = client.get(f"/api/movies?actress={actress}")
    assert r.get_json()["count"] >= 1

    tag = store.get_by_code("STARS-001").tags[0]
    r = client.get(f"/api/movies?tag={tag}")
    assert r.get_json()["count"] >= 1

    r = client.get("/")
    assert r.status_code == 200
    assert b"catalogGrid" in r.data

    r = client.get("/api/relationships")
    assert r.status_code == 404

    r = client.get("/api/labels")
    assert r.status_code == 200
    labels = r.get_json()
    assert labels["ok"] is True
    assert isinstance(labels.get("tags"), list)

    r = client.patch(
        "/api/movies/SSIS-001/labels",
        json={"tags": ["自定义标签", "美乳"], "categories": ["我的分类"]},
    )
    assert r.status_code == 200
    patched = r.get_json()["item"]
    assert patched["tags"] == ["自定义标签", "美乳"]
    assert patched["categories"] == ["我的分类"]

    r = client.patch("/api/movies/SSIS-001/labels", json={"tags": ["仅标签"]})
    assert r.status_code == 200
    assert r.get_json()["item"]["tags"] == ["仅标签"]
    assert r.get_json()["item"]["categories"] == ["我的分类"]

    r = client.patch("/api/movies/NOPE-000/labels", json={"tags": []})
    assert r.status_code == 404

    r = client.delete("/api/movies/SSIS-001")
    assert r.status_code == 200
    assert store.get_by_code("SSIS-001") is None

    r = client.delete("/api/movies/SSIS-001")
    assert r.status_code == 404
