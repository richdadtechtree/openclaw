"""Source-backed summary checkpoints and publication; never calls the gateway."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'stock'))
import news_summary as summary

DATE = '2026-11-09'
ANSWER = {'complete': True, 'printed_date': DATE, 'articles': [
    {'title': '실제 기사 제목', 'kind': 'news', 'what': '매출 30% 증가',
     'why': '수출 증가', 'how': ['수출 20조원', '국내 매출 10조원'], 'bbox': [.1, .2, .5, .4]}]}


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, NEWS_CACHE_DIR=self.tmp.name, OPENCLAW_ENV='/nonexistent', GATEWAY_TOKEN='test-token')
        p.start()
        self.addCleanup(p.stop)
        self.day = Path(self.tmp.name) / DATE
        self.day.mkdir()
        for i in (1, 2):
            Image.new('RGB', (1200, 1800), (240, 240, i)).save(self.day / ('%02d.jpg' % i))
        (self.day / 'index.json').write_text(json.dumps({'images': [{'name': '%02d.jpg' % i} for i in (1, 2)]}))

    def test_complete_summary_is_visible_with_article_page_links(self):
        notes = []
        with mock.patch.object(summary, 'ask_page', return_value=copy.deepcopy(ANSWER)) as ask:
            result = summary.run(DATE, notes.append)
        self.assertEqual(ask.call_count, 2)
        self.assertIn('2쪽 · 2개', result)
        self.assertEqual(len(notes), 2)
        msgs = summary.messages(DATE)
        self.assertEqual(len(msgs), 2)
        self.assertIn('• WHAT: 매출 30% 증가', msgs[0]['text'])
        self.assertIn('• HOW: 수출 20조원 / 국내 매출 10조원', msgs[0]['text'])
        self.assertIn('• 사진: 02', msgs[1]['text'])
        self.assertIn('"bbox": [0.1, 0.2, 0.5, 0.4]', msgs[1]['text'])

    def test_partial_failure_preserves_previous_complete_summary_and_resumes(self):
        previous = {'date': DATE, 'complete': True, 'messages': [{'text': 'previous'}]}
        summary.atomic_json(summary.result_path(DATE), previous)
        with mock.patch.object(summary, 'ask_page', side_effect=[copy.deepcopy(ANSWER), RuntimeError('connection down')]):
            with self.assertRaises(RuntimeError):
                summary.run(DATE)
        self.assertEqual(summary.messages(DATE), previous['messages'])
        with mock.patch.object(summary, 'ask_page', return_value=copy.deepcopy(ANSWER)) as ask:
            summary.run(DATE)
        self.assertEqual(ask.call_count, 1, 'completed first page must not be re-requested')
        self.assertEqual(len(summary.messages(DATE)), 2)

    def test_changed_original_invalidates_only_its_checkpoint(self):
        with mock.patch.object(summary, 'ask_page', return_value=copy.deepcopy(ANSWER)):
            summary.run(DATE)
        Image.new('RGB', (1200, 1800), 'red').save(self.day / '01.jpg')
        with mock.patch.object(summary, 'ask_page', return_value=copy.deepcopy(ANSWER)) as ask:
            summary.run(DATE)
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(ask.call_args.args[2], 1)

    def test_unreadable_wrong_date_and_empty_pages_never_publish(self):
        for bad in [dict(ANSWER, complete=False), dict(ANSWER, printed_date='2026-11-08'),
                    dict(ANSWER, articles=[]), dict(ANSWER, articles=[{'title': 'missing details'}])]:
            with self.subTest(bad=bad):
                with mock.patch.object(summary, 'ask_page', return_value=bad):
                    with self.assertRaises(RuntimeError):
                        summary.run(DATE)
                self.assertEqual(summary.messages(DATE), [])

    def test_advertisement_only_page_can_be_skipped_explicitly(self):
        with mock.patch.object(summary, 'ask_page', side_effect=[copy.deepcopy(ANSWER), {'complete': True, 'articles': [], 'empty_reason': '광고 전용'}]):
            summary.run(DATE)
        self.assertEqual(len(summary.messages(DATE)), 1)

    def test_unconfigured_gateway_is_an_error_not_success(self):
        with mock.patch.dict(os.environ, GATEWAY_TOKEN=''), mock.patch.object(summary, 'ask_page') as ask:
            with self.assertRaisesRegex(RuntimeError, 'GATEWAY_TOKEN'):
                summary.run(DATE)
            ask.assert_not_called()
        self.assertEqual(summary.messages(DATE), [])

    def test_missing_source_page_does_not_publish_partial_result(self):
        (self.day / '02.jpg').unlink()
        with mock.patch.object(summary, 'ask_page', return_value=copy.deepcopy(ANSWER)):
            with self.assertRaises(RuntimeError):
                summary.run(DATE)
        self.assertEqual(summary.messages(DATE), [])

    def test_vision_request_contains_the_actual_image_and_rejects_truncation(self):
        class R:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self, *args): return json.dumps({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}).encode()
        with mock.patch.object(summary.urllib.request, 'urlopen', return_value=R()) as call:
            with self.assertRaisesRegex(RuntimeError, '완성되지'):
                summary.ask_page(b'actual-image', DATE, 3)
        payload = json.loads(call.call_args.args[0].data)
        content = payload['messages'][1]['content']
        self.assertIn('3쪽', content[0]['text'])
        self.assertTrue(content[1]['image_url']['url'].endswith('YWN0dWFsLWltYWdl'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
