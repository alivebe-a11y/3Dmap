# 3Dmap (MapToPoster) — project context

## What this is
Self-hosted web tool that generates print-quality poster art (24x34in @ 500 DPI,
exactly 12000x17000 px, full-bleed) of football stadiums and cities, under the
BlueBearLabs label. The poster is a flat, theme-coloured OSM street map with
typography; the signature feature is a single 3D "hero" of the stadium itself —
the ONLY 3D object on the poster — cut out and composited over the map.
Themes (17 JSON palettes in `themes/`) drive the whole look.

This repo (`3Dmap`) is the canonical direction. `maptoposter-dock` is the legacy
base; `maptoposter-3d` is an older Mapbox-render variant. Don't split work
across them.

## Architecture
- `app.py` — Flask. `/generate` spawns `create_map_poster.py` per theme
  (subprocess). Caches browser captures in `overlays_cache/` keyed by
  camera+light+hero style; key is VERSIONED (`overlay_v2_...`) — bump the
  version whenever capture framing/geometry changes so stale captures retire
  themselves.
- `create_map_poster.py` — OSMnx fetch (cached) + matplotlib render. Full-bleed
  axes [0,0,1,1], view cropped to poster aspect (fetch dist = distance * h/w).
  Never use bbox_inches='tight' (breaks exact dimensions).
- `image_overlay.py` — compositor. Stadium isolation = diff(A,B) AND volume(C),
  then scipy morphology: binary_closing (seal shadow-side gaps) →
  binary_fill_holes (pitch/roof holes) → component pruning (drop blobs detached
  from the stadium = behind-buildings) → erosion-preserved soft rim. If a
  three-capture cutout fails, ship the poster WITHOUT the hero (no medallion).
- `static/script.js` — hero style tabs: Graphic (mapbox/standard) or Photo
  (mapbox/standard-satellite); the A/B/C pipeline is style-agnostic.
  Browser captures three 4096px images with one camera:
  A = chosen style with 3D (landmark models), B = same without 3D,
  C = stadium footprint polygons (from streets-v8 via invisible query layer)
  extruded magenta-on-black, per-feature height * 1.12.
  CRITICAL: capture zoom = preview zoom + log2(4096 / preview width) — zoom is
  metres-per-pixel, so capturing at preview zoom frames ~10x more area and
  shrinks the stadium to a blurry speck.
- `stadium_data.py` — stadium DB (python dict). `cache_manager.py` — geocoding/
  OSM/poster caches with TTL.

## Deploy loop (user's setup)
1. Push to branch `claude/check-3d-maptoposter-fork-e191D` (or main).
2. GitHub Actions builds `ghcr.io/alivebe-a11y/3dmap:latest` (~3-5 min) — the
   workflow publishes :latest from BOTH branches.
3. User pulls on TrueNAS (Dockge stack at
   `/mnt/Pool_1/Configs/dockge2/Stacks/3dmap`):
   `docker compose pull && docker compose up -d --force-recreate`
   (`up -d` alone does NOT re-pull a cached :latest — this bit us once).
4. Data volumes under `/mnt/Pool_1/Home/MapG/` (posters, @overlays, @team
   badges, @cache). Port 5026->5025. MAPBOX_TOKEN via .env next to compose.
5. After changing static/script.js or templates: user must HARD-REFRESH the
   browser (cached JS produced a whole confusing debug session).

## Decisions already made (don't relitigate)
- No rembg/SAM/GPU — removed. Isolation is deterministic (diff + footprint
  volume + morphology). Mapbox Standard's layers are encapsulated: you cannot
  getLayer()/repaint its internals, only setConfigProperty basemap keys.
- Marker/star is skipped when a 3D hero or badge is present.
- Overlay/badge sizing derives from figure inches * dpi with
  OffsetImage(dpi_cor=False); sources only ever downscale.
- Latitude/longitude text uses N/S + E/W with abs().
- Coordinate inputs use step="any".

## Known backlog (agreed, not yet done)
- Test "Tint 3D to match theme" on light themes; tune or default it.
- In-process rendering instead of subprocess-per-theme (biggest speed win;
  also capture stderr — subprocess errors currently reach the UI opaque).
- Theme colour access via .get() with fallbacks (custom themes can KeyError).
- Title auto-fit for long stadium names (fontsize 88 fixed today).
- Draft-preview mode (~72 DPI fast render before the 500 DPI final).
- Batch results: show thumbnails, not just a count.
- Serve with waitress/gunicorn (Flask dev server blocks during generates).
- Radius slider allows 50 km with network_type='all' — cap or switch network
  type above ~15 km; label says "Zoom" but it's a radius.
- Port custom_themes support over from maptoposter-3d if wanted.
- Poster margin attribution: "© OpenStreetMap contributors" always; add
  "© Mapbox © Maxar" when the Photo (satellite) hero is used. Required for
  sold prints.
