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
    {'title': '실제 기사 제목', 'kind': 'news', 'what': '[확정] 매출 30% 증가',
     'why': '[기자 해석] 수출 증가', 'how': ['[조사 데이터] 수출 20조원', '[계획] 국내 매출 10조원'], 'bbox': [.1, .2, .5, .4]}]}


class SummaryTests(unittest.TestCase):
    def setUp(self):
        fallback = mock.patch.object(summary, 'published_messages', return_value=[])
        fallback.start()
        self.addCleanup(fallback.stop)
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
        self.assertIn('• WHAT: [확정] 매출 30% 증가', msgs[0]['text'])
        self.assertIn('• HOW:\n- [조사 데이터] 수출 20조원\n- [계획] 국내 매출 10조원', msgs[0]['text'])
        self.assertIn('• 사진: 02', msgs[1]['text'])
        self.assertIn('"bbox": [0.1, 0.2, 0.5, 0.4]', msgs[1]['text'])

    def test_unreadable_page_retries_once_and_keeps_progress(self):
        notes = []
        with mock.patch.object(summary, 'ask_page', side_effect=[{'complete': False}, copy.deepcopy(ANSWER), copy.deepcopy(ANSWER)]) as ask:
            summary.run(DATE, notes.append)
        self.assertEqual(ask.call_count, 3)
        self.assertTrue(ask.call_args_list[1].kwargs['detail_retry'])
        self.assertTrue(any('확대' in note for note in notes))
        self.assertEqual(len(summary.messages(DATE)), 2)

    def test_decorative_page_is_not_a_reading_failure(self):
        with mock.patch.object(summary, 'ask_page', side_effect=[copy.deepcopy(ANSWER), {'complete': True, 'articles': [], 'empty_reason': '기사 없음'}]):
            summary.run(DATE)
        self.assertEqual(len(summary.messages(DATE)), 1)

    def test_missing_or_unknown_classification_is_not_published(self):
        for text in ['계획을 확정으로 추측하지 않음', '[사실일듯] 내용', '[확정] ']:
            with self.assertRaises(RuntimeError):
                summary.classified(text)
        for label in summary.LABELS:
            self.assertEqual(summary.classified('[' + label + '] 내용'), '[' + label + '] 내용')

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

    def test_incomplete_download_is_not_treated_as_a_complete_newspaper(self):
        ix = json.loads((self.day / 'index.json').read_text())
        ix['expected_count'] = 30
        (self.day / 'index.json').write_text(json.dumps(ix))
        with mock.patch.object(summary, 'ask_page') as ask:
            with self.assertRaisesRegex(RuntimeError, '일부가 아직'):
                summary.run(DATE)
            ask.assert_not_called()
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


class PublishedTests(unittest.TestCase):
    def test_reviewed_edition_is_complete_dated_and_stable(self):
        import news_published
        self.assertEqual(len(news_published.ARTICLES), 34)
        a = news_published.messages(DATE)
        self.assertEqual(a, news_published.messages(DATE))
        self.assertEqual(len(a), 29)
        self.assertEqual(news_published.messages('2026-11-10'), [])
        self.assertIn('[계획]', ''.join(m['text'] for m in a))
        for m in a:
            metadata = json.loads(m['text'].split('```json\n')[1].split('```')[0])
            self.assertTrue(all(1 <= x['page'] <= 29 for x in metadata['articles']))

    def test_cache_overrides_published_fallback(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, NEWS_CACHE_DIR=d):
            self.assertEqual(len(summary.messages(DATE)), 29)
            summary.atomic_json(summary.result_path(DATE), {'complete': True, 'date': DATE, 'messages': [{'text': 'new approved result'}]})
            self.assertEqual(summary.messages(DATE), [{'text': 'new approved result'}])


if __name__ == '__main__':
    unittest.main(verbosity=2)
