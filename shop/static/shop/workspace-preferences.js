(function (root, factory) {
    const api = factory(root || {});
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.DolgWorkspacePreferencesModule = api;
        if (root.document) {
            api.boot(root.document);
        }
    }
})(typeof window !== 'undefined' ? window : globalThis, function (root) {
    const DENSITIES = ['compact', 'comfortable', 'spacious'];
    const LAYOUTS = ['balanced', 'focus', 'lab', 'review'];
    const RENDER_MODES = ['auto', 'canvas2d', 'webgl'];
    const ENGINES = ['auto', 'browser_ngspice', 'pyspice', 'xyce', 'gnucap', 'openmodelica'];
    const WORKSPACE_CLASSES = [
        'dolg-workspace-page',
        'dolg-workspace-cad',
        'dolg-workspace-simulation',
        'dolg-density-compact',
        'dolg-density-comfortable',
        'dolg-density-spacious',
        'dolg-layout-balanced',
        'dolg-layout-focus',
        'dolg-layout-lab',
        'dolg-layout-review',
        'dolg-render-canvas2d',
        'dolg-render-webgl',
        'dolg-motion-on',
        'dolg-motion-off',
    ];

    function choice(value, allowed, fallback) {
        return allowed.includes(value) ? value : fallback;
    }

    function boolOn(value) {
        return value === true || value === 'on' || value === '1' || value === 'true';
    }

    function boolOff(value) {
        return value === false || value === 'off' || value === '0' || value === 'false';
    }

    function mediaPrefersReducedMotion() {
        if (!root.matchMedia) return false;
        try {
            return root.matchMedia('(prefers-reduced-motion: reduce)').matches;
        } catch (_error) {
            return false;
        }
    }

    function supportsWebgl(options) {
        if (typeof options?.webglSupported === 'boolean') {
            return options.webglSupported;
        }
        const doc = options?.document || root.document;
        if (!doc || !doc.createElement) return false;
        try {
            const canvas = doc.createElement('canvas');
            return !!(
                canvas &&
                canvas.getContext &&
                (canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
            );
        } catch (_error) {
            return false;
        }
    }

    function detectWorkspaceKind(doc) {
        if (!doc || !doc.querySelector) return 'unknown';
        if (doc.querySelector('#schematicCanvas') || doc.querySelector('.simulator-container')) {
            return 'simulation';
        }
        if (doc.querySelector('#app-container') || doc.querySelector('.cad-layout') || doc.querySelector('#canvas')) {
            return 'cad';
        }
        return 'unknown';
    }

    function normalizePreferences(dataset, options) {
        const data = dataset || {};
        const density = choice(data.interfaceDensity || data.interface_density, DENSITIES, 'comfortable');
        const layout = choice(data.workspaceLayout || data.workspace_layout, LAYOUTS, 'balanced');
        const rawRenderMode = choice(data.renderMode || data.render_mode, RENDER_MODES, 'auto');
        const webglAvailable = supportsWebgl(options || {});
        const effectiveRenderMode = rawRenderMode === 'auto'
            ? (webglAvailable ? 'webgl' : 'canvas2d')
            : (rawRenderMode === 'webgl' && !webglAvailable ? 'canvas2d' : rawRenderMode);
        const animations = boolOff(data.workspaceAnimations || data.workspace_animations) ? 'off' : 'on';
        const reducedMotion = boolOn(data.reduceMotion || data.reduce_motion) || mediaPrefersReducedMotion();
        const motionEnabled = animations === 'on' && !reducedMotion;
        const simEngine = choice(data.simEngine || data.sim_engine, ENGINES, 'auto');
        const aiBackend = data.aiBackend || data.ai_backend || 'auto';
        const workspaceKind = choice(
            options?.workspaceKind || data.workspaceKind || data.workspace_kind,
            ['cad', 'simulation', 'unknown'],
            'unknown',
        );

        return {
            ready: true,
            version: 1,
            density,
            layout,
            simEngine,
            aiBackend,
            renderMode: rawRenderMode,
            effectiveRenderMode,
            webglAvailable,
            animations,
            reducedMotion,
            motionEnabled,
            workspaceKind,
            classes: [
                'dolg-workspace-page',
                `dolg-workspace-${workspaceKind}`,
                `dolg-density-${density}`,
                `dolg-layout-${layout}`,
                `dolg-render-${effectiveRenderMode}`,
                motionEnabled ? 'dolg-motion-on' : 'dolg-motion-off',
            ].filter((name) => !name.endsWith('-unknown')),
        };
    }

    function createInstrumentContract(preferences) {
        const motion = preferences.motionEnabled ? 'animated' : 'static';
        return {
            version: 1,
            density: preferences.density,
            layout: preferences.layout,
            motionEnabled: preferences.motionEnabled,
            reducedMotion: preferences.reducedMotion,
            renderMode: preferences.effectiveRenderMode,
            simEngine: preferences.simEngine,
            pages: {
                simulation: {
                    scope: '#schematicCanvas, #schematicCanvasPixi',
                    dock: '#simDock',
                    lab: '#dolgLabBody',
                    probes: '#probes-panel',
                    results: '#results-panel, #analysisBottomPanel',
                },
                cad: {
                    scope: '#canvas',
                    toolbar: '.top-controls',
                    tools: '.tools-panel',
                    inspector: '.right-panel',
                    drc: '#cadDrcPanel',
                },
            },
            instruments: {
                oscilloscope: {
                    motion,
                    target: '#dolgLabBody',
                    channelSelector: '[data-lab-channel]',
                    animationClass: 'dolg-instrument-oscilloscope',
                },
                generator: {
                    motion,
                    target: '#dolgLabBody',
                    animationClass: 'dolg-instrument-generator',
                },
                multimeter: {
                    motion,
                    target: '#dolgLabBody',
                    animationClass: 'dolg-instrument-multimeter',
                },
                probes: {
                    motion,
                    target: '#probes-panel',
                    animationClass: 'dolg-instrument-probes',
                },
            },
        };
    }

    function applyPreferences(body, preferences) {
        if (!body || !body.classList) return;
        WORKSPACE_CLASSES.forEach((name) => body.classList.remove(name));
        preferences.classes.forEach((name) => body.classList.add(name));
        body.dataset.workspaceKind = preferences.workspaceKind;
        body.dataset.effectiveRenderMode = preferences.effectiveRenderMode;
        body.dataset.motionEnabled = preferences.motionEnabled ? 'on' : 'off';
    }

    function dispatchReady(doc, preferences, instrumentContract) {
        if (!doc || !doc.dispatchEvent || !root.CustomEvent) return;
        doc.dispatchEvent(new root.CustomEvent('dolg:workspace-preferences-ready', {
            detail: { preferences, instrumentContract },
        }));
    }

    function boot(doc) {
        const documentRef = doc || root.document;
        const body = documentRef && documentRef.body;
        if (!body) return null;
        const workspaceKind = detectWorkspaceKind(documentRef);
        if (workspaceKind === 'unknown') return null;
        const preferences = normalizePreferences(body.dataset || {}, { document: documentRef, workspaceKind });
        const instrumentContract = createInstrumentContract(preferences);

        applyPreferences(body, preferences);
        const publicPreferences = Object.assign({}, preferences, {
            refresh: function refreshWorkspacePreferences() {
                return boot(documentRef);
            },
        });
        root.DolgWorkspacePreferences = publicPreferences;
        root.DolgWorkspaceInstrumentContract = instrumentContract;
        dispatchReady(documentRef, publicPreferences, instrumentContract);
        return publicPreferences;
    }

    return {
        boot,
        normalizePreferences,
        createInstrumentContract,
        detectWorkspaceKind,
        supportsWebgl,
    };
});
