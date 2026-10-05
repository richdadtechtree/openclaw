#!/usr/bin/env python3
"""stock/news_keypoints.py 검사 — 대시보드 '오늘 신문 핵심' 칸이 고르는 내용 확인.

실행: python3 scripts/test_news_keypoints.py   (표준 라이브러리만, 서버·인터넷 불필요)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stock"))
from news_keypoints import extract_keypoints, latest_keypoints  # noqa: E402

ok = fail = 0


def check(name, cond, got=None):
    global ok, fail
    if cond:
        ok += 1
        print("  ✅", name)
    else:
        fail += 1
        print("  ❌", name, "→", repr(got))


# 1) 실제 화면 형식: 머리말과 1번이 한 줄, 굵게(*…*) 감쌈, 설명 줄, 2번도 굵게
SAMPLE = """📰 오늘의 신문 브리핑 (5/5)
*:mag: 오늘 신문에서 반드시 연결해서 봐야 할 5가지 1. 서울 매매 3% 이상 상승 전망 96% → 한강벨트·기존주택 선호 → 5대 은행 대출한도 소진 → 현금·대출 여력에 따른 매수 양극화*

공급 기대보다 즉시 입주 가능성과 금융 접근성이 실제 거래를 좌우하는 흐름임.

*2. 세제개편 부정 평가 78% → 임대료 전가 우려 → 공적주택 119만 계*
3. 반도체 수출 3.5% 증가 → 1. 5배 늘어난 HBM 비중
4. 금리 동결 &amp; 환율 1,380원
5. 마지막 항목
```json
{"articles":[]}
```"""
kp = extract_keypoints(SAMPLE)
check("묶음을 찾는다", kp is not None, kp)
check("머리말만 따로(5가지에서 끝남)", kp and kp["title"] == "🔍 오늘 신문에서 반드시 연결해서 봐야 할 5가지", kp and kp["title"])
check("항목 5개", kp and len(kp["items"]) == 5, kp and [i["n"] for i in kp["items"]])
check("1번 글", kp and kp["items"][0]["text"].startswith("서울 매매 3% 이상") and kp["items"][0]["text"].endswith("매수 양극화"), kp and kp["items"][0]["text"])
check("설명 줄은 1번 아래로", kp and kp["items"][0]["notes"] == ["공급 기대보다 즉시 입주 가능성과 금융 접근성이 실제 거래를 좌우하는 흐름임."], kp and kp["items"][0]["notes"])
check("굵게 감싼 2번도 번호로", kp and kp["items"][1]["text"].startswith("세제개편"), kp and kp["items"][1])
check("'3.5%'·'1. 5배' 는 번호로 안 자름", kp and "3.5% 증가 → 1. 5배" in kp["items"][2]["text"], kp and kp["items"][2]["text"])
check("&amp; 는 & 로", kp and "금리 동결 & 환율" in kp["items"][3]["text"], kp and kp["items"][3]["text"])
check("JSON 앞에서 끝남", kp and kp["items"][4]["text"] == "마지막 항목" and not kp["items"][4]["notes"], kp and kp["items"][4])

# 2) 머리말·번호가 각각 다른 줄, 동그라미 숫자
kp = extract_keypoints("🔍 오늘 꼭 볼 다섯 가지:\n① 첫째\n② 둘째\n• WHAT: 다음 기사")
check("동그라미 숫자·'다섯 가지'·콜론", kp and kp["title"] == "🔍 오늘 꼭 볼 다섯 가지" and [i["text"] for i in kp["items"]] == ["첫째", "둘째"], kp)

# 3) 오인하면 안 되는 것
check("'3가지 이유로' 평범한 문장은 무시", extract_keypoints("반도체가 3가지 이유로 올랐다.\n외국인 매수 지속") is None)
check("번호 1 없이 시작하면 무시", extract_keypoints("체크할 5가지\n2. 둘째\n3. 셋째") is None)
check("빈 글", extract_keypoints("") is None)

# 4) 같은 날 여러 번 보냈으면 가장 나중 것
msgs = [
    {"ts": "2026-10-06T07:00:00", "text": "봐야 할 2가지 1. 옛 요약 2. 옛 둘째"},
    {"ts": "2026-10-06T09:00:00", "text": "봐야 할 2가지 1. 새 요약 2. 새 둘째"},
    {"ts": "2026-10-06T10:00:00", "text": "고마워"},
]
kp = latest_keypoints(msgs)
check("가장 나중에 올라온 묶음", kp and kp["items"][0]["text"] == "새 요약" and kp["ts"].endswith("09:00:00"), kp)
check("묶음 없는 날은 None", latest_keypoints([{"ts": "x", "text": "안녕"}]) is None)

print("\n총평: %s (%d 통과 / %d 실패)" % ("✅ 전부 통과" if not fail else "❌ 실패 있음", ok, fail))
sys.exit(1 if fail else 0)
