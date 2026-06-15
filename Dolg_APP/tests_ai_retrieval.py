"""Tests for ai_retrieval ranking — TF-IDF-lite weighting (Фаза 2 усиления ассистента)."""

from __future__ import annotations

from django.test import SimpleTestCase

from Dolg_APP.services import ai_retrieval


class IdfWeightTests(SimpleTestCase):
    def test_rare_token_weighted_higher_than_common(self):
        df = {'common': 10, 'rare': 1}
        w_common = ai_retrieval._idf_weight('common', df, 10)
        w_rare = ai_retrieval._idf_weight('rare', df, 10)
        self.assertGreater(w_rare, w_common)


class RankItemsTests(SimpleTestCase):
    def _items(self):
        return [
            {'source': 'article', 'id': 1, 'title': 'резистор basics', 'snippet': 'резистор', 'keywords': ''},
            {'source': 'catalog', 'id': 2, 'title': 'lm358 opamp', 'snippet': 'резистор', 'keywords': ''},
            {'source': 'article', 'id': 3, 'title': 'резистор guide', 'snippet': 'резистор', 'keywords': ''},
        ]

    def test_rare_specific_token_outranks_common(self):
        # 'резистор' во всех трёх (частый, низкий IDF); 'lm358' только в одном (редкий, высокий IDF)
        ranked = ai_retrieval._rank_items(self._items(), ['резистор', 'lm358'])
        self.assertEqual(ranked[0]['id'], 2)

    def test_no_match_is_filtered(self):
        items = [{'source': 'catalog', 'id': 9, 'title': 'foo', 'snippet': 'bar', 'keywords': ''}]
        self.assertEqual(ai_retrieval._rank_items(items, ['xyzzy']), [])

    def test_base_score_preserved(self):
        # базовый score (напр. глоссарий=5) суммируется с match-score, не теряется
        items = [
            {'source': 'glossary', 'id': 'g1', 'title': 'foo', 'snippet': '', 'keywords': '', 'score': 5}
        ]
        ranked = ai_retrieval._rank_items(items, ['xyzzy'])
        self.assertEqual(ranked[0]['score'], 5)
