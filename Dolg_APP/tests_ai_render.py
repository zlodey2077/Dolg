"""Tests for L3 render-directives (hybrid: structured render array + inline tokens)."""

from __future__ import annotations

from django.test import SimpleTestCase

from Dolg_APP.services import ai_render, rule_ai


def _divider(v=9.0, r1=1000, r2=2000):
    return {
        'components': [
            {'id': 'B1', 'type': 'battery', 'voltage': v, 'ports': [{'id': '+'}, {'id': '-'}]},
            {'id': 'R1', 'type': 'resistor', 'resistance': r1, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'R2', 'type': 'resistor', 'resistance': r2, 'ports': [{'id': '1'}, {'id': '2'}]},
            {'id': 'G1', 'type': 'ground', 'ports': [{'id': '1'}]},
        ],
        'connections': [
            {'from': {'compId': 'B1', 'portId': '+'}, 'to': {'compId': 'R1', 'portId': '1'}},
            {'from': {'compId': 'R1', 'portId': '2'}, 'to': {'compId': 'R2', 'portId': '1'}},
            {'from': {'compId': 'R2', 'portId': '2'}, 'to': {'compId': 'B1', 'portId': '-'}},
            {'from': {'compId': 'B1', 'portId': '-'}, 'to': {'compId': 'G1', 'portId': '1'}},
        ],
    }


class InlineTokenTests(SimpleTestCase):
    def test_extracts_known_tokens(self):
        toks = ai_render.parse_inline_tokens('Напряжение [[value:узел 2]] и [[highlight:R1]]')
        types = {t['type'] for t in toks}
        self.assertEqual(types, {'value', 'highlight'})
        self.assertEqual(toks[1]['arg'], 'R1')

    def test_ignores_unknown_token_types(self):
        self.assertEqual(ai_render.parse_inline_tokens('мусор [[bogus:x]]'), [])

    def test_empty_text(self):
        self.assertEqual(ai_render.parse_inline_tokens(''), [])
        self.assertEqual(ai_render.parse_inline_tokens(None), [])


class DcPlotTests(SimpleTestCase):
    def test_divider_yields_svg(self):
        svg = ai_render.dc_voltage_plot(_divider())
        self.assertTrue(svg and '<svg' in svg, 'ожидался SVG-график')

    def test_empty_scheme_no_plot(self):
        self.assertIsNone(ai_render.dc_voltage_plot({'components': [], 'connections': []}))
        self.assertIsNone(ai_render.dc_voltage_plot(None))


class RenderItemsTests(SimpleTestCase):
    def test_measurement_intent_has_plot(self):
        items = ai_render.build_render_items(_divider(), 'measurement')
        self.assertTrue(any(i['type'] == 'plot' and i['format'] == 'svg' for i in items))

    def test_non_visual_intent_has_no_plot(self):
        self.assertEqual(ai_render.build_render_items(_divider(), 'recommend'), [])

    def test_empty_scheme_no_items(self):
        self.assertEqual(ai_render.build_render_items({'components': []}, 'measurement'), [])


class ReplyRenderFieldTests(SimpleTestCase):
    def test_reply_carries_render_list(self):
        result = rule_ai.build_rule_based_reply(
            'посчитай напряжения узлов', mode='explain', scheme=_divider()
        )
        self.assertIn('render', result)
        self.assertIsInstance(result['render'], list)

    def test_render_directives_helper_merges_layers(self):
        items = rule_ai._render_directives('measurement', 'смотри [[highlight:R1]]', _divider())
        kinds = {i['type'] for i in items}
        self.assertIn('plot', kinds)
        self.assertIn('highlight', kinds)
