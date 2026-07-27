from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .models import Actress, MovieEntry
from .normalize import normalize_code


class ParseError(ValueError):
    pass


def _text(el: Tag | None) -> str:
    if el is None:
        return ""
    return " ".join(el.get_text(" ", strip=True).split())


def normalize_cover_url(url: str) -> str:
    if not url:
        return ""
    u = str(url).strip()
    if u.startswith("//"):
        u = "https:" + u
    if "jdbstatic.com" in u and "/thumbs/" in u:
        u = u.replace("/thumbs/", "/covers/")
    u = re.sub(r"ps\.(jpe?g)(\?.*)?$", r"pl.\1\2", u, flags=re.IGNORECASE)
    u = re.sub(r"_s\.(jpe?g)(\?.*)?$", r"_b.\1\2", u, flags=re.IGNORECASE)
    return u


def _looks_like_image_url(url: str) -> bool:
    if not url:
        return False
    low = url.lower().split("?", 1)[0]
    if any(low.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return True
    return any(host in low for host in ("jdbstatic.com", "pics.dmm", "javbus", "pics.jav"))


def _extract_javdb_cover(soup: BeautifulSoup) -> str:
    candidates: list[str] = []
    col = soup.select_one(".column-video-cover")
    if col:
        for a in col.select("a[href]"):
            href = (a.get("href") or "").strip()
            if href and _looks_like_image_url(href):
                candidates.append(href)
        img = col.select_one("img")
        if img:
            for attr in ("data-src", "data-original", "src"):
                val = (img.get(attr) or "").strip()
                if val:
                    candidates.append(val)
                    break
    og = soup.select_one('meta[property="og:image"]')
    if og and og.get("content"):
        candidates.append(og["content"].strip())

    normalized = [normalize_cover_url(c) for c in candidates if c]
    for n in normalized:
        if n and "/thumbs/" not in n:
            return n
    return normalized[0] if normalized else ""


def _panel_value(soup: BeautifulSoup, label_keywords: tuple[str, ...]) -> Tag | None:
    for block in soup.select(".movie-panel-info .panel-block, .panel-block"):
        strong = block.find("strong")
        if not strong:
            continue
        label = strong.get_text(strip=True).rstrip(":")
        if any(k in label for k in label_keywords):
            return block.select_one("span.value") or block
    return None


def _cjk_tokens(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff]{2,}", text)


def title_consistent_with_origin_or_cast(
    current: str,
    origin: str,
    cast_names: list[str],
) -> bool:
    current = (current or "").strip()
    if not current:
        return False
    origin = (origin or "").strip()
    names = [n.strip() for n in cast_names if n and n.strip()]
    if not origin and not names:
        return True

    for name in names:
        if name in current:
            return True
        if len(name) >= 2 and name[:2] in current:
            return True

    if origin:
        origin_tokens = _cjk_tokens(origin)
        if not origin_tokens:
            return False
        hits = sum(1 for t in origin_tokens if t in current)
        if hits >= 2:
            return True
        for t in sorted(origin_tokens, key=len, reverse=True):
            if len(t) >= 4 and t in current:
                return True
    return False


def resolve_javdb_titles(
    current: str,
    origin: str,
    cast_names: list[str],
) -> tuple[str, str]:
    current = (current or "").strip()
    origin = (origin or "").strip()
    title_original = origin or current
    if origin:
        title = (
            current
            if current and title_consistent_with_origin_or_cast(current, origin, cast_names)
            else origin
        )
    else:
        title = current
    return title, title_original


def parse_javdb_search(html: str, code: str) -> str | None:
    if not html or len(html) < 200:
        raise ParseError("JavDB search response empty or too short")
    soup = BeautifulSoup(html, "lxml")
    want = normalize_code(code)
    if not want:
        return None
    best: str | None = None
    for item in soup.select(".movie-list .item, div.item"):
        link = item.select_one("a.box[href]")
        title_el = item.select_one(".video-title")
        if not link or not title_el:
            continue
        title_text = _text(title_el)
        strong = title_el.find("strong")
        item_code = normalize_code(_text(strong) if strong else title_text.split()[0])
        href = link.get("href") or ""
        if item_code == want and href.startswith("/v/"):
            return href
        if want.replace("-", "") in title_text.upper().replace("-", "") and href.startswith("/v/"):
            best = best or href
    return best


def parse_javdb_detail(html: str, code: str = "", source_url: str = "") -> MovieEntry:
    if not html or len(html) < 500:
        raise ParseError("JavDB detail response empty or too short")
    if "Just a moment" in html and "cf-browser-verification" in html:
        raise ParseError("JavDB detail blocked by challenge page")
    soup = BeautifulSoup(html, "lxml")

    code_val = ""
    code_block = _panel_value(soup, ("番號", "番号", "Code", "ID"))
    if code_block:
        raw = _text(code_block).replace("複製番號", "").replace("复制番号", "")
        code_val = normalize_code(raw)
    if not code_val:
        h2 = soup.select_one("h2.title strong")
        code_val = normalize_code(_text(h2)) if h2 else ""
    if not code_val:
        code_val = normalize_code(code)
    if not code_val:
        raise ParseError("Could not extract 番号 from JavDB detail page")

    cover = _extract_javdb_cover(soup)

    release_date = _text(_panel_value(soup, ("日期", "Date")))
    duration_raw = _text(_panel_value(soup, ("時長", "时长", "Duration")))
    duration_minutes = None
    dm = re.search(r"(\d+)", duration_raw)
    if dm:
        duration_minutes = int(dm.group(1))

    director = ""
    dval = _panel_value(soup, ("導演", "导演", "Director"))
    if dval:
        director = _text(dval)

    studio = ""
    for key in ("片商", "Maker", "Studio"):
        sval = _panel_value(soup, (key,))
        if sval:
            studio = _text(sval)
            break

    series = ""
    ser = _panel_value(soup, ("系列", "Series"))
    if ser:
        series = _text(ser)

    score = None
    score_el = _panel_value(soup, ("評分", "评分", "Score"))
    if score_el:
        sm = re.search(r"([\d.]+)\s*分", _text(score_el))
        if sm:
            score = float(sm.group(1))

    tags: list[str] = []
    cat_val = _panel_value(soup, ("類別", "类别", "Tags", "Genre"))
    if cat_val:
        for a in cat_val.select("a"):
            t = _text(a)
            if t and t not in tags:
                tags.append(t)
        if not tags:
            for part in re.split(r"[,，、]", _text(cat_val)):
                part = part.strip()
                if part and part not in tags:
                    tags.append(part)

    actresses: list[Actress] = []
    actor_val = _panel_value(soup, ("演員", "演员", "Actor", "Actress"))
    if actor_val:
        for a in actor_val.select('a[href*="/actors/"]'):
            name = _text(a)
            if not name:
                continue
            gender = "unknown"
            sib = a.find_next_sibling()
            while sib is not None and not isinstance(sib, Tag):
                sib = sib.next_sibling
            if isinstance(sib, Tag) and "symbol" in (sib.get("class") or []):
                sym = sib.get_text(strip=True)
                if "♀" in sym or "female" in " ".join(sib.get("class") or []):
                    gender = "female"
                elif "♂" in sym or "male" in " ".join(sib.get("class") or []):
                    gender = "male"
            elif "female" in " ".join((a.find_next("strong") or Tag(name="x")).get("class") or []):
                gender = "female"
            actresses.append(Actress(name=name, name_original=name, gender=gender))

    current_raw = _text(soup.select_one("strong.current-title"))
    origin_raw = _text(soup.select_one("span.origin-title"))
    h2_fallback = _text(soup.select_one("h2.title"))
    if not current_raw and h2_fallback:
        current_raw = h2_fallback
        if code_val and current_raw.upper().startswith(code_val):
            current_raw = current_raw[len(code_val) :].strip()

    cast_names = [a.name for a in actresses if a.gender != "male"]
    title, title_original = resolve_javdb_titles(current_raw, origin_raw, cast_names)
    if title.upper().startswith(code_val):
        title = title[len(code_val) :].strip()
    if title_original.upper().startswith(code_val):
        title_original = title_original[len(code_val) :].strip()

    if not title and not actresses and not tags:
        raise ParseError("JavDB detail page missing title, actresses, and tags")

    return MovieEntry(
        code=code_val,
        title=title,
        title_original=title_original,
        actresses=actresses,
        tags=tags,
        categories=[],
        cover_url=cover,
        release_date=release_date,
        duration_minutes=duration_minutes,
        studio=studio,
        director=director,
        series=series,
        source="javdb",
        source_url=source_url,
        score=score,
    )


def is_javlibrary_detail(html: str) -> bool:
    return 'id="video_id"' in html or "video_jacket" in html


def parse_javlibrary_search(
    html: str,
    code: str,
    base_url: str = "https://www.javlibrary.com/cn/",
) -> str | None:
    if not html or len(html) < 50:
        raise ParseError("javlibrary search response empty or too short")
    if "Just a moment" in html[:2000] or "cf-browser-verification" in html:
        raise ParseError("javlibrary blocked by Cloudflare challenge")
    if is_javlibrary_detail(html):
        return None

    soup = BeautifulSoup(html, "lxml")
    want = normalize_code(code)
    best: str | None = None
    for link in soup.select(".video a[href*='?v='], div.video > a"):
        href = (link.get("href") or "").strip()
        if not href:
            continue
        detail_url = href if href.startswith("http") else urljoin(base_url, href.lstrip("/"))
        title_text = _text(link)
        item_code = normalize_code(title_text.split()[0] if title_text else "")
        if want and item_code == want:
            return detail_url
        if want and want.replace("-", "") in title_text.upper().replace("-", ""):
            best = best or detail_url
        elif best is None:
            best = detail_url
    return best


def parse_javlibrary_detail(html: str, code: str = "", source_url: str = "") -> MovieEntry:
    if not html or len(html) < 200:
        raise ParseError("javlibrary response empty or too short")
    if "Just a moment" in html[:2000] or "cf-browser-verification" in html:
        raise ParseError("javlibrary blocked by Cloudflare challenge")
    soup = BeautifulSoup(html, "lxml")

    code_val = ""
    id_el = soup.select_one("#video_id .text, div#video_id td.text")
    if id_el:
        code_val = normalize_code(_text(id_el))
    if not code_val:
        code_val = normalize_code(code)
    if not code_val:
        raise ParseError("Could not extract 番号 from javlibrary page")

    title_el = soup.select_one("#video_title a, div#video_title h3 a, h3.post-title a")
    title = _text(title_el)
    if title.upper().startswith(code_val):
        title = title[len(code_val) :].strip(" \t-–—")

    cover = ""
    img = soup.select_one("#video_jacket_img, img#video_jacket_img")
    if img:
        cover = img.get("src") or img.get("data-src") or img.get("data-original") or ""
    if not cover:
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            cover = og["content"]
    cover = normalize_cover_url(cover)

    release_date = _text(soup.select_one("#video_date .text, div#video_date td.text"))
    duration_minutes = None
    length_el = soup.select_one("#video_length .text")
    if length_el:
        dm = re.search(r"(\d+)", _text(length_el))
        if dm:
            duration_minutes = int(dm.group(1))

    studio = _text(soup.select_one("#video_maker .text a, div#video_maker a"))
    director = _text(soup.select_one("#video_director .text a, div#video_director a"))

    tags: list[str] = []
    for a in soup.select("#video_genres .text a, div#video_genres a, span.genre a"):
        t = _text(a)
        if t and t not in tags:
            tags.append(t)

    actresses: list[Actress] = []
    for a in soup.select("#video_cast .text a.star, div#video_cast a.star, span.cast a.star"):
        name = _text(a)
        if name:
            actresses.append(Actress(name=name, name_original=name, gender="female"))
    if not actresses:
        for a in soup.select("#video_cast .text a, div#video_cast a"):
            name = _text(a)
            if name and name not in ("N/A", "----"):
                actresses.append(Actress(name=name, name_original=name, gender="female"))

    if not title and not actresses and not tags:
        raise ParseError("javlibrary page missing title, actresses, and tags")

    return MovieEntry(
        code=code_val,
        title=title,
        title_original=title,
        actresses=actresses,
        tags=tags,
        categories=[],
        cover_url=cover,
        release_date=release_date,
        duration_minutes=duration_minutes,
        studio=studio,
        director=director,
        source="javlibrary",
        source_url=source_url,
    )
