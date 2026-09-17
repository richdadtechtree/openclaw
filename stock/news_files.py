# -*- coding: utf-8 -*-
"""
news_files.py — news_sync.py 가 내려받아 둔 "그날 신문" 캐시를 웹에서 읽기 위한 도우미.

[역할 분담]
  scripts/news_sync.py  : 구글 드라이브 → 서버 로컬 캐시 (하루 한 번, gog CLI 사용)
  stock/news_files.py   : 그 캐시를 읽어서 웹(app.py)에 넘겨줌  ← 이 파일
  stock/app.py          : /api/news/* 엔드포인트
  slack_digest_live.html: 화면(상단 '오늘 신문 원본' 패널)

웹 서버는 구글 드라이브를 직접 부르지 않는다. 요청마다 외부 API 를 부르면
느리고, 인증이 끊기면 페이지 전체가 멈추기 때문이다. 여기서는 **로컬 폴더만** 읽는다.

캐시 구조:
    ~/.openclaw/news_cache/2026-09-15/
        index.json        ← 목록·크기·원문 주소 (news_sync.py 가 씀)
        2026-09-15.pdf
        01.jpg … 30.gif
        .thumb/01.jpg     ← 썸네일(Pillow 가 있을 때만, 없으면 원본을 그대로 씀)
        photos.zip        ← 처음 요청될 때 한 번 만들어 재사용
"""

import json
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Pillow 는 있으면 좋고 없어도 되는 선택 사항(썸네일 축소용).
try:
    from PIL import Image  # noqa: F401
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def cache_root():
    return os.path.expanduser(os.getenv("NEWS_CACHE_DIR", "~/.openclaw/news_cache"))


def day_dir(date):
    return os.path.join(cache_root(), date)


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def valid_date(date):
    return bool(date) and bool(DATE_RE.fullmatch(date))


def load_index(date):
    """그날의 index.json 을 읽는다. 없으면 None."""
    if not valid_date(date):
        return None
    try:
        with open(os.path.join(day_dir(date), "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def cached_dates():
    """캐시에 남아 있는 날짜들(최신순)."""
    root = cache_root()
    if not os.path.isdir(root):
        return []
    out = [d for d in os.listdir(root)
           if DATE_RE.fullmatch(d) and os.path.isfile(os.path.join(root, d, "index.json"))]
    return sorted(out, reverse=True)


def latest_date():
    dates = cached_dates()
    return dates[0] if dates else None


def allowed_names(index):
    """index.json 에 적힌 파일 이름만 허용 목록으로 만든다(경로 탈출·임의 파일 열람 차단)."""
    names = set()
    if not index:
        return names
    if index.get("pdf"):
        names.add(index["pdf"]["name"])
    for im in index.get("images") or []:
        names.add(im["name"])
    return names


def resolve(date, name):
    """
    (date, 파일명) → 실제 경로. 목록에 없는 이름이면 None 을 돌려준다.
    ⚠️ 보안 핵심: 사용자가 보낸 name 을 그대로 경로에 붙이면 ../../etc/passwd 같은
       요청으로 아무 파일이나 읽힐 수 있다. 그래서 index.json 에 있는 이름만 통과시킨다.
    """
    index = load_index(date)
    if not index or name not in allowed_names(index):
        return None
    path = os.path.join(day_dir(date), os.path.basename(name))
    return path if os.path.isfile(path) else None


def media_type(name):
    ext = os.path.splitext(name)[1].lower()
    return {
        ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def ensure_thumb(date, name, width=420):
    """
    썸네일 경로를 돌려준다. Pillow 가 없으면 원본 경로를 그대로 준다
    (화면은 똑같이 보이고 데이터만 더 쓴다 — 기능이 죽지는 않는다).
    """
    src = resolve(date, name)
    if not src:
        return None
    if not HAVE_PIL:
        return src
    tdir = os.path.join(day_dir(date), ".thumb")
    dst = os.path.join(tdir, os.path.basename(name) + ".jpg")
    try:
        if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            return dst
        os.makedirs(tdir, exist_ok=True)
        from PIL import Image
        with Image.open(src) as im:
            if getattr(im, "is_animated", False):
                im.seek(0)          # 움직이는 GIF 는 첫 장면만 쓴다
            im = im.convert("RGB")
            im.thumbnail((width, width * 6))
            tmp = dst + ".tmp"
            im.save(tmp, "JPEG", quality=72, optimize=True)
        os.replace(tmp, dst)
        return dst
    except Exception:
        return src  # 썸네일 실패는 치명적이지 않다 → 원본으로 대체


def ensure_zip(date, what="photos"):
    """
    한 번에 받을 ZIP 을 만든다(처음 요청될 때 만들고 그다음부터 재사용).
      what="photos" (기본) → 사진만        · 파일명 photos.zip
      what="all"           → 사진 + PDF    · 파일명 all.zip
    """
    index = load_index(date)
    if not index:
        return None
    if what == "all":
        names = sorted(allowed_names(index))
    else:
        names = sorted(im["name"] for im in index.get("images") or [])
    if not names:
        return None
    zpath = os.path.join(day_dir(date), "photos.zip" if what != "all" else "all.zip")
    if os.path.isfile(zpath) and os.path.getsize(zpath) > 0:
        return zpath
    tmp = zpath + ".tmp"
    try:
        # jpg/pdf 는 이미 압축된 형식이라 다시 압축해도 거의 안 줄고 CPU만 쓴다 → 그냥 담기(STORED).
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for n in names:
                p = resolve(date, n)
                if p:
                    z.write(p, arcname=n)
        os.replace(tmp, zpath)
        return zpath
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None


def summary(date):
    """
    화면이 그대로 쓸 수 있는 형태로 정리해서 준다.
    아직 안 올라왔으면 ready=False + 가장 최근 날짜(latest)를 같이 알려준다.
    """
    index = load_index(date)
    if not index:
        return {
            "ok": True, "ready": False, "date": date,
            "latest": latest_date(),
            "reason": "아직 준비되지 않았습니다 (보통 오전 6시경 올라옵니다).",
        }

    def furl(name, dl=0):
        return "/api/news/file?date=%s&name=%s%s" % (date, name, "&dl=1" if dl else "")

    pdf = None
    if index.get("pdf"):
        pdf = dict(index["pdf"])
        pdf["url"] = furl(pdf["name"], dl=1)
        pdf["view_url"] = furl(pdf["name"])

    images = []
    for im in index.get("images") or []:
        images.append({
            "name": im["name"], "size": im.get("size", 0),
            "url": furl(im["name"]), "download_url": furl(im["name"], dl=1),
            "thumb": "/api/news/thumb?date=%s&name=%s" % (date, im["name"]),
        })

    photos_size = sum(i["size"] for i in images)
    total = (pdf["size"] if pdf else 0) + photos_size
    return {
        "ok": True, "ready": True, "date": date,
        "title": index.get("title") or "",
        "source_url": index.get("source_url") or "",
        "updated": index.get("updated") or "",
        "pdf": pdf, "images": images, "count": len(images),
        "expected_count": index.get("expected_count") or len(images),
        "total_size": total,
        "photos_size": photos_size,
        "zip_url": "/api/news/zip?date=%s" % date,                 # 사진만
        "zip_all_url": "/api/news/zip?date=%s&what=all" % date,    # 사진+PDF
        "latest": latest_date(),
        "thumbs": HAVE_PIL,
    }
