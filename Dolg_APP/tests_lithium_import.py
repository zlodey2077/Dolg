"""Тесты парсера Lithium ECAD (.lpr/.lsc/.lbo)."""

from __future__ import annotations

import pytest

from Dolg_APP.services.lithium_import import (
    LithiumImportError,
    detect_lithium_file,
    parse_lbo,
    parse_lithium_project,
    parse_lpr,
    parse_lsc,
)

LSC_MIN = """<?xml version="1.0" encoding="utf-8"?>
<lithium_ecad version="2.0.0"/>
<schematic format="2">
<erc>
<rule param="BB" value="1"/>
<rule param="OO" value="2"/>
<rule param="II" value="0"/>
</erc>
<cache>
<cmp name="R-EU_" pkg="R0603"/>
<cmp name="C-EU" pkg="C0603"/>
</cache>
<pages offset="100">
<page name="Стр.1" w="297" h="210">
<parts>
<part cid="8" x="10" y="20"/>
<part cid="9" x="30" y="40" rot="90"/>
</parts>
<ports>
<port sym="g1" x="50" y="60" name="GND"/>
<port sym="p1" x="70" y="80" name="VDD"/>
</ports>
<fragments>
<fragment net="GND">
<rpin id="8" name="2"/>
<rpin id="9" name="1"/>
</fragment>
<fragment net="VDD">
<rpin id="8" name="1"/>
</fragment>
</fragments>
</page>
</pages>
</schematic>
"""

LPR_MIN = """<?xml version="1.0" encoding="utf-8"?>
<lithium_ecad version="2.0.0"/>
<project format="5">
<content>
<packages>
<package name="R0603">Resistor 0603</package>
<package name="C0603">Capacitor 0603</package>
</packages>
<components>
<component name="R-EU_" refdes="R" value="R-EU_">
<part name="R-EU"/>
<package name="R0603"/>
</component>
</components>
</content>
<layers>
<layer id="68" name="Top"/>
<layer id="75" name="Bottom"/>
</layers>
<classes>
<class name="Default" width_default="0.2" width_min="0.15" clearance_min="0.15" drill_min="0.3"/>
<class name="Power" width_default="0.5" width_min="0.3" clearance_min="0.2" drill_min="0.4"/>
</classes>
</project>
"""

LBO_MIN = """<?xml version="1.0" encoding="utf-8"?>
<lithium_ecad version="2.0.0"/>
<pcb format="1">
<layers>
<layer id="68" name="Top"/>
<layer id="75" name="Bottom"/>
</layers>
<fragments>
<fragment net="GND">
<wire x1="0" y1="0" x2="10" y2="10"/>
<wire x1="10" y1="10" x2="20" y2="10"/>
</fragment>
</fragments>
<via x="5" y="5" drill="0.3"/>
<pad x="0" y="0"/>
</pcb>
"""


class TestParseLsc:
    def test_extracts_erc_rules(self):
        result = parse_lsc(LSC_MIN)
        assert result['erc_rules']['BB'] == 1
        assert result['erc_rules']['OO'] == 2
        assert result['erc_rules']['II'] == 0

    def test_extracts_cache(self):
        result = parse_lsc(LSC_MIN)
        assert len(result['cache']) == 2
        assert result['cache'][0]['name'] == 'R-EU_'
        assert result['cache'][0]['pkg'] == 'R0603'

    def test_extracts_pages_and_parts(self):
        result = parse_lsc(LSC_MIN)
        assert len(result['pages']) == 1
        page = result['pages'][0]
        assert page['name'] == 'Стр.1'
        assert page['w'] == '297'
        assert len(page['parts']) == 2
        assert page['parts'][0]['cid'] == '8'
        assert page['parts'][1]['rot'] == '90'

    def test_extracts_ports(self):
        result = parse_lsc(LSC_MIN)
        assert len(result['ports']) == 2
        port_names = {p['name'] for p in result['ports']}
        assert port_names == {'GND', 'VDD'}

    def test_extracts_nets_with_rpins(self):
        result = parse_lsc(LSC_MIN)
        assert len(result['nets']) == 2
        gnd_net = next(n for n in result['nets'] if n['name'] == 'GND')
        assert gnd_net['rpins_count'] == 2
        assert gnd_net['rpins'][0]['id'] == '8'

    def test_reads_lithium_version(self):
        result = parse_lsc(LSC_MIN)
        assert result['version'] == '2.0.0'

    def test_rejects_invalid_xml(self):
        with pytest.raises(LithiumImportError, match='Невалидный XML'):
            parse_lsc('<not closed')

    def test_rejects_missing_schematic(self):
        text = '<?xml version="1.0"?>\n<lithium_ecad version="2.0.0"/>\n<other/>'
        with pytest.raises(LithiumImportError, match='не найден <schematic>'):
            parse_lsc(text)


class TestParseLpr:
    def test_extracts_packages_and_components(self):
        result = parse_lpr(LPR_MIN)
        assert len(result['packages']) == 2
        assert len(result['components']) == 1
        assert result['components'][0]['name'] == 'R-EU_'
        assert result['components'][0]['refdes'] == 'R'
        assert result['components'][0]['package'] == 'R0603'

    def test_extracts_layers(self):
        result = parse_lpr(LPR_MIN)
        assert len(result['layers']) == 2
        assert {layer['name'] for layer in result['layers']} == {'Top', 'Bottom'}

    def test_extracts_net_classes(self):
        result = parse_lpr(LPR_MIN)
        assert len(result['net_classes']) == 2
        power = next(c for c in result['net_classes'] if c['name'] == 'Power')
        assert power['width_default'] == '0.5'


class TestParseLbo:
    def test_extracts_pcb_layers_and_counts(self):
        result = parse_lbo(LBO_MIN)
        assert len(result['pcb_layers']) == 2
        assert result['pcb_traces_count'] == 2
        assert result['pcb_vias_count'] == 1
        assert result['pcb_pads_count'] == 1


class TestProjectAggregation:
    def test_combines_all_three_files(self):
        project = parse_lithium_project(
            lpr_text=LPR_MIN,
            lsc_text=LSC_MIN,
            lbo_text=LBO_MIN,
        )
        summary = project.to_dict()
        assert summary['version'] == '2.0.0'
        assert summary['components_count'] == 1
        assert summary['packages_count'] == 2
        assert summary['nets_count'] == 2
        assert summary['ports_count'] == 2
        assert summary['erc_rules_count'] == 3
        assert summary['pcb_traces_count'] == 2

    def test_works_with_only_lsc(self):
        project = parse_lithium_project(lsc_text=LSC_MIN)
        summary = project.to_dict()
        assert summary['nets_count'] == 2
        assert summary['components_count'] == 0

    def test_raises_when_no_files(self):
        with pytest.raises(LithiumImportError, match='Не передан'):
            parse_lithium_project()

    def test_collects_warnings_on_partial_failure(self):
        project = parse_lithium_project(
            lpr_text=LPR_MIN,
            lsc_text='not xml',
        )
        assert any('.lsc' in w for w in project.warnings)
        assert project.packages, 'lpr должен распарситься, несмотря на сломанный lsc'


class TestDetectLithiumFile:
    def test_detects_by_extension(self):
        assert detect_lithium_file('BluePill.lpr', '') == 'lpr'
        assert detect_lithium_file('Sheet.LSC', '') == 'lsc'
        assert detect_lithium_file('board.lbo', '') == 'lbo'

    def test_detects_by_content_when_extension_unknown(self):
        assert detect_lithium_file('noname', LSC_MIN) == 'lsc'
        assert detect_lithium_file('noname', LPR_MIN) == 'lpr'
        assert detect_lithium_file('noname', LBO_MIN) == 'lbo'

    def test_returns_empty_for_unrelated_text(self):
        assert detect_lithium_file('readme.txt', 'hello world') == ''
