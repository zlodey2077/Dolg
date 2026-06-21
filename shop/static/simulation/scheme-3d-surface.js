/* 3D-поверхность скалярного поля (например, напряжения по резисторной сетке).
 *
 * Самодостаточный Three.js-модуль: 2D-массив поля [[v,...],...] → grid-mesh, где z вершины =
 * нормированное значение (рельеф), а vertex-color — colormap (turbo). Вращение OrbitControls.
 * Без тяжёлых шейдеров (vertex colors), без PBR — урок прошлого отката.
 *
 * Данные: Dolg_APP/services/large_circuits.voltage_field (поле сетки N×N) или любой 2D-массив.
 *
 * API (window.DolgSurface3D):
 *   init(canvas, field, opts)  — построить сцену + поверхность; opts: {height, autoRotate}
 *   update(field)              — пересчитать z+цвета (для анимации по кадрам transient)
 *   tick()                     — один кадр RAF
 *   start()/stop()             — авто-RAF-цикл
 *   dispose()                  — освободить GPU
 *   colormap(t)                — [r,g,b] 0..1 для t∈[0,1] (turbo-аппрокс)
 *
 * Фолбэк: нет THREE → init возвращает {ok:false}.
 */
(function () {
  'use strict';

  function _three() {
    return window.THREE || null;
  }

  // turbo-подобная colormap: t∈[0,1] → [r,g,b]∈[0,1]. Синий(низ)→зелёный→жёлтый→красный(верх).
  function colormap(t) {
    t = Math.max(0, Math.min(1, t));
    const r = Math.max(0, Math.min(1, 1.4 * t - 0.3));
    const g = Math.max(0, Math.min(1, 1 - Math.abs(t - 0.5) * 2));
    const b = Math.max(0, Math.min(1, 1.1 - 1.4 * t));
    return [r, g, b];
  }

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
    if (!isFinite(lo) || !isFinite(hi) || hi <= lo) {
      hi = lo + 1;
    }
    return { lo, hi };
  }

  // Из поля строим BufferGeometry: сетка rows×cols, центрирована в XZ, y = высота.
  function _buildGeometry(THREE, field, height) {
    const rows = field.length;
    const cols = field[0] ? field[0].length : 0;
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(rows * cols * 3);
    const colors = new Float32Array(rows * cols * 3);
    const { lo, hi } = _fieldBounds(field);
    const span = hi - lo || 1;
    const sx = cols > 1 ? 10 / (cols - 1) : 1;
    const sz = rows > 1 ? 10 / (rows - 1) : 1;

    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        const idx = (i * cols + j) * 3;
        const t = (field[i][j] - lo) / span;
        positions[idx] = j * sx - 5;
        positions[idx + 1] = t * height;
        positions[idx + 2] = i * sz - 5;
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

  const _state = {
    scene: null,
    camera: null,
    renderer: null,
    controls: null,
    mesh: null,
    raf: 0,
    height: 6,
  };

  function init(canvas, field, opts) {
    const THREE = _three();
    if (!THREE || !canvas || !field || !field.length) {
      return { ok: false, reason: 'no-three-or-field' };
    }
    opts = opts || {};
    _state.height = opts.height || 6;
    const w = canvas.clientWidth || 640;
    const h = canvas.clientHeight || 420;

    _state.scene = new THREE.Scene();
    _state.scene.background = new THREE.Color(0x0d1017);
    _state.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
    _state.camera.position.set(11, 11, 13);
    _state.camera.lookAt(0, 0, 0);

    _state.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    _state.renderer.setSize(w, h, false);
    _state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    _state.scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const dir = new THREE.DirectionalLight(0xffffff, 0.7);
    dir.position.set(8, 14, 6);
    _state.scene.add(dir);

    if (THREE.OrbitControls) {
      _state.controls = new THREE.OrbitControls(_state.camera, canvas);
      _state.controls.enableDamping = true;
      _state.controls.autoRotate = !!opts.autoRotate;
      _state.controls.autoRotateSpeed = 0.8;
    }

    const geo = _buildGeometry(THREE, field, _state.height);
    const mat = new THREE.MeshPhongMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      shininess: 18,
      flatShading: false,
    });
    _state.mesh = new THREE.Mesh(geo, mat);
    _state.scene.add(_state.mesh);

    // лёгкий wireframe поверх для «сеточной» читаемости рельефа
    const wire = new THREE.LineSegments(
      new THREE.WireframeGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.06 })
    );
    _state.mesh.add(wire);

    tick();
    return { ok: true, rows: field.length, cols: field[0].length };
  }

  function update(field) {
    const THREE = _three();
    if (!THREE || !_state.mesh || !field || !field.length) return false;
    const old = _state.mesh.geometry;
    const geo = _buildGeometry(THREE, field, _state.height);
    _state.mesh.geometry = geo;
    if (old) old.dispose();
    // обновить wireframe-ребёнка
    if (_state.mesh.children[0]) {
      const wireOld = _state.mesh.children[0].geometry;
      _state.mesh.children[0].geometry = new THREE.WireframeGeometry(geo);
      if (wireOld) wireOld.dispose();
    }
    return true;
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
    if (_state.mesh) {
      if (_state.mesh.geometry) _state.mesh.geometry.dispose();
      if (_state.mesh.material) _state.mesh.material.dispose();
    }
    if (_state.renderer) _state.renderer.dispose();
    _state.scene = _state.camera = _state.renderer = _state.controls = _state.mesh = null;
  }

  window.DolgSurface3D = { init, update, tick, start, stop, dispose, colormap };
})();
