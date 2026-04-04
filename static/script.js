// Mapbox token (injected by Flask from MAPBOX_TOKEN env var)
mapboxgl.accessToken = window.MAPBOX_TOKEN;

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

// Preview map instance
let previewMap = null;

function get3DConfig() {
    return {
        lat: parseFloat(document.getElementById('lat3d').value),
        lon: parseFloat(document.getElementById('lon3d').value),
        zoom: parseFloat(document.getElementById('zoom3d').value),
        pitch: parseFloat(document.getElementById('pitch3d').value),
        bearing: parseFloat(document.getElementById('bearing3d').value),
        overlaySize: document.getElementById('overlaySize').value
    };
}

// Preview 3D landmark
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
        style: 'mapbox://styles/mapbox/standard',
        config: {
            basemap: {
                lightPreset: "dusk",
                showPedestrianRoads: false,
                showPlaceLabels: false,
                showPointOfInterestLabels: false,
                backgroundPointOfInterestLabels: "none",
                showRoadLabels: false,
                showTransitLabels: false,
                showAdminBoundaries: false,
                show3dBuildings: false,
                showLandmarkIconLabels: false
            }
        },
        center: [cfg.lon, cfg.lat],
        zoom: cfg.zoom,
        bearing: cfg.bearing,
        pitch: cfg.pitch,
        preserveDrawingBuffer: true
    });

    previewMap.on('load', () => {
        // Adjust sliders in real-time
        ['zoom3d', 'pitch3d', 'bearing3d'].forEach(id => {
            document.getElementById(id).addEventListener('input', () => {
                const c = get3DConfig();
                previewMap.jumpTo({ zoom: c.zoom, pitch: c.pitch, bearing: c.bearing });
            });
        });
    });
});

// Capture 3D map as base64 PNG
function capture3DMap() {
    return new Promise((resolve, reject) => {
        const cfg = get3DConfig();
        if (isNaN(cfg.lat) || isNaN(cfg.lon)) {
            reject(new Error('3D coordinates required'));
            return;
        }

        const captureContainer = document.getElementById('mapbox-capture');
        // Use larger canvas for high-res capture
        captureContainer.style.width = '1024px';
        captureContainer.style.height = '1024px';

        const captureMap = new mapboxgl.Map({
            container: 'mapbox-capture',
            style: 'mapbox://styles/mapbox/standard',
            config: {
                basemap: {
                    lightPreset: "dusk",
                    showPedestrianRoads: false,
                    showPlaceLabels: false,
                    showPointOfInterestLabels: false,
                    backgroundPointOfInterestLabels: "none",
                    showRoadLabels: false,
                    showTransitLabels: false,
                    showAdminBoundaries: false,
                    show3dBuildings: false,
                    showLandmarkIconLabels: false
                }
            },
            center: [cfg.lon, cfg.lat],
            zoom: cfg.zoom,
            bearing: cfg.bearing,
            pitch: cfg.pitch,
            preserveDrawingBuffer: true,
            interactive: false
        });

        captureMap.on('idle', () => {
            // Wait a bit for 3D models to fully render
            setTimeout(() => {
                try {
                    const canvas = captureMap.getCanvas();
                    const dataURL = canvas.toDataURL('image/png');
                    captureMap.remove();
                    resolve(dataURL);
                } catch (err) {
                    captureMap.remove();
                    reject(err);
                }
            }, 2000);
        });

        captureMap.on('error', (err) => {
            captureMap.remove();
            reject(err);
        });
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

    btn.disabled = true;
    loader.classList.remove('hidden');
    img.classList.add('hidden');
    link.classList.add('hidden');
    err.textContent = '';

    try {
        const payload = {
            city: document.getElementById('city').value,
            country: document.getElementById('country').value,
            theme: document.getElementById('theme').value,
            radius: document.getElementById('radius').value
        };

        // If 3D is enabled, capture the map first
        if (document.getElementById('enable3d').checked) {
            loader.textContent = '🔄 Capturing 3D landmark...';
            const cfg = get3DConfig();
            const dataURL = await capture3DMap();
            payload.overlay_3d = dataURL;
            payload.overlay_size = cfg.overlaySize;
            payload.overlay_config = {
                lat: cfg.lat, lon: cfg.lon,
                zoom: cfg.zoom, pitch: cfg.pitch, bearing: cfg.bearing
            };
            loader.textContent = '🔄 Generating poster with 3D overlay...';
        } else {
            loader.textContent = '🔄 Generating... (Please wait)';
        }

        const res = await fetch('/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.success) {
            img.src = `/posters/${data.filename}`;
            img.classList.remove('hidden');
            link.href = `/posters/${data.filename}`;
            link.download = data.filename;
            link.classList.remove('hidden');
            loader.classList.add('hidden');
        } else {
            throw new Error(data.error);
        }
    } catch (e) {
        err.textContent = e.message || "Connection error.";
        loader.classList.add('hidden');
    } finally {
        btn.disabled = false;
    }
});
