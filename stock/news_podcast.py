"""
news_podcast.py — 신문 요약 'AI 오디오 브리핑'(NotebookLM 오디오 오버뷰) 파일 찾기 (2026-10-27 사용자 요청)

서버 ~/newspaper-claude/notebook_audio.py 가 매일 아침 그날 요약을 NotebookLM '신문브리핑'에 넣고
오디오 오버뷰를 받아 <이 폴더>/.newspaper_audio/YYYY-MM-DD.m4a (+ .json 정보)로 둔다.
온라인신문(2026-10-28)은 시간대마다 online-YYYY-MM-DD-HH.m4a(HH = 09·18).
웹은 /api/news/podcast(정보) · /api/news/podcast/audio(파일)로 그것만 읽는다.
"""
import json
import os
import re

AUDIO_DIR = os.environ.get("NEWS_AUDIO_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".newspaper_audio")
_DATE = re.compile(r"^20\d\d-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
SLOTS = ("09", "18")                                # 온라인신문 시간대


def valid_date(date):
    return bool(_DATE.match(str(date or "")))


def audio_path(date, slot=""):
    """그날 오디오 파일 경로(slot 이 있으면 온라인신문 그 시간대). 날짜·시간대가 틀렸거나 파일이 없으면 None."""
    if not valid_date(date) or (slot and slot not in SLOTS):
        return None
    p = os.path.join(AUDIO_DIR, ("online-%s-%s" % (date, slot) if slot else date) + ".m4a")
    return p if os.path.isfile(p) else None


def byte_range(header, size, cap=4 * 1024 * 1024):
    """'Range: bytes=a-b' 해석. 헤더 없음/모름 → None(전체), 범위 밖 → False(416), 아니면 (start, end, size).
    한 번에 cap 바이트까지만 준다(브라우저가 이어서 다시 요청한다)."""
    m = re.match(r"^bytes=(\d*)-(\d*)$", str(header or "").strip())
    if not m or not (m.group(1) or m.group(2)):
        return None
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:                                       # bytes=-N : 끝에서 N 바이트
        start, end = max(0, size - int(m.group(2))), size - 1
    end = min(end, size - 1, start + cap - 1)
    if start >= size or end < start:
        return False
    return start, end, size


def info(date, slot=""):
    """화면이 그릴 정보. 없으면 ok:false."""
    p = audio_path(date, slot)
    if not p:
        return {"ok": False, "date": date}
    meta = {}
    try:
        with open(p[:-4] + ".json", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        pass
    return {"ok": True, "date": date, "title": str(meta.get("title") or ""),
            "bytes": os.path.getsize(p), "slot": slot,
            "url": "/api/news/podcast/audio?date=" + date + ("&slot=" + slot if slot else "")}


def online_info(date):
    """온라인신문: 그날 있는 시간대 오디오들(늦은 시간대 먼저). 하나도 없으면 ok:false."""
    items = [i for i in (info(date, s) for s in reversed(SLOTS)) if i["ok"]]
    return {"ok": bool(items), "date": date, "items": items}
