#!/usr/bin/env python3
"""newspaper_auto_pull.py 검사 — 진짜 git 저장소를 임시로 만들어 서버 상황을 흉내 낸다.

  'GitHub'  = 임시 bare 저장소 (git 의 insteadOf 로 github 주소를 이 폴더로 돌림)
  '서버'    = 그걸 받은 ~/newspaper 흉내 + 서버에서 손으로 고친 패치들
실행: python3 scripts/test_newspaper_auto_pull.py   (인터넷 불필요)
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import newspaper_auto_pull as ap  # noqa: E402

URL = "https://github.com/richdadtechtree/newspaper"
BR = "claude/naver-cafe-newspaper-download-caonzo"

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_CAFE = ("import re\nlogger = None\n\ndef find(title, date_pattern):\n"
            "    is_match = bool(date_pattern.search(title))\n    return is_match\n")
NEW_CAFE = ("import re\nlogger = None\n\ndef find(title, date_pattern):\n"
            "    is_match = bool(date_pattern.search(title)) and _oc_title_ok(title)\n    return is_match\n\n"
            "def _oc_title_ok(t):\n    return '신문스크랩' in t.replace(' ', '')\n")
NEW_MAIN = "import argparse\np = argparse.ArgumentParser()\np.add_argument(\"--force\")\n"


def sh(cwd, *args):
    return subprocess.run(list(args), cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class AutoPull(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="np_pull_")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        # git 설정을 이 검사 안에만 (진짜 사용자 설정을 건드리지 않음)
        self.env = mock.patch.dict(os.environ, {
            "HOME": self.home, "GIT_CONFIG_GLOBAL": os.path.join(self.home, ".gitconfig"),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t"})
        self.env.start()
        self.bare = os.path.join(self.tmp, "github.git")
        sh(self.tmp, "git", "init", "-q", "--bare", "-b", BR, self.bare)
        sh(self.tmp, "git", "config", "--global", "url.%s.insteadOf" % self.bare, URL)
        # 개발자 작업 폴더(= 내가 GitHub 에 올리는 쪽)
        self.dev = os.path.join(self.tmp, "dev")
        sh(self.tmp, "git", "clone", "-q", URL, self.dev)
        sh(self.dev, "git", "checkout", "-q", "-b", BR)
        self.write(self.dev, "app/naver_cafe.py", OLD_CAFE)
        self.write(self.dev, "app/main.py", "import argparse\n")
        self.write(self.dev, "app/drive_uploader.py", "import shutil\nshutil.rmtree\n")
        self.write(self.dev, "scripts/run_daily.sh", "CUTOFF=\"07:00\"\necho hi\n")
        self.commit(self.dev, "v1")
        # 서버 = 그걸 받은 폴더 + 서버에서 덧댄 패치 3개
        self.srv = os.path.join(self.tmp, "newspaper")
        sh(self.tmp, "git", "clone", "-q", "-b", BR, URL, self.srv)
        # 예전 제목 필터 패치 — 서버와 똑같이 진짜 패치 도구로 적용
        subprocess.run(["bash", os.path.join(HERE, "patch-newspaper-title-filter.sh")], check=True,
                       capture_output=True, env=dict(os.environ, NEWSPAPER_DIR=self.srv))
        self.patched_cafe = self.read("app/naver_cafe.py")
        assert "_oc_title_ok(title)" in self.patched_cafe and "[openclaw 패치]" in self.patched_cafe
        self.write(self.srv, "app/drive_uploader.py", "import shutil\n# keep today\n")  # 오늘치 보관 패치
        self.write(self.srv, "scripts/run_daily.sh", "CUTOFF=\"08:00\"\necho hi\n")  # 마감 08:00
        self.v1 = sh(self.srv, "git", "rev-parse", "HEAD")
        self.no_running = mock.patch.object(ap, "collector_running", return_value=False)
        self.no_running.start()

    def tearDown(self):
        self.no_running.stop()
        self.env.stop()

    def write(self, repo, rel, text):
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.srv, rel), encoding="utf-8") as f:
            return f.read()

    def commit(self, repo, msg):
        sh(repo, "git", "add", "-A")
        sh(repo, "git", "commit", "-q", "-m", msg)
        sh(repo, "git", "push", "-q", "origin", BR)

    def push_new_version(self, cafe=NEW_CAFE, main=NEW_MAIN):
        self.write(self.dev, "app/naver_cafe.py", cafe)
        self.write(self.dev, "app/main.py", main)
        self.commit(self.dev, "v2")
        return sh(self.dev, "git", "rev-parse", "HEAD")

    def head(self):
        return sh(self.srv, "git", "rev-parse", "HEAD")

    def run_pull(self, **kw):
        kw.setdefault("force_now", True)
        return ap.run(self.srv, **kw)

    # ── 실제로 일어날 상황: 서버에 패치 3개가 있는 채로 새 코드 받기 ─────────
    def test_pulls_and_keeps_server_patches(self):
        v2 = self.push_new_version()
        self.assertEqual(self.run_pull(), 0)
        self.assertEqual(self.head(), v2)                               # 새 코드 받음
        self.assertIn('"--force"', self.read("app/main.py"))
        self.assertEqual(self.read("app/naver_cafe.py"), NEW_CAFE)      # 예전 패치 대신 새 코드
        self.assertIn("keep today", self.read("app/drive_uploader.py"))  # 오늘치 보관 패치 보존
        self.assertIn("08:00", self.read("scripts/run_daily.sh"))        # 마감 08:00 보존
        baks = [f for f in os.listdir(os.path.join(self.srv, "app")) if ".bak-autopull-" in f]
        self.assertEqual(len(baks), 1)                                  # 지운 패치는 백업

    def test_already_latest_does_nothing(self):
        self.assertEqual(self.run_pull(), 0)
        self.assertEqual(self.head(), self.v1)
        self.assertEqual(self.read("app/naver_cafe.py"), self.patched_cafe)

    def test_other_overlapping_edit_is_refused(self):
        self.write(self.srv, "app/main.py", "print('서버에서 손으로 고침')\n")
        self.push_new_version()
        self.assertEqual(self.run_pull(), 1)
        self.assertEqual(self.head(), self.v1)                          # 안 받음
        self.assertIn("손으로 고침", self.read("app/main.py"))           # 손댄 것 그대로
        self.assertEqual(self.read("app/naver_cafe.py"), self.patched_cafe)  # 제목 패치도 그대로

    def test_title_patch_plus_other_edit_is_refused(self):
        self.write(self.srv, "app/naver_cafe.py", self.patched_cafe.replace("import re", "import re  # 서버에서 손질"))
        self.push_new_version()
        self.assertEqual(self.run_pull(), 1)                            # 다른 손질까지 지우면 안 됨
        self.assertIn("서버에서 손질", self.read("app/naver_cafe.py"))
        self.assertEqual(self.head(), self.v1)

    def test_broken_new_code_rolls_back(self):
        self.push_new_version(main="def broken(:\n")
        self.assertEqual(self.run_pull(), 1)
        self.assertEqual(self.head(), self.v1)                          # 예전으로 되돌림
        self.assertEqual(self.read("app/naver_cafe.py"), self.patched_cafe)  # 지웠던 패치 복구
        self.assertIn("keep today", self.read("app/drive_uploader.py"))

    def test_skips_while_collector_runs(self):
        self.push_new_version()
        with mock.patch.object(ap, "collector_running", return_value=True):
            self.assertEqual(self.run_pull(), 0)
        self.assertEqual(self.head(), self.v1)

    def test_throttle_checks_github_every_5_minutes(self):
        self.assertEqual(self.run_pull(force_now=False), 0)             # 첫 확인(기록 남김)
        v2 = self.push_new_version()
        self.assertEqual(self.run_pull(force_now=False), 0)
        self.assertEqual(self.head(), self.v1)                          # 5분 안 → 확인 안 함
        self.assertEqual(self.run_pull(force_now=False, every=0), 0)
        self.assertEqual(self.head(), v2)

    def test_diverged_or_ahead_is_refused(self):
        sh(self.srv, "git", "commit", "-q", "-am", "서버에서 커밋")
        local = self.head()
        self.assertEqual(self.run_pull(), 1)                            # 서버가 앞섬
        self.push_new_version()
        self.assertEqual(self.run_pull(), 1)                            # 갈라짐
        self.assertEqual(self.head(), local)

    def test_wrong_origin_or_not_git(self):
        sh(self.srv, "git", "remote", "set-url", "origin", "https://github.com/someone/else")
        self.assertEqual(self.run_pull(), 1)
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        self.assertEqual(ap.run(plain, force_now=True), 1)              # git 폴더 아님 → 이유 남김
        self.assertIn("git 폴더가 아니", ap.RESULT["msg"])

    def test_unknown_server_branch_uses_default(self):
        sh(self.srv, "git", "checkout", "-q", "-b", "main")             # GitHub 에 없는 이름
        v2 = self.push_new_version()
        self.assertEqual(self.run_pull(), 0)
        self.assertEqual(self.head(), v2)

    def test_server_on_other_branch_explains_why(self):
        # 서버가 다른 실험 브랜치(예: PressReader 시험)에 있고 거기에만 커밋이 있으면 → 이유를 남김
        sh(self.srv, "git", "checkout", "-q", "-b", "experiment")
        self.write(self.srv, "probe.py", "x = 1\n")
        sh(self.srv, "git", "add", "probe.py")
        sh(self.srv, "git", "commit", "-q", "-m", "probe")
        sh(self.srv, "git", "push", "-q", "origin", "experiment")
        self.push_new_version()
        status = os.path.join(self.tmp, "status.json")
        with mock.patch.dict(os.environ, {"NEWSPAPER_DIR": self.srv, "NEWSPAPER_PULL_STATUS": status}):
            self.assertEqual(ap.main(["--now"]), 1)
        import json
        saved = json.load(open(status, encoding="utf-8"))
        self.assertIn("experiment", saved["msg"])
        self.assertIn("갈라져", saved["msg"])

    def test_experiment_branch_merged_into_default_then_quiet(self):
        # 2026-11-13 실제 상황: 서버가 실험 브랜치(adoring-ride)에 있음 → 기본 브랜치에 그 실험을 합쳐 올림
        sh(self.srv, "git", "checkout", "-q", "-b", "experiment")
        self.write(self.srv, "probe.py", "x = 1\n")
        sh(self.srv, "git", "add", "probe.py")
        sh(self.srv, "git", "commit", "-q", "-m", "probe")
        sh(self.srv, "git", "push", "-q", "origin", "experiment")
        self.push_new_version()
        sh(self.dev, "git", "fetch", "-q", "origin", "experiment")
        sh(self.dev, "git", "merge", "-q", "--no-ff", "-m", "merge probe", "FETCH_HEAD")
        sh(self.dev, "git", "push", "-q", "origin", BR)
        merged = sh(self.dev, "git", "rev-parse", "HEAD")
        self.assertEqual(self.run_pull(), 0)
        self.assertEqual(self.head(), merged)                           # 기본 브랜치로 앞으로 감기
        self.assertIn('"--force"', self.read("app/main.py"))
        self.assertIn("keep today", self.read("app/drive_uploader.py"))
        self.assertTrue(os.path.exists(os.path.join(self.srv, "probe.py")))
        # 다음 확인: 서버 브랜치 이름은 그대로 experiment(옛 커밋)지만 경고 없이 '최신'
        self.assertEqual(self.run_pull(), 0)
        self.assertIn("최신", ap.RESULT["msg"])

    def test_default_branch_used_when_server_branch_has_nothing_new(self):
        sh(self.srv, "git", "checkout", "-q", "-b", "old-copy")          # 기본 브랜치의 옛 지점
        sh(self.srv, "git", "push", "-q", "origin", "old-copy")
        v2 = self.push_new_version()
        self.assertEqual(self.run_pull(), 0)
        self.assertEqual(self.head(), v2)

    def test_switch_off(self):
        self.push_new_version()
        with mock.patch.dict(os.environ, {"NEWSPAPER_AUTO_PULL": "off", "NEWSPAPER_DIR": self.srv}):
            self.assertEqual(ap.main(["--now"]), 0)
        self.assertEqual(self.head(), self.v1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
