"""Собирает автономную HTML-демку 3D-поверхности поля (DolgSurface3D) для скриншота.

Генерит реальное поле напряжений (large_circuits → solve_dc → voltage_field), встраивает в
HTML вместе со скриптами three/OrbitControls/scheme-3d-surface (по file:// путям), пишет в TEMP.
Запуск: python scripts/make_surface_demo.py  → печатает путь к .html.
"""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')
django.setup()

from Dolg_APP.services import large_circuits as lc
from Dolg_APP.services import monte_carlo


def file_url(rel):
    return 'file:///' + os.path.join(ROOT, rel).replace('\\', '/')


def main():
    n = 25
    circuit = lc.generate_resistor_grid_circuit(n, v=10.0, r=100.0)
    field = lc.voltage_field(monte_carlo.solve_dc(circuit)['voltages'], n)

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;background:#0d1017;overflow:hidden}}
#c{{width:900px;height:600px;display:block}}
#t{{position:fixed;left:14px;top:10px;color:#9fb0c8;font:600 14px system-ui}}
</style></head><body>
<div id="t">3D-поверхность поля напряжений — сетка {n}×{n} ({circuit['n_nodes']} узлов, {len(circuit['elements'])} элементов)</div>
<canvas id="c" width="900" height="600"></canvas>
<script src="{file_url('shop/static/lib/three.min.js')}"></script>
<script src="{file_url('shop/static/lib/OrbitControls.js')}"></script>
<script src="{file_url('shop/static/simulation/scheme-3d-surface.js')}"></script>
<script>
const FIELD = {json.dumps(field)};
window.addEventListener('load', function () {{
  const r = window.DolgSurface3D.init(document.getElementById('c'), FIELD, {{ height: 6 }});
  document.title = 'surface:' + (r && r.ok ? 'ok' : 'fail');
  window.DolgSurface3D.tick();
}});
</script></body></html>"""

    out = os.path.join(tempfile.gettempdir(), 'dolg_surface_demo.html')
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(html)
    print(out)


if __name__ == '__main__':
    main()
