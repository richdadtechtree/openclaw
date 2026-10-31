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

        import io
        import urllib.error

        def gone(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b""))
        real = ai.urllib.request.urlopen
        ai.urllib.request.urlopen = gone
        try:
            t = ai.topic("36200")
        finally:
            ai.urllib.request.urlopen = real
        r = ai.feed("geeknews")
        check("⑥ 지워진 글(404): gone 표시·목록에서 빠짐", t.get("gone") and [x["id"] for x in r["items"]] == ["36136", "36130"], (t, r))

        # ⑦ 글 하나 화면: 본인이 이어 쓴 글 + 남의 댓글에 단 답을 '하나도 빠짐없이' (2026-10-30 사용자 요청)
        page_groups = [[post("A", 100, "첫 글"), post("A1", 101, "1/ 이어서"), post("A2", 102, "2/ 이어서")],
                       [post("X", 110, "질문 있어요", user="kim"), post("R1", 111, "답변입니다")],
                       [post("A3", 120, "3/ 한참 뒤에 이어 씀")],
                       [post("Y", 130, "좋아요", user="lee")],
                       [post("Z", 140, "또 질문", user="park"), post("Q", 141, "끼어든 사람", user="lee"), post("R2", 142, "둘째 답")]]
        d = ai.parse_thread_page(page_groups, "A")
        check("⑦ 이어진 글 전부(따로 떨어진 3/ 포함)·뿌리 글 먼저", [p["code"] for p in d["posts"]] == ["A", "A1", "A2", "A3"], d)
        check("⑦ 남의 댓글에 단 답 전부 + 누구에게", [(r["code"], r["reply_to"]) for r in d["replies"]] == [("R1", "kim"), ("R2", "lee")]
              and all("reply_to_text" not in r for r in d["replies"]), d["replies"])
        check("⑦ 남의 댓글 글은 어디에도 저장 안 함(2026-10-31 사용자 요청)", "질문 있어요" not in json.dumps(d, ensure_ascii=False)
              and "또 질문" not in json.dumps(d, ensure_ascii=False), d)
        check("⑦ 남의 글은 안 들어감", all(p["code"] not in ("X", "Y", "Z", "Q") for p in d["posts"] + d["replies"]))
        check("⑦ 뿌리 글이 없으면(다른 화면) 쓰지 않음", ai.parse_thread_page(page_groups, "NOPE") is None)
        nested = {"data": {"x": [{"y": {"thread_items": [post("N", 1, "n")]}}], "z": {"thread_items": []}}}
        check("⑧ 어떤 JSON 속 thread_items 도 찾음", len(ai.walk_items(nested, [])) == 2)
        check("⑧ 받은 데이터 앞의 for(;;); 와 줄마다 JSON", ai._json_chunks('for (;;);{"a":1}') == [{"a": 1}]
              and ai._json_chunks('{"a":1}\n{"b":2}') == [{"a": 1}, {"b": 2}])

        # ⑨ 받기: 프로필엔 앞부분만 → 글 화면에서 전부 붙임, 다음번에 글 화면을 못 읽어도 모은 댓글은 남음
        prof = ai.parse_threads([[post("A", int(time.time()) - 3600, "첫 글"), post("A1", int(time.time()) - 3599, "1/ 이어서")]])
        full = ai.parse_thread_page([[post("A", int(time.time()) - 3600, "첫 글"), post("A1", int(time.time()) - 3599, "1/"),
                                      post("A2", int(time.time()) - 3598, "2/")],
                                     [post("X", int(time.time()) - 3000, "질문", user="kim"), post("R1", int(time.time()) - 2999, "답")]], "A")
        seen = {}

        def fake(deep=()):
            seen["deep"] = list(deep)
            return prof, {"A": full}
        ai.fetch_threads = fake
        ai.refresh("threads")
        t = ai._read("threads")["items"][0]
        check("⑨ 글 화면에서 모은 이어진 글 3개 + 댓글에 단 답 1개가 붙음", len(t["posts"]) == 3 and len(t["replies"]) == 1 and t.get("full_at"), t)
        def fake2(deep=()):                                 # 이번엔 글 화면을 못 읽음
            seen["deep"] = list(deep)
            return prof, {}
        ai.fetch_threads = fake2
        ai.refresh("threads")
        t = ai._read("threads")["items"][0]
        check("⑨ 다음번에 못 읽어도 예전에 모은 것은 그대로", len(t["posts"]) == 3 and len(t["replies"]) == 1, t)
        check("⑨ 최근 7일 글은 다시 열 목록(deep)에 들어감", seen.get("deep") == ["A"], seen)

        # ⑩ 숫자가 안 맞을 때: Threads 가 적은 답글 수로 '답이 숨은 댓글'을 찾고, 그 댓글 화면에서 본인 답을 모은다
        def withcount(item, n):
            item["post"]["text_post_app_info"] = {"direct_reply_count": n}
            return item
        g = [[withcount(post("A", 100, "첫 글"), 9), post("A1", 101, "1/")],
             [withcount(post("X", 110, "질문1", user="kim"), 2), post("R1", 111, "답1")],      # 답 2개라는데 1개만 보임 → 숨음
             [withcount(post("Y", 120, "질문2", user="lee"), 1), post("R2", 121, "답2")],      # 다 보임
             [withcount(post("Z", 130, "질문3", user="park"), 0)]]
        d = ai.parse_thread_page(g, "A")
        check("⑩ Threads 가 센 전체 댓글 수·남의 댓글 수 기록", d["stats"]["threads_comments"] == 9 and d["stats"]["others_comments"] == 3, d["stats"])
        check("⑩ 답이 숨어 있을 수 있는 댓글만 골라냄", [h["code"] for h in d["hidden"]] == ["X"] and d["hidden"][0]["user"] == "kim", d["hidden"])
        cpage = [[post("X", 110, "질문1", user="kim")],
                 [post("R1", 111, "답1")], [post("R9", 115, "숨어 있던 둘째 답")],
                 [post("W", 116, "끼어든 사람", user="choi"), post("R10", 117, "끼어든 사람에게 단 답")]]
        rs = ai.parse_comment_page(cpage, d["hidden"][0])
        check("⑩ 댓글 화면에서 본인 답 전부(누구에게 단 답인지 포함)",
              sorted((r["code"], r["reply_to"]) for r in rs) == [("R1", "kim"), ("R10", "choi"), ("R9", "kim")], rs)

    # ⑫ 글 화면에서 본 글을 못 찾으면 이유를 한 줄로(2026-10-30 서버에서 '글 화면 확인함'이 하나도 안 붙음 — 조용히 건너뛰던 것)
    why = ai.why_not_found([[post("Z", 1, "남의 글", user="kim")]], "Q", {"login_wall": True, "url": "https://x/login", "page_groups": 1, "data_resps": 0})
    check("⑫ 못 찾은 이유(본 글 없음·로그인 벽·주소)", "본 글 없음" in why and "로그인 벽 있음" in why and "https://x/login" in why, why)

    # ⑬ 서버 실제 모양(2026-10-30 debug): 글 하나 화면의 thread_items 는 '이 사람의 다른 글'뿐, 본 글·댓글은 다른 자리
    def rp(code, at, text, user="choi.openai", to=None, n=None):
        po = post(code, at, text, user=user)["post"]
        po["text_post_app_info"] = dict({"reply_to_author": {"username": to}} if to else {}, **({"direct_reply_count": n} if n is not None else {}))
        return po
    related = [[post("OLD1", 50, "다른 글")], [post("OLDX", 60, "남의 다른 글", user="the_future")], [post("OLD2", 70, "또 다른 글")]]
    flat = {"data": {"containing_thread": {"items": [{"node": rp("R0", 100, "본 글", n=3)}, {"node": rp("R0b", 101, "2/", to="choi.openai")}]},
                     "replies": [{"node": rp("K1", 110, "질문입니다", user="kim")}, {"node": rp("C1", 111, "답입니다", to="kim")},
                                 {"node": rp("L1", 120, "의견", user="lee")}, {"node": rp("C2", 121, "감사합니다", to="lee")}]}}
    flat["data"]["relatedPosts"] = {"threads": [{"thread_items": [{"post": rp("NEWREL", 500, "관련 글(더 최신)")}]}]}
    pool = {}
    ai.walk_posts(flat, pool)
    check("⑬ 화면 아래 '관련 글'(relatedPosts)은 모으지 않음", "NEWREL" not in pool and "R0" in pool, list(pool))
    for g in related:
        ai.walk_posts(g, pool)
    d = ai.thread_detail(related, "R0", {"posts": pool})
    check("⑬ thread_items 에 본 글이 없어도 화면 곳곳에서 이어진 글을 찾음", d and [x["code"] for x in d["posts"]] == ["R0", "R0b"], d)
    check("⑬ 댓글에 단 답(누구에게, 남의 댓글 글은 없음)", d and [(r["code"], r["reply_to"]) for r in d["replies"]] == [("C1", "kim"), ("C2", "lee")]
          and "질문입니다" not in json.dumps(d, ensure_ascii=False), d)
    check("⑬ 다른 글(OLD1·OLD2)은 섞이지 않음·Threads 댓글 수", d and not {"OLD1", "OLD2"} & {x["code"] for x in d["posts"] + d["replies"]} and d["stats"]["threads_comments"] == 3, d)
    check("⑬ 본 글이 어디에도 없으면 None", ai.thread_detail(related, "NONE", {"posts": pool}) is None)

    # ⑭ 2026-10-31 서버: 화면 곳곳 방식에선 '답이 숨은 댓글'이 늘 0 → 대댓글을 찾으러 댓글 화면을 안 열었다
    pool2 = {}
    ai.walk_posts({"d": [rp("S0", 100, "본 글", n=13), rp("S1", 101, "2/", to="choi.openai"),
                         rp("P1", 110, "질문A", user="park", n=1), rp("Q1", 120, "질문B", user="kwon", n=0),
                         rp("J1", 130, "질문C", user="jung", n=2), rp("C9", 131, "C 답", to="jung")]}, pool2)
    d2 = ai.thread_detail([], "S0", {"posts": pool2})
    check("⑭ 답글 수 > 보인 본인 답인 남의 댓글만 '숨은 댓글'(시각 포함)",
          [(h["code"], h["at"]) for h in d2["hidden"]] == [("P1", 110), ("J1", 130)], d2["hidden"])
    cpool = {}
    ai.walk_posts([rp("P1", 110, "질문A", user="park"), rp("C1", 112, "A 에 단 답", to="park"),
                   rp("X2", 113, "남이 단 답", user="lee", to="park"), rp("C2", 114, "lee 에게 단 답", to="lee"),
                   rp("S1", 101, "본 글 이어 쓰기(앞선 글)", to="choi.openai"), rp("C3", 115, "본인에게 이어 씀", to="choi.openai")], cpool)
    got = ai.comment_flat(cpool, d2["hidden"][0])
    check("⑭ 댓글 화면(화면 곳곳 방식)에서 본인이 남에게 단 답만",
          sorted((r["code"], r["reply_to"]) for r in got) == [("C1", "park"), ("C2", "lee")] and "질문A" not in json.dumps(got, ensure_ascii=False), got)

    # ⑮ 예전 캐시에 남아 있던 남의 댓글 글도 읽을 때 지움 · 화면에도 표시 안 함
    ai.CACHE_DIR = tempfile.mkdtemp(prefix="ai_news_t15_")      # 진짜 캐시는 건드리지 않음
    with open(ai._path("threads"), "w", encoding="utf-8") as f:
        json.dump({"items": [{"code": "OLD", "at": 1, "posts": [], "replies": [{"code": "r", "reply_to": "kim", "reply_to_text": "남의 댓글"}]}]}, f, ensure_ascii=False)
    check("⑮ 예전 캐시의 남의 댓글 글 지움", "남의 댓글" not in json.dumps(ai._read("threads"), ensure_ascii=False))
    view = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stock", "ai_view.html"), encoding="utf-8").read()
    check("⑮ 화면이 남의 댓글 글을 그리지 않음", "reply_to_text" not in view)

    # ⑪ 진짜 브라우저로 _open_collect 한 번 돌리기(2026-10-30 서버 오류 '_pw_impl_instance_' — 가짜 page 검사로는 못 잡았음)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sync_playwright = None
        print("  (⑪ 건너뜀: playwright 없음)")
    if sync_playwright:
        import glob
        import pathlib
        tmp = pathlib.Path(tempfile.mkdtemp()) / "t.html"
        data = {"thread_items": [{"post": {"code": "Q1", "taken_at": 100, "user": {"username": "choi.openai"}, "caption": {"text": "브라우저 시험 글"}}}]}
        other = {"require": [{"containing_thread": {"node": {"code": "ROOT9", "taken_at": 200, "user": {"username": "choi.openai"}, "caption": {"text": "본 글"}}}}]}
        tmp.write_text('<script type="application/json">%s</script><script type="application/json" data-sjs>%s</script><button>답글 2개 보기</button>'
                       % (json.dumps(data), json.dumps(other)), encoding="utf-8")
        exe = os.environ.get("PW_CHROME") or ai.CHROMIUM_PATH or (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
                info = {}
                groups = ai._open_collect(b.new_page(), tmp.as_uri(), 2, info)
                b.close()
            check("⑪ 진짜 브라우저에서 _open_collect 오류 없음·글 읽음", any(it.get("post", {}).get("code") == "Q1" for g in groups for it in g) and info.get("scrolls", 0) >= 1, (groups, info))
            check("⑪ thread_items 밖 script 의 본 글도 모음(info.posts)", "ROOT9" in (info.get("posts") or {}) and "Q1" in info["posts"], list(info.get("posts") or {}))
        except Exception as e:
            check("⑪ 진짜 브라우저에서 _open_collect 오류 없음", False, repr(e))

    print("모두 통과" if ok_all else "실패 있음")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
