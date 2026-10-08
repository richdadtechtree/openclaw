#!/usr/bin/env python3
"""mer_blog_slack.py 오프라인 검사 (네트워크 불필요). 실행: python3 scripts/test_mer_blog_slack.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mer_blog_slack as m

ok = fail = 0
def check(name, cond):
    global ok, fail
    print(("✅ " if cond else "❌ ") + name)
    ok, fail = ok + bool(cond), fail + (not cond)

RSS = """<?xml version="1.0"?><rss><channel>
<item><title><![CDATA[글 &amp; 둘]]></title><link>https://blog.naver.com/ranto28/223900002?x=1</link></item>
<item><title>글 하나</title><link>https://blog.naver.com/ranto28/223900001</link></item>
<item><title>번호없음</title><link>https://blog.naver.com/ranto28</link></item></channel></rss>"""
p = m.parse_rss(RSS)
check("RSS: 2건(번호 없는 항목 제외), 최신순", [x["no"] for x in p] == ["223900002", "223900001"])
check("RSS: 제목 엔티티 풀림", p[0]["title"] == "글 & 둘")

SE = """<html><script>var a="한줄평 가짜";</script><div class="se-main-container">
<div class="se-component"><p class="se-text-paragraph"><span>본문 첫 문단입니다.</span></p></div>
<div class="se-component"><p class="se-text-paragraph"><span>한줄평: 금리보다 중요한 건 방향이다.</span></p></div>
<div class="se-component"><p class="se-text-paragraph"><span>&#8203;</span></p></div>
<div class="se-component"><p class="se-text-paragraph"><span>#경제 #투자</span></p></div></div></html>"""
one, how = m.pick_oneliner(m.parse_paragraphs(SE))
check("표지 같은 줄: 콜론 뒤 문장", (one, how) == ("금리보다 중요한 건 방향이다.", "marker"))

SE2 = SE.replace("한줄평: 금리보다 중요한 건 방향이다.", "한줄평").replace(
    "<p class=\"se-text-paragraph\"><span>&#8203;", "<p class=\"se-text-paragraph\"><span>환율은 결국 심리다.</span></p><p class=\"se-text-paragraph\"><span>&#8203;")
one, how = m.pick_oneliner(m.parse_paragraphs(SE2))
check("표지만 있으면 다음 줄", (one, how) == ("환율은 결국 심리다.", "marker"))
check("script 안의 '한줄평' 은 무시", "가짜" not in " ".join(m.parse_paragraphs(SE)))

NO_MARK = SE.replace("한줄평: ", "")
one, how = m.pick_oneliner(m.parse_paragraphs(NO_MARK))
check("표지 없으면 마지막 문단(해시태그 건너뜀)", (one, how) == ("금리보다 중요한 건 방향이다.", "last"))

LONG = '<div class="se-main-container"><p class="se-text-paragraph">' + "가" * 600 + "</p></div>"
check("너무 긴 마지막 문단은 한줄평으로 안 씀", m.pick_oneliner(m.parse_paragraphs(LONG)) == (None, None))

OLD = '<div id="postViewArea">첫 줄<br>한줄평 - 오래된 에디터 글<br></div>'
check("옛 에디터(postViewArea)도 읽힘", m.pick_oneliner(m.parse_paragraphs(OLD))[0] == "오래된 에디터 글")
check("빈 페이지 → 문단 0개", m.parse_paragraphs("<html>로그인</html>") == [])


# 사용자가 보내준 실제 글의 마지막 문단(빨간 글씨 span 포함) — % 글자가 있어 문자열을 이어 붙인다
COMMENT = '한줄 코멘트. 미국국채 10년물의 응찰배율이 2.77배가 나왔고, 간접입찰이 80%를 넘겼으며, 프라이머리 딜러 비중이 2.54%밖에 나오지 않았다. 응찰배율과 프라이머리딜러 비중은 미국국채에 대한 전반적인 수요를 볼 수 있고, 간접입찰은 그중에서 해외 수요를 판단하는 지표로 쓰인다. 세 지표가 모두 강한 수요를 보여준 것이다. 5.3%라는 낙찰금리 자체는 2000년이후 26년만에 최고 수준이라 부담스러운 숫자다. 하지만, 미국국채 수요가 살아있는 것이 시장을 어느정도 안심시킬 것 같다. 프랑스 상황을 보고는, <span style="color:red">"그래도 미국이 낫네"</span>라는 생각들을 하는 것 같다. 5.3%라는 금리 자체가 매력적으로 보였을 수도 있다.'
REAL = ("<div class=\"se-main-container\"><p class=\"se-text-paragraph\"><span>앞 본문입니다.</span></p>"
        "<p class=\"se-text-paragraph\"><span>" + COMMENT + "</span></p>"
        "<p class=\"se-text-paragraph\"><span>#미국국채 #금리</span></p></div>")
one, how = m.pick_oneliner(m.parse_paragraphs(REAL))
check("실제 형식: '한줄 코멘트.' 로 시작하는 긴(370자↑) 문단 → 표지 제거 후 통째로", how == "marker" and one.startswith("미국국채") and one.endswith("수도 있다.") and len(one) > 300 and "#" not in one)
check("빨간 글씨(span) 안의 문장도 빠짐없이", "그래도 미국이 낫네" in one)

msg = m.build_message({"title": "A<B", "link": "https://x"}, "한 줄", "marker")
check("슬랙 메시지: 제목 이스케이프+링크+인용", "A&lt;B" in msg and "> 한 줄" in msg and "<https://x|원문 보기>" in msg)
check("한줄평 없으면 솔직한 안내", "찾지 못했어요" in m.build_message({"title": "t", "link": "l"}, None, None))

# ── GPT 요약 (게이트웨이 대신 가짜 chat 함수를 넣어 검사) ──
BODY = "10년물 응찰배율이 2.77배, 간접입찰이 80%를 넘겼다. 낙찰금리는 5.3%로 2,000건 이상 참여했다. " * 2
good = "• 응찰배율이 2.77배였다.\n2. 간접입찰은 80%를 넘겼다.\n- 낙찰금리는 5.3%였다.\n"
calls = []
def fake(ans):
    def chat(system, user):
        calls.append(user); return ans
    return chat
r = m.summarize("제목", BODY, chat=fake(good))
check("요약: 3줄, 불릿·번호 머리 제거", r == ["응찰배율이 2.77배였다.", "간접입찰은 80%를 넘겼다.", "낙찰금리는 5.3%였다."])
check("요약: 쉼표 숫자(2,000)와 2000 은 같은 숫자로 취급", m.numbers("2,000건") == {"2000"})
calls.clear()
r = m.summarize("제목", BODY, chat=fake("• 응찰배율 2.78배\n• 비중 9%\n• 금리 5.3%"))
check("요약: 본문에 없는 숫자(2.78·9) → 1번 다시 시키고 그래도 틀리면 요약 포기", r is None and len(calls) == 2 and "2.78" in calls[1])
seq = iter(["• 배율 2.78배\n• 간접 80%\n• 금리 5.3%", good])
r = m.summarize("제목", BODY, chat=lambda s_, u_: next(seq))
check("요약: 첫 답이 틀려도 재시도에서 맞으면 사용", r and len(r) == 3)
check("요약: 너무 짧은(2줄) 답은 버림", m.summarize("제목", BODY, chat=fake("• 하나\n• 둘")) is None)
def boom(s_, u_): raise RuntimeError("게이트웨이 꺼짐")
check("요약: 게이트웨이 오류여도 예외 없이 None(제목·한줄평은 계속 감)", m.summarize("제목", BODY, chat=boom) is None)
check("요약: 본문이 너무 짧으면(사진 글) 호출조차 안 함", m.summarize("제목", "짧다", chat=boom) is None)
b = m.body_for_summary(["본문", "한줄 코멘트. 이건 한줄평", "#태그 #경제"], "이건 한줄평")
check("요약 입력에서 한줄평 문단·해시태그 제외", b == "본문")
check("긴 글은 앞·뒤만 보냄", len(m.body_for_summary(["가" * 20000], None)) < 12100)
mm = m.build_message({"title": "t", "link": "https://x"}, "한 줄", "marker", ["A <1>", "B"])
check("슬랙 메시지: 요약(AI 요약 표시) → 한줄평 → 링크 순서", mm.index("핵심 요약") < mm.index("한줄평") < mm.index("원문 보기") and "AI 요약" in mm and "&lt;1&gt;" in mm)
check("요약 없으면 요약 블록 자체가 없음", "핵심 요약" not in m.build_message({"title": "t", "link": "l"}, "한 줄", "marker", None))
import subprocess
for bad in ("글번호", "https://blog.naver.com/ranto28"):
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mer_blog_slack.py"), "--show", bad], capture_output=True, text=True)
    check(f"--show '{bad}' (번호 없음) → 오류 덩어리 대신 안내 + 종료코드 2", r.returncode == 2 and "글 번호를 못 찾았습니다" in r.stderr and "Traceback" not in r.stderr)
print(f"\n{ok} 통과 / {fail} 실패"); sys.exit(1 if fail else 0)
