(function () {
    'use strict';

    function readPayload() {
        var node = document.getElementById('review-3d-data');
        if (!node) return null;
        try {
            return JSON.parse(node.textContent || '{}');
        } catch (err) {
            return null;
        }
    }

    function canUseWebGL() {
        try {
            var canvas = document.createElement('canvas');
            return Boolean(
                window.WebGLRenderingContext &&
                (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
            );
        } catch (err) {
            return false;
        }
    }

    function renderFallback(container, payload, reason) {
        container.classList.add('review-3d-stage-fallback');
        var columns = (payload && payload.columns) || [];
        var rows = columns.slice(0, 10).map(function (item) {
            var color = item.color || '#7fdbff';
            return (
                '<div class="review-3d-fallback-row">' +
                '<span class="review-3d-dot" style="background:' + color + '"></span>' +
                '<strong>' + escapeHtml(item.label || item.key || '') + '</strong>' +
                '<span>' + escapeHtml(item.value_label || String(item.value || 0)) + '</span>' +
                '</div>'
            );
        }).join('');
        container.innerHTML =
            '<div class="review-3d-fallback">' +
            '<strong>3D-график недоступен</strong>' +
            '<span>' + escapeHtml(reason || 'Показана табличная карта анализа.') + '</span>' +
            rows +
            '</div>';
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function makeMaterial(color, opacity) {
        return new THREE.MeshStandardMaterial({
            color: color,
            metalness: 0.18,
            roughness: 0.42,
            transparent: opacity < 1,
            opacity: opacity
        });
    }

    function addColumn(group, item, x, z) {
        var height = Math.max(0.35, Number(item.height) || 0.5);
        var color = new THREE.Color(item.color || '#7fdbff');
        var geometry = new THREE.BoxGeometry(0.72, height, 0.72);
        var mesh = new THREE.Mesh(geometry, makeMaterial(color, 0.92));
        mesh.position.set(x, height / 2, z);
        group.add(mesh);

        var edge = new THREE.LineSegments(
            new THREE.EdgesGeometry(geometry),
            new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.22 })
        );
        edge.position.copy(mesh.position);
        group.add(edge);

        var cap = new THREE.Mesh(
            new THREE.CylinderGeometry(0.39, 0.39, 0.08, 24),
            makeMaterial(color, 0.98)
        );
        cap.position.set(x, height + 0.05, z);
        group.add(cap);
    }

    function addRiskPoint(group, item, index, total) {
        var angle = total <= 1 ? 0 : (index / total) * Math.PI * 2;
        var radius = 3.8;
        var x = Math.cos(angle) * radius;
        var z = 2.1 + Math.sin(angle) * 1.3;
        var size = Math.max(0.22, Math.min(0.75, Number(item.radius) || 0.32));
        var y = 0.35 + Math.min(2.6, Number(item.value) * 0.22);
        var sphere = new THREE.Mesh(
            new THREE.SphereGeometry(size, 24, 16),
            makeMaterial(new THREE.Color(item.color || '#ff8a3d'), 0.88)
        );
        sphere.position.set(x, y, z);
        group.add(sphere);

        var stem = new THREE.Mesh(
            new THREE.CylinderGeometry(0.025, 0.025, Math.max(0.1, y), 10),
            makeMaterial(new THREE.Color(item.color || '#ff8a3d'), 0.42)
        );
        stem.position.set(x, y / 2, z);
        group.add(stem);
    }

    function init(container, payload) {
        if (!container || !payload || !payload.enabled) return;
        if (container.dataset.review3dReady === '1') return;
        container.dataset.review3dReady = '1';

        if (!window.THREE) {
            renderFallback(container, payload, 'Локальная библиотека Three.js не загрузилась.');
            return;
        }
        if (!canUseWebGL()) {
            renderFallback(container, payload, 'Браузер не предоставил WebGL-контекст.');
            return;
        }

        var width = Math.max(320, container.clientWidth || 720);
        var height = Math.max(320, container.clientHeight || 420);
        var scene = new THREE.Scene();
        scene.background = new THREE.Color(0x081126);
        scene.fog = new THREE.Fog(0x081126, 12, 28);

        var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
        renderer.setSize(width, height);
        renderer.outputEncoding = THREE.sRGBEncoding;
        container.innerHTML = '';
        container.appendChild(renderer.domElement);

        var camera = new THREE.PerspectiveCamera(46, width / height, 0.1, 100);
        camera.position.set(7.8, 6.4, 10.2);
        camera.lookAt(0, 2.2, 0);

        scene.add(new THREE.AmbientLight(0xffffff, 0.56));
        var key = new THREE.DirectionalLight(0x9cefff, 1.2);
        key.position.set(5, 8, 7);
        scene.add(key);
        var fill = new THREE.PointLight(0x72ffad, 0.8, 18);
        fill.position.set(-5, 3, -4);
        scene.add(fill);

        var grid = new THREE.GridHelper(13, 13, 0x00d4ff, 0x24334f);
        grid.material.transparent = true;
        grid.material.opacity = 0.42;
        scene.add(grid);

        var group = new THREE.Group();
        scene.add(group);

        var columns = (payload.columns || []).slice(0, 14);
        var spacing = columns.length > 10 ? 0.94 : 1.12;
        var startX = -((columns.length - 1) * spacing) / 2;
        columns.forEach(function (item, index) {
            addColumn(group, item, startX + index * spacing, item.category === 'risk' ? 0.7 : -0.55);
        });

        var risks = (payload.risk_points || []).slice(0, 10);
        risks.forEach(function (item, index) {
            addRiskPoint(group, item, index, risks.length);
        });

        var base = new THREE.Mesh(
            new THREE.CylinderGeometry(5.2, 5.2, 0.06, 96),
            new THREE.MeshStandardMaterial({
                color: 0x10233f,
                metalness: 0.08,
                roughness: 0.7,
                transparent: true,
                opacity: 0.62
            })
        );
        base.position.y = -0.06;
        scene.add(base);

        var dragging = false;
        var lastX = 0;
        var lastY = 0;
        var targetRotX = -0.06;
        var targetRotY = -0.55;
        group.rotation.x = targetRotX;
        group.rotation.y = targetRotY;

        container.addEventListener('pointerdown', function (event) {
            dragging = true;
            lastX = event.clientX;
            lastY = event.clientY;
            container.setPointerCapture(event.pointerId);
        });
        container.addEventListener('pointermove', function (event) {
            if (!dragging) return;
            var dx = event.clientX - lastX;
            var dy = event.clientY - lastY;
            lastX = event.clientX;
            lastY = event.clientY;
            targetRotY += dx * 0.008;
            targetRotX = Math.max(-0.72, Math.min(0.45, targetRotX + dy * 0.006));
        });
        container.addEventListener('pointerup', function (event) {
            dragging = false;
            try { container.releasePointerCapture(event.pointerId); } catch (err) {}
        });
        container.addEventListener('pointercancel', function () {
            dragging = false;
        });

        function resize() {
            var nextWidth = Math.max(320, container.clientWidth || width);
            var nextHeight = Math.max(320, container.clientHeight || height);
            if (nextWidth === width && nextHeight === height) return;
            width = nextWidth;
            height = nextHeight;
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
            renderer.setSize(width, height);
        }

        var ro = window.ResizeObserver ? new ResizeObserver(resize) : null;
        if (ro) ro.observe(container);
        window.addEventListener('resize', resize);

        function frame() {
            if (!dragging) targetRotY += 0.0025;
            group.rotation.x += (targetRotX - group.rotation.x) * 0.08;
            group.rotation.y += (targetRotY - group.rotation.y) * 0.08;
            renderer.render(scene, camera);
            requestAnimationFrame(frame);
        }
        frame();
    }

    function boot() {
        var container = document.getElementById('review-3d-stage');
        var payload = readPayload();
        if (!container || !payload) return;
        init(container, payload);
    }

    window.DolgReview3D = { init: init };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
