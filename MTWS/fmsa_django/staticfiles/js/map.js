// ========================================
// 地图告警功能
// 依赖 main.js 中的全局变量/函数：
//   filteredAirportData, airportData, currentTimeMode
//   getSelectedAlertMargin(), getAlertColor(), getRequestHeaders(), handleFetchResponse()
// ========================================

// 全局视图模式：'list' | 'map'，由 switchViewMode 维护，main.js 读取
window._viewMode   = 'list';

let _mapView       = 'china';   // 'china' | 'world'
let _mapCoordCache = null;      // null = 未获取；{} = 已获取（可能为空）
let _mapChart      = null;
let _worldGeoReady = false;
let _flightStatusCache = null;  // { airport_4code: { ...5项实况 } }

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
        if (typeof applyFilters === 'function') applyFilters();
        setTimeout(() => {
            _syncPanelPosition();
            _initMapCharts();
        }, 30);
    } else {
        document.body.classList.remove('map-mode');
        if (panel) panel.style.display = 'none';
        _destroyMapCharts();
        if (typeof applyFilters === 'function') applyFilters();
    }
}

// ─────────────────────────────────────────────────────────────────
// 地图子视图切换：中国聚焦 ↔ 世界全图
// ─────────────────────────────────────────────────────────────────

function _switchMapView(view) {
    _mapView = view;
    localStorage.setItem('fmsa_map_view', view);
    if (_mapChart) {
        _mapChart.setOption({
            geo: view === 'china' ? _GEO_CHINA_VIEW : _GEO_WORLD_VIEW
        });
    }
}

// ─────────────────────────────────────────────────────────────────
// 面板定位
// ─────────────────────────────────────────────────────────────────

function _syncPanelPosition() {
    const panel = document.getElementById('map-alert-panel');
    if (!panel) return;

    const titleRow = document.querySelector('.content-section > .title-row');
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
    const c = { R: '#e74c3c', Y: '#f39c12', G: '#27ae60', N: '#7f8c8d' };
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
                ['已有航班前往本场', fmtBool(_fv != null ? _fv.en_route    : null, '#f39c12', '#7f8c8d')],
                ['是否有飞机停场',  fmtBool(_fv != null ? _fv.has_parking : null, '#e74c3c', '#7f8c8d')],
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
        return;
    }

    fetch(base + 'world_pacific.json')
        .then(r => { if (!r.ok) throw new Error('world_pacific.json 加载失败'); return r.json(); })
        .then(data => {
            echarts.registerMap('fmsa_world_pacific', data);
            _worldGeoReady = true;
            _createInstances();
            _fetchCoordsAndRender();
        })
        .catch(err => console.error('[地图告警] GeoJSON 加载失败:', err));
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
    }

    setTimeout(() => { if (_mapChart) _mapChart.resize(); }, 200);
}

// ─────────────────────────────────────────────────────────────────
// ECharts option 构建（三个系列：内圆 + 外圈闪烁 + 外圈静态）
// ─────────────────────────────────────────────────────────────────

function _buildMapOption() {
    const geoView = _mapView === 'china' ? _GEO_CHINA_VIEW : _GEO_WORLD_VIEW;

    return {
        backgroundColor: '#1b2838',
        tooltip: _makeTooltip(),
        geo: {
            map: 'fmsa_world_pacific',
            left: '10px', right: '10px', top: '10px', bottom: '10px',
            center: geoView.center,
            zoom: geoView.zoom,
            roam: true,
            silent: true,
            label: { show: false },
            emphasis: { disabled: true },
            itemStyle: {
                areaColor: '#1e3348',
                borderColor: '#3d6680',
                borderWidth: 0.5
            },
            regions: [
                {
                    name: 'French Southern and Antarctic Lands',
                    itemStyle: { opacity: 0, borderWidth: 0 },
                    label: { show: false }
                }
            ]
        },
        series: [
            // ① 外圈 - 闪烁（effectScatter，scale:1 原地透明度渐变，不向外扩散）
            {
                name: 'airports-outer-flash',
                type: 'effectScatter',
                coordinateSystem: 'geo',
                symbolSize: 16,
                rippleEffect: { period: 1.5, scale: 2.4, brushType: 'stroke' },
                data: [],
                label: { show: false },
                emphasis: { disabled: true },
                z: 4
            },
            // ② 外圈 - 静态（scatter，其余情况）
            {
                name: 'airports-outer-static',
                type: 'scatter',
                coordinateSystem: 'geo',
                symbolSize: 16,
                data: [],
                label: { show: false },
                emphasis: { disabled: true },
                z: 4
            },
            // ③ 内圆（scatter，TAF × 航班告警色，z最高保证tooltip优先触发）
            {
                name: 'airports-inner',
                type: 'scatter',
                coordinateSystem: 'geo',
                symbolSize: 10,
                data: [],
                label: { show: false },
                emphasis: { disabled: true },
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

    filteredAirportData.forEach(airport => {
        const code   = airport.airport_4code;
        const coords = _mapCoordCache[code];
        if (!coords) return;

        const pos = [_toLonPacific(coords.lon), coords.lat];

        // 从预计算结果中读取当前裕度的数据
        const marginResults = ((airport.computed_alerts || {})[`margin_${margin}`]) || {};

        // ── 内圆：TAF × 航班 最高告警色 ──
        const tafLevel = marginResults.taf_highest_alert || 'N';
        inner.push({
            name: code,
            value: pos,
            itemStyle: { color: _mapColor(tafLevel), opacity: 0.92 }
        });

        // ── 外圈：METAR 告警色，metar.popup ≠ N 时闪烁 ──
        const metar       = airport.metar_data && airport.metar_data[0];
        const metarLevel  = (metar && metar.metar_warning) || 'N';
        const ringColor   = _mapColor(metarLevel);
        const shouldFlash = !!(metar && metar.popup && metar.popup !== 'N');

        if (shouldFlash) {
            outerFlash.push({
                name: code,
                value: pos,
                // rippleEffect.color 覆盖涟漪颜色，使其不依赖 itemStyle.color
                rippleEffect: { color: ringColor },
                itemStyle: {
                    color: 'transparent',
                    borderColor: ringColor,
                    borderWidth: 2,
                    opacity: 0.85
                }
            });
        } else {
            outerStatic.push({
                name: code,
                value: pos,
                itemStyle: {
                    color: 'transparent',
                    borderColor: ringColor,
                    borderWidth: 2,
                    opacity: metarLevel === 'N' ? 0.4 : 0.85
                }
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

    _mapChart.setOption({
        series: [
            { name: 'airports-outer-flash',  data: outerFlash  },
            { name: 'airports-outer-static', data: outerStatic },
            { name: 'airports-inner',        data: inner       }
        ]
    });
}

// ─────────────────────────────────────────────────────────────────
// 销毁 & resize
// ─────────────────────────────────────────────────────────────────

function _destroyMapCharts() {
    if (_mapChart) { _mapChart.dispose(); _mapChart = null; }
}

let _resizeTimer = null;
window.addEventListener('resize', () => {
    if (_resizeTimer) clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(() => {
        if (window._viewMode === 'map') {
            _syncPanelPosition();
            if (_mapChart) _mapChart.resize();
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

function initMapAlertState() {
    const savedMode = localStorage.getItem('fmsa_view_mode') || 'list';
    window._viewMode = savedMode;

    const viewToggle = document.getElementById('view-mode-toggle-input');
    if (viewToggle) viewToggle.checked = (savedMode === 'map');

    const savedView = localStorage.getItem('fmsa_map_view');
    _mapView = savedView === 'world' ? 'world' : 'china';
    const mapViewToggle = document.getElementById('map-view-toggle-input');
    if (mapViewToggle) mapViewToggle.checked = (_mapView === 'world');

    if (savedMode === 'map') {
        document.body.classList.add('map-mode');
        const panel = document.getElementById('map-alert-panel');
        if (panel) panel.style.display = 'flex';
        setTimeout(_syncPanelPosition, 100);
        _initMapCharts();
    }
}
