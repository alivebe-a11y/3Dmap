// Mapbox token (injected by Flask from MAPBOX_TOKEN env var)
mapboxgl.accessToken = window.MAPBOX_TOKEN;

// Mode switching: city vs stadium
let currentMode = 'city';
function setMode(mode) {
    currentMode = mode;
    document.getElementById('cityFields').classList.toggle('hidden', mode !== 'city');
    document.getElementById('stadiumFields').classList.toggle('hidden', mode !== 'stadium');
    document.getElementById('tabCity').classList.toggle('active', mode === 'city');
    document.getElementById('tabStadium').classList.toggle('active', mode === 'stadium');
    document.getElementById('city').required = (mode === 'city');
    document.getElementById('country').required = (mode === 'city');
}

// Stadium selection → auto-fill lat/lon in 3D controls
document.getElementById('stadium').addEventListener('input', function () {
    const name = this.value;
    if (window.STADIUMS && window.STADIUMS[name]) {
        const s = window.STADIUMS[name];
        document.getElementById('lat3d').value = s.lat;
        document.getElementById('lon3d').value = s.lon;
    }
});

// Radius slider
document.getElementById('radius').addEventListener('input', e =>
    document.getElementById('radiusVal').textContent = Math.round(e.target.value / 1000)
);

// 3D controls toggle
document.getElementById('enable3d').addEventListener('change', e => {
    document.getElementById('controls3d').classList.toggle('hidden', !e.target.checked);
    if (!e.target.checked) {
        document.getElementById('preview3dContainer').classList.add('hidden');
    }
});

// 3D sliders
document.getElementById('zoom3d').addEventListener('input', e =>
    document.getElementById('zoom3dVal').textContent = parseFloat(e.target.value).toFixed(1)
);
document.getElementById('pitch3d').addEventListener('input', e =>
    document.getElementById('pitch3dVal').textContent = e.target.value + '°'
);
document.getElementById('bearing3d').addEventListener('input', e =>
    document.getElementById('bearing3dVal').textContent = e.target.value + '°'
);

// Select All themes
document.getElementById('selectAllThemes').addEventListener('click', () => {
    const sel = document.getElementById('theme');
    Array.from(sel.options).forEach(o => o.selected = true);
});

// Preview map instance
let previewMap = null;

function get3DConfig() {
    return {
        lat: parseFloat(document.getElementById('lat3d').value),
        lon: parseFloat(document.getElementById('lon3d').value),
        zoom: parseFloat(document.getElementById('zoom3d').value),
        pitch: parseFloat(document.getElementById('pitch3d').value),
        bearing: parseFloat(document.getElementById('bearing3d').value),
        overlaySize: document.getElementById('overlaySize').value,
        lightPreset: document.getElementById('lightPreset').value
    };
}

// Minimal Mapbox style: 3D building extrusions on a guaranteed #050505
// background. The Standard style cannot be used for capture — its layers are
// encapsulated (getLayer('background') returns nothing), so the old "force
// the background black" hack never worked and captures were full map scenes
// the server-side cutout couldn't isolate. With this style the capture is
// genuinely landmark-on-black, which the poster compositor removes with a
// deterministic chroma key.
function makeCaptureStyle(lightPreset) {
    const lighting = {
        dawn:  { color: '#ffd9b3', intensity: 0.45 },
        day:   { color: '#ffffff', intensity: 0.55 },
        dusk:  { color: '#ffb366', intensity: 0.40 },
        night: { color: '#7799ff', intensity: 0.30 }
    }[lightPreset] || { color: '#ffffff', intensity: 0.45 };

    return {
        version: 8,
        sources: {
            composite: {
                type: 'vector',
                url: 'mapbox://mapbox.mapbox-streets-v8'
            }
        },
        light: {
            anchor: 'viewport',
            color: lighting.color,
            intensity: lighting.intensity,
            position: [1.15, 210, 30]
        },
        layers: [
            {
                id: 'background',
                type: 'background',
                paint: { 'background-color': '#050505' }
            },
            {
                id: 'buildings-3d',
                type: 'fill-extrusion',
                source: 'composite',
                'source-layer': 'building',
                filter: ['==', ['get', 'extrude'], 'true'],
                paint: {
                    'fill-extrusion-color': '#a8adb8',
                    'fill-extrusion-height': ['get', 'height'],
                    'fill-extrusion-base': ['get', 'min_height'],
                    'fill-extrusion-vertical-gradient': true,
                    'fill-extrusion-opacity': 1
                }
            }
        ]
    };
}

// Preview 3D landmark — uses the SAME style as the capture so the preview is
// exactly what ends up on the poster (WYSIWYG). Slider listeners are bound
// once at page load, not per preview click (they used to accumulate).
document.getElementById('preview3dBtn').addEventListener('click', () => {
    const cfg = get3DConfig();
    if (isNaN(cfg.lat) || isNaN(cfg.lon)) {
        document.getElementById('errorMsg').textContent = 'Enter lat/lon for 3D preview.';
        return;
    }

    const container = document.getElementById('preview3dContainer');
    container.classList.remove('hidden');

    if (previewMap) {
        previewMap.remove();
    }

    previewMap = new mapboxgl.Map({
        container: 'mapbox-container',
        style: makeCaptureStyle(cfg.lightPreset),
        center: [cfg.lon, cfg.lat],
        zoom: cfg.zoom,
        bearing: cfg.bearing,
        pitch: cfg.pitch,
        preserveDrawingBuffer: true
    });
});

['zoom3d', 'pitch3d', 'bearing3d'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
        if (!previewMap) return;
        const c = get3DConfig();
        previewMap.jumpTo({ zoom: c.zoom, pitch: c.pitch, bearing: c.bearing });
    });
});

document.getElementById('lightPreset').addEventListener('input', () => {
    if (!previewMap) return;
    previewMap.setStyle(makeCaptureStyle(get3DConfig().lightPreset));
});

// Capture 3D map as base64 PNG — stadium model on dark background only
function capture3DMap() {
    return new Promise((resolve, reject) => {
        const cfg = get3DConfig();
        if (isNaN(cfg.lat) || isNaN(cfg.lon)) {
            reject(new Error('3D coordinates required'));
            return;
        }

        const captureContainer = document.getElementById('mapbox-capture');
        captureContainer.style.width = '4096px';
        captureContainer.style.height = '4096px';
        captureContainer.style.background = '#050505';

        // Same style as the preview: buildings on a guaranteed #050505
        // background, so the server-side chroma key can cleanly cut the
        // landmark out.
        const captureMap = new mapboxgl.Map({
            container: 'mapbox-capture',
            style: makeCaptureStyle(cfg.lightPreset),
            center: [cfg.lon, cfg.lat],
            zoom: cfg.zoom,
            bearing: cfg.bearing,
            pitch: cfg.pitch,
            preserveDrawingBuffer: true,
            interactive: false
        });

        let settled = false;
        const finish = (fn, arg) => {
            if (settled) return;
            settled = true;
            clearTimeout(hardTimeout);
            try { captureMap.remove(); } catch (e) { /* already removed */ }
            fn(arg);
        };

        const doCapture = () => {
            try {
                const canvas = captureMap.getCanvas();
                const dataURL = canvas.toDataURL('image/png');
                finish(resolve, dataURL);
            } catch (err) {
                finish(reject, err);
            }
        };

        captureMap.on('idle', () => {
            // Give 3D geometry a moment to settle, then capture
            setTimeout(doCapture, 2000);
        });

        captureMap.on('error', (err) => {
            finish(reject, err);
        });

        // Hard fallback: if 'idle' never fires (partial style failure that emits no
        // 'error'), capture whatever has rendered so the promise can't hang forever.
        const hardTimeout = setTimeout(doCapture, 15000);
    });
}

// Form submit
document.getElementById('mapForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('generateBtn');
    const loader = document.getElementById('loader');
    const img = document.getElementById('resultImage');
    const link = document.getElementById('downloadLink');
    const err = document.getElementById('errorMsg');
    const batchMsg = document.getElementById('batchMsg');

    // Validate theme selection
    const themes = Array.from(document.getElementById('theme').selectedOptions).map(o => o.value);
    if (themes.length === 0) {
        err.textContent = 'Please select at least one theme.';
        return;
    }

    btn.disabled = true;
    loader.classList.remove('hidden');
    img.classList.add('hidden');
    link.classList.add('hidden');
    batchMsg.classList.add('hidden');
    err.textContent = '';

    try {
        const payload = {
            themes,
            radius: document.getElementById('radius').value
        };

        if (currentMode === 'stadium') {
            payload.stadium = document.getElementById('stadium').value;
            payload.badge = document.getElementById('badge').value;
        } else {
            payload.city = document.getElementById('city').value;
            payload.country = document.getElementById('country').value;
        }

        // If 3D is enabled, capture the map first
        if (document.getElementById('enable3d').checked) {
            loader.textContent = '🔄 Capturing 3D landmark...';
            const cfg = get3DConfig();
            const dataURL = await capture3DMap();
            payload.overlay_3d = dataURL;
            payload.overlay_size = cfg.overlaySize;
            payload.overlay_config = {
                lat: cfg.lat, lon: cfg.lon,
                zoom: cfg.zoom, pitch: cfg.pitch, bearing: cfg.bearing,
                lightPreset: cfg.lightPreset
            };
        }

        loader.textContent = themes.length > 1
            ? `🔄 Generating ${themes.length} posters...`
            : '🔄 Generating poster...';

        const res = await fetch('/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        loader.classList.add('hidden');

        if (data.success) {
            if (data.batch) {
                batchMsg.textContent = `✅ ${data.count} poster${data.count !== 1 ? 's' : ''} generated (${data.themes.join(', ')})`;
                batchMsg.classList.remove('hidden');
            } else {
                img.src = `/posters/${data.filename}`;
                img.classList.remove('hidden');
                link.href = `/posters/${data.filename}`;
                link.download = data.filename;
                link.classList.remove('hidden');
            }
        } else {
            throw new Error(data.error);
        }
    } catch (e) {
        err.textContent = e.message || 'Connection error.';
        loader.classList.add('hidden');
    } finally {
        btn.disabled = false;
    }
});
