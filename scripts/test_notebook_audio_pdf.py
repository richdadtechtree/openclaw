#!/usr/bin/env python3
"""notebook_audio.py(PDF 재료 버전)의 NotebookLM 과 상관없는 부분 점검. 실행: python3 -I scripts/test_notebook_audio_pdf.py"""
import importlib.util, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('nba', HERE / 'notebook_audio.py')
nba = importlib.util.module_from_spec(spec); spec.loader.exec_module(nba)


class T(unittest.TestCase):
    def test_source_key_knows_pdf_and_old_titles(self):
        self.assertEqual(nba.source_key('신문 PDF 2026-11-13'), '2026-11-13')
        self.assertEqual(nba.source_key('신문 요약 2026-11-13'), '2026-11-13')
        self.assertEqual(nba.source_key('온라인 요약 2026-11-13 09시'), 'online-2026-11-13-09')
        self.assertEqual(nba.source_key('내가 직접 넣은 자료'), '')           # 남의 소스는 안 건드림
        self.assertEqual(nba.source_day('신문 PDF 2026-11-12'), '2026-11-12')  # 하루만 두기 정리 대상

    def test_find_pdf(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'NEWS_CACHE_DIR': d}):
            day = Path(d, '2026-11-13'); day.mkdir()
            self.assertEqual(nba.find_pdf('2026-11-13'), '')
            real = Path(d, 'collector.pdf'); real.write_bytes(b'%PDF-1.4 hi')
            (day / '2026-11-13.pdf').symlink_to(real)                      # 수집기 폴더로 이어진 링크
            self.assertEqual(nba.find_pdf('2026-11-13'), str(real.resolve()))
            (day / 'index.json').write_text(json.dumps({'pdf': {'name': '../../etc/passwd'}}))
            self.assertEqual(nba.find_pdf('2026-11-13'), str(real.resolve()))  # 폴더 밖 이름은 무시

    def test_pdf_mode_fails_clearly_without_pdf_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'NEWS_CACHE_DIR': d}), \
             mock.patch.object(nba, 'OUT_DIR', d), mock.patch.object(nba, 'cleanup', return_value=True), \
             mock.patch.object(nba, 'nlm') as nlm, mock.patch.object(sys, 'argv', ['x', '--date', '2026-11-13']):
            self.assertEqual(nba.main(), 1)
            nlm.assert_not_called()                                         # NotebookLM 에 아무것도 안 올림

    def test_pdf_mode_uploads_pdf_with_pdf_title(self):
        calls = []
        def fake(*a, timeout=0):
            calls.append(a)
            if a[:2] == ('source', 'list'): return {'sources': [{'id': 'OLD', 'title': '신문 요약 2026-11-13'}]}
            if a[:2] == ('source', 'add'): return {'source_id': 'S1'}
            if a[:2] == ('generate', 'audio'): raise RuntimeError('stop')   # 여기서 멈춰 업로드까지만 확인
            return {}
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'NEWS_CACHE_DIR': d}), \
             mock.patch.object(nba, 'OUT_DIR', d), mock.patch.object(nba, 'cleanup', return_value=True), \
             mock.patch.object(nba, 'nlm', side_effect=fake), mock.patch.object(sys, 'argv', ['x', '--date', '2026-11-13']):
            day = Path(d, '2026-11-13'); day.mkdir(); (day / '2026-11-13.pdf').write_bytes(b'%PDF-1.4 hi')
            with self.assertRaises(RuntimeError): nba.main()
        add = next(c for c in calls if c[:2] == ('source', 'add'))
        self.assertIn('application/pdf', add); self.assertIn('신문 PDF 2026-11-13', add)
        self.assertTrue(add[2].endswith('2026-11-13.pdf'))
        gen = next(c for c in calls if c[:2] == ('generate', 'audio'))
        self.assertNotIn('OLD', gen)                                        # 예전 요약 소스는 섞지 않음

    def test_summary_mode_and_online_unchanged(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(nba, 'BASE', d), mock.patch.object(nba, 'OUT_DIR', d), \
             mock.patch.object(nba, 'cleanup', return_value=True), mock.patch.object(nba, 'nlm') as nlm:
            for argv in (['x', '--date', '2026-11-13', '--source', 'summary'], ['x', '--date', '2026-11-13', '--slot', '09']):
                with mock.patch.object(sys, 'argv', argv):
                    self.assertEqual(nba.main(), 1)                          # 요약 파일이 없으면 예전처럼 실패
            nlm.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
