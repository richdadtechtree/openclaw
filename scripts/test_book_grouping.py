"""Offline regression checks for book excerpt boundaries (no API or Slack calls)."""
import unittest
from unittest.mock import patch
import get_notion_book as book


def block(text, kind='bulleted_list_item', color=0):
    return {'text': text, 'type': kind, 'c': color, 'b': 0}


class ExcerptTests(unittest.TestCase):
    def test_page_sections_keep_complete_sentences_and_style_changes(self):
        lines = [block('126p. 내 삶의 가치를 다른 가족에게 강요해서는 안 된다.'),
                 block('가난하게 태어난 건 죄가 아니지만 가난하게 죽는 것은 나의 잘못이다.'),
                 block('부자가 되는 방법의 시작은 자신이 부자가 될 수 있다고 믿는 것이다.', color=1),
                 block('리스트'), block('128p. 금융 공황 발생에 따른 세 가지 인간상.'),
                 block('폭락장에는 거대한 부의 이동이 이뤄진다.', kind='paragraph')]
        groups = book.group_blocks(lines)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0][0], ' '.join(x['text'] for x in lines[:4])[6:])
        self.assertEqual(groups[0][2], '126p.')
        self.assertIn('폭락장에는', groups[1][0])

    def test_blank_blocks_and_internal_blank_lines(self):
        groups = book.group_blocks([block('첫 번째 문장이다.\n이어지는 문장이다.\n \n두 번째 구간이다.'),
                                    block(''), block('세 번째 구간이다.')])
        self.assertEqual([x[0] for x in groups],
                         ['첫 번째 문장이다. 이어지는 문장이다.', '두 번째 구간이다.', '세 번째 구간이다.'])

    def test_page_marker_variants(self):
        for marker in ['126p.', 'p.126', '126쪽', '126페이지']:
            with self.subTest(marker=marker):
                groups = book.group_blocks([block('앞 구간의 문장이다.'), block(marker),
                                            block('새 페이지의 문장이다.')])
                self.assertEqual(len(groups), 2)
                self.assertEqual(groups[1][2], marker)

    def test_long_section_is_not_fragmented_or_discarded_at_600(self):
        text = '이 문장은 같은 페이지에 적힌 원문이다. ' * 40
        groups = book.group_blocks([block('126p.'), block(text), block(text)])
        self.assertEqual(len(groups), 1)
        self.assertIsNotNone(book.score_sentence(book.clean_sentence(groups[0][0])))

    def test_old_cache_is_invalidated(self):
        with patch.object(book, '_load_json', return_value={'version': 5, 'pages': {'old': {}}}):
            self.assertEqual(book.load_cache()['pages'], {})

    def test_collection_keeps_trailing_blank_boundary(self):
        data = {'results': [{'type': 'paragraph', 'paragraph': {'rich_text': [
            {'plain_text': '첫 구간이다.\n\n'}]}}]}
        with patch.object(book, 'api_get', return_value=data):
            items = book.collect_blocks('unused', 'unused')
        groups = book.group_blocks(items + [block('다음 구간이다.')])
        self.assertEqual(len(groups), 2)


class ManualPickTests(unittest.TestCase):
    def test_manual_pick_uses_complete_live_body(self):
        page = {"id": "book"}
        full = "내 삶의 가치를 다른 가족에게 강요해서는 안 된다. 이어지는 원문이다."
        with patch.object(book, 'fetch_rows', return_value=[page]), \
             patch.object(book, 'filter_rows', return_value=[page]), \
             patch.object(book, 'page_blocks', return_value=[(full, 3, '126p.')]), \
             patch.object(book, 'load_state', return_value={}), \
             patch.object(book, 'emit', return_value=0) as emit:
            self.assertEqual(book.cmd_contains('unused', 'db', '돈의 속성', '내 삶의 가치'), 0)
            self.assertEqual(emit.call_args.args[0]['t'], full)

    def test_missing_or_ambiguous_match_never_emits(self):
        for count in (0, 2):
            with self.subTest(count=count), \
                 patch.object(book, 'fetch_rows', return_value=[]), \
                 patch.object(book, 'filter_rows', return_value=[{'id': 'book'}]), \
                 patch.object(book, 'page_blocks', return_value=[('내 삶의 가치를 지키는 문장이다.', 3, '')] * count), \
                 patch.object(book, 'emit') as emit, \
                 patch('sys.stderr'):
                with self.assertRaises(SystemExit) as error:
                    book.cmd_contains('unused', 'db', None, '내 삶의 가치')
                self.assertEqual(error.exception.code, 2)
                emit.assert_not_called()

    def test_sender_passes_phrase_to_picker(self):
        import book_slack
        from types import SimpleNamespace
        with patch.object(book_slack.subprocess, 'run', return_value=SimpleNamespace(
                stdout='원문 전체이다.\n<돈의 속성> 김승호', stderr='', returncode=0)) as run:
            book_slack.pick_quote('돈의 속성', '내 삶의 가치')
            self.assertEqual(run.call_args.args[0][-4:],
                             ['--book', '돈의 속성', '--contains', '내 삶의 가치'])


if __name__ == '__main__':
    unittest.main()
