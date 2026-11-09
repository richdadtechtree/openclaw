"""Manual newspaper jobs: real auth, isolated cache, no production calls."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TMP = tempfile.TemporaryDirectory(prefix='news_redo_')
os.environ.update(GATE_DIR=TMP.name, OPENCLAW_ENV='/nonexistent',
                  NEWS_CACHE_DIR=str(Path(TMP.name) / 'cache'),
                  GATE_BASE_URL='https://example.test', GATE_APPROVAL='auto',
                  GATE_GOOGLE_CLIENT_ID='test', GATE_GOOGLE_CLIENT_SECRET='test',
                  PRIVACY_OPERATOR='test', PRIVACY_CONTACT='test@example.test',
                  GATE_IP_ADMIN_PASSWORD='test-password-long-enough')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'stock'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import gate
import news_redo as redo


def wait_done(c):
    end = time.time() + 5
    while time.time() < end:
        s = c.get('/api/news/redo').json()['state']
        if not s['running']:
            return s
        time.sleep(.02)
    raise AssertionError('job did not finish')


class RedoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = FastAPI()
        gate.install(cls.app)
        redo.install(cls.app)
        cls.clients = {}
        for name, admin in [('admin', True), ('guest', False)]:
            u = gate.upsert_login('google', name)
            gate.record_consent(u['id'], ['privacy'], name)
            if admin:
                gate.set_admin(u['id'], True)
            c = TestClient(cls.app, base_url='https://example.test')
            c.cookies.set('gate_sess', gate._session_token(u['id']))
            cls.clients[name] = c

    def setUp(self):
        self.admin = self.clients['admin']
        redo._state.update(running=False, ok=None, step='', message='', date='', started=0., finished=0., steps={}, tail='')
        self.patches = [
            mock.patch.object(redo, 'run_collect', return_value=(True, '')),
            mock.patch.object(redo, 'run_sync', return_value=(True, '')),
            mock.patch.object(redo.news_files, 'load_index', return_value={'images': [{'name': '01.jpg'}]}),
            mock.patch.object(redo.news_summary, 'run', return_value='30쪽 · 90개 기사 요약을 완료했어요.')]
        self.collect, self.sync, self.index, self.summary = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def post(self, mode='all', client=None, **kw):
        return (client or self.admin).post('/api/news/redo', json=dict(mode=mode, **kw))

    def test_only_admin_can_see_or_start_jobs(self):
        for c in [self.clients['guest'], TestClient(self.app, base_url='https://example.test')]:
            self.assertIn(c.get('/api/news/redo').status_code, (401, 403))
            self.assertIn(self.post(client=c).status_code, (401, 403))
        self.collect.assert_not_called()
        self.summary.assert_not_called()

    def test_ip_admin(self):
        c = TestClient(self.app, base_url='https://127.0.0.1')
        c.cookies.set(gate.COOKIE_IPADM, gate._sign({'k': 'ipadm', 'v': gate._ipadm_ver()}, 3600))
        self.assertEqual(c.get('/api/news/redo').status_code, 200)

    def test_reject_csrf_bad_mode_non_object_and_past_date(self):
        self.assertEqual(self.admin.post('/api/news/redo', json={}, headers={'sec-fetch-site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.admin.post('/api/news/redo', content='x=1').status_code, 403)
        self.assertEqual(self.admin.post('/api/news/redo', json=[]).status_code, 400)
        self.assertEqual(self.post('unknown').status_code, 400)
        self.assertEqual(self.post(date='2020-01-01').status_code, 400)
        self.collect.assert_not_called()

    def test_download_only(self):
        self.assertTrue(self.post('download').json()['started'])
        s = wait_done(self.admin)
        self.assertTrue(s['ok'])
        self.assertEqual(s['steps']['summary']['status'], 'skip')
        self.collect.assert_called_once()
        self.sync.assert_called_once()
        self.summary.assert_not_called()

    def test_summary_only_uses_existing_pages(self):
        self.post('summary')
        s = wait_done(self.admin)
        self.assertTrue(s['ok'])
        self.assertIn('90개', s['message'])
        self.collect.assert_not_called()
        self.sync.assert_not_called()
        self.summary.assert_called_once()

    def test_summary_only_syncs_downloaded_files_if_cache_missing(self):
        self.index.return_value = None
        self.post('summary')
        self.assertTrue(wait_done(self.admin)['ok'])
        self.sync.assert_called_once()
        self.collect.assert_not_called()

    def test_all_executes_real_summary(self):
        self.post()
        s = wait_done(self.admin)
        self.assertTrue(s['ok'])
        self.assertEqual([s['steps'][k]['status'] for k in ('collect', 'sync', 'summary')], ['ok'] * 3)
        self.collect.assert_called_once()
        self.sync.assert_called_once()
        self.summary.assert_called_once()

    def test_unconfigured_or_failed_summary_is_failure(self):
        self.summary.side_effect = RuntimeError('요약 연결 설정이 없어요.')
        self.post()
        s = wait_done(self.admin)
        self.assertFalse(s['ok'])
        self.assertEqual(s['steps']['summary']['status'], 'fail')
        self.assertEqual(s['steps']['sync']['status'], 'ok')
        self.assertIn('설정', s['message'])

    def test_failed_download_stops_remaining_steps(self):
        self.collect.return_value = (False, '오늘 신문을 못 찾았어요.')
        self.post()
        s = wait_done(self.admin)
        self.assertFalse(s['ok'])
        self.sync.assert_not_called()
        self.summary.assert_not_called()

    def test_running_and_cooldown_prevent_duplicate_jobs(self):
        self.collect.side_effect = lambda: (time.sleep(.2) or (True, ''))
        self.assertTrue(self.post().json()['started'])
        self.assertFalse(self.post().json()['started'])
        self.assertTrue(wait_done(self.admin)['ok'])
        self.assertFalse(self.post().json()['started'])
        self.collect.assert_called_once()

    def test_exception_releases_lock_for_retry(self):
        self.summary.side_effect = ValueError('unexpected')
        self.post('summary')
        self.assertFalse(wait_done(self.admin)['ok'])
        redo._state['finished'] = 0
        self.summary.side_effect = None
        self.assertTrue(self.post('summary').json()['started'])
        self.assertTrue(wait_done(self.admin)['ok'])

    def test_requested_one_off_expires_and_is_not_repeated(self):
        fn = next(h for h in self.app.router.on_startup if h.__name__ == 'resume_status_and_recover_today')
        marker = Path(os.environ['NEWS_CACHE_DIR']) / '.recovery-2026-11-09.started'
        marker.unlink(missing_ok=True)
        with mock.patch.object(redo, 'today_kst', return_value='2026-11-10'), mock.patch.object(redo, 'start') as start:
            fn()
            start.assert_not_called()
        with mock.patch.object(redo, 'today_kst', return_value='2026-11-09'), mock.patch.object(redo.news_summary, 'configured', return_value=True), mock.patch.object(redo.news_summary, 'messages', return_value=[]), mock.patch.object(redo, 'start', return_value=True) as start:
            fn()
            fn()
            start.assert_called_once_with('2026-11-09', True, download=False)
        marker.unlink(missing_ok=True)

    # 오디오 파일 수동 만들기 (2026-11-09)
    def test_audio_only_runs_just_audio_step(self):
        with mock.patch.object(redo.news_summary, 'messages', return_value=[{'text': 'x'}]), \
             mock.patch.object(redo, 'run_audio', return_value=(True, '오디오 파일을 만들었어요.')) as audio:
            self.assertTrue(self.post('audio').json()['started'])
            s = wait_done(self.admin)
        self.assertTrue(s['ok'])
        self.assertEqual((s['job'], s['steps']['audio']['status']), ('audio', 'ok'))
        audio.assert_called_once()
        self.collect.assert_not_called(); self.sync.assert_not_called(); self.summary.assert_not_called()

    def test_audio_needs_summary_first(self):
        with mock.patch.object(redo.news_summary, 'messages', return_value=[]), \
             mock.patch.object(redo.os.path, 'isfile', return_value=False), \
             mock.patch.object(redo, 'run_audio') as audio:
            self.post('audio')
            s = wait_done(self.admin)
        self.assertFalse(s['ok']); audio.assert_not_called()
        self.assertEqual(s['steps']['audio']['status'], 'fail')

    def test_audio_failure_shows_reason_and_guest_denied(self):
        with mock.patch.object(redo.news_summary, 'messages', return_value=[{'text': 'x'}]), \
             mock.patch.object(redo, 'run_audio', return_value=(False, '오디오 만들기에 실패했어요')):
            self.post('audio')
            s = wait_done(self.admin)
        self.assertFalse(s['ok']); self.assertIn('실패', s['message'])
        self.assertIn(self.post('audio', client=self.clients['guest']).status_code, (401, 403))

    def test_audio_command_default_and_custom(self):
        cmd, _ = redo.audio_cmd('2026-11-09')
        self.assertTrue(cmd[1].endswith('notebook_audio.py'))
        self.assertEqual(cmd[2:], ['--date', '2026-11-09', '--force'])
        with mock.patch.dict(redo.os.environ, {'NEWS_AUDIO_CMD': 'echo hi {date}'}):
            self.assertEqual(redo.audio_cmd('2026-11-09')[0], ['echo', 'hi', '2026-11-09'])

    def test_summary_file_made_from_web_summary_only_when_missing(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(redo.os.environ, {'NEWSPAPER_CLAUDE_DIR': d}), \
             mock.patch.object(redo.news_summary, 'messages', return_value=[{'text': '기사 A'}, {'text': '기사 B'}]):
            p = redo.ensure_summary_file('2026-11-09')
            self.assertTrue(p.endswith('summaries/summary-2026-11-09.txt'))
            self.assertEqual(open(p, encoding='utf-8').read(), '기사 A\n\n기사 B\n')
            open(p, 'w', encoding='utf-8').write('기존')
            redo.ensure_summary_file('2026-11-09')
            self.assertEqual(open(p, encoding='utf-8').read(), '기존')      # 있으면 안 덮음

    def test_summary_file_none_without_web_summary(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(redo.os.environ, {'NEWSPAPER_CLAUDE_DIR': d}), \
             mock.patch.object(redo.news_summary, 'messages', return_value=[]):
            self.assertIsNone(redo.ensure_summary_file('2026-11-09'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
