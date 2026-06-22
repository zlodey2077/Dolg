/* 3D-поверхность скалярного поля (напряжение по сетке / бегущая волна по линии).
 *
 * Self-contained Three.js: 2D-массив поля [[v,...],...] → grid-mesh (z=рельеф, vertex-color
 * turbo-colormap) + ИНФОРМАТИВНОСТЬ: сетка-пол, осевой бокс, подписи осей (X/Z/Y), числовые
 * засечки по вертикали (мин/сер/макс в вольтах), OrbitControls. Без PBR (vertex colors).
 *
 * API (window.DolgSurface3D):
 *   init(canvas, field, opts) — построить; opts: {height, autoRotate, xLabel, zLabel, yLabel, unit}
 *   update(field)             — пересчитать z+цвета (морфинг по кадрам)
 *   getBounds()               — {lo, hi} диапазон значений (для легенды)
 *   tick()/start()/stop()/dispose()
 *   colormap(t)               — [r,g,b] для t∈[0,1]
 */
(function () {
  'use strict';

  function _three() {
    return window.THREE || null;
  }

  function colormap(t) {
    t = Math.max(0, Math.min(1, t));
    const r = Math.max(0, Math.min(1, 1.4 * t - 0.3));
    const g = Math.max(0, Math.min(1, 1 - Math.abs(t - 0.5) * 2));
    const b = Math.max(0, Math.min(1, 1.1 - 1.4 * t));
    return [r, g, b];
  }

  const BASE = 10; // сторона базы поверхности в мире (центрирована: [-5..5])

  function _fieldBounds(field) {
    let lo = Infinity;
    let hi = -Infinity;
    for (let i = 0; i < field.length; i++) {
      for (let j = 0; j < field[i].length; j++) {
        const v = field[i][j];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    if (!isFinite(lo) || !isFinite(hi) || hi <= lo) hi = lo + 1;
    return { lo, hi };
  }

  function _buildGeometry(THREE, field, height, lo, hi) {
    const rows = field.length;
    const cols = field[0] ? field[0].length : 0;
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(rows * cols * 3);
    const colors = new Float32Array(rows * cols * 3);
    const span = hi - lo || 1;
    const sx = cols > 1 ? BASE / (cols - 1) : 1;
    const sz = rows > 1 ? BASE / (rows - 1) : 1;
    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        const idx = (i * cols + j) * 3;
        const t = (field[i][j] - lo) / span;
        positions[idx] = j * sx - BASE / 2;
        positions[idx + 1] = t * height;
        positions[idx + 2] = i * sz - BASE / 2;
        const c = colormap(t);
        colors[idx] = c[0];
        colors[idx + 1] = c[1];
        colors[idx + 2] = c[2];
      }
    }
    const indices = [];
    for (let i = 0; i < rows - 1; i++) {
      for (let j = 0; j < cols - 1; j++) {
        const a = i * cols + j;
        const b = a + 1;
        const cc = a + cols;
        const d = cc + 1;
        indices.push(a, cc, b, b, cc, d);
      }
    }
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    return geo;
  }

  function _label(THREE, text, color, scale) {
    const FONT = 'bold 30px system-ui, sans-serif';
    const cvs = document.createElement('canvas');
    let ctx = cvs.getContext('2d');
    ctx.font = FONT;
    cvs.width = Math.max(48, Math.ceil(ctx.measureText(text).width) + 16); // авто-ширина под текст
    cvs.height = 48;
    ctx = cvs.getContext('2d');
    ctx.font = FONT;
    ctx.fillStyle = color || '#cfe';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, cvs.width / 2, 26);
    const sp = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cvs), transparent: true, depthTest: false })
    );
    const s = scale || 3;
    sp.scale.set(s, (s * cvs.height) / cvs.width, 1); // сохраняем пропорции текста
    return sp;
  }

  function _line(THREE, ax, ay, az, bx, by, bz, color, opacity) {
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(ax, ay, az),
      new THREE.Vector3(bx, by, bz),
    ]);
    return new THREE.Line(g, new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
  }

  function _fmt(v, unit) {
    const a = Math.abs(v);
    let s;
    if (a !== 0 && (a < 0.01 || a >= 10000)) s = v.toPrecision(2);
    else s = String(Math.round(v * 100) / 100);
    return unit ? s + ' ' + unit : s;
  }

  // Бокс-оси (стиль matplotlib 3D): тонкая сетка на 3 дальних стенах + числовые засечки и
  // имена на всех трёх осях (X = позиция, Z = время/позиция, Y = значение).
  function _addDecor(THREE, root, height, lo, hi, opts) {
    const half = BASE / 2;
    const NT = 5;
    const xr = opts.xRange || [0, 1];
    const zr = opts.zRange || [0, 1];
    const GC = 0x2b3a55;
    const GO = 0.55;
    const at = (i) => i / (NT - 1);
    const w = (t) => -half + t * BASE;

    // Пол: тонкая сетка по засечкам (читается с любого угла, не лезет вперёд при вращении).
    for (let i = 0; i < NT; i++) {
      const p = w(at(i));
      root.add(_line(THREE, p, 0, -half, p, 0, half, GC, GO));
      root.add(_line(THREE, -half, 0, p, half, 0, p, GC, GO));
    }
    // Рёбра бокса данных.
    const box = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(BASE, height, BASE)),
      new THREE.LineBasicMaterial({ color: 0x3a4a66, transparent: true, opacity: 0.45 })
    );
    box.position.y = height / 2;
    root.add(box);

    const place = (text, color, scale, x, y, z) => {
      const sp = _label(THREE, text, color, scale);
      sp.position.set(x, y, z);
      root.add(sp);
    };

    for (let i = 0; i < NT; i++) {
      const t = at(i);
      place(_fmt(xr[0] + (xr[1] - xr[0]) * t), '#8fd6ff', 1.8, w(t), -0.6, half + 0.5); // X-засечки (перёд)
      place(_fmt(zr[0] + (zr[1] - zr[0]) * t), '#a6f0c0', 1.8, -half - 0.7, -0.6, w(t)); // Z-засечки (слева)
      place(_fmt(lo + (hi - lo) * t, opts.unit), '#ffd27f', 2.0, half + 1.1, t * height, -half); // Y-засечки
    }

    place(opts.xLabel || 'X', '#8fd6ff', 4.0, 0, -1.4, half + 1.5);
    place(opts.zLabel || 'Z', '#a6f0c0', 4.0, -half - 1.7, -1.4, 0);
    place(opts.yLabel || 'Y', '#ffd27f', 3.8, half + 1.4, height + 1.0, -half);
  }

  const _state = { scene: null, camera: null, renderer: null, controls: null, mesh: null, raf: 0, height: 8, bounds: { lo: 0, hi: 1 } };

  function init(canvas, field, opts) {
    const THREE = _three();
    if (!THREE || !canvas || !field || !field.length) return { ok: false, reason: 'no-three-or-field' };
    opts = opts || {};
    _state.height = opts.height || 8;
    const w = canvas.clientWidth || 640;
    const h = canvas.clientHeight || 420;
    const { lo, hi } = _fieldBounds(field);
    _state.bounds = { lo, hi };

    _state.scene = new THREE.Scene();
    _state.scene.background = new THREE.Color(0x0d1017);
    _state.camera = new THREE.PerspectiveCamera(40, w / h, 0.1, 2000);
    _state.camera.position.set(-17, 10.5, 18); // сбоку к диагонали фронта: волна читается как гребень

    _state.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    _state.renderer.setSize(w, h, false);
    _state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    _state.scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const dir = new THREE.DirectionalLight(0xffffff, 0.78);
    dir.position.set(10, 18, 8);
    _state.scene.add(dir);
    const fill = new THREE.DirectionalLight(0x9fc0ff, 0.35); // мягкий заполняющий свет с другой стороны
    fill.position.set(-12, 6, -8);
    _state.scene.add(fill);

    if (THREE.OrbitControls) {
      _state.controls = new THREE.OrbitControls(_state.camera, canvas);
      _state.controls.enableDamping = true;
      _state.controls.target.set(0, _state.height * 0.35, 0);
      _state.controls.autoRotate = !!opts.autoRotate;
      _state.controls.autoRotateSpeed = 0.7;
      _state.controls.update();
    } else {
      _state.camera.lookAt(0, _state.height * 0.35, 0);
    }

    const geo = _buildGeometry(THREE, field, _state.height, lo, hi);
    _state.mesh = new THREE.Mesh(
      geo,
      new THREE.MeshPhongMaterial({ vertexColors: true, side: THREE.DoubleSide, shininess: 16 })
    );
    _state.scene.add(_state.mesh);
    _state.mesh.add(
      new THREE.LineSegments(
        new THREE.WireframeGeometry(geo),
        new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.05 })
      )
    );
    _addDecor(THREE, _state.scene, _state.height, lo, hi, opts);

    tick();
    return { ok: true, rows: field.length, cols: field[0].length, vmin: lo, vmax: hi };
  }

  function update(field) {
    const THREE = _three();
    if (!THREE || !_state.mesh || !field || !field.length) return false;
    const { lo, hi } = _fieldBounds(field);
    _state.bounds = { lo, hi };
    const old = _state.mesh.geometry;
    const geo = _buildGeometry(THREE, field, _state.height, lo, hi);
    _state.mesh.geometry = geo;
    if (old) old.dispose();
    if (_state.mesh.children[0]) {
      const wireOld = _state.mesh.children[0].geometry;
      _state.mesh.children[0].geometry = new THREE.WireframeGeometry(geo);
      if (wireOld) wireOld.dispose();
    }
    return true;
  }

  function getBounds() {
    return _state.bounds;
  }

  function tick() {
    if (!_state.renderer || !_state.scene || !_state.camera) return;
    if (_state.controls) _state.controls.update();
    _state.renderer.render(_state.scene, _state.camera);
  }

  function _loop() {
    tick();
    _state.raf = window.requestAnimationFrame(_loop);
  }

  function start() {
    if (!_state.raf) _loop();
  }

  function stop() {
    if (_state.raf) {
      window.cancelAnimationFrame(_state.raf);
      _state.raf = 0;
    }
  }

  function dispose() {
    stop();
    if (_state.renderer) _state.renderer.dispose();
    _state.scene = _state.camera = _state.renderer = _state.controls = _state.mesh = null;
  }

  window.DolgSurface3D = { init, update, getBounds, tick, start, stop, dispose, colormap };
})();
