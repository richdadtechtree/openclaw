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
print(f"\n{ok} 통과 / {fail} 실패"); sys.exit(1 if fail else 0)
