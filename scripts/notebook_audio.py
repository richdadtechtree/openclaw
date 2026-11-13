#!/usr/bin/env python3
"""그날 신문을 NotebookLM '신문브리핑'에 소스로 넣고 AI 오디오 오버뷰를 받아 웹(/economy)에 올린다.

  venv-nlm/bin/python notebook_audio.py --date YYYY-MM-DD                  # 종이신문: 신문 PDF 를 소스로(기본, 2026-11-13~)
  venv-nlm/bin/python notebook_audio.py --date YYYY-MM-DD --source summary # 예전 방식: 요약 글을 소스로
  venv-nlm/bin/python notebook_audio.py --date YYYY-MM-DD --slot 09|18     # 온라인신문(요약 글만 있음 → 늘 summary)

- 2026-11-13 사용자 요청: 오디오 재료를 '요약 글'이 아니라 '신문 PDF 원본'으로.
  PDF 는 웹이 쓰는 캐시(~/.openclaw/news_cache/DATE/)에서 찾는다(수집기 폴더로 이어진 링크여도 OK).
  PDF 가 없으면 요약으로 몰래 대신하지 않고 이유를 적고 실패한다(원하면 --source summary).
- 같은 제목 소스가 이미 있으면 다시 넣지 않는다. 오디오 파일이 이미 있으면 아무것도 안 한다.
- 결과: ~/stock/stock/.newspaper_audio/DATE.m4a(+DATE.json), 온라인신문은 online-DATE-HH.m4a(+.json).
  웹 /api/news/podcast 가 읽는다.
- 하루만 둔다: --cleanup(또는 --date 실행 첫머리)이 오늘(KST) 전 날짜의 파일·NotebookLM 소스·오디오를 지운다.
- 비공식 라이브러리(notebooklm-py) 사용. 로그인 세션: ~/.notebooklm/profiles/default/storage_state.json
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(BASE, "venv-nlm", "bin", "notebooklm")
# '신문브리핑' 이름의 노트북이 여러 개라 ID로 고정한다(2026-10-27 사용자가 만든 것).
NOTEBOOK = os.environ.get("NLM_NOTEBOOK", "c2af3e46-e281-4d65-b22d-61b8d56e0c8d")
OUT_DIR = os.path.expanduser("~/stock/stock/.newspaper_audio")
WEB = "https://mystatus-btr.duckdns.org/economy?date=%s"
PROMPT = ("오늘 아침 신문 요약 기사들을 한국어로 쉽게 풀어 주는 경제 브리핑. "
          "소스에 있는 기사 내용과 숫자만 말하고, 소스에 없는 전망이나 조언은 덧붙이지 말 것.")
PROMPT_PDF = ("오늘 아침 종이신문 PDF 의 주요 경제 기사들을 한국어로 쉽게 풀어 주는 경제 브리핑. "
              "소스(신문 PDF)에 있는 기사 내용과 숫자만 말하고, 소스에 없는 전망이나 조언은 덧붙이지 말 것.")
PROMPT_ONLINE = ("지금 네이버 경제 주요 기사 요약을 한국어로 쉽게 풀어 주는 경제 브리핑. "
                 "소스에 있는 기사 내용과 숫자만 말하고, 소스에 없는 전망이나 조언은 덧붙이지 말 것.")
# NotebookLM 소스 파일 한도는 200MB. 넘으면 올리다 실패하므로 미리 알려 준다.
PDF_MAX_BYTES = 190 * 1024 * 1024


def say(msg):
    print("[notebook_audio] %s %s" % (time.strftime("%F %T"), msg), flush=True)


def nlm(*args, timeout=120):
    """notebooklm CLI 를 --json 으로 부르고 JSON 을 돌려준다(앞에 붙는 'Matched:' 줄은 건너뜀)."""
    r = subprocess.run([CLI, *args, "--json"], capture_output=True, text=True, timeout=timeout)
    out = r.stdout
    i = out.find("{")
    if r.returncode != 0 or i < 0:
        raise RuntimeError("notebooklm %s 실패(%s): %s" % (args[0], r.returncode, (r.stderr or out)[-400:]))
    return json.loads(out[i:])


def find_id(d):
    """응답 JSON 어디에 있든 첫 id(task_id/artifact_id/source_id/id)를 찾는다."""
    if isinstance(d, dict):
        for k in ("task_id", "artifact_id", "source_id", "id"):
            if isinstance(d.get(k), str) and d[k]:
                return d[k]
        for v in d.values():
            got = find_id(v)
            if got:
                return got
    if isinstance(d, list):
        for v in d:
            got = find_id(v)
            if got:
                return got
    return ""


def today_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")


def source_key(title):
    """이 스크립트가 넣은 소스면 그 브리핑 열쇠(종이 'DATE', 온라인 'online-DATE-HH'), 아니면 ''.
    제목: '신문 요약 DATE'·'신문 PDF DATE'·'온라인 요약 DATE HH시', 이름 바꾸기 전 'newspaper-DATE.txt'·'newspaper-online-DATE-HH.txt'."""
    t = str(title or "")
    m = re.fullmatch(r"(?:신문 요약 |신문 PDF |newspaper-)(20\d\d-\d\d-\d\d)(?:\.txt)?", t)
    if m:
        return m.group(1)
    m = re.fullmatch(r"온라인 요약 (20\d\d-\d\d-\d\d) (\d\d)시|newspaper-online-(20\d\d-\d\d-\d\d)-(\d\d)\.txt", t)
    return "online-%s-%s" % (m.group(1) or m.group(3), m.group(2) or m.group(4)) if m else ""


def source_day(title):
    """이 스크립트가 넣은 소스면 그 날짜, 아니면 ''."""
    m = re.search(r"20\d\d-\d\d-\d\d", source_key(title))
    return m.group(0) if m else ""


def find_pdf(day):
    """그날 신문 PDF 의 실제 경로(없으면 ''). 웹 캐시 index.json 의 pdf 이름 → <날짜>.pdf → 폴더의 첫 *.pdf 순.
    캐시 파일이 수집기 폴더로 이어진 심볼릭 링크일 수 있어 realpath 로 풀고, 끊어진 링크·빈 파일은 건너뛴다."""
    root = os.path.expanduser(os.environ.get("NEWS_CACHE_DIR", "~/.openclaw/news_cache"))
    d = os.path.join(root, day)
    cands = []
    try:
        with open(os.path.join(d, "index.json"), encoding="utf-8") as f:
            name = ((json.load(f) or {}).get("pdf") or {}).get("name")
        if name and os.path.basename(name) == name:     # 폴더 밖을 가리키는 이름은 무시
            cands.append(os.path.join(d, name))
    except Exception:
        pass
    cands.append(os.path.join(d, day + ".pdf"))
    cands += sorted(glob.glob(os.path.join(d, "*.pdf")))
    for p in cands:
        real = os.path.realpath(p)
        if os.path.isfile(real) and os.path.getsize(real) > 0:
            return real
    return ""


def write_meta(day, meta):
    path = os.path.join(OUT_DIR, day + ".json")
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    os.replace(path + ".part", path)


def cleanup(keep):
    """브리핑 자료는 하루만 둔다(2026-10-27 사용자 요청): keep 날짜보다 앞선 것을 서버·NotebookLM 에서 지운다.
    지우는 것은 이 스크립트가 만든 것뿐 — 제목 '신문 요약/신문 PDF 날짜' 소스와 .json 에 적어 둔 오디오 ID."""
    old = {}                                    # 파일 이름 앞부분(DATE 또는 online-DATE-HH) → 파일들
    if os.path.isdir(OUT_DIR):
        for name in os.listdir(OUT_DIR):
            m = re.match(r"^((?:online-)?(20\d\d-\d\d-\d\d)(?:-\d\d)?)\.", name)
            if m and m.group(2) < keep:
                old.setdefault(m.group(1), []).append(os.path.join(OUT_DIR, name))
    arts = set()
    for stem, files in old.items():
        try:
            with open(os.path.join(OUT_DIR, stem + ".json"), encoding="utf-8") as f:
                aid = json.load(f).get("artifact_id")
            if aid:
                arts.add(aid)
        except Exception:
            pass
    ok = True
    try:
        live = {x.get("id") for x in nlm("artifact", "list", "-n", NOTEBOOK).get("artifacts", [])}
        for aid in sorted(arts & live):
            nlm("artifact", "delete", aid, "-n", NOTEBOOK, "-y")
            say("NotebookLM 오디오 삭제: %s" % aid)
        for s in nlm("source", "list", "-n", NOTEBOOK).get("sources", []):
            d = source_day(s.get("title"))
            if d and d < keep:
                nlm("source", "delete", s["id"], "-n", NOTEBOOK, "-y")
                say("NotebookLM 소스 삭제: %s" % s.get("title"))
    except Exception as e:                      # NotebookLM 이 안 되면 서버 파일은 남겨 다음에 다시 시도
        say("NotebookLM 정리 실패: %s" % e)
        ok = False
    if ok:
        for files in old.values():
            for p in files:
                os.unlink(p)
                say("서버 파일 삭제: %s" % p)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="이 날짜 브리핑을 만든다(먼저 그 전날까지 자료를 지움)")
    ap.add_argument("--cleanup", action="store_true", help="오늘(KST) 전 자료 지우기만 한다")
    ap.add_argument("--slot", choices=["09", "18"], help="온라인신문 이 시간대 요약으로 만든다")
    ap.add_argument("--force", action="store_true", help="오디오가 있어도 다시 만든다")
    ap.add_argument("--source", choices=["pdf", "summary"],
                    default=os.environ.get("NLM_AUDIO_SOURCE", "pdf"),
                    help="종이신문 오디오의 재료: pdf=신문 PDF 원본(기본), summary=요약 글 (온라인신문은 늘 summary)")
    a = ap.parse_args()
    if a.cleanup:
        return 0 if cleanup(today_kst()) else 1
    day = a.date
    if not day or not re.fullmatch(r"20\d\d-\d\d-\d\d", day):
        sys.exit("날짜 형식 오류")
    cleanup(min(day, today_kst()))
    key = "online-%s-%s" % (day, a.slot) if a.slot else day   # 파일 이름·소스 구분 열쇠
    audio = os.path.join(OUT_DIR, key + ".m4a")
    if os.path.exists(audio) and not a.force:
        say("오디오 이미 있음; 건너뜀: " + audio)
        return 0

    use_pdf = (a.source == "pdf") and not a.slot          # 온라인신문엔 PDF 가 없다
    if use_pdf:
        pdf = find_pdf(day)
        if not pdf:
            say("신문 PDF 없음: %s (요약으로 대신하지 않음. 요약으로 만들려면 --source summary)"
                % os.path.join(os.path.expanduser(os.environ.get("NEWS_CACHE_DIR", "~/.openclaw/news_cache")), day))
            return 1
        size = os.path.getsize(pdf)
        if size > PDF_MAX_BYTES:
            say("신문 PDF 가 너무 커요(%d MB > 190 MB, NotebookLM 한도 200 MB): %s" % (size // 1048576, pdf))
            return 1
        title = "신문 PDF %s" % day
        mime, prompt, kind = "application/pdf", PROMPT_PDF, "pdf"
        text = ""
    else:
        summ = os.path.join(BASE, "summaries", "summary-%s.txt" % key)
        tail = os.path.join(BASE, "summaries", "tail-%s.txt" % key)
        if not os.path.exists(summ):
            say("요약 없음: " + summ)
            return 1
        text = open(summ, encoding="utf-8").read().strip()
        if os.path.exists(tail):
            text = open(tail, encoding="utf-8").read().strip() + "\n\n" + text
        title = "온라인 요약 %s %s시" % (day, a.slot) if a.slot else "신문 요약 %s" % day
        web = WEB % day + ("&edition=online" if a.slot else "")
        text = "%s\n원문 화면: %s\n\n%s" % (title, web, text)
        mime, prompt, kind = "text/plain", (PROMPT_ONLINE if a.slot else PROMPT), "summary"

    # 1) 소스: 같은 제목이 있으면 그것을 쓴다(중복 방지). 제목까지 같아야 같은 소스로 본다
    #    → 예전 '신문 요약 DATE' 소스가 남아 있어도 PDF 오디오에 섞이지 않는다.
    srcs = nlm("source", "list", "-n", NOTEBOOK).get("sources", [])
    src = next((s for s in srcs if s.get("title") == title and s.get("status") != "error"), None)
    if src:
        sid = src["id"]
        say("소스 이미 있음: %s" % sid)
    else:
        tmpdir = None
        try:
            if use_pdf:
                path = pdf
                say("신문 PDF 올리는 중: %s (%.1f MB)" % (pdf, size / 1048576.0))
            else:
                # 요약이 100KB 가까이 돼 명령 인자 길이 제한에 걸릴 수 있으므로 .txt 파일로 올린다
                tmpdir = tempfile.mkdtemp()
                path = os.path.join(tmpdir, "newspaper-%s.txt" % key)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            sid = find_id(nlm("source", "add", path, "--type", "file", "--title", title,
                              "--mime-type", mime, "-n", NOTEBOOK, timeout=900))
        finally:
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
        if not sid:
            raise RuntimeError("소스 ID를 못 받음")
        say("소스 추가: %s" % sid)
        nlm("source", "wait", sid, "-n", NOTEBOOK, timeout=900)
        nlm("source", "rename", sid, title, "-n", NOTEBOOK)   # 파일 업로드는 --title 이 안 먹어 파일명이 제목이 됨

    # 2) 오디오 오버뷰: 그날 소스만으로, 한국어
    gen = nlm("generate", "audio", prompt, "-n", NOTEBOOK, "-s", sid, "--language", "ko",
              "--retry", "2", timeout=300)
    aid = find_id(gen)
    if not aid:
        raise RuntimeError("오디오 작업 ID를 못 받음: %s" % json.dumps(gen, ensure_ascii=False)[:300])
    say("오디오 생성 시작: %s (재료: %s)" % (aid, kind))
    # 다운로드 전에 실패해도 다음 날 정리가 이 오디오를 찾아 지울 수 있게 ID부터 적어 둔다
    os.makedirs(OUT_DIR, exist_ok=True)
    write_meta(key, {"date": day, "slot": a.slot or "", "artifact_id": aid, "source_id": sid,
                     "notebook_id": NOTEBOOK, "source_kind": kind})
    done = nlm("artifact", "wait", aid, "-n", NOTEBOOK, "--timeout", "1800", "--interval", "15",
               timeout=1900)
    st = json.dumps(done, ensure_ascii=False)
    if "completed" not in st:
        raise RuntimeError("오디오 생성 실패: %s" % st[:300])

    # 3) 내려받아 웹 폴더에 임시파일 → mv
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = audio + ".part"
    r = subprocess.run([CLI, "download", "audio", "-n", NOTEBOOK, "-a", aid, "--force", tmp],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 10000:
        raise RuntimeError("다운로드 실패: %s" % (r.stderr or r.stdout)[-300:])
    # NotebookLM 은 조각 MP4(DASH)로 준다 → 브라우저 앞뒤 넘기기가 잘 되게 일반 m4a 로 다시 감싼다(재인코딩 없음)
    if shutil.which("ffmpeg"):
        fixed = tmp + ".m4a"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-c", "copy", "-movflags", "+faststart",
                            "-f", "mp4", fixed], capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and os.path.getsize(fixed) > 10000:
            os.replace(fixed, tmp)
        else:
            say("ffmpeg 변환 실패, 원본 그대로 씀: %s" % r.stderr[-200:])
            if os.path.exists(fixed):
                os.unlink(fixed)
    os.chmod(tmp, 0o644)
    arts = nlm("artifact", "list", "-n", NOTEBOOK).get("artifacts", [])
    art = next((x for x in arts if x.get("id") == aid), {})
    meta = {"date": day, "slot": a.slot or "", "title": art.get("title") or title, "artifact_id": aid,
            "source_id": sid, "notebook_id": NOTEBOOK, "source_kind": kind,
            "created": time.strftime("%FT%T%z"), "bytes": os.path.getsize(tmp)}
    os.replace(tmp, audio)
    write_meta(key, meta)
    say("오디오 저장: %s (%d bytes, %s)" % (audio, meta["bytes"], meta["title"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        say("실패: %s" % e)
        sys.exit(1)
