#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_retention_cleanup.py — 보관 기간 정리기가 '지울 것만 지우는지' 확인한다.

실제 파일을 지우는 코드라 실수하면 복구가 안 된다. 그래서 임시 폴더에 가짜 자료를
만들어 두고 다음을 검사한다.

  1. 14일 정책이 달력 기준으로 맞게 동작하는가 (오늘 포함 14일치 보관)
  2. 전부 오래됐을 때 '가장 최근 1개' 를 지키는가
  3. 0일(무제한) 이면 아무것도 안 지우는가
  4. 날짜 이름이 아닌 파일(index.json 등)은 절대 안 건드리는가
  5. 심볼릭 링크를 지울 때 원본이 살아남는가
  6. 홈 밖 경로는 거부하는가

실행:  python3 scripts/test_retention_cleanup.py     (외부 라이브러리 불필요)
"""
import os
import sys
import shutil
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retention_cleanup as rc


TODAY = date(2026, 9, 19)     # 테스트는 '오늘' 을 고정해서 날짜에 흔들리지 않게 한다.


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="retention-test-")
        # expanduser("~") 가 임시 폴더를 가리키게 해서 '홈 밑' 안전장치를 통과시킨다.
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp
        self.cache = os.path.join(self.tmp, "news_cache")
        os.makedirs(self.cache)
        os.environ["NEWS_CACHE_DIR"] = self.cache
        os.environ.pop("NEWS_CACHE_KEEP_DAYS", None)
        self.target = rc.BY_KEY["news_cache"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._home
        os.environ.pop("NEWS_CACHE_DIR", None)
        os.environ.pop("NEWS_CACHE_KEEP_DAYS", None)

    def make_day(self, d, size=1000):
        """가짜 '그날 신문' 폴더 하나를 만든다."""
        p = os.path.join(self.cache, d.isoformat())
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "01.jpg"), "wb") as f:
            f.write(b"x" * size)
        return p

    def remaining(self):
        return sorted(os.listdir(self.cache))


class TestPolicy(Base):
    def test_14일_정책은_오늘_포함_14일치를_남긴다(self):
        for i in range(20):                      # 오늘부터 19일 전까지
            self.make_day(TODAY - timedelta(days=i))
        rc.sweep(self.target, days=14, verbose=False, today=TODAY)

        left = self.remaining()
        self.assertEqual(len(left), 14)
        self.assertIn("2026-09-19", left)                    # 오늘
        self.assertIn((TODAY - timedelta(days=13)).isoformat(), left)   # 경계: 남는다
        self.assertNotIn((TODAY - timedelta(days=14)).isoformat(), left)  # 경계: 지운다

    def test_평일만_있어도_달력_기준으로_지운다(self):
        """예전 '최근 7개 폴더' 방식은 주말이 빠져 9~10일 전까지 남았다 → 이제 안 그렇다."""
        d = TODAY
        made = 0
        while made < 12:                         # 평일만 12일치
            if d.weekday() < 5:
                self.make_day(d)
                made += 1
            d -= timedelta(days=1)
        rc.sweep(self.target, days=14, verbose=False, today=TODAY)

        cutoff = TODAY - timedelta(days=13)
        for name in self.remaining():
            self.assertGreaterEqual(date.fromisoformat(name), cutoff)

    def test_전부_오래됐으면_가장_최근_1개는_남긴다(self):
        for i in (40, 50, 60):
            self.make_day(TODAY - timedelta(days=i))
        rc.sweep(self.target, days=14, verbose=False, today=TODAY)
        self.assertEqual(self.remaining(), [(TODAY - timedelta(days=40)).isoformat()])

    def test_보호를_끄면_전부_지운다(self):
        for i in (40, 50):
            self.make_day(TODAY - timedelta(days=i))
        rc.sweep(self.target, days=14, verbose=False, keep_latest=False, today=TODAY)
        self.assertEqual(self.remaining(), [])

    def test_0일이면_무제한_보관(self):
        self.make_day(TODAY - timedelta(days=365))
        r = rc.sweep(self.target, days=0, verbose=False, today=TODAY)
        self.assertEqual(r["removed"], 0)
        self.assertEqual(len(self.remaining()), 1)

    def test_미리보기는_지우지_않는다(self):
        for i in (30, 40):
            self.make_day(TODAY - timedelta(days=i))
        r = rc.sweep(self.target, days=14, dry_run=True, verbose=False, today=TODAY)
        self.assertEqual(r["removed"], 1)              # 1개는 '가장 최근' 보호
        self.assertEqual(len(self.remaining()), 2)     # 실제로는 그대로


class TestSafety(Base):
    def test_날짜_이름이_아닌_것은_안_건드린다(self):
        self.make_day(TODAY - timedelta(days=30))
        for junk in (".gog_shape.json", "README.md", "2026-09", "backup-2026-09-01"):
            open(os.path.join(self.cache, junk), "w").close()
        rc.sweep(self.target, days=14, keep_latest=False, verbose=False, today=TODAY)
        left = self.remaining()
        self.assertNotIn((TODAY - timedelta(days=30)).isoformat(), left)
        for junk in (".gog_shape.json", "README.md", "2026-09", "backup-2026-09-01"):
            self.assertIn(junk, left)

    def test_없는_날짜_이름은_무시(self):
        self.assertIsNone(rc.parse_date_name("2026-02-31"))     # 2월 31일은 없다
        self.assertIsNone(rc.parse_date_name("26-09-02"))
        self.assertEqual(rc.parse_date_name("2026-09-02.jsonl"), date(2026, 9, 2))
        self.assertEqual(rc.parse_date_name("2026-09-02"), date(2026, 9, 2))

    def test_심볼릭_링크를_지워도_원본은_살아남는다(self):
        """news_cache 의 사진은 수집기 원본을 가리키는 링크다 — 원본까지 지우면 대형사고."""
        origin_dir = os.path.join(self.tmp, "newspaper")
        os.makedirs(origin_dir)
        origin = os.path.join(origin_dir, "01.jpg")
        with open(origin, "wb") as f:
            f.write("원본".encode("utf-8") * 100)

        old = (TODAY - timedelta(days=30)).isoformat()
        day = os.path.join(self.cache, old)
        os.makedirs(day)
        os.symlink(origin, os.path.join(day, "01.jpg"))

        r = rc.sweep(self.target, days=14, keep_latest=False, verbose=False, today=TODAY)
        self.assertFalse(os.path.exists(day))          # 캐시 폴더는 사라지고
        self.assertTrue(os.path.isfile(origin))        # 원본은 그대로
        self.assertEqual(r["freed"], 0)                # 링크라 실제 절약은 0
        self.assertEqual(r["links"], 1)                # 대신 링크 개수로 알려준다

    def test_홈_밖_경로는_거부한다(self):
        outside = tempfile.mkdtemp(prefix="retention-outside-")
        try:
            os.makedirs(os.path.join(outside, "2000-01-01"))
            os.environ["NEWS_CACHE_DIR"] = outside
            r = rc.sweep(self.target, days=14, keep_latest=False, verbose=False, today=TODAY)
            self.assertEqual(r["removed"], 0)
            self.assertTrue(r["errors"])
            self.assertTrue(os.path.isdir(os.path.join(outside, "2000-01-01")))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_환경변수가_이상해도_기본값으로_돈다(self):
        os.environ["NEWS_CACHE_KEEP_DAYS"] = "열네일"
        self.assertEqual(self.target.days(), 14)
        os.environ["NEWS_CACHE_KEEP_DAYS"] = "-5"
        self.assertEqual(self.target.days(), 0)        # 음수는 0(무제한)으로 막는다
        os.environ["NEWS_CACHE_KEEP_DAYS"] = "30"
        self.assertEqual(self.target.days(), 30)


class TestDefaults(unittest.TestCase):
    def test_기본_정책값(self):
        """2026-09-19 사용자 결정: 사진 14일, 텍스트 요약은 계속 보관."""
        self.assertEqual(rc.BY_KEY["news_cache"].default_days, 14)
        self.assertEqual(rc.BY_KEY["slack_logs"].default_days, 0)   # 0 = 무제한
        self.assertEqual(rc.BY_KEY["news_marks"].default_days, 14)


if __name__ == "__main__":
    unittest.main(verbosity=2)
