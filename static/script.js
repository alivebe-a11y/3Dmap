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

// Hero style: 'graphic' = Mapbox Standard (stylised), 'photo' = Standard
// Satellite (real imagery with the same 3D landmark models on top). Both
// share the same config surface, so the whole A/B/C capture pipeline is
// style-agnostic — the diff+volume cutout works identically.
const HERO_STYLES = {
    graphic: 'mapbox://styles/mapbox/standard',
    photo: 'mapbox://styles/mapbox/standard-satellite'
};
let heroStyle = 'graphic';

function setHeroStyle(mode) {
    if (!HERO_STYLES[mode]) return;
    heroStyle = mode;
    document.getElementById('tabHeroGraphic').classList.toggle('active', mode === 'graphic');
    document.getElementById('tabHeroPhoto').classList.toggle('active', mode === 'photo');
    // Rebuild the preview in the new style if it's open
    if (previewMap) {
        const cfg = get3DConfig();
        previewMap.remove();
        previewMap = new mapboxgl.Map({
            container: 'mapbox-container',
            ...standardMapOptions(cfg)
        });
    }
}

// Mapbox Standard(-Satellite) map options shared by the preview and captures
// A/B. Both styles render the detailed 3D landmark models (the whole point
// of the hero shot); labels are hidden via their documented config
// properties.
function standardMapOptions(cfg) {
    return {
        style: HERO_STYLES[heroStyle],
        config: {
            basemap: {
                lightPreset: cfg.lightPreset,
                showPlaceLabels: false,
                showPointOfInterestLabels: false,
                showRoadLabels: false,
                showTransitLabels: false,
                show3dObjects: true
            }
        },
        center: [cfg.lon, cfg.lat],
        zoom: cfg.zoom,
        bearing: cfg.bearing,
        pitch: cfg.pitch,
        preserveDrawingBuffer: true
    };
}

// Style for capture C: the stadium's footprint polygons extruded as a flat
// magenta volume on black. The server intersects (A minus B) with this
// volume so ONLY the stadium survives — no segmentation model involved.
function makeMaskStyle(footprintsGeojson) {
    return {
        version: 8,
        sources: {
            fp: { type: 'geojson', data: footprintsGeojson }
        },
        light: { anchor: 'viewport', color: '#ffffff', intensity: 0 },
        layers: [
            { id: 'bg', type: 'background', paint: { 'background-color': '#000000' } },
            {
                id: 'vol',
                type: 'fill-extrusion',
                source: 'fp',
                paint: {
                    'fill-extrusion-color': '#ff00ff',
                    // Per-feature height with a slim 12% overshoot. A tall
                    // flat volume (the old 1.4x + 45m floor) left a wide
                    // band above the real roofline where buildings BEHIND
                    // the stadium projected into the silhouette and leaked
                    // into the cutout.
                    'fill-extrusion-height': ['*', 1.12, ['get', 'h']],
                    'fill-extrusion-base': 0,
                    'fill-extrusion-opacity': 1
                }
            }
        ]
    };
}

// Pick the building footprints that form the stadium at the map centre.
// Ring-shaped stands surround the pitch, so the centre point is often NOT
// inside the polygon — prefer polygons whose bbox contains the centre,
// falling back to the nearest footprints within ~120 m.
function selectStadiumFootprints(features, center) {
    const mPerDegLat = 111320;
    const mPerDegLon = 111320 * Math.cos(center.lat * Math.PI / 180);
    const containing = [];
    const near = [];

    for (const f of features) {
        const g = f.geometry;
        if (!g || (g.type !== 'Polygon' && g.type !== 'MultiPolygon')) continue;
        const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const poly of polys) {
            for (const pt of poly[0]) {
                if (pt[0] < minX) minX = pt[0];
                if (pt[0] > maxX) maxX = pt[0];
                if (pt[1] < minY) minY = pt[1];
                if (pt[1] > maxY) maxY = pt[1];
            }
        }
        const height = Number(f.properties && f.properties.height) || 0;
        const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
        const distM = Math.hypot((cx - center.lng) * mPerDegLon, (cy - center.lat) * mPerDegLat);
        const item = { geometry: g, height, distM };
        if (center.lng >= minX && center.lng <= maxX && center.lat >= minY && center.lat <= maxY) {
            containing.push(item);
        } else if (distM < 120) {
            near.push(item);
        }
    }

    let chosen = containing;
    if (!chosen.length) {
        near.sort((a, b) => a.distM - b.distM);
        chosen = near.slice(0, 6);
    }

    return {
        fc: {
            type: 'FeatureCollection',
            // Carry each footprint's real height (fallback 45 m when the
            // tile has no height data) — the mask style extrudes per
            // feature so the volume hugs the actual roofline.
            features: chosen.map(i => ({
                type: 'Feature',
                properties: { h: i.height > 0 ? i.height : 45 },
                geometry: i.geometry
            }))
        },
        count: chosen.length
    };
}

// Wait for a map to go idle; resolves (never rejects) after timeoutMs as a
// hard fallback so a stalled style can't hang the capture pipeline.
function waitForIdle(map, timeoutMs, settleMs) {
    return new Promise((resolve) => {
        let settled = false;
        const done = () => {
            if (settled) return;
            settled = true;
            clearTimeout(hard);
            setTimeout(resolve, settleMs || 0);
        };
        map.on('idle', done);
        map.on('error', done);
        const hard = setTimeout(done, timeoutMs);
    });
}

// Preview 3D landmark — Mapbox Standard, so the detailed landmark model is
// visible while framing the shot. Slider listeners are bound once at page
// load, not per preview click (they used to accumulate).
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
        ...standardMapOptions(cfg)
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
    try {
        previewMap.setConfigProperty('basemap', 'lightPreset', get3DConfig().lightPreset);
    } catch (e) { /* style still loading */ }
});

// Three-capture pipeline for stadium isolation:
//   A — Standard scene with 3D objects (landmark model renders here)
//   B — identical camera, 3D objects off
//   C — magenta volume of the stadium footprint on black
// The server keeps pixels that are 3D (A≠B) AND inside the volume (C):
// exactly the stadium, with automatic fallback to a generic extrusion where
// Mapbox has no landmark model, and to the vignette medallion if the
// footprint can't be found at all.
async function capture3DMap(onProgress) {
    const cfg = get3DConfig();
    if (isNaN(cfg.lat) || isNaN(cfg.lon)) {
        throw new Error('3D coordinates required');
    }
    const progress = onProgress || (() => {});

    const captureContainer = document.getElementById('mapbox-capture');
    captureContainer.style.width = '4096px';
    captureContainer.style.height = '4096px';
    captureContainer.style.background = '#050505';

    // Zoom fixes metres-per-pixel, so a 4096px canvas at the preview's zoom
    // frames a ~10x wider area and leaves the stadium a few hundred pixels
    // tall (blurry on the poster, and so small the volume-mask sanity check
    // rejected it). Raise the zoom by log2(capture/preview) so the capture
    // reproduces the preview's framing at full 4096px resolution.
    const previewEl = document.getElementById('mapbox-container');
    const previewW = (previewEl && previewEl.clientWidth) ? previewEl.clientWidth : 480;
    const captureCfg = { ...cfg, zoom: Math.min(22, cfg.zoom + Math.log2(4096 / previewW)) };

    // --- Capture A: full scene with 3D ---
    progress('Capturing 3D scene (1/3)...');
    const map = new mapboxgl.Map({
        container: 'mapbox-capture',
        ...standardMapOptions(captureCfg),
        interactive: false
    });

    // Invisible building layer so we can query the stadium footprint from
    // Mapbox's own vector data (Standard's internal layers can't be queried).
    map.on('style.load', () => {
        try {
            map.addSource('fpq', { type: 'vector', url: 'mapbox://mapbox.mapbox-streets-v8' });
            map.addLayer({
                id: 'fpq-fill', type: 'fill', source: 'fpq',
                'source-layer': 'building', paint: { 'fill-opacity': 0 }
            });
        } catch (e) { /* footprint query is best-effort */ }
    });

    await waitForIdle(map, 20000, 2000);
    const imageA = map.getCanvas().toDataURL('image/png');

    let footprints = { fc: null, count: 0 };
    try {
        const feats = map.querySourceFeatures('fpq', { sourceLayer: 'building' });
        footprints = selectStadiumFootprints(feats, { lng: cfg.lon, lat: cfg.lat });
    } catch (e) { /* fall through to medallion */ }

    // --- Capture B: same camera, 3D off ---
    progress('Capturing base scene (2/3)...');
    let imageB = null;
    try {
        map.setConfigProperty('basemap', 'show3dObjects', false);
        await waitForIdle(map, 15000, 800);
        imageB = map.getCanvas().toDataURL('image/png');
    } catch (e) { /* fall through to medallion */ }
    map.remove();

    // --- Capture C: footprint volume mask ---
    let imageC = null;
    if (imageB && footprints.count > 0) {
        progress('Capturing footprint mask (3/3)...');
        const maskMap = new mapboxgl.Map({
            container: 'mapbox-capture',
            style: makeMaskStyle(footprints.fc),
            center: [captureCfg.lon, captureCfg.lat],
            zoom: captureCfg.zoom,
            bearing: captureCfg.bearing,
            pitch: captureCfg.pitch,
            preserveDrawingBuffer: true,
            interactive: false
        });
        await waitForIdle(maskMap, 15000, 500);
        imageC = maskMap.getCanvas().toDataURL('image/png');
        maskMap.remove();
    }

    return { imageA, imageB, imageC };
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
            const cfg = get3DConfig();
            const caps = await capture3DMap(msg => { loader.textContent = '🔄 ' + msg; });
            payload.overlay_3d = caps.imageA;
            if (caps.imageB) payload.overlay_3d_base = caps.imageB;
            if (caps.imageC) payload.overlay_3d_mask = caps.imageC;
            payload.overlay_size = cfg.overlaySize;
            payload.overlay_tint = document.getElementById('overlayTint').checked;
            payload.overlay_config = {
                lat: cfg.lat, lon: cfg.lon,
                zoom: cfg.zoom, pitch: cfg.pitch, bearing: cfg.bearing,
                lightPreset: cfg.lightPreset,
                hero: heroStyle
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
