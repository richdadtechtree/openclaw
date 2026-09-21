#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pilates_blog.py — 블로그 글 자동 생성기가 '규칙대로 도는지' 확인한다.

왜 필요한가
-----------
이 스크립트는 매일 아침 아무도 안 볼 때 혼자 돈다. 그래서 조용히 잘못되면
"오늘 글이 이상하네?" 하고 사람이 눈치챌 때까지 며칠이 지나간다.
그래서 **AI를 부르지 않고도** 확인할 수 있는 부분(주제 고르기·형식 읽기·규칙 점검)은
전부 여기서 미리 검사한다.

검사 항목
---------
  1. 주제 고르기 — 1일→Day1, 30일→Day30, 31일→Day1 로 순환하는가
  2. 규칙서 읽기 — 주석(<!-- -->) 안의 예시를 진짜 주제로 착각하지 않는가
  3. AI 답변 쪼개기 — [제목]/[본문]/[사진컨셉] 을 제대로 나누는가 (표시가 흐트러져도)
  4. 글자 수 세기 — [사진N] 표시와 줄바꿈을 빼고 세는가
  5. 규칙 점검기 — 제목 길이·특수문자·사진 누락·키워드 과다·금지 표현을 잡아내는가
  6. 최종 메시지 — 규칙서의 출력 형식대로 조립되는가
  7. 전체 흐름 — 가짜 모델을 끼워 넣고 처음부터 끝까지 굴러가는가 (네트워크 없이)

실행:  python3 scripts/test_pilates_blog.py      (외부 라이브러리 불필요)
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilates_blog as pb


SPEC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "workspace", "mybpilates_blog_prompt.md")


def make_body(main_kw, chars=1100):
    """검사용 '합격하는 본문' 을 만든다.

    - 메인 키워드 3번
    - 굵은 소제목 2개
    - [사진1]~[사진5]
    - 글자 수를 원하는 만큼 채운다
    """
    head = (f"{main_kw}를 처음 시작할 때 저도 똑같은 고민을 했습니다. [사진1]\n\n"
            f"**첫 번째로 확인할 것**\n"
            f"저희 스튜디오에서는 {main_kw} 수업 전에 자세부터 봅니다. [사진2]\n\n"
            f"**두 번째로 확인할 것**\n"
            f"회원님들이 가장 많이 묻는 부분이기도 합니다. [사진3]\n\n"
            f"제가 직접 해보니 {main_kw}는 꾸준함이 전부였습니다. [사진4]\n\n"
            f"궁금한 점은 편하게 문의해주세요. [사진5]\n\n")
    filler = "저희 회원님들과 함께 해온 기록을 담담하게 적어둡니다. "
    while pb.body_length(head) < chars:
        head += filler
    return head


class 주제고르기(unittest.TestCase):
    def setUp(self):
        self.topics = [{"day": i, "name": f"주제{i}", "main": f"키워드{i}",
                        "subs": [], "direction": "", "photos": []} for i in range(1, 31)]

    def test_날짜대로_고른다(self):
        self.assertEqual(pb.pick_topic(self.topics, 1)["day"], 1)
        self.assertEqual(pb.pick_topic(self.topics, 15)["day"], 15)
        self.assertEqual(pb.pick_topic(self.topics, 30)["day"], 30)

    def test_31일은_1번으로_돌아온다(self):
        self.assertEqual(pb.pick_topic(self.topics, 31)["day"], 1)

    def test_주제가_적어도_안터진다(self):
        few = self.topics[:7]
        self.assertEqual(pb.pick_topic(few, 8)["day"], 1)     # 7개뿐이면 8일은 다시 1번
        self.assertIsNone(pb.pick_topic([], 5))


class 규칙서읽기(unittest.TestCase):
    def setUp(self):
        self.md = io.open(SPEC, encoding="utf-8").read()
        self.topics = pb.parse_topics(self.md)

    def test_주제가_30개다(self):
        self.assertEqual(len(self.topics), 30, "30일 주제 풀이 30개가 아닙니다")

    def test_번호가_안겹친다(self):
        days = [t["day"] for t in self.topics]
        self.assertEqual(sorted(days), list(range(1, 31)))

    def test_주석_속_예시는_주제가_아니다(self):
        """규칙서 맨 위 주석에 적어둔 `### Day 3 — …` 예시를 세면 31개가 된다."""
        self.assertEqual(len([t for t in self.topics if t["day"] == 3]), 1)

    def test_모든_주제에_키워드와_사진힌트가_있다(self):
        for t in self.topics:
            self.assertTrue(t["main"], f"Day {t['day']} 메인 키워드 없음")
            self.assertTrue(t["subs"], f"Day {t['day']} 서브 키워드 없음")
            self.assertEqual(len(t["photos"]), 5, f"Day {t['day']} 사진 힌트가 5개가 아님")

    def test_규칙본문이_뽑힌다(self):
        rules = pb.build_rules_text(pb.split_sections(self.md))
        self.assertIn("제목 규칙", rules)
        self.assertIn("1000~1200자", rules)
        # 출력 형식은 스크립트가 직접 만들므로 AI에게 주지 않는다
        self.assertNotIn("📝 마이비필라테스 블로그 글 (YYYY-MM-DD)", rules)


class 답변쪼개기(unittest.TestCase):
    def test_기본형식(self):
        raw = "[제목]\n필라테스 초보가 알아야 할 세 가지\n\n[본문]\n본문입니다. [사진1]\n\n[사진컨셉]\n1. 가\n2. 나\n3. 다\n4. 라\n5. 마"
        title, body, photos = pb.parse_draft(raw)
        self.assertEqual(title, "필라테스 초보가 알아야 할 세 가지")
        self.assertIn("본문입니다", body)
        self.assertEqual(photos, ["가", "나", "다", "라", "마"])

    def test_표시가_흐트러져도_알아듣는다(self):
        raw = "**[제목]**\n제목: 코어 운동 시작하기\n## [본문]\n내용\n【사진컨셉】\n1) 하나\n2) 둘"
        title, body, photos = pb.parse_draft(raw)
        self.assertEqual(title, "코어 운동 시작하기")     # 앞의 '제목:' 은 떼어낸다
        self.assertEqual(body.strip(), "내용")
        self.assertEqual(photos, ["하나", "둘"])

    def test_빈_답변은_None(self):
        self.assertEqual(pb.parse_draft(""), (None, None, []))


class 글자수세기(unittest.TestCase):
    def test_사진표시와_줄바꿈은_안센다(self):
        self.assertEqual(pb.body_length("가나다[사진1]라마"), 5)
        self.assertEqual(pb.body_length("가나\n다라"), 4)
        self.assertEqual(pb.body_length("가 나"), 3)        # 공백은 센다(규칙서: 공백 포함)

    def test_키워드_세기는_띄어쓰기를_무시한다(self):
        self.assertEqual(pb.count_keyword("코어운동과 코어 운동", "코어 운동"), 2)


class 규칙점검(unittest.TestCase):
    def setUp(self):
        self.topic = {"day": 1, "name": "필라테스 초보", "main": "필라테스 초보",
                      "subs": ["필라테스 입문"], "direction": "", "photos": []}
        self.title = "필라테스 초보가 첫 수업 전에 알아야 할 세 가지"   # 26자
        self.body = make_body("필라테스 초보", 1100)
        self.photos = ["가", "나", "다", "라", "마"]

    def test_정상_원고는_통과한다(self):
        hard, soft = pb.validate(self.title, self.body, self.photos, self.topic)
        self.assertEqual(hard, [], f"정상 원고인데 걸림: {hard}")

    def test_제목이_너무_짧으면_걸린다(self):
        hard, _ = pb.validate("필라테스 초보 안내", self.body, self.photos, self.topic)
        self.assertTrue(any("제목이" in h for h in hard))

    def test_제목_특수문자를_잡는다(self):
        hard, _ = pb.validate("필라테스 초보가 알아야 할 세 가지★☆", self.body, self.photos, self.topic)
        self.assertTrue(any("특수문자" in h for h in hard))

    def test_제목에_키워드가_없으면_걸린다(self):
        hard, _ = pb.validate("처음 운동 시작할 때 알아두면 좋은 것들 정리", self.body, self.photos, self.topic)
        self.assertTrue(any("메인 키워드" in h for h in hard))

    def test_본문이_짧으면_걸린다(self):
        hard, _ = pb.validate(self.title, make_body("필라테스 초보", 300), self.photos, self.topic)
        self.assertTrue(any("본문이" in h for h in hard))

    def test_사진표시_누락을_잡는다(self):
        body = self.body.replace("[사진3]", "").replace("[사진5]", "")
        hard, _ = pb.validate(self.title, body, self.photos, self.topic)
        self.assertTrue(any("[사진3]" in h and "[사진5]" in h for h in hard))

    def test_키워드_남발을_잡는다(self):
        body = self.body + "필라테스 초보 " * 6
        hard, _ = pb.validate(self.title, body, self.photos, self.topic)
        self.assertTrue(any("스팸" in h for h in hard))

    def test_의학적_단정을_잡는다(self):
        body = self.body.replace("꾸준함이 전부였습니다", "허리디스크가 완치됩니다")
        hard, _ = pb.validate(self.title, body, self.photos, self.topic)
        self.assertTrue(any("완치" in h for h in hard))

    def test_사진컨셉이_5개가_아니면_걸린다(self):
        hard, _ = pb.validate(self.title, self.body, ["가", "나"], self.topic)
        self.assertTrue(any("사진 컨셉" in h for h in hard))

    def test_소제목이_없으면_걸린다(self):
        body = self.body.replace("**", "")
        hard, _ = pb.validate(self.title, body, self.photos, self.topic)
        self.assertTrue(any("소제목" in h for h in hard))


class 최종메시지(unittest.TestCase):
    def test_출력형식대로_조립된다(self):
        topic = {"day": 1, "name": "필라테스 초보", "main": "필라테스 초보",
                 "subs": ["필라테스 입문", "필라테스 준비물"], "direction": "", "photos": []}
        msg = pb.build_message("2026-09-21", topic, "제목입니다",
                               "**소제목**\n본문 [사진1]", ["가", "나", "다", "라", "마"], [])
        self.assertIn("📝 *마이비필라테스 블로그 글* (2026-09-21)", msg)
        self.assertIn("🔑 메인 키워드: 필라테스 초보", msg)
        self.assertIn("🏷️ 서브 키워드: 필라테스 입문, 필라테스 준비물", msg)
        self.assertIn("제목: 제목입니다", msg)
        self.assertIn("📷 오늘의 사진 컨셉:", msg)
        self.assertIn("✅ 발행 전 체크리스트:", msg)
        self.assertIn("*소제목*", msg)          # 슬랙에서 굵게 보이도록 ** → *
        self.assertNotIn("**소제목**", msg)

    def test_점검경고가_붙는다(self):
        topic = {"day": 1, "name": "x", "main": "x", "subs": [], "direction": "", "photos": []}
        msg = pb.build_message("2026-09-21", topic, "t", "b", ["1"], ["본문 900자"])
        self.assertIn("⚠️ 자동 점검에서 걸린 부분", msg)
        self.assertIn("본문 900자", msg)

    def test_긴글은_쪼갠다(self):
        parts = pb.chunk("가" * 4000 + "\n" + "나" * 4000)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 3500 + 1 for p in parts))


class 전체흐름(unittest.TestCase):
    """가짜 모델을 끼워 넣어 '네트워크 없이' 처음부터 끝까지 돌려본다."""

    def setUp(self):
        self.sent = []
        self._gen, self._post = pb.generate, pb.post_to_slack

        def fake_generate(system, user, timeout, order=None):
            main = "필라테스 초보" if "필라테스 초보" in user else "코어 운동"
            body = make_body(main, 1100)
            photos = "\n".join(f"{i}. 사진{i} 설명" for i in range(1, 6))
            return (f"[제목]\n{main}가 첫 수업 전에 알아야 할 세 가지\n\n"
                    f"[본문]\n{body}\n\n[사진컨셉]\n{photos}"), "fake", []

        pb.generate = fake_generate
        pb.post_to_slack = lambda text, channel, token: self.sent.append((channel, text)) or True
        os.environ["SLACK_BOT_TOKEN_DEFAULT"] = "xoxb-test"

    def tearDown(self):
        pb.generate, pb.post_to_slack = self._gen, self._post
        os.environ.pop("SLACK_BOT_TOKEN_DEFAULT", None)

    def test_하루치가_발송된다(self):
        rc = pb.main_for_test(["--date", "2026-09-01", "--no-history"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.sent), 1)
        channel, text = self.sent[0]
        self.assertEqual(channel, pb.DEFAULT_CHANNEL)       # #심부름
        self.assertIn("필라테스 초보", text)
        self.assertIn("📷 오늘의 사진 컨셉:", text)

    def test_dry_run은_발송하지_않는다(self):
        rc = pb.main_for_test(["--date", "2026-09-02", "--dry-run", "--no-history"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.sent, [])

    def test_모델이_다_죽으면_실패로_끝난다(self):
        pb.generate = lambda *a, **k: (None, None, ["gateway: 연결 실패"])
        os.environ["PILATES_NOTIFY_ON_FAIL"] = "0"          # 실패 알림도 끄고 본다
        try:
            rc = pb.main_for_test(["--date", "2026-09-03", "--no-history", "--retries", "0"])
        finally:
            os.environ.pop("PILATES_NOTIFY_ON_FAIL", None)
        self.assertEqual(rc, 3)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
