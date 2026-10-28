#!/usr/bin/env python3
"""
test_news_podcast.py — stock/news_podcast.py(AI 오디오 브리핑 파일 찾기) 오프라인 검사 (2026-10-27)

  ① 파일이 있으면 ok:true + 제목(.json)·크기·재생 주소
  ② .json 이 없거나 깨져도 ok:true(제목만 빈 글)
  ③ 파일이 없는 날짜는 ok:false, audio_path 는 None
  ④ 날짜 형식이 틀리면(경로 넘기기 포함) 파일을 찾지 않는다
  ⑤ Range 헤더 해석(아이폰 사파리 재생·앞뒤 넘기기용 206 응답)
  ⑥ 온라인신문 시간대(09·18) 오디오: 늦은 시간대 먼저, 틀린 시간대는 안 찾음 (2026-10-28)
실행: python3 scripts/test_news_podcast.py
"""
import importlib
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "stock"))


def main():
    ok_all = True

    def check(name, cond):
        nonlocal ok_all
        print(("  OK  " if cond else "  XX  ") + name)
        ok_all = ok_all and bool(cond)

    with tempfile.TemporaryDirectory() as d:
        os.environ["NEWS_AUDIO_DIR"] = d
        import news_podcast
        pod = importlib.reload(news_podcast)
        with open(os.path.join(d, "2026-10-27.m4a"), "wb") as f:
            f.write(b"\0" * 2048)
        with open(os.path.join(d, "2026-10-27.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "코스피 6개월 최저"}, f, ensure_ascii=False)
        with open(os.path.join(d, "2026-10-26.m4a"), "wb") as f:
            f.write(b"\0" * 10)
        with open(os.path.join(d, "2026-10-26.json"), "w") as f:
            f.write("{깨짐")

        i = pod.info("2026-10-27")
        check("① 있는 날: ok·제목·크기·주소", i["ok"] and i["title"] == "코스피 6개월 최저" and i["bytes"] == 2048
              and i["url"] == "/api/news/podcast/audio?date=2026-10-27")
        i = pod.info("2026-10-26")
        check("② .json 깨져도 ok, 제목 빈 글", i["ok"] and i["title"] == "")
        check("③ 없는 날: ok:false", not pod.info("2026-10-25")["ok"] and pod.audio_path("2026-10-25") is None)
        bad = ["", "2026-13-01", "../2026-10-27", "2026-10-27/../../x", "2026-10-27.m4a"]
        check("④ 틀린 날짜는 None", all(pod.audio_path(b) is None and not pod.info(b)["ok"] for b in bad))

        check("⑥ 온라인 없는 날: ok:false", pod.online_info("2026-10-27") == {"ok": False, "date": "2026-10-27", "items": []})
        for slot, title in (("09", "아침 온라인"), ("18", "저녁 온라인")):
            with open(os.path.join(d, "online-2026-10-27-%s.m4a" % slot), "wb") as f:
                f.write(b"\0" * 100)
            with open(os.path.join(d, "online-2026-10-27-%s.json" % slot), "w", encoding="utf-8") as f:
                json.dump({"title": title}, f, ensure_ascii=False)
        o = pod.online_info("2026-10-27")
        check("⑥ 온라인: 18시 먼저·제목·주소", o["ok"] and [i["slot"] for i in o["items"]] == ["18", "09"]
              and o["items"][0]["title"] == "저녁 온라인"
              and o["items"][1]["url"] == "/api/news/podcast/audio?date=2026-10-27&slot=09")
        check("⑥ 종이 정보는 온라인 파일과 섞이지 않음", pod.info("2026-10-27")["title"] == "코스피 6개월 최저")
        check("⑥ 틀린 시간대는 None", all(pod.audio_path("2026-10-27", s) is None for s in ("12", "../09", "9")))

    br = pod.byte_range
    check("⑤ Range: 없음/모름 → 전체", br(None, 100) is None and br("items=0-1", 100) is None and br("bytes=-", 100) is None)
    check("⑤ Range: 0-1(사파리 첫 요청)", br("bytes=0-1", 100) == (0, 1, 100))
    check("⑤ Range: 열린 끝·끝에서 N", br("bytes=10-", 100) == (10, 99, 100) and br("bytes=-30", 100) == (70, 99, 100))
    check("⑤ Range: 끝 넘으면 잘라 줌", br("bytes=90-500", 100) == (90, 99, 100))
    check("⑤ Range: 시작이 크기 밖 → 416", br("bytes=100-", 100) is False and br("bytes=5-2", 100) is False)
    check("⑤ Range: 한 번에 cap 까지", br("bytes=0-", 10_000_000, cap=1000) == (0, 999, 10_000_000))

    print("모두 통과" if ok_all else "실패 있음")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
