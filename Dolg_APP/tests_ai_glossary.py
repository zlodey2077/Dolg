from django.test import TestCase

from Dolg_APP.services.ai_retrieval import (
    _glossary_items,
    _load_glossary,
    build_retrieval_context,
    retrieval_lines,
)


class GlossaryRetrievalTests(TestCase):
    def test_glossary_loads(self):
        entries = _load_glossary()
        self.assertGreaterEqual(len(entries), 10)
        ids = {e['id'] for e in entries}
        self.assertIn('resistor', ids)
        self.assertIn('ground', ids)

    def test_glossary_item_matches_term_token(self):
        items = _glossary_items(['резистор'])
        self.assertTrue(items)
        item = items[0]
        self.assertEqual(item['source'], 'glossary')
        self.assertEqual(item['title'], 'Резистор')
        self.assertIn('закону Ома', item['snippet'])
        # Базовый score высокий, чтобы определение шло первым в контексте.
        self.assertGreaterEqual(item['score'], 5)

    def test_glossary_does_not_match_unrelated_token(self):
        self.assertEqual(_glossary_items(['квазар', 'foobar']), [])

    def test_build_context_grounds_basic_question(self):
        ctx = build_retrieval_context('что такое резистор')
        self.assertIn('glossary', ctx['sources'])
        titles = [i['title'] for i in ctx['items'] if i['source'] == 'glossary']
        self.assertIn('Резистор', titles)

    def test_retrieval_lines_label_glossary(self):
        ctx = build_retrieval_context('что такое конденсатор')
        lines = retrieval_lines(ctx, limit=6)
        self.assertTrue(any(line.startswith('глоссарий:') for line in lines))
