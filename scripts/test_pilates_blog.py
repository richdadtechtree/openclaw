#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pilates_blog.py — '글 배달부' 가 제대로 도는지 확인한다.

왜 필요한가
-----------
이 스크립트는 매일 아침 아무도 안 볼 때 혼자 돈다. 조용히 잘못되면
"오늘 글이 왜 안 왔지?" 를 며칠 뒤에나 알게 된다. 그래서 **슬랙도 AI도 부르지 않고**
확인할 수 있는 부분은 전부 여기서 미리 검사한다.

검사 항목
---------
  1. 글 파일 읽기 — 형식이 어긋나면 추측하지 않고 사유를 말하는가
  2. 차례 고르기 — 안 보낸 글 중 제일 앞 것을 고르고, 보낸 건 건너뛰는가
  3. 글자 수 세기 — [사진N] 표시와 줄바꿈을 빼고 세는가
  4. 규칙 점검기 — 제목 길이·특수문자·사진 누락·키워드 과다·금지 표현을 잡아내는가
  5. 최종 메시지 — 규칙서의 출력 형식대로 조립되고, 재고가 적으면 알려주는가
  6. 전체 흐름 — 가짜 창고로 발송 → 다음날 그 다음 글 → 창고가 비면 안내만

실행:  python3 scripts/test_pilates_blog.py      (외부 라이브러리 불필요)
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilates_blog as pb


def make_post_text(main_kw="필라테스 초보",
                   title="필라테스 초보가 첫 수업 전에 알아야 할 세 가지",
                   chars=1100, photos=5):
    """검사용 '합격하는 글 파일' 내용을 만든다."""
    body = (f"{main_kw}를 시작할 때 저도 똑같은 고민을 했습니다. [사진1]\n\n"
            f"**첫 번째로 확인할 것**\n"
            f"저희 스튜디오에서는 {main_kw} 수업 전에 자세부터 봅니다. [사진2]\n\n"
            f"**두 번째로 확인할 것**\n"
            f"회원님들이 가장 많이 묻는 부분입니다. [사진3]\n\n"
            f"제가 직접 해보니 {main_kw}는 꾸준함이 전부였습니다. [사진4]\n\n"
            f"궁금한 점은 편하게 문의해주세요. [사진5]\n\n")
    filler = "저희 회원님들과 함께 해온 기록을 담담하게 적어둡니다. "
    while pb.body_length(body) < chars:
        body += filler
    photo_lines = "\n".join(
        f"{i}. 촬영: 사진{i} 장면을 어떤 각도로 찍을지 적은 설명\n"
        f"   포인트: 사진에 담겨야 할 동작 정보\n"
        f"   캡션: 사진 밑에 넣을 한 줄" for i in range(1, photos + 1))
    return (f"제목: {title}\n"
            f"메인: {main_kw}\n"
            f"서브: 필라테스 입문, 필라테스 준비물\n"
            f"주제: Day 1 — {main_kw}\n"
            f"{pb.BODY_MARK}\n{body}\n{pb.PHOTO_MARK}\n{photo_lines}\n")


class 글파일읽기(unittest.TestCase):
    def test_정상_파일을_읽는다(self):
        post, err = pb.parse_post(make_post_text())
        self.assertIsNone(err)
        self.assertEqual(post["main"], "필라테스 초보")
        self.assertEqual(post["subs"], ["필라테스 입문", "필라테스 준비물"])
        self.assertEqual(len(post["photos"]), 5)
        self.assertIn("[사진1]", post["body"])

    def test_본문표시가_없으면_사유를_말한다(self):
        post, err = pb.parse_post("제목: 무언가\n메인: 키워드\n본문만 덩그러니")
        self.assertIsNone(post)
        self.assertIn(pb.BODY_MARK, err)

    def test_제목이_없으면_보내지_않는다(self):
        text = make_post_text().replace("제목: 필라테스 초보가 첫 수업 전에 알아야 할 세 가지\n", "")
        post, err = pb.parse_post(text)
        self.assertIsNone(post)
        self.assertIn("제목", err)

    def test_사진설명이_여러_줄이면_붙여_읽는다(self):
        post, err = pb.parse_post(make_post_text())
        self.assertIsNone(err)
        self.assertEqual(len(post["photos"]), 5)          # 줄이 3개여도 사진은 1개로 센다
        self.assertIn("포인트:", post["photos"][0])
        self.assertIn("캡션:", post["photos"][0])

    def test_사진표시가_없어도_본문은_읽힌다(self):
        text = make_post_text().split(pb.PHOTO_MARK)[0]
        post, err = pb.parse_post(text)
        self.assertIsNone(err)
        self.assertEqual(post["photos"], [])      # 사진 컨셉 0개 → 점검에서 걸린다


class 차례고르기(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pilates-test-")
        self.posts = os.path.join(self.tmp, "posts")
        os.makedirs(self.posts)
        for i in (1, 2, 3):
            with open(os.path.join(self.posts, f"day{i:02d}-글.md"), "w", encoding="utf-8") as f:
                f.write(make_post_text(title=f"필라테스 초보 {i}번째 이야기를 적어봅니다 오늘도"))
        self.state = os.path.join(self.tmp, "sent.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_안보낸_글중_제일_앞을_고른다(self):
        target, remaining, rnd = pb.pick_next(self.posts, self.state)
        self.assertTrue(os.path.basename(target).startswith("day01"))
        self.assertEqual((remaining, rnd), (3, 1))

    def test_보낸_글은_건너뛴다(self):
        pb.mark_sent({"file": "day01-글.md"}, self.state)
        target, remaining, rnd = pb.pick_next(self.posts, self.state)
        self.assertTrue(os.path.basename(target).startswith("day02"))
        self.assertEqual((remaining, rnd), (2, 1))

    def test_다_보내면_처음부터_다시_돈다(self):
        """한 바퀴가 끝나도 멈추지 않는다 — 배달이 끊기면 안 된다."""
        for i in (1, 2, 3):
            pb.mark_sent({"file": f"day{i:02d}-글.md"}, self.state)
        target, remaining, rnd = pb.pick_next(self.posts, self.state)
        self.assertTrue(os.path.basename(target).startswith("day01"))
        self.assertEqual(rnd, 2)                       # 2바퀴째
        self.assertEqual(remaining, 3)

    def test_새로_넣은_글이_먼저_나간다(self):
        for i in (1, 2, 3):
            pb.mark_sent({"file": f"day{i:02d}-글.md"}, self.state)
        with open(os.path.join(self.posts, "day04-새글.md"), "w", encoding="utf-8") as f:
            f.write(make_post_text(title="필라테스 초보 네 번째 이야기를 적어봅니다 오늘"))
        target, remaining, rnd = pb.pick_next(self.posts, self.state)
        self.assertTrue(os.path.basename(target).startswith("day04"))
        self.assertEqual(rnd, 1)                       # 아직 0번 보낸 글이라 1바퀴째

    def test_글_파일이_하나도_없으면_None(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        self.assertEqual(pb.pick_next(empty, self.state), (None, 0, 1))


class 글자수세기(unittest.TestCase):
    def test_사진표시와_줄바꿈은_안센다(self):
        self.assertEqual(pb.body_length("가나다[사진1]라마"), 5)
        self.assertEqual(pb.body_length("가나\n다라"), 4)
        self.assertEqual(pb.body_length("가 나"), 3)        # 공백은 센다(규칙서: 공백 포함)

    def test_키워드_세기는_띄어쓰기를_무시한다(self):
        self.assertEqual(pb.count_keyword("코어운동과 코어 운동", "코어 운동"), 2)


class 규칙점검(unittest.TestCase):
    def post(self, **kw):
        p, err = pb.parse_post(make_post_text(**kw))
        self.assertIsNone(err)
        return p

    def test_정상_글은_통과한다(self):
        self.assertEqual(pb.validate(self.post()), [])

    def test_제목이_짧으면_걸린다(self):
        issues = pb.validate(self.post(title="필라테스 초보 안내"))
        self.assertTrue(any("제목" in i for i in issues))

    def test_제목_특수문자를_잡는다(self):
        issues = pb.validate(self.post(title="필라테스 초보가 알아야 할 세 가지 정리★"))
        self.assertTrue(any("특수문자" in i for i in issues))

    def test_본문이_짧으면_걸린다(self):
        issues = pb.validate(self.post(chars=400))
        self.assertTrue(any("본문" in i for i in issues))

    def test_사진표시_누락을_잡는다(self):
        p = self.post()
        p["body"] = p["body"].replace("[사진3]", "")
        self.assertTrue(any("[사진3]" in i for i in pb.validate(p)))

    def test_키워드_남발을_잡는다(self):
        p = self.post()
        p["body"] += "필라테스 초보 " * 6
        self.assertTrue(any("과다" in i for i in pb.validate(p)))

    def test_의학적_단정을_잡는다(self):
        p = self.post()
        p["body"] = p["body"].replace("꾸준함이 전부였습니다", "허리디스크가 완치됩니다")
        self.assertTrue(any("완치" in i for i in pb.validate(p)))

    def test_사진컨셉이_5개가_아니면_걸린다(self):
        issues = pb.validate(self.post(photos=3))
        self.assertTrue(any("사진 컨셉" in i for i in issues))

    def test_소제목이_없으면_걸린다(self):
        p = self.post()
        p["body"] = p["body"].replace("**", "")
        self.assertTrue(any("소제목" in i for i in pb.validate(p)))


class 최종메시지(unittest.TestCase):
    def post(self):
        p, _ = pb.parse_post(make_post_text())
        return p

    def test_출력형식대로_조립된다(self):
        msg = pb.build_message("2026-09-21", self.post())
        self.assertIn("📝 *마이비필라테스 블로그 글* (2026-09-21)", msg)
        self.assertIn("🔑 메인 키워드: 필라테스 초보", msg)
        self.assertIn("📷 오늘의 사진 컨셉:", msg)
        self.assertIn("✅ 발행 전 체크리스트:", msg)
        self.assertIn("*첫 번째로 확인할 것*", msg)     # ** → * (슬랙 굵게)
        self.assertNotIn("**첫 번째", msg)

    def test_재고가_적으면_알려준다(self):
        self.assertIn("새 글이 3편 남았습니다", pb.build_message("2026-09-21", self.post(), remaining=3))
        self.assertNotIn("남았습니다", pb.build_message("2026-09-21", self.post(), remaining=20))

    def test_두번째_바퀴는_회차를_알려준다(self):
        msg = pb.build_message("2026-09-21", self.post(), remaining=3, round_no=2)
        self.assertIn("2회차", msg)
        self.assertIn("그대로 올리지 마시고", msg)
        self.assertNotIn("새 글이 3편 남았습니다", msg)   # 회차 안내가 재고 안내를 대신한다

    def test_사진설명_여러_줄이_들여쓰기된다(self):
        msg = pb.build_message("2026-09-21", self.post())
        self.assertIn("1. 촬영:", msg)
        self.assertIn("    포인트:", msg)

    def test_점검경고가_붙는다(self):
        msg = pb.build_message("2026-09-21", self.post(), warnings=["본문 900자"])
        self.assertIn("⚠️ 자동 점검에서 걸린 부분", msg)

    def test_긴글은_쪼갠다(self):
        parts = pb.chunk("가" * 4000 + "\n" + "나" * 4000)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 3501 for p in parts))


class 전체흐름(unittest.TestCase):
    """가짜 창고를 만들어 '슬랙 없이' 처음부터 끝까지 돌려본다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pilates-flow-")
        self.posts = os.path.join(self.tmp, "posts")
        os.makedirs(self.posts)
        for i in (1, 2):
            with open(os.path.join(self.posts, f"day{i:02d}-글.md"), "w", encoding="utf-8") as f:
                f.write(make_post_text(title=f"필라테스 초보 {i}번째 이야기를 적어봅니다 오늘"))
        self.sent = []
        self._post, self._sentfile = pb.post_to_slack, pb.SENT_FILE
        pb.SENT_FILE = os.path.join(self.tmp, "sent.jsonl")
        pb.post_to_slack = lambda text, channel, token: self.sent.append((channel, text)) or True
        os.environ["SLACK_BOT_TOKEN_DEFAULT"] = "xoxb-test"

    def tearDown(self):
        pb.post_to_slack, pb.SENT_FILE = self._post, self._sentfile
        os.environ.pop("SLACK_BOT_TOKEN_DEFAULT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_main(self, *extra):
        return pb.main_for_test(["--posts-dir", self.posts, *extra])

    def test_하루에_한편씩_순서대로_간다(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(len(self.sent), 2)
        self.assertIn("1번째", self.sent[0][1])
        self.assertIn("2번째", self.sent[1][1])          # 같은 글을 두 번 안 보낸다
        self.assertEqual(self.sent[0][0], pb.DEFAULT_CHANNEL)   # #심부름

    def test_한_바퀴_돌면_멈추지_않고_다시_보낸다(self):
        self.run_main(); self.run_main()
        self.sent.clear()
        self.assertEqual(self.run_main(), 0)             # 멈추지 않는다
        self.assertEqual(len(self.sent), 1)
        self.assertIn("1번째", self.sent[0][1])          # 처음 글로 돌아왔다
        self.assertIn("2회차", self.sent[0][1])          # 재탕임을 분명히 알린다

    def test_글_파일이_없을_때만_안내로_끝난다(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        self.assertEqual(pb.main_for_test(["--posts-dir", empty]), 1)
        self.assertIn("보낼 필라테스 블로그 글이 없습니다", self.sent[0][1])
        self.assertNotIn("📷 오늘의 사진 컨셉", self.sent[0][1])   # 글을 지어내지 않는다

    def test_dry_run은_보내지도_기록하지도_않는다(self):
        self.assertEqual(self.run_main("--dry-run"), 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.run_main(), 0)
        self.assertIn("1번째", self.sent[0][1])          # dry-run 이 차례를 까먹지 않았다

    def test_day_로_지정해서_보낼_수_있다(self):
        self.assertEqual(self.run_main("--day", "2"), 0)
        self.assertIn("2번째", self.sent[0][1])

    def test_check_는_창고를_검사한다(self):
        self.assertEqual(self.run_main("--check"), 0)
        with open(os.path.join(self.posts, "day03-깨진글.md"), "w", encoding="utf-8") as f:
            f.write("제목만 있고 본문 표시가 없음")
        self.assertEqual(self.run_main("--check"), 2)    # 문제 있으면 2


if __name__ == "__main__":
    unittest.main(verbosity=2)
