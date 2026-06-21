"""Fast static-asset smoke tests for the CAD and simulation workspaces."""

from __future__ import annotations

import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

TEST_STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

STATIC_ATTRS = {'href', 'poster', 'src'}
SRCSET_ATTRS = {'imagesrcset', 'srcset'}

CRITICAL_SIMULATION_ASSETS = {
    'ai/dolg-embeddings.js',
    'ai/dolg-semantic.js',
    'ai/lib/transformers.min.js',
    'lib/GLTFExporter.js',
    'lib/OrbitControls.js',
    'lib/pixi.min.js',
    'lib/qrcode.min.js',
    'lib/three.min.js',
    'shop/workspace-preferences.css',
    'shop/workspace-preferences.js',
    'simulation/ml-toolbar.js',
    'simulation/ngspice-worker.js',
    'simulation/ngspice.js',
    'simulation/ngspice.wasm',
    'simulation/scheme-3d-components.js',
    'simulation/scheme-3d-materials.js',
    'simulation/scheme-3d.js',
    'simulation/scheme-bom.js',
    'simulation/scheme-export.js',
    'simulation/scheme-lab.js',
    'simulation/scheme-netlist.js',
    'simulation/scheme-normalizer.js',
    'simulation/server-engine-ui.js',
    'simulation/simulation-engine.js',
    'simulation/simulation-worker.js',
}


class StaticReferenceParser(HTMLParser):
    """Collect static references from HTML tags without running a browser."""

    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        for name, value in attrs:
            if not value:
                continue
            if name in STATIC_ATTRS:
                self.references.add(value)
            elif name in SRCSET_ATTRS:
                self.references.update(_split_srcset(value))


def _split_srcset(value: str) -> set[str]:
    refs = set()
    for candidate in value.split(','):
        url = candidate.strip().split(' ', 1)[0]
        if url:
            refs.add(url)
    return refs


def _static_asset_path(reference: str) -> str | None:
    path = unquote(urlsplit(reference).path)
    static_url = settings.STATIC_URL or '/static/'
    if not static_url.startswith('/'):
        static_url = f'/{static_url}'
    if not path.startswith(static_url):
        return None
    return path.removeprefix(static_url).lstrip('/')


def _html_static_assets(html: str) -> set[str]:
    parser = StaticReferenceParser()
    parser.feed(html)
    return {asset for ref in parser.references if (asset := _static_asset_path(ref))}


def _missing_static_assets(paths: set[str]) -> list[str]:
    return sorted(path for path in paths if finders.find(path) is None)


@override_settings(ALLOWED_HOSTS=['*'], SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class ToolAssetSmokeTests(TestCase):
    def assertStaticAssetsExist(self, paths: set[str]) -> None:
        missing = _missing_static_assets(paths)
        self.assertEqual(missing, [], f'Missing static assets: {missing}')

    def test_simulation_page_static_contract(self):
        response = self.client.get(reverse('hello:simulation'))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode(response.charset or 'utf-8')
        self.assertIn('server-engine-catalog-data', html)
        self.assertIn('simulation/scheme-normalizer.js', html)
        self.assertIn('simulation/scheme-3d.js', html)
        self.assertIn('simulation/ml-toolbar.js', html)
        self.assertIn('simulation/server-engine-ui.js', html)
        self.assertIn('shop/workspace-preferences.css', html)
        self.assertIn('shop/workspace-preferences.js', html)

        self.assertStaticAssetsExist(_html_static_assets(html) | CRITICAL_SIMULATION_ASSETS)

    def test_cad_page_static_contract(self):
        response = self.client.get(reverse('hello:cad'))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode(response.charset or 'utf-8')
        self.assertIn('id="app-container"', html)
        self.assertIn('cad-layout', html)
        self.assertIn('id="canvas"', html)
        self.assertIn('shop/workspace-preferences.css', html)
        self.assertIn('shop/workspace-preferences.js', html)

        self.assertStaticAssetsExist(_html_static_assets(html))

    def test_server_engine_catalog_api_contract(self):
        response = self.client.get('/api/sim/server-engines/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['router_profile']['primary_engine'], 'dolg-engine-router')
        self.assertEqual(data['router_profile']['primary_external_engine'], 'xyce')
        self.assertIn('engines', data)

    def test_server_engine_recommend_api_contract(self):
        scheme = {
            'components': [
                {'id': 'V1', 'type': 'battery', 'voltage': 5},
                {'id': 'R1', 'type': 'resistor', 'resistance': 1000},
                {'id': 'GND', 'type': 'ground'},
            ],
            'connections': [],
        }
        response = self.client.post(
            '/api/sim/server-engines/recommend/',
            data=json.dumps({'scheme_data': scheme, 'limit': 3}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['ok'])
        self.assertLessEqual(len(data['engines']), 3)

    def test_server_engine_ui_js_contract(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('node is not installed')

        asset_path = Path(settings.BASE_DIR) / 'shop' / 'static' / 'simulation' / 'server-engine-ui.js'
        runner = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({json.dumps(str(asset_path))}, 'utf8');
const context = {{ window: {{}}, module: {{ exports: {{}} }} }};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(source, context, {{ filename: 'server-engine-ui.js' }});
const ui = context.window.DolgServerEngineUI || context.module.exports;
function assert(condition, message) {{
  if (!condition) throw new Error(message);
}}
assert(typeof ui.renderResult === 'function', 'renderResult export is missing');
const html = ui.renderResult({{
  metrics: {{ gain: 12.345678, samples: [0.0000001, 2] }},
  node_voltages: {{ out: 5 }},
  currents_a: {{ R1: 0.002 }},
  warnings: ['check <probe>'],
}}, {{ engine_name: 'Xyce <core>', analysis_type: 'dc' }});
assert(html.includes('server-engine-result'), 'result wrapper is missing');
assert(html.includes('Xyce &lt;core&gt;'), 'engine name is not escaped');
assert(!html.includes('check <probe>'), 'warning leaked as raw HTML');
assert(html.includes('check &lt;probe&gt;'), 'warning is not escaped');
const counts = ui.countJobs([{{ status: 'queued' }}, {{ status: 'success' }}, {{}}]);
assert(counts.queued === 2 && counts.success === 1, 'job counts are wrong');
const card = ui.renderCard({{
  id: 'xyce',
  name: 'Xyce',
  status: 'primary-candidate',
  outputs: ['json'],
  tags: ['spice'],
}}, {{ primaryId: 'xyce', recommended: true }});
assert(card.includes('server-engine-card--primary'), 'primary card class is missing');
assert(card.includes('рекомендован'), 'recommended marker is missing');
"""
        result = subprocess.run(
            [node, '-e', runner],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_workspace_preferences_js_contract(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('node is not installed')

        asset_path = Path(settings.BASE_DIR) / 'shop' / 'static' / 'shop' / 'workspace-preferences.js'
        runner = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({json.dumps(str(asset_path))}, 'utf8');
const CustomEvent = function CustomEvent(type, init) {{
  this.type = type;
  this.detail = init && init.detail;
}};
const context = {{ window: {{ CustomEvent }}, module: {{ exports: {{}} }}, globalThis: {{}} }};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(source, context, {{ filename: 'workspace-preferences.js' }});
const prefsApi = context.module.exports;
function assert(condition, message) {{
  if (!condition) throw new Error(message);
}}
assert(typeof prefsApi.normalizePreferences === 'function', 'normalizePreferences export is missing');
const normalized = prefsApi.normalizePreferences({{
  interfaceDensity: 'compact',
  workspaceLayout: 'lab',
  renderMode: 'auto',
  simEngine: 'xyce',
  workspaceAnimations: 'off',
}}, {{ webglSupported: true, workspaceKind: 'simulation' }});
assert(normalized.density === 'compact', 'density was not normalized');
assert(normalized.layout === 'lab', 'layout was not normalized');
assert(normalized.effectiveRenderMode === 'webgl', 'auto render mode did not prefer WebGL');
assert(normalized.motionEnabled === false, 'animation-off profile did not disable motion');
assert(normalized.classes.includes('dolg-workspace-simulation'), 'workspace class is missing');
const contract = prefsApi.createInstrumentContract(normalized);
assert(contract.version === 1, 'instrument contract version is wrong');
assert(contract.instruments.oscilloscope.motion === 'static', 'oscilloscope did not inherit reduced motion');
const classes = new Set();
const body = {{
  dataset: {{
    interfaceDensity: 'spacious',
    workspaceLayout: 'review',
    renderMode: 'canvas2d',
    reduceMotion: 'on',
  }},
  classList: {{
    add: (name) => classes.add(name),
    remove: (name) => classes.delete(name),
  }},
}};
const doc = {{
  body,
  querySelector: (selector) => selector === '#canvas' ? {{}} : null,
  createElement: () => ({{ getContext: () => null }}),
  dispatchEvent: (event) => {{ doc.lastEvent = event; }},
}};
const booted = prefsApi.boot(doc);
assert(booted.workspaceKind === 'cad', 'boot did not detect CAD workspace');
assert(body.dataset.effectiveRenderMode === 'canvas2d', 'body render dataset was not written');
assert(body.dataset.motionEnabled === 'off', 'motion dataset was not written');
assert(classes.has('dolg-workspace-cad'), 'CAD body class is missing');
assert(context.window.DolgWorkspaceInstrumentContract.pages.cad.scope === '#canvas', 'CAD instrument scope is wrong');
assert(doc.lastEvent.type === 'dolg:workspace-preferences-ready', 'ready event was not dispatched');
"""
        result = subprocess.run(
            [node, '-e', runner],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
