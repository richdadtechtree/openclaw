#!/usr/bin/env python3
"""
test_ai_news.py — stock/ai_news.py('AI 소식' 글 모으기) 오프라인 검사 (2026-10-28)

  ① GeekNews /new HTML → 제목·원문·토론 주소·요약·점수·글쓴이·시각·댓글 수, 원문 없는 글은 토론 주소
  ② Threads thread_items → 그 사람 글만, 이어진 글 묶음째, 최신 묶음 먼저, 같은 묶음 한 번
  ③ 캐시 합치기: 새 글 + 예전 글, 같은 글은 새 것으로, 최대 개수
  ④ feed(): 받기 실패해도 예전 글은 남고 오류만 적힘 · 모르는 출처는 ok:false
실행: python3 scripts/test_ai_news.py   (네트워크·크로미움 안 씀)
"""
import importlib
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "stock"))

GEEK = ("<h1 class=\"visually-hidden\">새 소식</h1>"
        "<div class='topic_row' data-topic-state-id='36136' data-topic-voteable='1'><div class=votenum>1</div>"
        "<div class=topictitle><span id='dead36136'></span><a href='https://github.com/x/StreamFusion' rel='nofollow' id='tr1'"
        " class='topic-title-link'><h2 class='topic-title-heading'>StreamFusion - Flink SQL &amp; Rust</h2></a>"
        " <span class=topicurl>(github.com/x)</span></div><div class='topicdesc'><a href='topic?id=36136' class='c99 breakall'>"
        "Apache Flink 요약...</a></div><div class='topicinfo'><span id='tp36136'>3</span> point by <a href='/@xguru'>xguru</a>"
        " <time class=\"js-relative-time\" datetime=\"2026-10-28T09:30:02+09:00\">3시간전</time> | <a href='topic?id=36136&go=comments'"
        " class=u data-topic-comment-topic-id='36136' data-topic-comment-count='2'>댓글과 토론</a></div></div>"
        "<div class='topic_row' data-topic-state-id='36130' data-topic-voteable='1'><div class=topictitle>"
        "<a href='topic?id=36130' id='tr2' class='topic-title-link'><h2>Ask GN: 질문</h2></a></div>"
        "<div class='topicinfo'><span id='tp36130'>1</span> point by <a href='/@kim'>kim</a>"
        " <time datetime=\"2026-10-28T08:00:00+09:00\">x</time></div></div>")


def post(code, at, text, user="choi.openai", media=False):
    p = {"code": code, "taken_at": at, "user": {"username": user}, "caption": {"text": text}}
    if media:
        p["carousel_media"] = [{}]
    return {"post": p}


def main():
    ok_all = True

    def check(name, cond, extra=""):
        nonlocal ok_all
        print(("  OK  " if cond else "  XX  ") + name + (("  " + str(extra)) if extra and not cond else ""))
        ok_all = ok_all and bool(cond)

    with tempfile.TemporaryDirectory() as d:
        os.environ["AI_NEWS_DIR"] = d
        import ai_news
        ai = importlib.reload(ai_news)

        g = ai.parse_geeknews(GEEK)
        check("① 두 글", len(g) == 2, g)
        a = g[0]
        check("① 제목·원문·도메인·요약", a["title"] == "StreamFusion - Flink SQL & Rust" and a["url"] == "https://github.com/x/StreamFusion"
              and a["domain"] == "github.com/x" and a["desc"] == "Apache Flink 요약...", a)
        check("① 점수·글쓴이·시각·댓글·토론 주소", a["points"] == 3 and a["author"] == "xguru" and a["at"] == "2026-10-28T09:30:02+09:00"
              and a["comments"] == 2 and a["topic"] == "https://news.hada.io/topic?id=36136", a)
        check("① 원문 없는 글은 토론 주소", g[1]["url"] == "https://news.hada.io/topic?id=36130" and g[1]["comments"] == 0)

        page = ("<p>머리</p><div class=topic_contents><div><section id='topic_contents' class='article-content'><ul>\n"
                "<li>첫 <strong>굵게</strong> &amp; 끝</li>\n<li>둘째\n<ul>\n<li>안쪽</li>\n</ul>\n</li>\n</ul>"
                "<p>문단 <code>x</code></p></section></div></div>")
        check("⑤ 본문: 목록·안쪽 목록 들여쓰기·문단", ai.parse_topic(page) == "• 첫 굵게 & 끝\n• 둘째\n  • 안쪽\n\n문단 x",
              repr(ai.parse_topic(page)))
        check("⑤ 본문 칸 없음·잘못된 번호", ai.parse_topic("<p>x</p>") == "" and ai.topic("1;rm")["ok"] is False)

        groups = [[post("A", 100, "첫 글 🧵"), post("A1", 101, "1/ 이어서", media=True), post("X", 102, "남의 답글", user="other")],
                  [post("B", 200, "새 글")], [post("A", 100, "첫 글 🧵")], [post("Z", 300, "남의 글", user="other")]]
        t = ai.parse_threads(groups)
        check("② 그 사람 글만·최신 묶음 먼저·같은 묶음 한 번", [x["code"] for x in t] == ["B", "A"], t)
        check("② 이어진 글 묶음째(남의 답글 빠짐)·사진 표시·주소",
              [p["code"] for p in t[1]["posts"]] == ["A", "A1"] and t[1]["posts"][1]["media"] and not t[1]["posts"][0]["media"]
              and t[1]["url"] == "https://www.threads.com/@choi.openai/post/A")

        old = [{"code": "A", "at": 100, "posts": [{"text": "옛"}]}, {"code": "C", "at": 50, "posts": []}]
        new = [{"code": "B", "at": 200, "posts": []}, {"code": "A", "at": 100, "posts": [{"text": "새"}]}]
        m = ai.merge("threads", old, new)
        check("③ 합치기: 최신순·같은 글은 새 것", [x["code"] for x in m] == ["B", "A", "C"] and m[1]["posts"][0]["text"] == "새")
        many = [{"id": str(i), "at": "2026-10-28T%02d:00:00+09:00" % (i % 24)} for i in range(200)]
        check("③ 최대 개수", len(ai.merge("geeknews", [], many)) == ai.MAX_KEEP["geeknews"])

        ai.fetch_geeknews = lambda: g
        r = ai.feed("geeknews")
        check("④ 처음엔 그 자리에서 받아 옴", r["ok"] and len(r["items"]) == 2 and not r["error"], r)

        def boom():
            raise RuntimeError("막힘")
        ai.fetch_geeknews = boom
        ai.refresh("geeknews")
        r = ai.feed("geeknews")
        check("④ 받기 실패해도 예전 글은 남고 오류만", r["ok"] and len(r["items"]) == 2 and "막힘" in r["error"], r)
        check("④ 실패 직후엔 다시 두드리지 않음", not ai._stale(ai._read("geeknews"), "geeknews"))
        data = ai._read("geeknews")
        data["fetched_at"] = data["failed_at"] = int(time.time()) - 3600
        ai.fetch_geeknews = lambda: [dict(g[0], id="36200", title="새로 온 글")]
        with open(ai._path("geeknews"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        r = ai.feed("geeknews", background=False)
        check("④ 오래되면 새로 받아 합침", r and r["items"][0]["title"] == "새로 온 글" and len(r["items"]) == 3 and not r["error"], r)
        check("④ 모르는 출처", ai.feed("x")["ok"] is False)

    print("모두 통과" if ok_all else "실패 있음")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
