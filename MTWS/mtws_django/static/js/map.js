// ========================================
// 地图告警（MapLibre）：底图 + RainViewer raster 同变换，杜绝雷达/底图漂移
// 参考 rainViewerLayer.js：radar 为 native raster source，与 basemap 共用同一 WebGL 矩阵
// ========================================

window._viewMode = window._viewMode || 'list';

let _mapView = 'china';
let _mapCoordCache = null;
let _mlMap = null;
let _mlReady = false;
let _geoReady = { world: false, provinces: false, admin1: false, lakes: false, rivers: false };
let _worldGj = null;
let _provinceGj = null;
let _admin1Gj = null;
let _lakesGj = null;
let _riversGj = null;
let _flightStatusCache = null;
let _mapStyle = null;
let _mapPalette = null;
let _borderWidths = { country: 1.35, province: 0.75, admin1: 0.55 };
let _blinkPhase = false;
let _blinkTimer = null;
let _radarAlertCache = { alerts: [], observe: [], watch: [] };
let _radarPollTimer = null;
let _radarBlinkCodes = new Set();
let _radarListMode = 'alarm'; // alarm | observe
let _rippleRaf = 0;
const _RADAR_VISIBLE_ROWS = 10;
let _radarOverlayMeta = null;
let _radarFramePath = null;

const _ML_CHINA = { center: [105, 35], zoom: 3.6 };
const _ML_WORLD = { center: [150, 12], zoom: 1.4 };

function _staticBase() {
    const el = document.querySelector('script[src*="map.js"]');
    if (el && el.src) return el.src.replace(/js\/map\.js.*$/, '');
    return (window.staticUrl || '/static/');
}

function _glyphsUrl() {
    // 本地 MapLibre glyphs（Noto Sans Regular），不依赖外网字形服务
    return _staticBase() + 'fonts/{fontstack}/{range}.pbf';
}

function _palette() {
    return _mapPalette || {
        background: '#2a3038',
        land: '#0c1016',
        country_border: '#9aa4b0',
        province_border: '#5c6670',
        admin1_border: '#6a7480',
        label_color: '#c4ccd4',
        country_label: '#a8b2bc',
        river: '#5d7380',
        river_width: 0.75,
        river_opacity: 0.5,
        label_halo: 'rgba(8,12,18,0.88)',
        lake: 'rgba(28, 40, 52, 0.85)',
        lake_border: '#3a4858',
    };
}

function _labelHalo(pal) {
    return (pal && pal.label_halo) || 'rgba(8,12,18,0.88)';
}

function _riverStyle(pal) {
    const p = pal || _palette();
    return {
        color: p.river || '#5d7380',
        width: p.river_width != null ? p.river_width : 0.75,
        opacity: p.river_opacity != null ? p.river_opacity : 0.5,
    };
}

function _isLightBasemap() {
    if (_mapStyle && _mapStyle.color_scheme === 'warm_dim') return true;
    const land = String((_palette().land) || '').trim();
    const m = /^#([0-9a-f]{6})$/i.exec(land);
    if (!m) return false;
    const n = parseInt(m[1], 16);
    const r = (n >> 16) & 255;
    const g = (n >> 8) & 255;
    const b = n & 255;
    return (r * 299 + g * 587 + b * 114) / 1000 >= 180;
}

/** 无告警，以及闪烁/涟漪的另一相：深色底用白，浅色底用黑 */
function _contrastMarkColor() {
    return _isLightBasemap() ? '#000000' : '#ffffff';
}

function _mapColor(level) {
    if (level === 'N' || !level) return _contrastMarkColor();
    if (typeof getAlertColorHex === 'function') return getAlertColorHex(level);
    return ({ R: '#e74c3c', Y: '#f39c12', G: '#27ae60' })[level] || '#7f8c8d';
}

function _flashAltColor() {
    return _contrastMarkColor();
}

function _markerSizes() {
    const inner = (_mapStyle && _mapStyle.marker_inner_size) || 6;
    const outer = (_mapStyle && _mapStyle.marker_outer_size) || 10;
    return { inner, outer, border: Math.max(1.5, (outer - inner) / 2) };
}

// ── 主模式切换 ───────────────────────────────────────────

function switchViewMode(mode) {
    window._viewMode = mode;
    localStorage.setItem('mtws_view_mode', mode);
    const panel = document.getElementById('map-alert-panel');
    if (mode === 'map') {
        document.body.classList.add('map-mode');
        if (panel) panel.style.display = 'flex';
        if (typeof hideFlightMarksLegend === 'function') hideFlightMarksLegend();
        if (typeof applyFilters === 'function') applyFilters();
        setTimeout(() => {
            _syncPanelPosition();
            _initMap();
            _bindMapFlightScope();
            _initRadarAlertFloat();
            _refreshRadarAlerts();
        }, 30);
    } else {
        document.body.classList.remove('map-mode');
        if (panel) panel.style.display = 'none';
        const radarFloat = document.getElementById('radar-alert-float');
        if (radarFloat) radarFloat.style.display = 'none';
        if (typeof closeRadarEcho === 'function') closeRadarEcho();
        _destroyMap();
        if (typeof applyFilters === 'function') applyFilters();
        if (mode === 'list' && typeof ensureFlightMarksLegend === 'function') {
            ensureFlightMarksLegend();
        }
    }
}

function _switchMapView(view) {
    _mapView = view;
    localStorage.setItem('mtws_map_view', view);
    if (!_mlMap) return;
    const v = view === 'china' ? _ML_CHINA : _ML_WORLD;
    _mlMap.easeTo({ center: v.center, zoom: v.zoom, duration: 500 });
    _applyLayerVisibility();
    if (typeof updateMapAlert === 'function') updateMapAlert();
}

function _syncPanelPosition() {
    const panel = document.getElementById('map-alert-panel');
    if (!panel) return;
    const topPx = (typeof window.contentBandTop === 'function')
        ? window.contentBandTop() : 180;
    const totalH = window.innerHeight - topPx;
    panel.style.top = topPx + 'px';
    panel.style.height = totalH + 'px';
    const mapEl = document.getElementById('map-world');
    const bar = panel.querySelector('.map-flight-toolbar');
    const barH = bar ? bar.offsetHeight : 0;
    if (mapEl) mapEl.style.height = Math.max(100, totalH - barH) + 'px';
    if (_mlMap) _mlMap.resize();
    if (typeof window.syncNavTop === 'function') window.syncNavTop();
}

// ── MapLibre style / layers ──────────────────────────────

function _emptyFc() {
    return { type: 'FeatureCollection', features: [] };
}

/**
 * 旧的共边提取。相邻面顶点对不齐时国界会断开，海岸也会被丢掉。
 * 可见的海陆轮廓和国界改由 OpenFreeMap 矢量瓦片提供，这里不再用于上图。
 */
function _extractSharedBorders(gj) {
    const edgeMap = new Map();
    const q = (n) => Math.round(Number(n) * 1e5) / 1e5;
    const addRing = (ring) => {
        if (!ring || ring.length < 2) return;
        for (let i = 0; i < ring.length - 1; i++) {
            const a = ring[i];
            const b = ring[i + 1];
            if (!a || !b || a.length < 2 || b.length < 2) continue;
            const ax = q(a[0]); const ay = q(a[1]);
            const bx = q(b[0]); const by = q(b[1]);
            if (ax === bx && ay === by) continue;
            const ka = ax + ',' + ay;
            const kb = bx + ',' + by;
            const key = ka < kb ? ka + '|' + kb : kb + '|' + ka;
            const hit = edgeMap.get(key);
            if (hit) hit.count += 1;
            else {
                edgeMap.set(key, {
                    count: 1,
                    coords: ka < kb ? [[ax, ay], [bx, by]] : [[bx, by], [ax, ay]],
                });
            }
        }
    };
    const walkGeom = (g) => {
        if (!g || !g.coordinates) return;
        if (g.type === 'Polygon') {
            addRing(g.coordinates[0]);
        } else if (g.type === 'MultiPolygon') {
            g.coordinates.forEach(poly => addRing(poly && poly[0]));
        }
    };
    ((gj && gj.features) || []).forEach(ft => walkGeom(ft.geometry));

    const features = [];
    edgeMap.forEach(v => {
        if (v.count < 2) return; // 海岸线 / 外轮廓
        features.push({
            type: 'Feature',
            properties: {},
            geometry: { type: 'LineString', coordinates: v.coords },
        });
    });
    return { type: 'FeatureCollection', features };
}

function _waterFilter(includeLakes) {
    const classes = ['ocean', 'sea', 'bay', 'strait'];
    if (includeLakes) classes.push('lake', 'reservoir');
    return ['in', ['get', 'class'], ['literal', classes]];
}

function _buildStyle(pal) {
    const showLakes = !!(_mapStyle && _mapStyle.global && _mapStyle.global.lakes);
    return {
        version: 8,
        glyphs: _glyphsUrl(),
        sources: {
            openmaptiles: {
                type: 'vector',
                url: 'https://tiles.openfreemap.org/planet',
                attribution: '© OpenStreetMap contributors, OpenFreeMap'
            },
            world: { type: 'geojson', data: _worldGj || _emptyFc() },
            'country-borders': { type: 'geojson', data: _emptyFc() },
            provinces: { type: 'geojson', data: _provinceGj || _emptyFc() },
            'province-borders': { type: 'geojson', data: _emptyFc() },
            admin1: { type: 'geojson', data: _admin1Gj || _emptyFc() },
            'admin1-borders': { type: 'geojson', data: _emptyFc() },
            lakes: { type: 'geojson', data: _lakesGj || _emptyFc() },
            rivers: { type: 'geojson', data: _riversGj || _emptyFc() },
            airports: { type: 'geojson', data: _emptyFc() },
            'province-labels': { type: 'geojson', data: _emptyFc() },
            'admin1-labels': { type: 'geojson', data: _emptyFc() },
            'country-labels': { type: 'geojson', data: _emptyFc() },
        },
        layers: [
            // 陆地是底色，海陆轮廓用瓦片水域面，避免简化多边形把海岸抹平
            { id: 'bg', type: 'background', paint: { 'background-color': pal.land } },
            {
                id: 'water', type: 'fill', source: 'openmaptiles', 'source-layer': 'water',
                filter: _waterFilter(showLakes),
                paint: { 'fill-color': pal.background }
            },
            {
                id: 'land', type: 'fill', source: 'world',
                layout: { visibility: 'none' },
                paint: { 'fill-color': pal.land, 'fill-opacity': 1 }
            },
            {
                id: 'lakes-fill', type: 'fill', source: 'lakes',
                layout: { visibility: 'none' },
                paint: { 'fill-color': typeof pal.lake === 'string' ? pal.lake : '#1c2834', 'fill-opacity': 0.9 }
            },
            {
                id: 'rivers', type: 'line', source: 'rivers',
                layout: { visibility: 'none' },
                paint: {
                    'line-color': _riverStyle(pal).color,
                    'line-width': _riverStyle(pal).width,
                    'line-opacity': _riverStyle(pal).opacity
                }
            },
            // 国界/省界来自瓦片 boundary，连续且不含被抹掉的海岸段
            {
                id: 'boundary-state', type: 'line', source: 'openmaptiles', 'source-layer': 'boundary',
                filter: ['all', ['==', ['get', 'admin_level'], 4], ['!=', ['get', 'maritime'], 1]],
                minzoom: 3,
                paint: {
                    'line-color': pal.province_border,
                    'line-opacity': 0.55,
                    'line-dasharray': [2, 3],
                    'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 8, 1.2, 12, 2]
                }
            },
            {
                id: 'boundary-country', type: 'line', source: 'openmaptiles', 'source-layer': 'boundary',
                filter: ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1]],
                layout: { 'line-cap': 'round', 'line-join': 'round' },
                paint: {
                    'line-color': pal.country_border,
                    'line-opacity': 0.9,
                    'line-width': ['interpolate', ['linear'], ['zoom'], 0, 0.7, 4, 1.2, 8, 2, 12, 3]
                }
            },
            // 旧的共边国界/省界不再显示（顶点对不齐会断成一段一段）
            {
                id: 'province-border', type: 'line', source: 'province-borders',
                layout: { visibility: 'none' },
                paint: {
                    'line-color': pal.province_border,
                    'line-width': _borderWidths.province,
                    'line-dasharray': [2.2, 2.2],
                    'line-opacity': 0.85
                }
            },
            {
                id: 'admin1-border', type: 'line', source: 'admin1-borders',
                layout: { visibility: 'none' },
                paint: {
                    'line-color': pal.admin1_border,
                    'line-width': _borderWidths.admin1,
                    'line-dasharray': [2, 2.5],
                    'line-opacity': 0.8
                }
            },
            {
                id: 'country-border', type: 'line', source: 'country-borders',
                layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
                paint: {
                    'line-color': pal.country_border,
                    'line-width': _borderWidths.country,
                    'line-opacity': 0.95
                }
            },
            {
                id: 'country-labels', type: 'symbol', source: 'country-labels',
                layout: {
                    visibility: 'none',
                    'text-field': ['get', 'name'],
                    'text-size': 11,
                    'text-font': ['Noto Sans Regular'],
                    'text-allow-overlap': false
                },
                paint: {
                    'text-color': pal.country_label,
                    'text-halo-color': _labelHalo(pal),
                    'text-halo-width': 1.6
                }
            },
            {
                id: 'province-labels', type: 'symbol', source: 'province-labels',
                layout: {
                    visibility: 'none',
                    'text-field': ['get', 'name'],
                    'text-size': 10,
                    'text-font': ['Noto Sans Regular'],
                    'text-allow-overlap': false
                },
                paint: {
                    'text-color': pal.label_color,
                    'text-halo-color': _labelHalo(pal),
                    'text-halo-width': 1.5
                }
            },
            {
                id: 'admin1-labels', type: 'symbol', source: 'admin1-labels',
                layout: {
                    visibility: 'none',
                    'text-field': ['get', 'name'],
                    'text-size': 9,
                    'text-font': ['Noto Sans Regular'],
                    'text-allow-overlap': false
                },
                paint: {
                    'text-color': pal.label_color,
                    'text-halo-color': _labelHalo(pal),
                    'text-halo-width': 1.4
                }
            },
            {
                id: 'airports-ripple', type: 'circle', source: 'airports',
                filter: ['==', ['get', 'radarRipple'], 1],
                paint: {
                    'circle-radius': 10,
                    'circle-color': 'transparent',
                    'circle-stroke-width': 2,
                    'circle-stroke-color': ['get', 'rippleColor'],
                    'circle-stroke-opacity': 0.85,
                    'circle-pitch-alignment': 'map'
                }
            },
            {
                id: 'airports-outer', type: 'circle', source: 'airports',
                paint: {
                    'circle-radius': _markerSizes().outer / 2,
                    'circle-color': 'transparent',
                    'circle-stroke-width': _markerSizes().border,
                    'circle-stroke-color': ['get', 'ringColor'],
                    'circle-stroke-opacity': ['get', 'ringOpacity'],
                    'circle-pitch-alignment': 'map'
                }
            },
            {
                id: 'airports-inner', type: 'circle', source: 'airports',
                paint: {
                    'circle-radius': _markerSizes().inner / 2,
                    'circle-color': ['get', 'fillColor'],
                    'circle-opacity': 0.92,
                    'circle-pitch-alignment': 'map'
                }
            },
            {
                id: 'airports-label', type: 'symbol', source: 'airports',
                layout: {
                    visibility: 'none',
                    'text-field': ['get', 'code'],
                    'text-size': 10,
                    'text-offset': [0, 1.2],
                    'text-font': ['Noto Sans Regular'],
                    'text-allow-overlap': false
                },
                paint: {
                    'text-color': pal.label_color,
                    'text-halo-color': _labelHalo(pal),
                    'text-halo-width': 1.4
                }
            },
        ]
    };
}

function _labelPointsFromPolygons(gj, nameKey) {
    const seen = new Set();
    const features = [];
    ((gj && gj.features) || []).forEach(ft => {
        const name = (ft.properties || {})[nameKey || 'name'];
        if (!name || seen.has(name)) return;
        seen.add(name);
        let coords = (ft.properties && (ft.properties.centroid || ft.properties.center)) || null;
        if (!coords) {
            const g = ft.geometry;
            if (!g) return;
            let ring = null;
            if (g.type === 'Polygon') ring = g.coordinates[0];
            else if (g.type === 'MultiPolygon') {
                let best = 0;
                g.coordinates.forEach(p => {
                    if (p[0] && p[0].length > best) { best = p[0].length; ring = p[0]; }
                });
            }
            if (!ring || !ring.length) return;
            let sx = 0, sy = 0, n = 0;
            ring.forEach(p => { sx += p[0]; sy += p[1]; n++; });
            coords = [sx / n, sy / n];
        }
        features.push({
            type: 'Feature',
            properties: { name },
            geometry: { type: 'Point', coordinates: coords }
        });
    });
    return { type: 'FeatureCollection', features };
}

function _setSourceData(id, data) {
    if (!_mlMap || !_mlMap.getSource(id)) return;
    _mlMap.getSource(id).setData(data || _emptyFc());
}

function _vis(id, on) {
    if (!_mlMap || !_mlMap.getLayer(id)) return;
    _mlMap.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}

function _applyLayerVisibility() {
    if (!_mlMap || !_mlReady) return;
    const g = (_mapStyle && _mapStyle.global) || {};
    const c = (_mapStyle && _mapStyle.china) || {};
    const w = (_mapStyle && _mapStyle.world) || {};
    _vis('land', false);
    _vis('country-border', false);
    _vis('province-border', false);
    _vis('admin1-border', false);
    _vis('lakes-fill', false);
    _vis('boundary-country', g.country_borders !== false);
    const showState = (_mapView !== 'world' && c.province_borders !== false)
        || (_mapView === 'world' && !!w.admin1_borders);
    _vis('boundary-state', showState);
    if (_mlMap.getLayer('water')) _mlMap.setFilter('water', _waterFilter(!!g.lakes));
    if (_mlMap.getLayer('boundary-state')) {
        const pal = _palette();
        _mlMap.setPaintProperty('boundary-state', 'line-color',
            _mapView === 'world' ? pal.admin1_border : pal.province_border);
    }
    _vis('province-labels', !!c.province_labels && _geoReady.provinces);
    _vis('admin1-labels', _mapView === 'world' && !!w.admin1_labels && _geoReady.admin1);
    _vis('country-labels', !!g.country_labels);
    _vis('rivers', !!g.rivers && _geoReady.rivers);
    _vis('airports-label', !!(_mapStyle && _mapStyle.show_airport_labels));
}

function _applyPaletteToMap() {
    if (!_mlMap || !_mlReady) return;
    const pal = _palette();
    const bw = _borderWidths;
    const setPaint = (layer, prop, val) => {
        if (_mlMap.getLayer(layer)) _mlMap.setPaintProperty(layer, prop, val);
    };
    setPaint('bg', 'background-color', pal.land);
    setPaint('water', 'fill-color', pal.background);
    setPaint('land', 'fill-color', pal.land);
    setPaint('boundary-country', 'line-color', pal.country_border);
    setPaint('boundary-state', 'line-color', _mapView === 'world' ? pal.admin1_border : pal.province_border);
    setPaint('country-border', 'line-color', pal.country_border);
    setPaint('country-border', 'line-width', bw.country);
    setPaint('province-border', 'line-color', pal.province_border);
    setPaint('province-border', 'line-width', bw.province);
    setPaint('province-border', 'line-dasharray', [2.2, 2.2]);
    setPaint('admin1-border', 'line-color', pal.admin1_border);
    setPaint('admin1-border', 'line-width', bw.admin1);
    setPaint('admin1-border', 'line-dasharray', [2, 2.5]);
    const halo = _labelHalo(pal);
    const river = _riverStyle(pal);
    setPaint('country-labels', 'text-color', pal.country_label);
    setPaint('country-labels', 'text-halo-color', halo);
    setPaint('province-labels', 'text-color', pal.label_color);
    setPaint('province-labels', 'text-halo-color', halo);
    setPaint('admin1-labels', 'text-color', pal.label_color);
    setPaint('admin1-labels', 'text-halo-color', halo);
    setPaint('airports-label', 'text-color', pal.label_color);
    setPaint('airports-label', 'text-halo-color', halo);
    setPaint('rivers', 'line-color', river.color);
    setPaint('rivers', 'line-width', river.width);
    setPaint('rivers', 'line-opacity', river.opacity);
    setPaint('lakes-fill', 'fill-color', typeof pal.lake === 'string' ? pal.lake : '#1c2834');
    const sizes = _markerSizes();
    setPaint('airports-inner', 'circle-radius', sizes.inner / 2);
    setPaint('airports-outer', 'circle-radius', sizes.outer / 2);
    setPaint('airports-outer', 'circle-stroke-width', sizes.border);
}

function _syncMapToolbarTone() {
    const bar = document.querySelector('.map-flight-toolbar');
    if (!bar) return;
    const scheme = (_mapStyle && _mapStyle.color_scheme) || '';
    bar.classList.toggle('is-dark-map', !_isLightBasemap());
    if (scheme) bar.dataset.scheme = scheme;
}

function applyMapStyleConfig(cfg, borderWidths, palette) {
    _mapStyle = cfg || _mapStyle;
    if (borderWidths) _borderWidths = borderWidths;
    if (palette) _mapPalette = palette;
    _syncMapToolbarTone();
    _ensureBlinkTimer();
    _applyPaletteToMap();
    _applyLayerVisibility();
    updateMapAlert();
}
window.applyMapStyleConfig = applyMapStyleConfig;

function _loadMapStyleConfig() {
    if (typeof currentTimeMode === 'undefined') return;
    fetch(`/${currentTimeMode}/api/map-style/config/`, {
        headers: typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) applyMapStyleConfig(data.config, data.border_widths, data.palette);
        })
        .catch(err => console.warn('[地图样式] 加载失败', err));
}

// ── GeoJSON 加载（标准 WGS84，非 pacific）────────────────

function _loadGeo() {
    const base = _staticBase() + 'geo/';
    const jobs = [
        ['world.json', 'world', (d) => { _worldGj = d; }],
        ['china.json', 'provinces', (d) => { _provinceGj = d; }],
        ['admin1_pacific.json', 'admin1', (d) => { _admin1Gj = _unpacificGeoJson(d); }],
        ['lakes_pacific.json', 'lakes', (d) => { _lakesGj = _unpacificGeoJson(d); }],
        ['rivers_pacific.json', 'rivers', (d) => { _riversGj = _unpacificGeoJson(d); }],
    ];
    return Promise.all(jobs.map(([file, key, assign]) =>
        fetch(base + file).then(r => (r.ok ? r.json() : null)).then(data => {
            if (!data) return;
            assign(data);
            _geoReady[key] = true;
            if (_mlMap && _mlReady) {
                if (key === 'world') {
                    _setSourceData('world', data);
                    _setSourceData('country-borders', _extractSharedBorders(data));
                    _setSourceData('country-labels', _labelPointsFromPolygons(data, 'name'));
                }
                if (key === 'provinces') {
                    _setSourceData('provinces', data);
                    _setSourceData('province-borders', _extractSharedBorders(data));
                    _setSourceData('province-labels', _labelPointsFromPolygons(data, 'name'));
                }
                if (key === 'admin1') {
                    _setSourceData('admin1', _admin1Gj);
                    _setSourceData('admin1-borders', _extractSharedBorders(_admin1Gj));
                    _setSourceData('admin1-labels', _labelPointsFromPolygons(_admin1Gj, 'name'));
                }
                if (key === 'lakes') _setSourceData('lakes', _lakesGj);
                if (key === 'rivers') _setSourceData('rivers', _riversGj);
                _applyLayerVisibility();
            }
        }).catch(() => { /* optional */ })
    ));
}

/** 将 pacific 偏移 GeoJSON 还原为标准经度（近似；用于 admin1/lakes/rivers） */
function _fromLonPacific(lon) {
    const CUT = -30;
    const SHIFT = 150;
    // toPacific: lon < CUT ? lon + (360-SHIFT) : lon - SHIFT
    // 亚洲侧约在 [-180,-30] 映射区：lonP = lon - 150 ∈ [-330,-180]∪… 实际落在左侧
    // 经验：lonP > 0 多为美洲（原 lon = lonP - 210?）；lonP <= 0 多为欧亚（lon = lonP + 150）
    if (lon > 30) return lon - (360 - SHIFT); // 美洲段
    return lon + SHIFT;
}

function _unpacificCoords(coords) {
    if (!coords) return coords;
    if (typeof coords[0] === 'number') {
        return [_fromLonPacific(coords[0]), coords[1]];
    }
    return coords.map(_unpacificCoords);
}

function _unpacificGeoJson(gj) {
    if (!gj || !gj.features) return gj;
    return {
        type: 'FeatureCollection',
        features: gj.features.map(ft => ({
            type: 'Feature',
            properties: ft.properties || {},
            geometry: ft.geometry ? {
                type: ft.geometry.type,
                coordinates: _unpacificCoords(ft.geometry.coordinates)
            } : null
        })).filter(f => f.geometry)
    };
}

// ── Map 初始化 ───────────────────────────────────────────

function _initMapCharts() { _initMap(); }

function _initMap() {
    _syncPanelPosition();
    if (_mlMap || typeof maplibregl === 'undefined') {
        if (_mlMap) { _mlMap.resize(); updateMapAlert(); }
        if (typeof maplibregl === 'undefined') console.error('[地图] maplibre-gl 未加载');
        return;
    }
    const mapEl = document.getElementById('map-world');
    if (!mapEl) return;

    const view = _mapView === 'china' ? _ML_CHINA : _ML_WORLD;
    const pal = _palette();

    _mlMap = new maplibregl.Map({
        container: mapEl,
        style: _buildStyle(pal),
        center: view.center,
        zoom: view.zoom,
        minZoom: 1,
        maxZoom: 14,
        attributionControl: false,
        dragRotate: false,
        pitchWithRotate: false,
    });
    _mlMap.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

    _mlMap.on('load', () => {
        _mlReady = true;
        if (_worldGj) {
            _setSourceData('world', _worldGj);
            _setSourceData('country-borders', _extractSharedBorders(_worldGj));
            _setSourceData('country-labels', _labelPointsFromPolygons(_worldGj, 'name'));
        }
        if (_provinceGj) {
            _setSourceData('provinces', _provinceGj);
            _setSourceData('province-borders', _extractSharedBorders(_provinceGj));
            _setSourceData('province-labels', _labelPointsFromPolygons(_provinceGj, 'name'));
        }
        if (_admin1Gj) {
            _setSourceData('admin1', _admin1Gj);
            _setSourceData('admin1-borders', _extractSharedBorders(_admin1Gj));
            _setSourceData('admin1-labels', _labelPointsFromPolygons(_admin1Gj, 'name'));
        }
        if (_lakesGj) _setSourceData('lakes', _lakesGj);
        if (_riversGj) _setSourceData('rivers', _riversGj);
        _ensureRadarLayer();
        _applyPaletteToMap();
        _applyLayerVisibility();
        _ensureBlinkTimer();
        updateMapAlert();
        _initWxLayerPanel();
        _scheduleWxRefresh();
        _applyWxLayer(_wxLayerId);
    });

    _mlMap.on('click', 'airports-inner', (e) => {
        const f = e.features && e.features[0];
        const code = f && f.properties && f.properties.code;
        if (code && typeof showAirportDetail === 'function') showAirportDetail(code);
    });
    _mlMap.on('mouseenter', 'airports-inner', () => { _mlMap.getCanvas().style.cursor = 'pointer'; });
    _mlMap.on('mouseleave', 'airports-inner', () => { _mlMap.getCanvas().style.cursor = ''; });

    // hover tip
    _mlMap.on('mousemove', 'airports-inner', (e) => {
        const f = e.features && e.features[0];
        const tip = document.getElementById('map-airport-tip');
        if (!f || !tip) return;
        tip.style.display = 'block';
        tip.style.left = (e.point.x + 14) + 'px';
        tip.style.top = (e.point.y + 14) + 'px';
        tip.innerHTML = _airportTipHtml(f.properties.code);
    });
    _mlMap.on('mouseleave', 'airports-inner', () => {
        const tip = document.getElementById('map-airport-tip');
        if (tip) tip.style.display = 'none';
    });

    _loadGeo().then(() => _loadMapStyleConfig());
}

function _destroyMap() {
    if (_wxRefreshTimer) {
        clearInterval(_wxRefreshTimer);
        _wxRefreshTimer = null;
    }
    if (_mlMap) {
        try { _mlMap.remove(); } catch (e) { /* noop */ }
        _mlMap = null;
    }
    _mlReady = false;
}

function _ensureBlinkTimer() {
    if (_blinkTimer) return;
    _blinkTimer = setInterval(() => {
        if (window._viewMode !== 'map' || !_mlMap) return;
        _blinkPhase = !_blinkPhase;
        updateMapAlert();
    }, 650);
    _ensureRippleLoop();
}

function _ensureRippleLoop() {
    if (_rippleRaf) return;
    const tick = (now) => {
        _rippleRaf = requestAnimationFrame(tick);
        if (window._viewMode !== 'map' || !_mlMap || !_mlReady) return;
        if (!_mlMap.getLayer('airports-ripple')) return;
        const t = (now % 1400) / 1400;
        const base = _markerSizes().outer / 2;
        _mlMap.setPaintProperty('airports-ripple', 'circle-radius', base * (1.15 + 1.8 * t));
        _mlMap.setPaintProperty('airports-ripple', 'circle-stroke-opacity', 0.9 * (1 - t));
    };
    _rippleRaf = requestAnimationFrame(tick);
}

function _radarRecord(code) {
    const pools = [].concat(_radarAlertCache.alerts || [], _radarAlertCache.observe || []);
    return pools.find(a => a.airport_4code === code) || null;
}

function _airportRecord(code) {
    const src = (typeof airportData !== 'undefined' && airportData) || [];
    return src.find(a => a.airport_4code === code) || null;
}

// ── 机场标记 ─────────────────────────────────────────────

function _buildAirportFc() {
    if (!_mapCoordCache) return _emptyFc();
    const margin = typeof getSelectedAlertMargin === 'function' ? getSelectedAlertMargin() : 2;
    const features = [];
    const seen = new Set();

    const pushAirport = (airport) => {
        if (!airport) return;
        const code = airport.airport_4code;
        if (!code || seen.has(code)) return;
        const coords = _mapCoordCache[code];
        if (!coords) return;
        seen.add(code);
        const marginResults = ((airport.computed_alerts || {})[`margin_${margin}`]) || {};
        const tafLevel = marginResults.taf_highest_alert || 'N';
        const metar = airport.metar_data && airport.metar_data[0];
        const metarLevel = (metar && metar.metar_warning) || 'N';
        const ringColor = _mapColor(metarLevel);
        const flashAlt = _flashAltColor();
        const shouldMetarFlash = !!(metar && (
            metar.operation_popup === 'Y' || metar.operation_popup === 'I'
            || metar.parking_popup === 'Y' || metar.parking_popup === 'I'
        ));
        const radarHit = !!(_radarBlinkCodes && _radarBlinkCodes.has(code));
        const radarRec = radarHit ? _radarRecord(code) : null;
        const radarLvl = radarRec ? (radarRec.alert_highest || 'Y') : null;
        const radarColor = radarLvl ? _mapColor(radarLvl) : flashAlt;

        let stroke = ringColor;
        let opacity = 0.85;
        if (shouldMetarFlash) {
            stroke = _blinkPhase ? ringColor : flashAlt;
            opacity = 0.95;
        }

        features.push({
            type: 'Feature',
            properties: {
                code,
                fillColor: _mapColor(tafLevel),
                ringColor: stroke,
                ringOpacity: opacity,
                radarRipple: radarHit ? 1 : 0,
                rippleColor: radarHit ? (_blinkPhase ? radarColor : flashAlt) : flashAlt,
            },
            geometry: { type: 'Point', coordinates: [coords.lon, coords.lat] }
        });
    };

    (filteredAirportData || []).forEach(pushAirport);
    // 强对流达标机场即使被实况告警筛选挡住，也要画出涟漪
    if (_radarBlinkCodes) {
        _radarBlinkCodes.forEach(code => {
            if (seen.has(code)) return;
            pushAirport(_airportRecord(code) || { airport_4code: code });
        });
    }
    return { type: 'FeatureCollection', features };
}

function updateMapAlert() {
    if (window._viewMode !== 'map') return;
    if (!_mlMap) {
        _initMap();
        return;
    }
    if (_mapCoordCache === null) {
        _fetchCoordsAndRender();
        return;
    }
    if (_mlReady) _setSourceData('airports', _buildAirportFc());
}
window.updateMapAlert = updateMapAlert;

function _fetchCoordsAndRender() {
    _prefetchFlightStatus();
    if (_mapCoordCache !== null) { updateMapAlert(); return; }
    const codes = (typeof airportData !== 'undefined' && airportData.length)
        ? airportData.map(a => a.airport_4code).join(',') : '';
    if (!codes) return;
    fetch(`/${currentTimeMode}/api/airport-coords/?codes=${encodeURIComponent(codes)}`, {
        headers: typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}
    })
        .then(r => r.json())
        .then(data => {
            if (data.coords) { _mapCoordCache = data.coords; updateMapAlert(); }
            if (data.error) alert(data.error);
            else if (!data.success) alert('获取机场坐标失败');
        })
        .catch(err => console.error('[地图告警] 坐标接口失败', err));
}

function _prefetchFlightStatus() {
    fetch(`/${currentTimeMode}/api/airport-flight-status/`, {
        headers: typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}
    })
        .then(r => r.json())
        .then(data => { if (data.success) _flightStatusCache = data.data; })
        .catch(() => {});
}

function _airportTipHtml(code) {
    const airport = filteredAirportData && filteredAirportData.find(a => a.airport_4code === code);
    if (!airport) return `<b>${code}</b>`;
    const metar = airport.metar_data && airport.metar_data[0];
    const taf = airport.taf_data && airport.taf_data[0];
    let html = `<div style="line-height:1.5;color:#c8dff0;font-size:12px;font-family:monospace">`;
    html += `<div style="font-weight:700;color:#7ecbff;margin-bottom:4px">${code}</div>`;
    if (metar && metar.metar_content) {
        html += `<div style="color:#90c8f0;font-size:11px;margin-bottom:2px">${metar.metar_content}</div>`;
    }
    if (taf && taf.taf_content) {
        html += `<div style="color:#78b0d8;font-size:11px">${String(taf.taf_content).slice(0, 180)}…</div>`;
    }
    html += `</div>`;
    return html;
}

// ── 气象图层（雷达 / 葵花红外·水汽·可见光，互斥）──────────
// 雷达：RainViewer raster；卫星：NASA GIBS Himawari AHI（水汽用气团合成，GIBS 无 Band8）

let _wxLayerId = 'radar'; // none|radar|sat_ir|sat_wv|sat_vis
let _wxTimeMs = 0;
let _wxTimeLayer = '';
let _wxRefreshTimer = null;
let _wxBusy = false;
const _WX_SRC = 'wx-overlay';
const _WX_LAYER = 'wx-overlay';

const _WX_GIBS = {
    sat_ir: {
        layer: 'Himawari_AHI_Band13_Clean_Infrared',
        matrix: 'GoogleMapsCompatible_Level6',
        maxzoom: 6,
        label: '卫星·红外',
    },
    sat_wv: {
        layer: 'Himawari_AHI_Air_Mass',
        matrix: 'GoogleMapsCompatible_Level6',
        maxzoom: 6,
        label: '卫星·水汽',
    },
    sat_vis: {
        layer: 'Himawari_AHI_Band3_Red_Visible_1km',
        matrix: 'GoogleMapsCompatible_Level7',
        maxzoom: 7,
        label: '卫星·可见光',
    },
};

function _fmtWxTime(ms) {
    if (!ms) return '';
    const d = new Date(ms);
    const utc = window.displayTimezone === 'UTC';
    const p = (n) => String(n).padStart(2, '0');
    const month = utc ? d.getUTCMonth() + 1 : d.getMonth() + 1;
    const day = utc ? d.getUTCDate() : d.getDate();
    let hh, mm, ss;
    if (utc) {
        hh = d.getUTCHours();
        mm = d.getUTCMinutes();
        ss = d.getUTCSeconds();
    } else {
        const parts = new Intl.DateTimeFormat('en-GB', {
            timeZone: 'Asia/Shanghai',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false,
        }).formatToParts(d);
        const get = (t) => (parts.find(x => x.type === t) || {}).value || '00';
        const dateParts = new Intl.DateTimeFormat('en-GB', {
            timeZone: 'Asia/Shanghai',
            month: '2-digit', day: '2-digit',
        }).formatToParts(d);
        const dm = (dateParts.find(x => x.type === 'month') || {}).value || p(month);
        const dd = (dateParts.find(x => x.type === 'day') || {}).value || p(day);
        return `${dm}-${dd} ${get('hour')}:${get('minute')}:${get('second')}`;
    }
    return `${p(month)}-${p(day)} ${p(hh)}:${p(mm)}:${p(ss)}`;
}

function _wxTimeSlot(layerId) {
    if (!layerId) return '';
    if (layerId.indexOf('sat_') === 0) return 'sat';
    return layerId;
}

function _setWxTime(layerId, ms) {
    _wxTimeLayer = layerId || '';
    _wxTimeMs = ms || 0;
    const slot = _wxTimeSlot(_wxTimeLayer);
    const text = !slot ? '' : (_wxTimeMs ? _fmtWxTime(_wxTimeMs) : '-- --:--:--');
    document.querySelectorAll('[data-wx-time]').forEach(el => {
        const on = !!slot && el.getAttribute('data-wx-time') === slot;
        el.textContent = on ? text : '';
        el.classList.toggle('is-show', on);
        el.classList.toggle('is-pending', on && !_wxTimeMs);
    });
}

function _wxTip(msg, ok) {
    const el = document.getElementById('map-wx-layer-tip');
    if (!el) return;
    if (!msg) {
        el.style.display = 'none';
        el.textContent = '';
        el.classList.remove('is-ok');
        return;
    }
    el.style.display = 'block';
    el.textContent = msg;
    el.classList.toggle('is-ok', !!ok);
}

function _wxUtcDate(offsetDays) {
    const d = new Date(Date.now() + (offsetDays || 0) * 86400000);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function _wxGibsTileUrl(cfg, timeStr) {
    return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${cfg.layer}/default/${timeStr}/${cfg.matrix}/{z}/{y}/{x}.png`;
}

function _wxRadarTileUrl(meta) {
    if (!meta || !meta.host || !meta.path) return null;
    const size = meta.tile_size || 256;
    const color = meta.color != null ? meta.color : 2;
    const smooth = meta.smooth != null ? meta.smooth : 0;
    const snow = meta.snow != null ? meta.snow : 0;
    return `${meta.host}${meta.path}/${size}/{z}/{x}/{y}/${color}/${smooth}_${snow}.png`;
}

function _wxBeforeId() {
    if (!_mlMap) return undefined;
    if (_mlMap.getLayer('boundary-state')) return 'boundary-state';
    if (_mlMap.getLayer('province-border')) return 'province-border';
    if (_mlMap.getLayer('country-border')) return 'country-border';
    return undefined;
}

function _ensureWxLayer() {
    if (!_mlMap || !_mlReady) return;
    if (_mlMap.getSource(_WX_SRC)) return;
    _mlMap.addSource(_WX_SRC, {
        type: 'raster',
        tiles: ['https://tilecache.rainviewer.com/v2/radar/0/256/{z}/{x}/{y}/2/0_0.png'],
        tileSize: 256,
        minzoom: 0,
        maxzoom: 7,
        attribution: 'RainViewer / NASA GIBS Himawari',
    });
    _mlMap.addLayer({
        id: _WX_LAYER,
        type: 'raster',
        source: _WX_SRC,
        paint: { 'raster-opacity': 0.78 },
        layout: { visibility: 'none' },
    }, _wxBeforeId());
}

let _wxTileUrl = '';

function _setWxTiles(tileUrl, maxzoom, visible) {
    if (!_mlMap || !_mlReady) return;
    const zoom = maxzoom != null ? maxzoom : 7;
    const layer = _mlMap.getLayer(_WX_LAYER);
    const src = _mlMap.getSource(_WX_SRC);
    if (layer && src && _wxTileUrl === tileUrl) {
        _mlMap.setLayoutProperty(_WX_LAYER, 'visibility', visible ? 'visible' : 'none');
        return;
    }
    _ensureWxLayer();
    // 地址变了才重建。每次拆掉再铺上会让整幅回波闪一下。
    const before = _wxBeforeId();
    if (_mlMap.getLayer(_WX_LAYER)) _mlMap.removeLayer(_WX_LAYER);
    if (_mlMap.getSource(_WX_SRC)) _mlMap.removeSource(_WX_SRC);
    _wxTileUrl = tileUrl || '';
    _mlMap.addSource(_WX_SRC, {
        type: 'raster',
        tiles: [tileUrl],
        tileSize: 256,
        minzoom: 0,
        maxzoom: zoom,
        attribution: 'RainViewer / NASA GIBS Himawari',
    });
    _mlMap.addLayer({
        id: _WX_LAYER,
        type: 'raster',
        source: _WX_SRC,
        paint: { 'raster-opacity': 0.78 },
        layout: { visibility: visible ? 'visible' : 'none' },
    }, before);
}

function _hideWxOverlay() {
    if (_mlMap && _mlMap.getLayer(_WX_LAYER)) {
        _mlMap.setLayoutProperty(_WX_LAYER, 'visibility', 'none');
    }
}

async function _probeTile(urlTemplate) {
    // 优先探测东亚瓦片（葵花覆盖区）；再试全球通用格点
    const samples = [
        [3, 6, 3],
        [2, 1, 1],
        [4, 12, 6],
    ];
    for (const [z, x, y] of samples) {
        const url = urlTemplate
            .replace('{z}', String(z))
            .replace('{x}', String(x))
            .replace('{y}', String(y));
        try {
            const res = await fetch(url, { method: 'GET', cache: 'no-store' });
            if (!res.ok) continue;
            const buf = await res.arrayBuffer();
            if (buf && buf.byteLength > 100) return true;
        } catch (e) { /* try next */ }
    }
    return false;
}

async function _loadRadarWx() {
    // 优先用告警任务帧，失败则拉 RainViewer 最新 past
    let meta = _radarOverlayMeta;
    const tryMeta = async (m) => {
        const tpl = _wxRadarTileUrl(m);
        if (!tpl) return false;
        const ok = await _probeTile(tpl);
        if (!ok) return false;
        if (_wxLayerId !== 'radar') return false;
        _setWxTiles(tpl, 7, true);
        _radarOverlayMeta = m;
        _radarFramePath = `${m.frame_time}|${m.path}`;
        return true;
    };
    if (meta && await tryMeta(meta)) {
        if (_wxLayerId !== 'radar') return;
        _wxTip('');
        _setWxTime('radar', (meta.frame_time || 0) * 1000);
        return;
    }
    if (_wxLayerId !== 'radar') return;
    try {
        const res = await fetch('https://api.rainviewer.com/public/weather-maps.json', { cache: 'no-store' });
        if (!res.ok) throw new Error('索引 HTTP ' + res.status);
        const data = await res.json();
        const past = (data.radar && data.radar.past) || [];
        if (!past.length) throw new Error('无雷达帧');
        const frame = past[past.length - 1];
        meta = {
            host: (data.host || 'https://tilecache.rainviewer.com').replace(/\/$/, ''),
            path: frame.path,
            frame_time: frame.time,
            z: 3,
            tile_size: 256,
            color: 2,
            smooth: 0,
            snow: 0,
        };
        if (_wxLayerId !== 'radar') return;
        if (!(await tryMeta(meta))) throw new Error('雷达瓦片不可用');
        if (_wxLayerId !== 'radar') return;
        _wxTip('');
        _setWxTime('radar', frame.time * 1000);
    } catch (e) {
        if (_wxLayerId !== 'radar') return;
        _hideWxOverlay();
        _setWxTime('radar', 0);
        _wxTip('雷达数据异常：' + (e.message || '加载失败'));
    }
}

async function _loadSatWx(kind) {
    const cfg = _WX_GIBS[kind];
    if (!cfg) {
        _wxTip('未知卫星通道');
        return;
    }
    const dates = [_wxUtcDate(0), _wxUtcDate(-1), _wxUtcDate(-2)];
    let lastErr = '';
    for (const day of dates) {
        const tpl = _wxGibsTileUrl(cfg, day);
        const ok = await _probeTile(tpl);
        if (ok) {
            if (_wxLayerId !== kind) return;
            _setWxTiles(tpl, cfg.maxzoom, true);
            _wxTip('');
            _setWxTime(kind, Date.parse(`${day}T00:00:00Z`));
            return;
        }
        lastErr = day;
    }
    if (_wxLayerId !== kind) return;
    _hideWxOverlay();
    _setWxTime(kind, 0);
    _wxTip('卫星数据异常：近几日瓦片不可用（试过 ' + lastErr + '）');
}

async function _applyWxLayer(id) {
    const next = id || 'none';
    _wxLayerId = next;
    if (next === 'none') {
        _wxTip('');
        _setWxTime('', 0);
        if (_mlMap && _mlReady) _hideWxOverlay();
        return;
    }
    if (_wxTimeLayer !== next) _setWxTime(next, 0);
    if (!_mlMap || !_mlReady) return;
    if (_wxBusy) return;
    _wxBusy = true;
    const requested = next;
    try {
        _wxTip('');
        if (requested === 'radar') await _loadRadarWx();
        else await _loadSatWx(requested);
    } finally {
        _wxBusy = false;
        if (_wxLayerId === 'none') {
            _hideWxOverlay();
            _setWxTime('', 0);
        } else if (_wxLayerId !== requested) {
            _applyWxLayer(_wxLayerId);
        }
    }
}

const _SAT_NAMES = { sat_ir: '红外', sat_wv: '水汽', sat_vis: '可见光' };

function _accessAllows(module, action) {
    if (typeof hasAccess !== 'function' || !window.__accessIdentity) return true;
    return hasAccess(module, action);
}

function _applyWxPermission() {
    const panel = document.getElementById('map-wx-layer-panel');
    if (!panel) return;
    const radarOn = _accessAllows('map_radar', 'display');
    const satOn = _accessAllows('map_satellite', 'display');
    const radarInput = panel.querySelector('input[data-wx="radar"]');
    const radarLabel = radarInput && radarInput.closest('label');
    if (radarLabel) radarLabel.style.display = radarOn ? '' : 'none';
    const radarTime = panel.querySelector('[data-wx-time="radar"]');
    if (radarTime) radarTime.style.display = radarOn ? '' : 'none';
    const satBlock = document.getElementById('map-wx-sat-block');
    if (satBlock) satBlock.style.display = satOn ? '' : 'none';
    const satTime = panel.querySelector('[data-wx-time="sat"]');
    if (satTime) satTime.style.display = satOn ? '' : 'none';
    panel.style.display = (radarOn || satOn) ? '' : 'none';
    if (_wxLayerId === 'radar' && !radarOn) _wxLayerId = 'none';
    if (_wxLayerId && String(_wxLayerId).indexOf('sat_') === 0 && !satOn) _wxLayerId = 'none';
}

function _syncWxPanelUI(layerId) {
    const panel = document.getElementById('map-wx-layer-panel');
    if (!panel) return;
    const isSat = !!(layerId && layerId.indexOf('sat_') === 0);
    const radar = panel.querySelector('input[data-wx="radar"]');
    if (radar) radar.checked = layerId === 'radar';
    const satBtn = panel.querySelector('[data-wx="sat-toggle"]');
    if (satBtn) satBtn.classList.toggle('is-on', isSat);
    const label = panel.querySelector('.map-wx-sat-label');
    if (label) label.textContent = isSat ? `卫星数据>>${_SAT_NAMES[layerId] || ''}` : '卫星云图';
    panel.querySelectorAll('[data-wx="sat_ir"], [data-wx="sat_wv"], [data-wx="sat_vis"]').forEach(btn => {
        btn.classList.toggle('is-on', btn.getAttribute('data-wx') === layerId);
    });
}

function _initWxLayerPanel() {
    const panel = document.getElementById('map-wx-layer-panel');
    _applyWxPermission();
    if (!panel || panel.dataset.bound) {
        if (panel) _syncWxPanelUI(_wxLayerId);
        return;
    }
    panel.dataset.bound = '1';

    const applyAndSave = (id) => {
        localStorage.setItem('mtws_wx_layer', id);
        _syncWxPanelUI(id);
        _applyWxLayer(id);
    };

    const radarBtn = panel.querySelector('input[data-wx="radar"]');
    if (radarBtn) {
        radarBtn.addEventListener('change', () => {
            applyAndSave(radarBtn.checked ? 'radar' : 'none');
        });
    }
    const satToggle = panel.querySelector('[data-wx="sat-toggle"]');
    const satMenu = document.getElementById('map-wx-sat-sub');
    if (satToggle && satMenu) {
        satToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            satMenu.hidden = !satMenu.hidden;
        });
        document.addEventListener('click', (e) => {
            if (!satMenu.hidden && !panel.contains(e.target)) satMenu.hidden = true;
        });
    }
    panel.querySelectorAll('[data-wx="sat_ir"], [data-wx="sat_wv"], [data-wx="sat_vis"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.getAttribute('data-wx');
            if (satMenu) satMenu.hidden = true;
            applyAndSave(_wxLayerId === id ? 'none' : id);
        });
    });

    let saved = localStorage.getItem('mtws_wx_layer');
    if (!saved || !['none', 'radar', 'sat_ir', 'sat_wv', 'sat_vis'].includes(saved)) {
        saved = 'radar';
    }
    _wxLayerId = saved;
    _applyWxPermission();
    _syncWxPanelUI(_wxLayerId);
}

function _scheduleWxRefresh() {
    if (_wxRefreshTimer) clearInterval(_wxRefreshTimer);
    _wxRefreshTimer = setInterval(() => {
        if (window._viewMode !== 'map') return;
        if (_wxLayerId && _wxLayerId !== 'none') _applyWxLayer(_wxLayerId);
    }, 5 * 60 * 1000);
}

// 兼容旧调用名
function _ensureRadarLayer() { _ensureWxLayer(); }

function _applyRadarOverlay(meta) {
    if (!meta) return;
    _radarOverlayMeta = meta;
    if (_wxLayerId === 'radar' && _mlReady) _applyWxLayer('radar');
}

function _fetchRainViewerOverlayFallback() {
    if (_wxLayerId === 'radar') _applyWxLayer('radar');
}

// ── 雷达告警浮层 ─────────────────────────────────────────

function _radarCodeColor(level) {
    if (!level || level === 'N') return '';
    if (typeof getAlertColorHex === 'function') return getAlertColorHex(level);
    return ({ R: '#e74c3c', Y: '#f39c12', G: '#27ae60' })[level] || '';
}

function _radarUnhandledCount(alerts) {
    return (alerts || []).filter(a => !a.handled).length;
}

function _radarHandleButton(item) {
    const code = item.airport_4code || '';
    const handled = !!item.handled;
    const level = item.alert_highest || 'Y';
    const color = _radarCodeColor(level) || '#e74c3c';
    const bg = handled ? '#6d7b8a' : color;
    const fg = handled ? '#e6edf3' : (level === 'Y' ? '#1b2838' : '#fff');
    const levelCls = !handled && level === 'Y' ? ' level-y' : '';
    return `<button type="button" class="radar-handle-btn${handled ? ' is-handled' : ''}${levelCls}" data-code="${code}" style="--handle-bg:${bg};color:${fg}">${handled ? '已处理' : '未处理'}</button>`;
}

function _radarAlertRow(item, withHandle) {
    const color = _radarCodeColor(item.alert_highest);
    const codeStyle = color ? ` style="color:${color}"` : '';
    const rowStyle = color ? ` style="--alert:${color}"` : '';
    const code = item.airport_4code || '';
    const handle = withHandle ? _radarHandleButton(item) : '';
    return `<div class="radar-alert-row"${rowStyle}><div class="radar-alert-code" data-code="${code}" title="查看周边200公里雷达回波"${codeStyle}>${code}</div>${handle}</div>`;
}

function _renderAlarmList(list) {
    if (!list || !list.length) return '<div class="radar-alert-empty">暂无告警</div>';
    const scroll = list.length > _RADAR_VISIBLE_ROWS ? ' is-scroll' : '';
    return `<div class="radar-alert-alarm-list${scroll}">${list.map(item => _radarAlertRow(item, true)).join('')}</div>`;
}

function _renderObserveList(list) {
    if (!list || !list.length) return '<div class="radar-alert-empty">暂无观察项</div>';
    const scroll = list.length > _RADAR_VISIBLE_ROWS * 2 ? ' is-scroll' : '';
    return `<div class="radar-alert-observe-list${scroll}">${list.map(item => _radarAlertRow(item, false)).join('')}</div>`;
}

function _radarVisibleItems() {
    const alarms = (_radarAlertCache.alerts || []).map(a => Object.assign({ kind: 'alarm' }, a));
    if (_radarListMode !== 'observe') return alarms;
    const observes = (_radarAlertCache.observe || []).map(a => Object.assign({ kind: 'observe' }, a));
    return alarms.concat(observes);
}

function _syncRadarBlink() {
    _radarBlinkCodes = new Set(_radarVisibleItems().map(a => a.airport_4code));
}

function _renderRadarList() {
    const body = document.getElementById('radar-alert-float-body');
    if (!body) return;
    const alarms = (_radarAlertCache.alerts || []).map(a => Object.assign({ kind: 'alarm' }, a));
    const observes = _radarListMode === 'observe'
        ? (_radarAlertCache.observe || []).map(a => Object.assign({ kind: 'observe' }, a))
        : [];
    const showObserve = _radarListMode === 'observe';
    let html = '<div class="radar-alert-section">告警项</div>';
    html += _renderAlarmList(alarms);
    if (showObserve) {
        html += `<div class="radar-alert-observe-block"><div class="radar-alert-section">观察项</div>${_renderObserveList(observes)}</div>`;
    }
    body.innerHTML = html;
    _syncRadarBlink();
}

function _applyRadarFloat(data) {
    _radarAlertCache = data || { alerts: [], observe: [], watch: [] };
    const panel = document.getElementById('radar-alert-float');
    const tip = document.getElementById('radar-alert-rate-tip');
    if (!panel) return;
    if (!_accessAllows('map_radar', 'display')) {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = (window._viewMode === 'map') ? 'flex' : 'none';
    _renderRadarList();
    const st = data.status || {};
    const rl = st.rate_limiter || {};
    if (tip) {
        if (rl.rate_limited || st.state === 'rate_limited') {
            tip.textContent = `API限流中，排队 ${rl.queued || 0}，约 ${rl.paused_seconds || '?'}s`;
            tip.classList.add('radar-alert-rate-warn');
        } else if (st.state === 'running') {
            tip.textContent = `计算中 ${st.phase || ''} ${rl.window_count || 0}/${rl.max_per_minute || 80}`;
            tip.classList.remove('radar-alert-rate-warn');
        } else {
            tip.textContent = rl.window_count != null
                ? `请求 ${rl.window_count}/${rl.max_per_minute || 80}` : '';
            tip.classList.remove('radar-alert-rate-warn');
        }
    }
    if (data.overlay) {
        const nextSig = `${data.overlay.frame_time}|${data.overlay.path}|${data.overlay.host || ''}`;
        const changed = nextSig !== _radarFramePath;
        _radarOverlayMeta = data.overlay;
        if (changed && _wxLayerId === 'radar') _applyWxLayer('radar');
    }
    if (typeof window.updateRadarAlarmNavBadge === 'function') {
        window.updateRadarAlarmNavBadge(_radarUnhandledCount(data.alerts));
    }
    updateMapAlert();
}

const _FLIGHT_HOURS_KEY = 'mtws_flight_future_hours';
let _radarScopePoll = null;

function _mapFlightScope() {
    const picked = document.querySelector('input[name="map-flight-scope"]:checked');
    return picked ? picked.value : 'has_flight';
}

function _readFlightHours() {
    const raw = localStorage.getItem(_FLIGHT_HOURS_KEY);
    const n = parseInt(raw == null || raw === '' ? '2' : raw, 10);
    if (!Number.isFinite(n)) return 2;
    return Math.max(0, Math.min(9, n));
}

function _mapFutureHours() {
    const input = document.getElementById('map-future-hours');
    const n = input ? parseInt(input.value, 10) : _readFlightHours();
    if (!Number.isFinite(n)) return 2;
    return Math.max(0, Math.min(9, n));
}

function _syncMapHoursVisibility() {
    const label = document.getElementById('map-hours-label');
    if (label) label.classList.toggle('is-on', _mapFlightScope() === 'recent2h');
}

function _radarListQuery() {
    const scope = encodeURIComponent(_mapFlightScope());
    return `scope=${scope}&future_hours=${_mapFutureHours()}`;
}

window.addEventListener('mtws-carriers-changed', () => {
    _prefetchFlightStatus();
    updateMapAlert();
    _refreshRadarAlerts();
});

function _refreshRadarAlerts() {
    if (typeof currentTimeMode === 'undefined') return;
    if (!_accessAllows('map_radar', 'display')) {
        const panel = document.getElementById('radar-alert-float');
        if (panel) panel.style.display = 'none';
        return;
    }
    fetch(`/${currentTimeMode}/api/radar/alerts/?${_radarListQuery()}`, {
        headers: typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}
    })
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            _applyRadarFloat(data);
            const running = data.status && data.status.state === 'running';
            if (running) _scheduleRadarPoll();
            else _stopRadarPoll();
        })
        .catch(err => console.warn('[雷达告警] 拉取失败', err));
}

function _stopRadarPoll() {
    if (_radarScopePoll) {
        clearTimeout(_radarScopePoll);
        _radarScopePoll = null;
    }
}

function _scheduleRadarPoll() {
    if (_radarScopePoll) return;
    const tick = () => {
        _radarScopePoll = null;
        if (window._viewMode !== 'map') return;
        _refreshRadarAlerts();
    };
    _radarScopePoll = setTimeout(tick, 4000);
}

function _runRadarForCurrentScope(hideStale) {
    if (typeof currentTimeMode === 'undefined') return;
    const hours = _mapFutureHours();
    localStorage.setItem(_FLIGHT_HOURS_KEY, String(hours));
    sessionStorage.setItem('mtws_map_flight_scope', _mapFlightScope());
    _syncMapHoursVisibility();
    const trendHours = document.getElementById('trend-future-hours');
    if (trendHours) trendHours.value = String(hours);
    if (!_accessAllows('map_radar', 'activate')) return;
    return fetch(`/${currentTimeMode}/api/radar/run/`, {
        method: 'POST',
        headers: {
            ...(typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}),
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            force: false,
            scope: _mapFlightScope(),
            future_hours: hours,
            hide_stale: !!hideStale
        })
    })
        .then(r => r.json())
        .then(() => _refreshRadarAlerts())
        .catch(err => console.warn('[雷达告警] 触发失败', err));
}

function _bindMapFlightScope() {
    const panel = document.getElementById('map-alert-panel');
    if (!panel || panel.dataset.flightScopeBound) return;
    panel.dataset.flightScopeBound = '1';
    const stored = sessionStorage.getItem('mtws_map_flight_scope');
    if (stored) {
        const radio = panel.querySelector(`input[name="map-flight-scope"][value="${stored}"]`);
        if (radio) radio.checked = true;
    }
    const hoursInput = document.getElementById('map-future-hours');
    if (hoursInput) hoursInput.value = String(_readFlightHours());
    _syncMapHoursVisibility();
    panel.querySelectorAll('input[name="map-flight-scope"]').forEach((el) => {
        el.addEventListener('change', () => _runRadarForCurrentScope(true));
    });
    if (hoursInput) {
        hoursInput.addEventListener('change', () => {
            hoursInput.value = String(_mapFutureHours());
            _runRadarForCurrentScope(true);
        });
    }
}

function _runRadarAlertFromFloat() {
    const btn = document.getElementById('radar-alert-run-btn');
    if (btn) btn.disabled = true;
    const done = () => { if (btn) btn.disabled = false; };
    try {
        const pending = _runRadarForCurrentScope(false);
        if (pending && typeof pending.finally === 'function') pending.finally(done);
        else done();
    } catch (err) {
        done();
    }
}

function _markRadarHandled(btn) {
    if (!btn || btn.classList.contains('is-handled') || btn.disabled) return;
    if (typeof hasAccess === 'function' && window.__accessIdentity && !hasAccess('map_radar', 'write')) {
        alert('当前角色无雷达告警写入权限，处理结果不会保存，告警不会消除');
        return;
    }
    const code = btn.getAttribute('data-code');
    if (!code || typeof currentTimeMode === 'undefined') return;
    btn.disabled = true;
    fetch(`/${currentTimeMode}/api/radar/alerts/handle/`, {
        method: 'POST',
        headers: {
            ...(typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}),
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ airport_4code: code })
    })
        .then(r => r.json())
        .then(data => {
            if (!data.success) throw new Error(data.error || '处理失败');
            (_radarAlertCache.alerts || []).forEach(item => {
                if (item.airport_4code === code) item.handled = true;
            });
            _renderRadarList();
            if (typeof window.updateRadarAlarmNavBadge === 'function') {
                window.updateRadarAlarmNavBadge(_radarUnhandledCount(_radarAlertCache.alerts));
            }
        })
        .catch(err => {
            btn.disabled = false;
            alert(err.message || '处理失败');
        });
}

const _RADAR_FLOAT_POS_KEY = 'mtws_radar_float_pos';

function _radarFloatParent(panel) {
    return panel.offsetParent || panel.parentElement;
}

function _clampRadarFloat(panel, left, top) {
    const parent = _radarFloatParent(panel);
    const maxL = Math.max(0, (parent ? parent.clientWidth : 0) - panel.offsetWidth);
    const maxT = Math.max(0, (parent ? parent.clientHeight : 0) - panel.offsetHeight);
    return {
        left: Math.min(Math.max(0, left), maxL),
        top: Math.min(Math.max(0, top), maxT),
    };
}

function _pinRadarFloat(panel, left, top) {
    const pos = _clampRadarFloat(panel, left, top);
    panel.style.left = pos.left + 'px';
    panel.style.top = pos.top + 'px';
    panel.style.right = 'auto';
    panel.style.transform = 'none';
    return pos;
}

function _restoreRadarFloatPos(panel) {
    let saved = null;
    try {
        saved = JSON.parse(localStorage.getItem(_RADAR_FLOAT_POS_KEY) || '');
    } catch (e) {
        saved = null;
    }
    if (!saved || !Number.isFinite(saved.left) || !Number.isFinite(saved.top)) return;
    _pinRadarFloat(panel, saved.left, saved.top);
}

function _initRadarAlertFloat() {
    const drag = document.getElementById('radar-alert-float-drag');
    const panel = document.getElementById('radar-alert-float');
    if (panel) _restoreRadarFloatPos(panel);
    if (drag && panel && !panel.dataset.dragBound) {
        panel.dataset.dragBound = '1';
        let ox = 0, oy = 0, parentLeft = 0, parentTop = 0, dragging = false;
        drag.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            const parent = _radarFloatParent(panel);
            if (!parent) return;
            dragging = true;
            const r = panel.getBoundingClientRect();
            const pr = parent.getBoundingClientRect();
            ox = e.clientX - r.left;
            oy = e.clientY - r.top;
            parentLeft = pr.left;
            parentTop = pr.top;
            _pinRadarFloat(panel, r.left - pr.left, r.top - pr.top);
            e.preventDefault();
        });
        window.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            _pinRadarFloat(panel, e.clientX - ox - parentLeft, e.clientY - oy - parentTop);
        });
        window.addEventListener('mouseup', () => {
            if (!dragging) return;
            dragging = false;
            localStorage.setItem(_RADAR_FLOAT_POS_KEY, JSON.stringify({
                left: parseFloat(panel.style.left),
                top: parseFloat(panel.style.top),
            }));
        });
    }
    const runBtn = document.getElementById('radar-alert-run-btn');
    if (runBtn && !runBtn.dataset.bound) {
        runBtn.dataset.bound = '1';
        runBtn.addEventListener('click', _runRadarAlertFromFloat);
    }
    const modeBox = document.getElementById('radar-alert-mode');
    if (modeBox && !modeBox.dataset.bound) {
        modeBox.dataset.bound = '1';
        modeBox.addEventListener('mousedown', (e) => e.stopPropagation());
        const savedMode = localStorage.getItem('mtws_radar_list_mode');
        _radarListMode = savedMode === 'observe' ? 'observe' : 'alarm';
        const observeBtn = modeBox.querySelector('button[data-mode="observe"]');
        if (observeBtn) {
            observeBtn.classList.toggle('is-on', _radarListMode === 'observe');
            observeBtn.addEventListener('click', () => {
                _radarListMode = _radarListMode === 'observe' ? 'alarm' : 'observe';
                localStorage.setItem('mtws_radar_list_mode', _radarListMode);
                observeBtn.classList.toggle('is-on', _radarListMode === 'observe');
                _renderRadarList();
                updateMapAlert();
            });
        }
    }
    const float = document.getElementById('radar-alert-float');
    if (float && !float.dataset.echoBound) {
        float.dataset.echoBound = '1';
        float.addEventListener('click', (e) => {
            const handleBtn = e.target.closest('.radar-handle-btn');
            if (handleBtn) {
                e.preventDefault();
                e.stopPropagation();
                _markRadarHandled(handleBtn);
                return;
            }
            const codeEl = e.target.closest('.radar-alert-code');
            if (!codeEl) return;
            const code = codeEl.getAttribute('data-code');
            if (code) openRadarEcho(code);
        });
    }
    if (!_radarPollTimer) {
        _radarPollTimer = setInterval(() => {
            if (window._viewMode === 'map') _refreshRadarAlerts();
        }, 60000);
    }
}

const _echoByCode = new Map();
let _echoZ = 25000;
let _echoSlot = 0;

function _raiseEcho(modal) {
    const open = document.querySelectorAll('.radar-echo-modal');
    if (_echoZ >= 28900) {
        const nodes = Array.from(open).sort((a, b) =>
            (parseInt(a.style.zIndex, 10) || 0) - (parseInt(b.style.zIndex, 10) || 0));
        nodes.forEach((n, i) => { n.style.zIndex = String(25000 + i); });
        _echoZ = 25000 + nodes.length;
    }
    _echoZ += 1;
    modal.style.zIndex = String(_echoZ);
}

function _placeEcho(modal) {
    const step = 46;
    const i = _echoSlot % 12;
    _echoSlot += 1;
    const col = i % 4;
    const row = Math.floor(i / 4);
    const left = 56 + col * step + row * 18;
    const top = 72 + col * 36 + row * 52;
    modal.style.left = left + 'px';
    modal.style.top = top + 'px';
}

function _bindEchoDrag(modal) {
    const head = modal.querySelector('.radar-echo-head');
    if (!head) return;
    head.addEventListener('mousedown', (e) => {
        if (e.button !== 0 || e.target.closest('.radar-echo-close')) return;
        _raiseEcho(modal);
        const rect = modal.getBoundingClientRect();
        const ox = e.clientX - rect.left;
        const oy = e.clientY - rect.top;
        const onMove = (ev) => {
            const maxL = Math.max(0, window.innerWidth - 48);
            const maxT = Math.max(0, window.innerHeight - 36);
            modal.style.left = Math.max(0, Math.min(maxL, ev.clientX - ox)) + 'px';
            modal.style.top = Math.max(0, Math.min(maxT, ev.clientY - oy)) + 'px';
        };
        const onUp = () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        e.preventDefault();
    });
}

function _createEchoPopup(code) {
    const modal = document.createElement('div');
    modal.className = 'radar-echo-modal';
    modal.setAttribute('role', 'dialog');
    modal.dataset.code = code;
    modal.innerHTML =
        '<div class="radar-echo-head"><span class="radar-echo-title"></span>' +
        '<button type="button" class="radar-echo-close" aria-label="关闭">×</button></div>' +
        '<div class="radar-echo-body"></div>';
    const title = modal.querySelector('.radar-echo-title');
    if (title) title.textContent = `${code} 周边 200 公里雷达回波`;
    const rec = { code, el: modal, token: 1, timer: 0 };
    modal.querySelector('.radar-echo-close').addEventListener('click', (e) => {
        e.stopPropagation();
        _closeEchoPopup(rec);
    });
    modal.addEventListener('mousedown', () => _raiseEcho(modal));
    _bindEchoDrag(modal);
    _placeEcho(modal);
    _raiseEcho(modal);
    document.body.appendChild(modal);
    _echoByCode.set(code, rec);
    return rec;
}

function _closeEchoPopup(rec) {
    if (!rec) return;
    rec.token += 1;
    if (rec.timer) {
        clearTimeout(rec.timer);
        rec.timer = 0;
    }
    if (rec.el && rec.el.parentNode) rec.el.remove();
    if (_echoByCode.get(rec.code) === rec) _echoByCode.delete(rec.code);
}

function closeRadarEcho() {
    Array.from(_echoByCode.values()).forEach(_closeEchoPopup);
}

function _echoWaitText(seconds) {
    const n = Math.max(1, Math.ceil(seconds));
    return `雷达访问已达每分钟上限，约 ${n} 秒后自动显示`;
}

function _showEchoMessage(modal, text, waiting) {
    const body = modal.querySelector('.radar-echo-body');
    if (!body) return;
    body.innerHTML = `<div class="radar-echo-wait${waiting ? ' is-wait' : ''}"></div>`;
    body.querySelector('.radar-echo-wait').textContent = text;
}

function _drawEchoCanvas(body, data, rec) {
    const img = new Image();
    img.onload = () => {
        if (rec.token !== data._token) return;
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        canvas.className = 'radar-echo-canvas';
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#0c1520';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        const cx = Number(data.center_x) || canvas.width / 2;
        const cy = Number(data.center_y) || canvas.height / 2;
        const pxPerKm = Number(data.px_per_km) || 0;
        const rings = (data.rings_km && data.rings_km.length) ? data.rings_km : [50, 100, 150, 200];
        ctx.font = '12px sans-serif';
        ctx.textBaseline = 'middle';
        rings.forEach((km) => {
            const r = km * pxPerKm;
            if (!(r > 1)) return;
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(0,0,0,0.7)';
            ctx.lineWidth = 3;
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(255,255,255,0.95)';
            ctx.lineWidth = 1.25;
            ctx.stroke();
            const label = `${km}km`;
            const lx = cx + 6;
            const ly = cy - r + 12;
            ctx.lineWidth = 3;
            ctx.strokeStyle = 'rgba(0,0,0,0.75)';
            ctx.strokeText(label, lx, ly);
            ctx.fillStyle = '#fff';
            ctx.fillText(label, lx, ly);
        });
        ctx.beginPath();
        ctx.arc(cx, cy, 3, 0, Math.PI * 2);
        ctx.fillStyle = '#fff';
        ctx.fill();
        ctx.strokeStyle = '#111';
        ctx.lineWidth = 1;
        ctx.stroke();
        body.innerHTML = '';
        body.appendChild(canvas);
    };
    img.onerror = () => {
        if (rec.token !== data._token) return;
        body.innerHTML = '<div class="radar-echo-wait">雷达回波图片无法显示</div>';
    };
    img.src = data.image;
}

function _armEchoWait(rec, seconds) {
    const token = rec.token;
    const until = Date.now() + Math.max(0.5, seconds) * 1000;
    const tick = () => {
        if (rec.token !== token) return;
        const left = Math.max(0, (until - Date.now()) / 1000);
        _showEchoMessage(rec.el, _echoWaitText(left), true);
        if (left <= 0) {
            rec.timer = 0;
            _loadRadarEcho(rec);
            return;
        }
        rec.timer = setTimeout(tick, 250);
    };
    tick();
}

function _loadRadarEcho(rec) {
    if (typeof currentTimeMode === 'undefined') return;
    const token = rec.token;
    _showEchoMessage(rec.el, '正在获取雷达回波…', false);
    const headers = typeof getRequestHeaders === 'function' ? getRequestHeaders() : {};
    fetch(`/${currentTimeMode}/api/radar/echo/?code=${encodeURIComponent(rec.code)}`, { headers })
        .then(r => r.json())
        .then(data => {
            if (rec.token !== token) return;
            if (!data || !data.success) {
                _showEchoMessage(rec.el, (data && data.error) || '获取雷达回波失败', false);
                return;
            }
            if (data.waiting) {
                _armEchoWait(rec, Number(data.retry_after) || 1);
                return;
            }
            const body = rec.el.querySelector('.radar-echo-body');
            if (body) _drawEchoCanvas(body, Object.assign({ _token: token }, data), rec);
        })
        .catch(() => {
            if (rec.token !== token) return;
            _showEchoMessage(rec.el, '获取雷达回波失败', false);
        });
}

function openRadarEcho(code) {
    if (!code || !_accessAllows('map_radar', 'display')) return;
    const existing = _echoByCode.get(code);
    if (existing && existing.el.isConnected) {
        _raiseEcho(existing.el);
        return;
    }
    const rec = _createEchoPopup(code);
    _loadRadarEcho(rec);
}
window.closeRadarEcho = closeRadarEcho;
window.openRadarEcho = openRadarEcho;

function initMapAlertState() {
    const savedView = localStorage.getItem('mtws_map_view');
    _mapView = savedView === 'world' ? 'world' : 'china';
    const mapViewToggle = document.getElementById('map-view-toggle-input');
    if (mapViewToggle) mapViewToggle.checked = (_mapView === 'world');
    _initWxLayerPanel();
    _bindMapFlightScope();
    _initRadarAlertFloat();
    _refreshRadarAlerts();
}
window.initMapAlertState = initMapAlertState;
window.switchViewMode = switchViewMode;

// ── 事件 ─────────────────────────────────────────────────

let _resizeTimer = null;
window.addEventListener('resize', () => {
    if (_resizeTimer) clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(() => {
        if (window._viewMode === 'map') {
            _syncPanelPosition();
            if (_mlMap) _mlMap.resize();
        }
    }, 100);
});

const _viewModeToggle = document.getElementById('view-mode-toggle-input');
if (_viewModeToggle) {
    _viewModeToggle.addEventListener('change', () => {
        switchViewMode(_viewModeToggle.checked ? 'map' : 'list');
    });
}
const _mapViewToggle = document.getElementById('map-view-toggle-input');
if (_mapViewToggle) {
    _mapViewToggle.addEventListener('change', () => {
        _switchMapView(_mapViewToggle.checked ? 'world' : 'china');
    });
}
const _tzToggle = document.getElementById('timezone-toggle-input');
if (_tzToggle) {
    _tzToggle.addEventListener('change', () => {
        if (_wxTimeMs && _wxTimeLayer) _setWxTime(_wxTimeLayer, _wxTimeMs);
        if (window._viewMode === 'map') setTimeout(_syncPanelPosition, 80);
    });
}
