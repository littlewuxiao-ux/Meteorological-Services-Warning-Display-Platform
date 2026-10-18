// ========================================
// 地图告警功能
// 依赖 main.js 中的全局变量/函数：
//   filteredAirportData, airportData, currentTimeMode
//   getSelectedAlertMargin(), getAlertColor(), getRequestHeaders(), handleFetchResponse()
// ========================================

// 全局视图模式：'list' | 'map'，由 switchViewMode 维护，main.js 读取
// 本模块按需注入，注入时视图导航可能已经定了模式，不要覆盖
window._viewMode   = window._viewMode || 'list';

let _mapView       = 'china';   // 'china' | 'world'
let _mapCoordCache = null;      // null = 未获取；{} = 已获取（可能为空）
let _mapChart      = null;
let _worldGeoReady = false;
let _worldGeoJson  = null;
let _flightStatusCache = null;  // { airport_4code: { ...5项实况 } }
let _mapStyle = null;
let _mapPalette = null;
let _borderWidths = { country: 1.35, province: 0.75, admin1: 0.55 };
let _extraGeoReady = { provinces: false, admin1: false, lakes: false, rivers: false };
let _provinceGeoJson = null;
let _provinceBorderLines = [];
let _provinceCentroids = [];
let _admin1BorderLines = [];
let _admin1Centroids = [];
let _lakeBorderLines = [];
let _riverLineData = [];
let _blinkPhase = false;
let _blinkTimer = null;

// 太平洋中心世界地图参数（截断线 30°W，中心 150°E）
const _PACIFIC_CUT   = -30;
const _PACIFIC_SHIFT = 150;

/** 将原始 WGS84 经度转换为 world_pacific.json 坐标系 */
function _toLonPacific(lon) {
    return lon < _PACIFIC_CUT ? lon + (360 - _PACIFIC_SHIFT) : lon - _PACIFIC_SHIFT;
}

// ─────────────────────────────────────────────────────────────────
// 两种地图子视图的 geo 参数
// ─────────────────────────────────────────────────────────────────

const _GEO_CHINA_VIEW = {
    center: [-45, 35],  // pacific coords 中心（105°E, 35°N）
    zoom: 4.5,
    roam: true
};

const _GEO_WORLD_VIEW = {
    center: [0, 12],
    zoom: 1.0,
    roam: true
};

// ─────────────────────────────────────────────────────────────────
// 主模式切换：列表 ↔ 地图
// ─────────────────────────────────────────────────────────────────

function switchViewMode(mode) {
    window._viewMode = mode;
    localStorage.setItem('fmsa_view_mode', mode);

    const panel = document.getElementById('map-alert-panel');

    if (mode === 'map') {
        document.body.classList.add('map-mode');
        if (panel) panel.style.display = 'flex';
        if (typeof hideFlightMarksLegend === 'function') hideFlightMarksLegend();
        if (typeof applyFilters === 'function') applyFilters();
        setTimeout(() => {
            _syncPanelPosition();
            _initMapCharts();
            _initRadarAlertFloat();
            _refreshRadarAlerts();
        }, 30);
    } else {
        document.body.classList.remove('map-mode');
        if (panel) panel.style.display = 'none';
        const radarFloat = document.getElementById('radar-alert-float');
        const radarWatch = document.getElementById('radar-alert-watch-panel');
        if (radarFloat) radarFloat.style.display = 'none';
        if (radarWatch) radarWatch.style.display = 'none';
        _destroyMapCharts();
        if (typeof applyFilters === 'function') applyFilters();
        if (mode === 'list' && typeof ensureFlightMarksLegend === 'function') {
            ensureFlightMarksLegend();
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// 地图子视图切换：中国聚焦 ↔ 世界全图
// ─────────────────────────────────────────────────────────────────

function _switchMapView(view) {
    _mapView = view;
    localStorage.setItem('fmsa_map_view', view);
    if (_mapChart) {
        const geoView = view === 'china' ? _GEO_CHINA_VIEW : _GEO_WORLD_VIEW;
        _mapChart.setOption({
            geo: [{ center: geoView.center, zoom: geoView.zoom }]
        });
        _applyMapStyleToChart();
        if (typeof updateMapAlert === 'function') updateMapAlert();
    }
}

// ─────────────────────────────────────────────────────────────────
// 面板定位
// ─────────────────────────────────────────────────────────────────

function _syncPanelPosition() {
    const panel = document.getElementById('map-alert-panel');
    if (!panel) return;

    const titleRow = document.querySelector('.main-title-row');
    const topPx = (titleRow && titleRow.getBoundingClientRect().top > 0)
        ? Math.round(titleRow.getBoundingClientRect().top)
        : 180;

    const totalH = window.innerHeight - topPx;

    panel.style.top    = topPx + 'px';
    panel.style.height = totalH + 'px';

    const mapEl = document.getElementById('map-world');
    if (mapEl) mapEl.style.height = Math.max(100, totalH) + 'px';

    if (_mapChart) _mapChart.resize();
}

// ─────────────────────────────────────────────────────────────────
// 颜色工具（实心、不透明，地图用）
// ─────────────────────────────────────────────────────────────────

function _mapColor(level) {
    if (level === 'N' || !level) return '#7f8c8d';
    if (typeof getAlertColorHex === 'function') {
        return getAlertColorHex(level);
    }
    const c = { R: '#e74c3c', Y: '#f39c12', G: '#27ae60' };
    return c[level] || '#7f8c8d';
}

// ─────────────────────────────────────────────────────────────────
// 报文关键字换行工具函数
// ─────────────────────────────────────────────────────────────────

/**
 * 从左到右扫描报文字符串，找出所有需要换行的位置（关键字前的空格索引）。
 * keywords 按优先级从高到低排列（较长的组合词须排在前面），避免 PROB30 TEMPO 被拆成 PROB30 + TEMPO。
 */
function _findReportSplitPoints(content, keywords) {
    const points = [];
    let i = 0;
    while (i < content.length) {
        if (content[i] === ' ') {
            let matched = false;
            for (const kw of keywords) {
                if (content.startsWith(kw, i + 1)) {
                    const afterPos = i + 1 + kw.length;
                    // 有效边界：字符串结束，或紧跟的字符不是字母（允许数字，如 FM020900）
                    const afterChar = afterPos < content.length ? content[afterPos] : '';
                    if (afterChar === '' || !/[A-Za-z]/.test(afterChar)) {
                        points.push(i);
                        i = afterPos;
                        matched = true;
                        break;
                    }
                }
            }
            if (!matched) i++;
        } else {
            i++;
        }
    }
    return points;
}

/**
 * 格式化实况报文（METAR）：在 BECMG/TEMPO/FM/RMK 前换行；
 * 第2行起若超过第1行字符数则按词边界折行。
 * 若无上述关键字（如 NOSIG= 结尾）则原样返回。
 */
function _formatMetarContent(content) {
    if (!content) return '';
    const keywords = ['BECMG', 'TEMPO', 'FM', 'RMK'];
    const points = _findReportSplitPoints(content, keywords);
    if (points.length === 0) return content;

    const parts = [];
    let prev = 0;
    for (const pos of points) {
        parts.push(content.substring(prev, pos));
        prev = pos + 1;
    }
    parts.push(content.substring(prev));

    const line1Len = parts[0].length;
    const lines = [parts[0]];

    for (let idx = 1; idx < parts.length; idx++) {
        let remaining = parts[idx];
        while (remaining.length > line1Len) {
            let breakPos = line1Len;
            while (breakPos > 0 && remaining[breakPos] !== ' ') breakPos--;
            if (breakPos === 0) breakPos = line1Len;
            lines.push(remaining.substring(0, breakPos));
            remaining = remaining.substring(breakPos).trimStart();
        }
        if (remaining.length > 0) lines.push(remaining);
    }

    return lines.join('<br>');
}

/**
 * 格式化预报报文（TAF）：在所有关键字前换行，每个关键字作为新行行首。
 * 优先匹配 PROB30 TEMPO / PROB40 TEMPO，避免被拆开。
 */
function _formatTafContent(content) {
    if (!content) return '';
    const keywords = ['PROB30 TEMPO', 'PROB40 TEMPO', 'PROB30', 'PROB40', 'BECMG', 'TEMPO', 'FM', 'RMK'];
    const points = _findReportSplitPoints(content, keywords);
    if (points.length === 0) return content;

    const parts = [];
    let prev = 0;
    for (const pos of points) {
        parts.push(content.substring(prev, pos));
        prev = pos + 1;
    }
    parts.push(content.substring(prev));

    return parts.filter(s => s.length > 0).join('<br>');
}

// ─────────────────────────────────────────────────────────────────
// Tooltip 构建
// ─────────────────────────────────────────────────────────────────

function _makeTooltip() {
    return {
        trigger: 'item',
        enterable: false,
        backgroundColor: 'rgba(15,28,44,0.97)',
        borderColor: '#3a6a8a',
        borderWidth: 1,
        padding: [10, 14],
        textStyle: { color: '#c8dff0', fontSize: 12, fontFamily: 'monospace' },
        formatter: params => {
            if (!params.name) return '';
            const code = params.name;

            const airport = filteredAirportData && filteredAirportData.find(a => a.airport_4code === code);
            if (!airport) return `<b>${code}</b>`;

            const metar = airport.metar_data && airport.metar_data[0];
            const taf   = airport.taf_data   && airport.taf_data[0];
            const fd    = airport.flight_data;
            // 优先使用 flight_data 中的新增字段；若服务端尚未更新则退化到异步缓存
            const fs    = (_flightStatusCache && _flightStatusCache[code]) || null;
            const _fv   = (fd && ('en_route' in fd)) ? fd : fs;

            // ── 时间格式化（响应 SCT/UTC 开关；30分钟内红色加粗，否则白色）──
            function fmtTs(ts) {
                if (ts == null) return '<span style="color:#4a6a80">--</span>';
                try {
                    const parts = formatTimestampPartsByMode(ts);
                    const timeStr = parts.date
                        ? `${parts.date.slice(5)} ${parts.time.slice(0, 5)}`
                        : parts.time.slice(0, 5);
                    const isUtc = window.displayTimezone === 'UTC';
                    const suffix = isUtc ? 'Z' : '';
                    const isSoon = ts <= Date.now() + 1800000;
                    if (isSoon) {
                        return `<span style="color:#ff4d4d;font-weight:bold">${timeStr}${suffix}</span>`;
                    }
                    return `<span style="color:#ffffff">${timeStr}${suffix}</span>`;
                } catch { return '<span style="color:#4a6a80">--</span>'; }
            }

            // ── 布尔值格式化（"是" 统一红色加粗）──
            function fmtBool(val, _trueColor, falseColor) {
                if (val == null) return '<span style="color:#4a6a80">--</span>';
                return val
                    ? `<span style="color:#ff4d4d;font-weight:bold">是</span>`
                    : `<span style="color:${falseColor}">否</span>`;
            }

            let html = `<div style="line-height:1.6;min-width:280px">`;

            // 机场代码标题
            html += `<div style="font-weight:bold;font-size:14px;color:#7ecbff;margin-bottom:6px;letter-spacing:1px">${code}</div>`;

            // METAR 报文
            if (metar && metar.metar_content) {
                const metarFormatted = _formatMetarContent(metar.metar_content);
                html += `<div style="color:#90c8f0;font-size:11px;white-space:nowrap;margin-bottom:3px;padding:4px 6px;background:rgba(40,80,120,0.3);border-radius:3px">${metarFormatted}</div>`;
            } else {
                html += `<div style="color:#4a6a80;font-size:11px;margin-bottom:3px">METAR: 暂无</div>`;
            }

            // TAF 报文
            if (taf && taf.taf_content) {
                const tafFormatted = _formatTafContent(taf.taf_content);
                html += `<div style="color:#78b0d8;font-size:11px;white-space:nowrap;margin-bottom:6px;padding:4px 6px;background:rgba(30,60,100,0.3);border-radius:3px">${tafFormatted}</div>`;
            } else {
                html += `<div style="color:#4a6a80;font-size:11px;margin-bottom:6px">TAF: 暂无</div>`;
            }

            // 分隔线
            html += `<div style="border-top:1px solid #2a4a64;margin:4px 0 6px"></div>`;

            // 5 项实况信息（优先用 flight_data 新字段，无则退化到 _flightStatusCache）
            const rows = [
                ['上一站最近起飞', fmtTs(_fv ? _fv.closest_departure_time_of_arriving_flight : null)],
                ['本场最近着陆',   fmtTs(_fv ? _fv.closest_landing_time_of_arriving_flight   : null)],
                ['本场最近起飞',   fmtTs(_fv ? _fv.closest_departure_time_at_this_airport     : null)],
                ['已有航班前往本场', fmtBool(_fv != null ? _fv.en_route    : null, getAlertColorHex('Y'), '#7f8c8d')],
                ['是否有飞机停场',  fmtBool(_fv != null ? _fv.has_parking : null, getAlertColorHex('R'), '#7f8c8d')],
            ];

            rows.forEach(([label, value]) => {
                html += `<div style="display:flex;justify-content:space-between;align-items:center;margin:2px 0;white-space:nowrap">`;
                html += `<span style="color:#6a9ab8;margin-right:16px">${label}</span>`;
                html += `<span>${value}</span>`;
                html += `</div>`;
            });

            html += `</div>`;
            return html;
        }
    };
}

// ─────────────────────────────────────────────────────────────────
// ECharts 初始化
// ─────────────────────────────────────────────────────────────────

function _initMapCharts() {
    const base = (window.staticUrl || '/static/') + 'geo/';

    if (_worldGeoReady) {
        _createInstances();
        _fetchCoordsAndRender();
        _loadMapStyleConfig();
        return;
    }

    fetch(base + 'world_pacific.json')
        .then(r => { if (!r.ok) throw new Error('world_pacific.json 加载失败'); return r.json(); })
        .then(data => {
            _worldGeoJson = data;
            echarts.registerMap('fmsa_world_pacific', data);
            _worldGeoReady = true;
            _createInstances();
            _fetchCoordsAndRender();
            _loadMapStyleConfig();
            _loadExtraGeoLayers(base);
        })
        .catch(err => console.error('[地图告警] GeoJSON 加载失败:', err));
}

function _loadExtraGeoLayers(base) {
    const jobs = [
        ['china_provinces_pacific.json', 'fmsa_china_provinces', 'provinces'],
        ['admin1_pacific.json', 'fmsa_admin1', 'admin1'],
        ['lakes_pacific.json', 'fmsa_lakes', 'lakes'],
        ['rivers_pacific.json', null, 'rivers'],
    ];
    jobs.forEach(([file, mapName, key]) => {
        fetch(base + file)
            .then(r => (r.ok ? r.json() : null))
            .then(data => {
                if (!data) return;
                if (mapName) echarts.registerMap(mapName, data);
                if (key === 'rivers') _riverLineData = _geojsonToLineData(data);
                if (key === 'provinces') {
                    _provinceGeoJson = data;
                    _provinceBorderLines = _geojsonToBorderLines(data);
                    _provinceCentroids = _geojsonToCentroids(data);
                }
                if (key === 'admin1') {
                    _admin1BorderLines = _geojsonToBorderLines(data);
                    _admin1Centroids = _geojsonToCentroids(data);
                }
                if (key === 'lakes') {
                    _lakeBorderLines = _geojsonToBorderLines(data);
                }
                _extraGeoReady[key] = true;
                if (_mapChart) {
                    _applyMapStyleToChart();
                    if (typeof updateMapAlert === 'function') updateMapAlert();
                }
            })
            .catch(() => { /* optional layers */ });
    });
}

function _geojsonToLineData(gj) {
    const out = [];
    const feats = (gj && gj.features) || [];
    feats.forEach(ft => {
        const g = ft.geometry || {};
        const coords = g.coordinates;
        if (!coords) return;
        const rank = Number((ft.properties || {}).scalerank);
        const scalerank = Number.isFinite(rank) ? rank : 5;
        // 等级越高（数字越小）线越粗
        const width = scalerank <= 1 ? 1.8 : scalerank <= 2 ? 1.4 : scalerank <= 4 ? 1.0 : 0.7;
        if (g.type === 'LineString') {
            out.push({ coords, lineStyle: { width } });
        } else if (g.type === 'MultiLineString') {
            coords.forEach(line => out.push({ coords: line, lineStyle: { width } }));
        }
    });
    return out;
}

/** 把面状 GeoJSON 的边界环拆成 lines，保证与底图共用 geo 坐标系、绝不漂移 */
function _geojsonToBorderLines(gj) {
    const out = [];
    const feats = (gj && gj.features) || [];
    const pushRings = (rings) => {
        (rings || []).forEach(ring => {
            if (ring && ring.length >= 2) out.push({ coords: ring });
        });
    };
    feats.forEach(ft => {
        const g = ft.geometry || {};
        const coords = g.coordinates;
        if (!coords) return;
        if (g.type === 'Polygon') pushRings(coords);
        else if (g.type === 'MultiPolygon') coords.forEach(poly => pushRings(poly));
    });
    return out;
}

function _geojsonToCentroids(gj) {
    const out = [];
    const feats = (gj && gj.features) || [];
    const ringCentroid = (ring) => {
        if (!ring || !ring.length) return null;
        let sx = 0, sy = 0, n = 0;
        for (let i = 0; i < ring.length; i++) {
            const p = ring[i];
            if (!p || p.length < 2) continue;
            sx += Number(p[0]); sy += Number(p[1]); n++;
        }
        if (!n) return null;
        return [sx / n, sy / n];
    };
    const geomCentroid = (g) => {
        if (!g || !g.coordinates) return null;
        if (g.type === 'Polygon') return ringCentroid(g.coordinates[0]);
        if (g.type === 'MultiPolygon') {
            // 取面积最大环的粗略质心：用点数最多的外环近似
            let best = null, bestN = 0;
            g.coordinates.forEach(poly => {
                const ring = poly && poly[0];
                if (ring && ring.length > bestN) { bestN = ring.length; best = ring; }
            });
            return ringCentroid(best);
        }
        return null;
    };
    feats.forEach(ft => {
        const name = (ft.properties || {}).name;
        const c = geomCentroid(ft.geometry);
        if (name && c) out.push({ name, value: c });
    });
    return out;
}

function _loadMapStyleConfig() {
    if (typeof currentTimeMode === 'undefined') return;
    fetch(`/${currentTimeMode}/api/map-style/config/`, {
        headers: typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                applyMapStyleConfig(data.config, data.border_widths, data.palette);
            }
        })
        .catch(err => console.warn('[地图样式] 加载失败', err));
}

function applyMapStyleConfig(cfg, borderWidths, palette) {
    _mapStyle = cfg || _mapStyle;
    if (borderWidths) _borderWidths = borderWidths;
    if (palette) _mapPalette = palette;
    _ensureBlinkTimer();
    if (_mapChart) {
        _applyMapStyleToChart();
        updateMapAlert();
    }
}
window.applyMapStyleConfig = applyMapStyleConfig;

function _ensureBlinkTimer() {
    if (_blinkTimer) return;
    _blinkTimer = setInterval(() => {
        if (window._viewMode !== 'map' || !_mapChart) return;
        _blinkPhase = !_blinkPhase;
        updateMapAlert();
    }, 650);
}

function _markerSizes() {
    const inner = (_mapStyle && _mapStyle.marker_inner_size) || 6;
    const outer = (_mapStyle && _mapStyle.marker_outer_size) || 10;
    const border = Math.max(1.5, (outer - inner) / 2);
    return { inner, outer, border };
}

function _palette() {
    return _mapPalette || {
        background: '#1b2838',
        land: '#1e3348',
        country_border: '#6a9ab8',
        province_border: '#5a9aba',
        admin1_border: '#7aa0b8',
        label_color: '#b8d8f0',
        country_label: '#8eb4d0',
        river: '#3d8aaa',
        lake: 'rgba(45, 100, 140, 0.55)',
        lake_border: '#4a8ab0',
    };
}

function _nameLabelFormatter(params) {
    if (params == null) return '';
    if (typeof params === 'string' || typeof params === 'number') return String(params);
    if (params.name != null && params.name !== '') return String(params.name);
    if (params.data && params.data.name != null) return String(params.data.name);
    return '';
}

function _getLiveGeoView() {
    const fallback = _mapView === 'china' ? _GEO_CHINA_VIEW : _GEO_WORLD_VIEW;
    if (!_mapChart) return { center: fallback.center, zoom: fallback.zoom };
    try {
        const opt = _mapChart.getOption();
        const g0 = (opt.geo || [])[0] || {};
        const center = Array.isArray(g0.center) ? g0.center : fallback.center;
        const zoom = (typeof g0.zoom === 'number') ? g0.zoom : fallback.zoom;
        return { center, zoom };
    } catch (e) {
        return { center: fallback.center, zoom: fallback.zoom };
    }
}

function _buildCountryRegions() {
    const feats = (_worldGeoJson && _worldGeoJson.features) || [];
    const g = (_mapStyle && _mapStyle.global) || {};
    const c = (_mapStyle && _mapStyle.china) || {};
    const bw = _borderWidths;
    const pal = _palette();
    // 省界开启时：中国外轮廓只由省界面虚线承担，避免国界+省界双描
    const hideChinaStroke = c.province_borders !== false && _extraGeoReady.provinces;
    const regions = [{
        name: 'French Southern and Antarctic Lands',
        itemStyle: { opacity: 0, borderWidth: 0 },
        label: { show: false }
    }];
    feats.forEach(ft => {
        const name = (ft.properties || {}).name;
        if (!name || name === 'French Southern and Antarctic Lands') return;
        const isChina = name === 'China';
        let borderW = g.country_borders === false ? 0 : bw.country;
        if (isChina && hideChinaStroke) borderW = 0;
        regions.push({
            name,
            itemStyle: {
                borderColor: pal.country_border,
                borderWidth: borderW
            },
            label: {
                show: !!g.country_labels && !isChina,
                color: pal.country_label,
                fontSize: 10,
                formatter: _nameLabelFormatter
            }
        });
    });
    return regions;
}

function _buildProvinceRegions() {
    const feats = (_provinceGeoJson && _provinceGeoJson.features) || [];
    const c = (_mapStyle && _mapStyle.china) || {};
    const bw = _borderWidths;
    const pal = _palette();
    const showBorder = c.province_borders !== false;
    const showLabel = !!c.province_labels;
    return feats.map(ft => {
        const name = (ft.properties || {}).name;
        return {
            name,
            itemStyle: {
                areaColor: 'rgba(0,0,0,0)',
                borderColor: pal.province_border,
                borderWidth: showBorder ? bw.province : 0,
                borderType: 'dashed'
            },
            label: {
                show: showLabel,
                color: pal.label_color,
                fontSize: 9,
                formatter: _nameLabelFormatter
            }
        };
    }).filter(r => r.name);
}

function _overlayMapSeries() {
    const g = (_mapStyle && _mapStyle.global) || {};
    const w = (_mapStyle && _mapStyle.world) || {};
    const c = (_mapStyle && _mapStyle.china) || {};
    const pal = _palette();
    const bw = _borderWidths;
    const showProvinceBorders = _extraGeoReady.provinces && c.province_borders !== false;
    const showProvinceLabels = _extraGeoReady.provinces && !!c.province_labels;
    const showAdmin1Borders = _mapView === 'world' && !!w.admin1_borders && _extraGeoReady.admin1;
    const showAdmin1Labels = _mapView === 'world' && !!w.admin1_labels && _extraGeoReady.admin1;
    const showLakes = !!g.lakes && _extraGeoReady.lakes;
    const showRivers = !!g.rivers && _extraGeoReady.rivers;

    const riverData = showRivers ? _riverLineData.map(d => ({
        coords: d.coords,
        lineStyle: { width: (d.lineStyle && d.lineStyle.width) || 0.8, color: pal.river, opacity: 0.85 }
    })) : [];

    const provinceLines = showProvinceBorders
        ? _provinceBorderLines.map(d => ({ coords: d.coords }))
        : [];
    const admin1Lines = showAdmin1Borders
        ? _admin1BorderLines.map(d => ({ coords: d.coords }))
        : [];
    const lakeLines = showLakes
        ? _lakeBorderLines.map(d => ({ coords: d.coords }))
        : [];

    return [
        {
            name: 'map-lakes',
            type: 'lines',
            coordinateSystem: 'geo',
            geoIndex: 0,
            polyline: true,
            silent: true,
            animation: false,
            z: 2,
            lineStyle: { color: pal.lake_border, width: 1.1, opacity: 0.9 },
            data: lakeLines
        },
        {
            name: 'map-provinces',
            type: 'lines',
            coordinateSystem: 'geo',
            geoIndex: 0,
            polyline: true,
            silent: true,
            animation: false,
            z: 3,
            lineStyle: {
                color: pal.province_border,
                width: bw.province,
                type: 'dashed',
                opacity: 0.95
            },
            data: provinceLines
        },
        {
            name: 'map-province-labels',
            type: 'scatter',
            coordinateSystem: 'geo',
            geoIndex: 0,
            silent: true,
            animation: false,
            z: 3,
            symbolSize: 1,
            itemStyle: { color: 'transparent' },
            label: {
                show: showProvinceLabels,
                formatter: '{b}',
                color: pal.label_color,
                fontSize: 9,
                position: 'inside'
            },
            data: showProvinceLabels ? _provinceCentroids : []
        },
        {
            name: 'map-admin1',
            type: 'lines',
            coordinateSystem: 'geo',
            geoIndex: 0,
            polyline: true,
            silent: true,
            animation: false,
            z: 3,
            lineStyle: {
                color: pal.admin1_border,
                width: bw.admin1,
                type: 'dashed',
                opacity: 0.9
            },
            data: admin1Lines
        },
        {
            name: 'map-admin1-labels',
            type: 'scatter',
            coordinateSystem: 'geo',
            geoIndex: 0,
            silent: true,
            animation: false,
            z: 3,
            symbolSize: 1,
            itemStyle: { color: 'transparent' },
            label: {
                show: showAdmin1Labels,
                formatter: '{b}',
                color: pal.label_color,
                fontSize: 8,
                position: 'inside'
            },
            data: showAdmin1Labels ? _admin1Centroids : []
        },
        {
            name: 'rivers',
            type: 'lines',
            coordinateSystem: 'geo',
            geoIndex: 0,
            polyline: true,
            silent: true,
            animation: false,
            z: 3,
            lineStyle: { color: pal.river, width: 0.8, opacity: 0.85 },
            data: riverData
        }
    ];
}

function _applyMapStyleToChart() {
    if (!_mapChart) return;
    const live = _getLiveGeoView();
    const pal = _palette();

    // 只用一个 geo；省界/州界/湖泊全部挂 geoIndex:0 的 map 系列，从根上消除多层漫游漂移
    _mapChart.setOption({
        backgroundColor: pal.background,
        geo: [{
            id: 'main',
            map: 'fmsa_world_pacific',
            left: '10px', right: '10px', top: '10px', bottom: '10px',
            center: live.center,
            zoom: live.zoom,
            roam: true,
            silent: true,
            label: { show: false },
            emphasis: { disabled: true },
            itemStyle: {
                areaColor: pal.land,
                borderColor: pal.country_border,
                borderWidth: 0.35
            },
            regions: _buildCountryRegions()
        }],
        series: _overlayMapSeries()
    });
}

function _createInstances() {
    _syncPanelPosition();

    const mapEl = document.getElementById('map-world');
    if (mapEl && !_mapChart) {
        _mapChart = echarts.init(mapEl, null, { renderer: 'canvas' });
        _mapChart.setOption(_buildMapOption());

        // 点击机场图标打开详情页（与列表模式点击四字代码功能一致）
        _mapChart.on('click', params => {
            if (params.name && typeof showAirportDetail === 'function') {
                showAirportDetail(params.name);
            }
        });
        _bindRadarGeoRoamSync();
        _ensureBlinkTimer();
        _ensureRadarCanvasHost();
    }

    setTimeout(() => {
        if (_mapChart) {
            _mapChart.resize();
            _ensureRadarCanvasHost();
            _scheduleRadarCanvasPaint();
        }
    }, 200);
}

// ─────────────────────────────────────────────────────────────────
// ECharts option 构建（三个系列：内圆 + 外圈闪烁 + 外圈静态）
// ─────────────────────────────────────────────────────────────────

function _buildMapOption() {
    const geoView = _mapView === 'china' ? _GEO_CHINA_VIEW : _GEO_WORLD_VIEW;
    const sizes = _markerSizes();
    const pal = _palette();

    return {
        backgroundColor: pal.background,
        animation: false,
        animationDurationUpdate: 0,
        tooltip: _makeTooltip(),
        geo: [{
            id: 'main',
            map: 'fmsa_world_pacific',
            left: '10px', right: '10px', top: '10px', bottom: '10px',
            center: geoView.center,
            zoom: geoView.zoom,
            roam: true,
            silent: true,
            animation: false,
            label: { show: false },
            emphasis: { disabled: true },
            itemStyle: {
                areaColor: pal.land,
                borderColor: pal.country_border,
                borderWidth: 0.35
            },
            regions: _buildCountryRegions()
        }],
        series: [
            ..._overlayMapSeries(),
            {
                name: 'airports-outer-flash',
                type: 'effectScatter',
                coordinateSystem: 'geo',
                geoIndex: 0,
                symbolSize: sizes.outer,
                rippleEffect: { period: 1.4, scale: 2.2, brushType: 'stroke' },
                data: [],
                label: { show: false },
                emphasis: { disabled: true },
                zlevel: 2,
                z: 4
            },
            {
                name: 'airports-outer-static',
                type: 'scatter',
                coordinateSystem: 'geo',
                geoIndex: 0,
                symbolSize: sizes.outer,
                data: [],
                label: { show: false },
                emphasis: { disabled: true },
                zlevel: 2,
                z: 4
            },
            {
                name: 'airports-inner',
                type: 'scatter',
                coordinateSystem: 'geo',
                geoIndex: 0,
                symbolSize: sizes.inner,
                data: [],
                label: {
                    show: false,
                    position: 'bottom',
                    distance: 2,
                    color: '#c8dff0',
                    fontSize: 10,
                    formatter: '{b}'
                },
                emphasis: { disabled: true },
                zlevel: 2,
                z: 10
            }
        ]
    };
}

// ─────────────────────────────────────────────────────────────────
// 坐标获取 + 实况状态预取
// ─────────────────────────────────────────────────────────────────

function _fetchCoordsAndRender() {
    // 实况状态预取（与坐标并行，不阻塞渲染）
    _prefetchFlightStatus();

    if (_mapCoordCache !== null) {
        updateMapAlert();
        return;
    }

    const codes = (typeof airportData !== 'undefined' && airportData.length)
        ? airportData.map(a => a.airport_4code).join(',')
        : '';

    if (!codes) {
        // airportData 尚未加载完成，保持 _mapCoordCache 为 null，
        // 等 applyFilters → updateMapAlert 再次触发时重试
        return;
    }

    fetch(`/${currentTimeMode}/api/airport-coords/?codes=${encodeURIComponent(codes)}`, {
        headers: getRequestHeaders ? getRequestHeaders() : {}
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            _mapCoordCache = data.coords;
            updateMapAlert();
        } else {
            console.error('[地图告警] 坐标接口返回失败:', data.error);
        }
    })
    .catch(err => console.error('[地图告警] 坐标接口请求失败:', err));
}

function _prefetchFlightStatus() {
    fetch(`/${currentTimeMode}/api/airport-flight-status/`, {
        headers: getRequestHeaders ? getRequestHeaders() : {}
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            _flightStatusCache = data.data;
        } else {
            console.warn('[地图告警] 实况状态接口返回失败:', data.error);
        }
    })
    .catch(err => console.error('[地图告警] 实况状态预取失败:', err));
}

// ─────────────────────────────────────────────────────────────────
// 标记数据构建
// ─────────────────────────────────────────────────────────────────

function _buildMarkers() {
    if (!_mapCoordCache || !filteredAirportData) {
        return { inner: [], outerFlash: [], outerStatic: [] };
    }

    const inner       = [];
    const outerFlash  = [];
    const outerStatic = [];
    const margin      = typeof getSelectedAlertMargin === 'function' ? getSelectedAlertMargin() : 2;
    const sizes       = _markerSizes();
    const showNames   = !!( _mapStyle && _mapStyle.show_airport_labels );
    const pal         = _palette();

    filteredAirportData.forEach(airport => {
        const code   = airport.airport_4code;
        const coords = _mapCoordCache[code];
        if (!coords) return;

        const pos = [_toLonPacific(coords.lon), coords.lat];
        const marginResults = ((airport.computed_alerts || {})[`margin_${margin}`]) || {};
        const tafLevel = marginResults.taf_highest_alert || 'N';
        inner.push({
            name: code,
            value: pos,
            itemStyle: { color: _mapColor(tafLevel), opacity: 0.92 },
            label: {
                show: showNames,
                position: 'bottom',
                distance: 2,
                color: pal.label_color || '#c8dff0',
                fontSize: 10,
                formatter: code
            }
        });

        const metar       = airport.metar_data && airport.metar_data[0];
        const metarLevel  = (metar && metar.metar_warning) || 'N';
        const ringColor   = _mapColor(metarLevel);
        const shouldMetarFlash = !!(metar && (
            metar.operation_popup === 'Y' || metar.operation_popup === 'I'
            || metar.parking_popup === 'Y' || metar.parking_popup === 'I'
        ));
        const radarHit = _radarBlinkCodes && _radarBlinkCodes.has(code);
        const radarLvl = radarHit
            ? (((_radarAlertCache.alerts || []).find(a => a.airport_4code === code) || {}).alert_highest || 'Y')
            : null;
        const radarColor = radarLvl ? _mapColor(radarLvl) : null;

        const ringStyle = (borderColor, opacity) => ({
            color: 'transparent',
            borderColor,
            borderWidth: sizes.border,
            opacity
        });

        // 二者互补：实况 → 告警色↔白闪；雷达 → 告警色↔白交替涟漪；同时满足时两者都体现
        if (shouldMetarFlash) {
            outerStatic.push({
                name: code,
                value: pos,
                itemStyle: ringStyle(_blinkPhase ? ringColor : '#ffffff', 0.95)
            });
        }
        if (radarHit) {
            const rippleCol = _blinkPhase ? radarColor : '#ffffff';
            outerFlash.push({
                name: code,
                value: pos,
                rippleEffect: { color: rippleCol, period: 1.4, scale: 2.2, brushType: 'stroke' },
                itemStyle: ringStyle(rippleCol, 0.9)
            });
        }
        if (!shouldMetarFlash && !radarHit) {
            outerStatic.push({
                name: code,
                value: pos,
                itemStyle: ringStyle(ringColor, metarLevel === 'N' ? 0.4 : 0.85)
            });
        }
    });

    return { inner, outerFlash, outerStatic };
}

// ─────────────────────────────────────────────────────────────────
// 主更新入口（由 main.js 在 applyFilters 后调用）
// ─────────────────────────────────────────────────────────────────

function updateMapAlert() {
    if (window._viewMode !== 'map') return;

    if (!_mapChart) {
        if (_worldGeoReady) {
            _createInstances();
        } else {
            return;
        }
    }

    if (_mapCoordCache === null) {
        _fetchCoordsAndRender();
        return;
    }

    const { inner, outerFlash, outerStatic } = _buildMarkers();
    const sizes = _markerSizes();

    _mapChart.setOption({
        series: [
            ..._overlayMapSeries(),
            { name: 'airports-outer-flash',  data: outerFlash,  symbolSize: sizes.outer },
            { name: 'airports-outer-static', data: outerStatic, symbolSize: sizes.outer },
            { name: 'airports-inner',        data: inner,       symbolSize: sizes.inner }
        ]
    });
    _scheduleRadarCanvasPaint();
}

// ─────────────────────────────────────────────────────────────────
// 销毁 & resize
// ─────────────────────────────────────────────────────────────────

function _destroyMapCharts() {
    if (_mapChart) { _mapChart.dispose(); _mapChart = null; }
    _radarRoamBound = false;
    if (_radarPaintRaf) {
        cancelAnimationFrame(_radarPaintRaf);
        _radarPaintRaf = 0;
    }
    const cv = document.getElementById('map-radar-canvas');
    if (cv && cv.parentNode) cv.parentNode.removeChild(cv);
}

let _resizeTimer = null;
window.addEventListener('resize', () => {
    if (_resizeTimer) clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(() => {
        if (window._viewMode === 'map') {
            _syncPanelPosition();
            if (_mapChart) {
                _mapChart.resize();
                _ensureRadarCanvasHost();
                _scheduleRadarCanvasPaint();
            }
        }
    }, 100);
});

// ─────────────────────────────────────────────────────────────────
// 视图模式切换开关事件（列表/地图）
// ─────────────────────────────────────────────────────────────────

const _viewModeToggle = document.getElementById('view-mode-toggle-input');
if (_viewModeToggle) {
    _viewModeToggle.addEventListener('change', () => {
        switchViewMode(_viewModeToggle.checked ? 'map' : 'list');
    });
}

// ─────────────────────────────────────────────────────────────────
// 中国/世界切换开关事件
// ─────────────────────────────────────────────────────────────────

const _mapViewToggle = document.getElementById('map-view-toggle-input');
if (_mapViewToggle) {
    _mapViewToggle.addEventListener('change', () => {
        _switchMapView(_mapViewToggle.checked ? 'world' : 'china');
    });
}

// ─────────────────────────────────────────────────────────────────
// 时区切换时重新定位
// ─────────────────────────────────────────────────────────────────

const _tzToggle = document.getElementById('timezone-toggle-input');
if (_tzToggle) {
    _tzToggle.addEventListener('change', () => {
        if (window._viewMode === 'map') setTimeout(_syncPanelPosition, 80);
    });
}

// ─────────────────────────────────────────────────────────────────
// 页面加载时恢复状态
// ─────────────────────────────────────────────────────────────────

/**
 * 恢复中国/世界子视图。列表↔地图的主模式已由左侧视图导航（views_nav.js）接管，
 * 本函数只负责本模块自己的状态，供导航在按需注入 map.js 后调用一次。
 */
function initMapAlertState() {
    const savedView = localStorage.getItem('fmsa_map_view');
    _mapView = savedView === 'world' ? 'world' : 'china';
    const mapViewToggle = document.getElementById('map-view-toggle-input');
    if (mapViewToggle) mapViewToggle.checked = (_mapView === 'world');
    _initRadarAlertFloat();
    _refreshRadarAlerts();
}

// ─────────────────────────────────────────────────────────────────
// 强对流雷达预警悬浮列表 + z3 回波铺图 + 限流提示
// ─────────────────────────────────────────────────────────────────

let _radarAlertCache = { alerts: [], watch: [] };
let _radarPollTimer = null;
let _radarBlinkCodes = new Set();
let _radarOverlayMeta = null;
let _radarOverlayPieces = []; // {lonW,latS,lonE,latN,url,sx,sw,tileSize}
let _radarOverlayFrame = null;
let _radarTileImgCache = new Map(); // url -> HTMLImageElement
let _radarPaintRaf = 0;
let _radarRoamBound = false;
const _PACIFIC_CUT_LON = -30;
const _RADAR_OVERLAY_OPACITY = 0.72;

function _radarColorSpan(level) {
    const map = { R: '#e74c3c', Y: '#f39c12', G: '#27ae60', N: '#7f8c8d' };
    const c = map[level] || map.N;
    return `<span style="color:${c};font-weight:700">${level || 'N'}</span>`;
}

function _renderRadarAlertRows(list) {
    if (!list || !list.length) {
        return '<div class="radar-alert-empty">暂无告警</div>';
    }
    return list.map(a => {
        const show = (a.alert_33 === 'R' || a.alert_33 === 'Y' || a.alert_41 === 'R' || a.alert_41 === 'Y'
            || a.alert_33 === 'G' || a.alert_41 === 'G');
        if (!show) return '';
        return `<div class="radar-alert-row">
          <span class="radar-alert-code">${a.airport_4code}</span>
          <span class="radar-alert-type">雷达回波</span>
          <span class="radar-alert-thr">${_radarColorSpan(a.alert_33)}</span>
          <span class="radar-alert-thr">${_radarColorSpan(a.alert_41)}</span>
        </div>`;
    }).join('');
}

function _tileLonLatBounds(z, x, y) {
    const n = Math.pow(2, z);
    const lonW = x / n * 360 - 180;
    const lonE = (x + 1) / n * 360 - 180;
    const latN = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI;
    const latS = Math.atan(Math.sinh(Math.PI * (1 - 2 * (y + 1) / n))) * 180 / Math.PI;
    return { lonW, lonE, latN, latS };
}

function _radarTileUrl(meta, z, x, y) {
    const size = meta.tile_size || 256;
    const color = meta.color != null ? meta.color : 2;
    const smooth = meta.smooth != null ? meta.smooth : 0;
    const snow = meta.snow != null ? meta.snow : 0;
    return `${meta.host}${meta.path}/${size}/${z}/${x}/${y}/${color}/${smooth}_${snow}.png`;
}

function _pushRadarOverlayPiece(out, url, lonW, lonE, latS, latN, sx, sw, tileSize) {
    if (!(lonE > lonW) || !(latN > latS) || sw <= 0) return;
    out.push({
        lonW: _toLonPacific(lonW),
        latS,
        lonE: _toLonPacific(lonE),
        latN,
        url,
        sx,
        sw,
        tileSize
    });
}

function _buildRadarOverlayPieces(meta) {
    if (!meta || !meta.host || !meta.path) return [];
    const z = meta.z || 3;
    const n = Math.pow(2, z);
    const tileSize = meta.tile_size || 256;
    const cut = _PACIFIC_CUT_LON;
    const out = [];
    for (let x = 0; x < n; x++) {
        for (let y = 0; y < n; y++) {
            const b = _tileLonLatBounds(z, x, y);
            const url = _radarTileUrl(meta, z, x, y);
            if (b.lonW < cut && b.lonE > cut) {
                const frac = (cut - b.lonW) / (b.lonE - b.lonW);
                const mid = Math.round(tileSize * frac);
                _pushRadarOverlayPiece(out, url, b.lonW, cut - 1e-6, b.latS, b.latN, 0, mid, tileSize);
                _pushRadarOverlayPiece(out, url, cut + 1e-6, b.lonE, b.latS, b.latN, mid, tileSize - mid, tileSize);
            } else {
                _pushRadarOverlayPiece(out, url, b.lonW, b.lonE, b.latS, b.latN, 0, tileSize, tileSize);
            }
        }
    }
    return out;
}

function _loadRadarTileImage(url) {
    let img = _radarTileImgCache.get(url);
    if (img) return img;
    img = new Image();
    img.crossOrigin = 'anonymous';
    img.decoding = 'async';
    img.onload = () => _scheduleRadarCanvasPaint();
    img.src = url;
    _radarTileImgCache.set(url, img);
    // 控制缓存体积
    if (_radarTileImgCache.size > 120) {
        const first = _radarTileImgCache.keys().next().value;
        _radarTileImgCache.delete(first);
    }
    return img;
}

function _ensureRadarCanvasHost() {
    const mapEl = document.getElementById('map-world');
    if (!mapEl) return null;
    let cv = document.getElementById('map-radar-canvas');
    if (!cv) {
        cv = document.createElement('canvas');
        cv.id = 'map-radar-canvas';
        cv.className = 'map-radar-canvas';
        cv.setAttribute('aria-hidden', 'true');
    }
    // 插到 ECharts 底图 canvas 与机场 canvas 之间，保证：底图 < 雷达 < 机场
    const layerRoot = mapEl.querySelector('div') || mapEl;
    const layerCanvases = [...layerRoot.querySelectorAll(':scope > canvas')].filter(c => c.id !== 'map-radar-canvas');
    if (layerCanvases.length >= 1) {
        const base = layerCanvases[0];
        if (cv.parentNode !== layerRoot || cv.previousSibling !== base) {
            if (base.nextSibling) layerRoot.insertBefore(cv, base.nextSibling);
            else layerRoot.appendChild(cv);
        }
    } else if (cv.parentNode !== mapEl) {
        mapEl.appendChild(cv);
    }
    cv.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;';
    return cv;
}

function _scheduleRadarCanvasPaint() {
    if (_radarPaintRaf) cancelAnimationFrame(_radarPaintRaf);
    // 双 rAF：等 ECharts 本帧底图变换完成后再按投影绘制，避免雷达“抢跑”
    _radarPaintRaf = requestAnimationFrame(() => {
        _radarPaintRaf = requestAnimationFrame(() => {
            _radarPaintRaf = 0;
            _paintRadarCanvas();
        });
    });
}

function _paintRadarCanvas() {
    if (!_mapChart) return;
    const cv = _ensureRadarCanvasHost();
    if (!cv) return;
    const mapEl = document.getElementById('map-world');
    if (!mapEl) return;
    const w = mapEl.clientWidth;
    const h = mapEl.clientHeight;
    if (w < 2 || h < 2) return;
    const dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
        cv.style.width = w + 'px';
        cv.style.height = h + 'px';
    }
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!_radarOverlayPieces.length) return;
    ctx.globalAlpha = _RADAR_OVERLAY_OPACITY;

    for (const p of _radarOverlayPieces) {
        let sw, ne;
        try {
            sw = _mapChart.convertToPixel({ geoIndex: 0 }, [p.lonW, p.latS]);
            ne = _mapChart.convertToPixel({ geoIndex: 0 }, [p.lonE, p.latN]);
        } catch (e) {
            continue;
        }
        if (!sw || !ne) continue;
        const x = Math.min(sw[0], ne[0]);
        const y = Math.min(sw[1], ne[1]);
        const width = Math.abs(ne[0] - sw[0]);
        const height = Math.abs(sw[1] - ne[1]);
        if (width < 1 || height < 1) continue;
        // 视口裁剪
        if (x + width < 0 || y + height < 0 || x > w || y > h) continue;
        const img = _loadRadarTileImage(p.url);
        if (!img.complete || !img.naturalWidth) continue;
        try {
            ctx.drawImage(
                img,
                p.sx, 0, p.sw, p.tileSize,
                x, y, width, height
            );
        } catch (e) { /* tainted / decode */ }
    }
    ctx.globalAlpha = 1;
}

function _bindRadarGeoRoamSync() {
    if (!_mapChart || _radarRoamBound) return;
    _radarRoamBound = true;
    _mapChart.on('georoam', () => _scheduleRadarCanvasPaint());
    _mapChart.on('finished', () => _scheduleRadarCanvasPaint());
}

function _applyRadarOverlay(meta) {
    if (!meta) return;
    const key = `${meta.frame_time}|${meta.path}|${meta.z}`;
    if (key === _radarOverlayFrame && _radarOverlayPieces.length) {
        _scheduleRadarCanvasPaint();
        return;
    }
    _radarOverlayMeta = meta;
    _radarOverlayFrame = key;
    _radarOverlayPieces = _buildRadarOverlayPieces(meta);
    // 预加载瓦片
    _radarOverlayPieces.forEach(p => _loadRadarTileImage(p.url));
    _scheduleRadarCanvasPaint();
}

function _fetchRainViewerOverlayFallback() {
    if (_radarOverlayPieces.length) return;
    fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then(r => r.json())
        .then(data => {
            const past = (data.radar && data.radar.past) || [];
            if (!past.length) return;
            const frame = past[past.length - 1];
            _applyRadarOverlay({
                host: (data.host || 'https://tilecache.rainviewer.com').replace(/\/$/, ''),
                path: frame.path,
                frame_time: frame.time,
                z: 3,
                tile_size: 256,
                color: 2,
                smooth: 0,
                snow: 0,
            });
        })
        .catch(err => console.warn('[雷达铺图] maps.json 失败', err));
}

function _applyRadarFloat(data) {
    _radarAlertCache = data || { alerts: [], watch: [] };
    const panel = document.getElementById('radar-alert-float');
    const body = document.getElementById('radar-alert-float-body');
    const tip = document.getElementById('radar-alert-rate-tip');
    if (!panel || !body) return;

    const alerts = (_radarAlertCache.alerts || []).filter(a =>
        a.alert_33 === 'R' || a.alert_33 === 'Y' || a.alert_41 === 'R' || a.alert_41 === 'Y'
    );
    panel.style.display = (window._viewMode === 'map') ? 'flex' : 'none';
    body.innerHTML = _renderRadarAlertRows(alerts);

    _radarBlinkCodes = new Set(alerts.map(a => a.airport_4code));
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
                ? `请求 ${rl.window_count}/${rl.max_per_minute || 80}`
                : '';
            tip.classList.remove('radar-alert-rate-warn');
        }
    }
    if (data.overlay) _applyRadarOverlay(data.overlay);
    else _fetchRainViewerOverlayFallback();
    if (typeof updateMapAlert === 'function' && _mapChart) {
        try { updateMapAlert(); } catch (e) { /* ignore */ }
    }
}

function _refreshRadarAlerts() {
    if (typeof currentTimeMode === 'undefined') return;
    fetch(`/${currentTimeMode}/api/radar/alerts/?include_g=1`, {
        headers: typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) _applyRadarFloat(data);
        })
        .catch(err => console.warn('[雷达告警] 拉取失败', err));
}

function _runRadarAlertFromFloat() {
    if (typeof currentTimeMode === 'undefined') return;
    const btn = document.getElementById('radar-alert-run-btn');
    if (btn) btn.disabled = true;
    fetch(`/${currentTimeMode}/api/radar/run/`, {
        method: 'POST',
        headers: {
            ...(typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}),
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ force: false })
    })
        .then(r => r.json())
        .then(() => {
            setTimeout(_refreshRadarAlerts, 1500);
            setTimeout(_refreshRadarAlerts, 8000);
        })
        .catch(err => console.warn('[雷达告警] 触发失败', err))
        .finally(() => { if (btn) btn.disabled = false; });
}

function _initRadarAlertFloat() {
    const drag = document.getElementById('radar-alert-float-drag');
    const panel = document.getElementById('radar-alert-float');
    if (drag && panel && !panel.dataset.dragBound) {
        panel.dataset.dragBound = '1';
        let ox = 0, oy = 0, dragging = false;
        drag.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            dragging = true;
            const rect = panel.getBoundingClientRect();
            const parent = panel.offsetParent || panel.parentElement;
            const parentRect = parent.getBoundingClientRect();
            // client 坐标 → 相对定位父元素坐标，避免点击瞬间向下跳
            ox = e.clientX - rect.left;
            oy = e.clientY - rect.top;
            panel.style.left = (rect.left - parentRect.left) + 'px';
            panel.style.top = (rect.top - parentRect.top) + 'px';
            panel.style.right = 'auto';
            e.preventDefault();
        });
        window.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            const parent = panel.offsetParent || panel.parentElement;
            const parentRect = parent.getBoundingClientRect();
            panel.style.left = Math.max(0, e.clientX - ox - parentRect.left) + 'px';
            panel.style.top = Math.max(0, e.clientY - oy - parentRect.top) + 'px';
            panel.style.right = 'auto';
        });
        window.addEventListener('mouseup', () => { dragging = false; });
    }
    const runBtn = document.getElementById('radar-alert-run-btn');
    if (runBtn && !runBtn.dataset.bound) {
        runBtn.dataset.bound = '1';
        runBtn.addEventListener('click', _runRadarAlertFromFloat);
    }
    const watchBtn = document.getElementById('radar-alert-watch-btn');
    const watchPanel = document.getElementById('radar-alert-watch-panel');
    const watchBody = document.getElementById('radar-alert-watch-body');
    const watchClose = document.getElementById('radar-alert-watch-close');
    if (watchBtn && watchPanel && watchBody) {
        watchBtn.onclick = () => {
            watchBody.innerHTML = _renderRadarAlertRows(_radarAlertCache.watch || []);
            watchPanel.style.display = 'flex';
        };
    }
    if (watchClose && watchPanel) {
        watchClose.onclick = () => { watchPanel.style.display = 'none'; };
    }
    if (_radarPollTimer) clearInterval(_radarPollTimer);
    _radarPollTimer = setInterval(() => {
        if (window._viewMode === 'map') _refreshRadarAlerts();
    }, 20000);
}
