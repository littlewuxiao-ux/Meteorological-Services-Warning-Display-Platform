// ============================================================
// 报文入库异常告警模块（实况 METAR + 预报 TAF）
// 依赖：main.js 中的全局变量 importAlerts / alertedAirports /
//       importAlertUnhandledCount / currentTimeMode / currentToken
// ============================================================

// ============================================================
// CSS 注入
// ============================================================
(function injectImportAlertStyles() {
    const style = document.createElement('style');
    style.id = 'import-alert-styles';
    style.textContent = `
/* 过期实况 weather-info 红色斜线背景 */
.weather-info.import-alerted {
    position: relative;
}
.weather-info.import-alerted::before {
    content: '';
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
        135deg,
        transparent 0px,
        transparent 8px,
        rgba(255, 0, 0, 0.3) 8px,
        rgba(255, 0, 0, 0.3) 16px
    );
    pointer-events: none;
    z-index: 0;
}
.weather-info.import-alerted .weather-info-container {
    position: relative;
    z-index: 1;
}

/* TAF入库告警 forecast-row 红色斜线背景 */
.forecast-row.taf-import-alerted {
    position: relative;
}
.forecast-row.taf-import-alerted::before {
    content: '';
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
        135deg,
        transparent 0px,
        transparent 8px,
        rgba(255, 0, 0, 0.3) 8px,
        rgba(255, 0, 0, 0.3) 16px
    );
    pointer-events: none;
    z-index: 2;
}

/* 入库视图：占满导航栏右侧、顶栏功能区以下的区域 */
#import-alert-panel {
    flex-direction: column;
    background: #fff;
    border-top: 1px solid #d5deea;
    overflow: hidden;
    min-height: 0;
    box-sizing: border-box;
}

.ia-panel-header {
    display: flex;
    align-items: center;
    padding: 12px 20px;
    background: #2c3e50;
    color: #fff;
    font-size: 15px;
    font-weight: bold;
    flex-shrink: 0;
    letter-spacing: 0.04em;
}

/* Tab 切换器 */
.ia-tab-bar {
    display: flex;
    flex-shrink: 0;
    background: #e8ecf0;
    border-bottom: 1px solid #ccc;
    overflow: hidden;
}
.ia-tab {
    flex: 0 0 auto;
    min-width: 168px;
    padding: 10px 28px;
    text-align: center;
    font-size: 14px;
    font-weight: bold;
    cursor: pointer;
    color: #666;
    transition: background 0.15s, color 0.15s;
    user-select: none;
    border-right: 1px solid #ccc;
}
.ia-tab:last-child { border-right: none; }
.ia-tab:hover { background: #dde3e9; }
.ia-tab.active {
    background: #fff;
    color: #2c3e50;
    border-bottom: 2px solid #2c3e50;
    margin-bottom: -1px;
}

/* 表格头与行共用列宽，随视图宽度拉伸 */
.ia-table-head,
.ia-row-main {
    display: grid;
    grid-template-columns:
        minmax(88px, 0.7fr)
        minmax(72px, 0.55fr)
        minmax(168px, 1.15fr)
        minmax(188px, 1.35fr)
        minmax(168px, 1.15fr)
        minmax(160px, 1.3fr);
    column-gap: 12px;
    align-items: center;
}
.ia-table-head {
    padding: 10px 20px;
    background: #f0f2f5;
    border-bottom: 1px solid #ddd;
    font-size: 13px;
    font-weight: bold;
    color: #555;
    flex-shrink: 0;
}
.ia-table-head span {
    white-space: normal;
    line-height: 1.35;
}
.ia-head-alert { color: red; }

/* 告警列表滚动区 */
.ia-list {
    overflow-y: auto;
    flex: 1;
    min-height: 0;
}

/* 每条告警 */
.ia-row {
    border-bottom: 1px solid #eee;
}
.ia-row-main {
    padding: 10px 20px;
    font-size: 14px;
}
.ia-row-main:hover { background: #fafafa; }
.ia-row.unhandled .ia-row-main { background: #fffbe6; }
.ia-row.unhandled .ia-row-main:hover { background: #fff8d6; }

.ia-cell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ia-red { color: red; font-weight: bold; }
.ia-handle-btn {
    color: #555;
    cursor: default;
    border-radius: 3px;
    padding: 2px 6px;
    transition: background 0.15s, color 0.15s;
}
.ia-handle-btn.hovering {
    background: #c0392b;
    color: #fff;
    font-weight: bold;
    cursor: pointer;
}
.ia-handle-time { color: #888; cursor: pointer; }
.ia-handle-time:hover { text-decoration: underline; }

/* 展开的处理选项区 */
.ia-expand {
    padding: 10px 20px 12px 20px;
    background: #f9f9f9;
    border-top: 1px dashed #ddd;
    font-size: 13px;
}
.ia-expand-options {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    margin-bottom: 8px;
}
.ia-expand-options label {
    display: flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;
}
.ia-confirm-btn {
    padding: 4px 16px;
    border: none;
    border-radius: 4px;
    background: #bbb;
    color: #fff;
    cursor: not-allowed;
    font-size: 12px;
    transition: background 0.15s;
}
.ia-confirm-btn.active {
    background: #27ae60;
    cursor: pointer;
}
.ia-confirm-btn.active:hover { background: #219a52; }

/* 只读处理详情 */
.ia-detail-expand {
    padding: 6px 14px 8px 14px;
    background: #f0f8ff;
    border-top: 1px dashed #b3d9f7;
    font-size: 12px;
    color: #444;
}

/* 分页 */
.ia-pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 6px;
    padding: 10px 16px;
    background: #f0f2f5;
    border-top: 1px solid #ddd;
    flex-shrink: 0;
    font-size: 13px;
}
.ia-page-btn {
    padding: 2px 8px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: #fff;
    cursor: pointer;
    font-size: 12px;
}
.ia-page-btn:hover { background: #e8e8e8; }
.ia-page-btn.current { background: #2c3e50; color: #fff; border-color: #2c3e50; cursor: default; }
.ia-page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
`;
    document.head.appendChild(style);
})();

// ============================================================
// 模块状态：TAF 专用（METAR 状态在 main.js 中定义）
// ============================================================
let tafAlerts = [];
let tafAlertedAirports = new Set();
let tafAlertUnhandledCount = 0;
let tafAlertCurrentPage = 1;
let tafAlertTotalPages = 1;
let tafAlertExpandedId = null;
let tafAlertDetailOpenId = null;

// 当前激活的 Tab：'metar' | 'taf'
let currentAlertTab = 'metar';

// ============================================================
// 辅助：生成 weather-info div（供 main.js 的 buildWeatherInfoDiv 调用）
// ============================================================
function buildWeatherInfoDiv(airportCode, latestMetar) {
    const isAlerted = typeof alertedAirports !== 'undefined' && alertedAirports.has(airportCode);
    const alertClass = isAlerted ? ' import-alerted' : '';
    const alertTitle = isAlerted ? ' title="【过期实况数据，注意提醒】"' : '';
    const styleAttr = latestMetar ? getWeatherInfoStyle(latestMetar) : '';
    const inner = latestMetar
        ? createWeatherInfo(latestMetar)
        : '<div class="no-data">无METAR数据</div>';
    return `<div class="weather-info${alertClass}"${alertTitle} ${styleAttr}>${inner}</div>`;
}

// ============================================================
// 从已加载的 metar 数据同步 METAR 告警状态（由 main.js 调用）
// ============================================================
function syncAlertStateFromMetarData(airports) {
    alertedAirports = new Set();
    importAlertUnhandledCount = 0;

    (airports || []).forEach(airport => {
        const metar = airport.metar_data && airport.metar_data[0];
        if (!metar || metar.import_alert !== 'Y') return;
        alertedAirports.add(airport.airport_4code);
        if (!metar.import_alert_handle_time) importAlertUnhandledCount++;
    });

    _updateAlertBadge();
}

// ============================================================
// 从已加载的 taf 数据同步 TAF 告警状态（由 main.js 调用）
// ============================================================
function syncAlertStateFromTafData(airports) {
    tafAlertedAirports = new Set();
    tafAlertUnhandledCount = 0;

    (airports || []).forEach(airport => {
        const taf = airport.taf_data && airport.taf_data[0];
        if (!taf || taf.import_alert !== 'Y') return;
        tafAlertedAirports.add(airport.airport_4code);
        if (!taf.import_alert_handle_time) tafAlertUnhandledCount++;
    });

    _updateAlertBadge();
}

// ============================================================
// 徽章更新：导航图标右上角显示实况 + 预报未处理合计
// ============================================================
function _updateAlertBadge() {
    updateImportAlertNavBadge();

    const tabMetar = document.getElementById('ia-tab-metar');
    const tabTaf = document.getElementById('ia-tab-taf');
    if (tabMetar) tabMetar.textContent = `实况 METAR${importAlertUnhandledCount > 0 ? ' (' + importAlertUnhandledCount + ')' : ''}`;
    if (tabTaf) tabTaf.textContent = `预报 TAF${tafAlertUnhandledCount > 0 ? ' (' + tafAlertUnhandledCount + ')' : ''}`;
}

function updateImportAlertNavBadge() {
    const btn = document.querySelector('.view-nav-item[data-view="import"]');
    if (!btn) return;
    const total = (Number(importAlertUnhandledCount) || 0) + (Number(tafAlertUnhandledCount) || 0);
    let badge = btn.querySelector('.view-nav-badge');
    if (total <= 0) {
        if (badge) badge.remove();
        return;
    }
    if (!badge) {
        badge = document.createElement('span');
        badge.className = 'view-nav-badge';
        btn.appendChild(badge);
    }
    badge.textContent = String(total);
}

// ============================================================
// 数据拉取 — METAR
// ============================================================
function fetchImportAlerts(page) {
    page = page || importAlertCurrentPage || 1;
    const headers = _authHeaders();
    fetch(`/${currentTimeMode}/api/import-alerts/?page=${page}`, { headers })
        .then(r => r.json())
        .then(data => {
            if (!data.success) { _renderAlertPanel(); return; }
            importAlerts = data.alerts || [];
            importAlertCurrentPage = data.current_page || 1;
            importAlertTotalPages = data.total_pages || 1;
            _renderAlertPanel();
        })
        .catch(err => console.error('fetchImportAlerts 失败:', err));
}

// ============================================================
// 数据拉取 — TAF
// ============================================================
function fetchTafImportAlerts(page) {
    page = page || tafAlertCurrentPage || 1;
    const headers = _authHeaders();
    fetch(`/${currentTimeMode}/api/taf-import-alerts/?page=${page}`, { headers })
        .then(r => r.json())
        .then(data => {
            if (!data.success) { _renderAlertPanel(); return; }
            tafAlerts = data.alerts || [];
            tafAlertCurrentPage = data.current_page || 1;
            tafAlertTotalPages = data.total_pages || 1;
            _renderAlertPanel();
        })
        .catch(err => console.error('fetchTafImportAlerts 失败:', err));
}

// ============================================================
// 入库视图：绑定页签，并按顶栏实际高度撑满剩余视口
// ============================================================
let _importPanelBound = false;

function syncImportAlertLayout() {
    const panel = document.getElementById('import-alert-panel');
    if (!panel || panel.style.display === 'none') return;
    const chrome = document.querySelector('.page-chrome');
    const top = chrome ? Math.max(0, chrome.getBoundingClientRect().bottom) : 0;
    panel.style.height = Math.max(240, window.innerHeight - top) + 'px';
}

function _bindImportAlertPanel() {
    if (_importPanelBound) return;
    const tabMetar = document.getElementById('ia-tab-metar');
    const tabTaf = document.getElementById('ia-tab-taf');
    if (!tabMetar || !tabTaf) return;
    tabMetar.addEventListener('click', function () { _switchTab('metar'); });
    tabTaf.addEventListener('click', function () { _switchTab('taf'); });
    window.addEventListener('resize', syncImportAlertLayout);
    const chrome = document.querySelector('.page-chrome');
    if (chrome && typeof ResizeObserver === 'function') {
        new ResizeObserver(syncImportAlertLayout).observe(chrome);
    }
    _importPanelBound = true;
}

function startImportView() {
    _bindImportAlertPanel();
    const tafHasUnhandled = tafAlertUnhandledCount > 0;
    const metarHasUnhandled = importAlertUnhandledCount > 0;
    const defaultTab = (tafHasUnhandled && !metarHasUnhandled) ? 'taf' : 'metar';
    _switchTab(defaultTab, false);
    _fetchCurrentTab();
    _updateAlertBadge();
    syncImportAlertLayout();
}

function stopImportView() {}

window.startImportView = startImportView;
window.stopImportView = stopImportView;
window.updateImportAlertNavBadge = updateImportAlertNavBadge;
window.syncImportAlertLayout = syncImportAlertLayout;

function _switchTab(tab, fetchData) {
    currentAlertTab = tab;
    // 重置展开状态
    importAlertExpandedId = null;
    importAlertDetailOpenId = null;
    tafAlertExpandedId = null;
    tafAlertDetailOpenId = null;

    const tabMetar = document.getElementById('ia-tab-metar');
    const tabTaf = document.getElementById('ia-tab-taf');
    if (tabMetar) tabMetar.classList.toggle('active', tab === 'metar');
    if (tabTaf) tabTaf.classList.toggle('active', tab === 'taf');

    if (fetchData !== false) {
        _fetchCurrentTab();
    }
}

function _fetchCurrentTab() {
    if (currentAlertTab === 'taf') {
        fetchTafImportAlerts(tafAlertCurrentPage);
    } else {
        fetchImportAlerts(importAlertCurrentPage);
    }
}

// ============================================================
// 面板渲染（根据当前 Tab 路由）
// ============================================================
function _renderAlertPanel() {
    if (currentAlertTab === 'taf') {
        _renderTafAlertPanel();
    } else {
        _renderMetarAlertPanel();
    }
}

// --- METAR 面板渲染 ---
function _renderMetarAlertPanel() {
    const list = document.getElementById('ia-list');
    const pag = document.getElementById('ia-pagination');
    if (!list || !pag) return;

    if (importAlerts.length === 0) {
        list.innerHTML = '<div style="padding:20px;text-align:center;color:#999;font-size:13px;">暂无实况告警记录</div>';
        pag.innerHTML = '';
        return;
    }

    list.innerHTML = importAlerts.map(a => _renderAlertRow(a)).join('');
    _renderPagination(pag, importAlertCurrentPage, importAlertTotalPages, 'metar');
    _bindRowEvents(list);
}

// --- TAF 面板渲染 ---
function _renderTafAlertPanel() {
    const list = document.getElementById('ia-list');
    const pag = document.getElementById('ia-pagination');
    if (!list || !pag) return;

    if (tafAlerts.length === 0) {
        list.innerHTML = '<div style="padding:20px;text-align:center;color:#999;font-size:13px;">暂无预报告警记录</div>';
        pag.innerHTML = '';
        return;
    }

    list.innerHTML = tafAlerts.map(a => _renderTafAlertRow(a)).join('');
    _renderPagination(pag, tafAlertCurrentPage, tafAlertTotalPages, 'taf');
    _bindRowEvents(list);
}

// ============================================================
// METAR 行渲染
// ============================================================
function _renderAlertRow(a) {
    const isUnhandled = !a.import_alert_handle_time;
    const rowClass = isUnhandled ? 'unhandled' : '';
    const rowKey = btoa(unescape(encodeURIComponent(a.sqc)));

    const alertTimeStr = _fmtTs(a.import_alert_time);
    const latestIssueStr = _fmtTs(a.metar_observation_time);
    const expectedStr = _metarExpectedIssueText(a);

    const handleCell = _buildHandleCell(a, rowKey, isUnhandled, 'metar');
    const expandHtml = _renderExpandSection(a, rowKey, 'metar');

    return `
<div class="ia-row ${rowClass}" id="ia-row-${rowKey}">
    <div class="ia-row-main">
        <span class="ia-cell">${a.airport_4code}</span>
        <span class="ia-cell">${a.metar_type || '—'}</span>
        <span class="ia-cell">${alertTimeStr}</span>
        <span class="ia-cell">${latestIssueStr}</span>
        <span class="ia-cell">${expectedStr}</span>
        <span class="ia-cell">${handleCell}</span>
    </div>
    ${expandHtml}
</div>`;
}

// ============================================================
// TAF 行渲染
// ============================================================
function _renderTafAlertRow(a) {
    const isUnhandled = !a.import_alert_handle_time;
    const rowClass = isUnhandled ? 'unhandled' : '';
    const rowKey = btoa(unescape(encodeURIComponent(a.sqc)));

    const alertTimeStr = _fmtTs(a.import_alert_time);
    const latestIssueStr = _fmtTs(a.taf_observation_time);
    const expectedStr = _fmtTs(a.expected_issue_time);

    const handleCell = _buildHandleCell(a, rowKey, isUnhandled, 'taf');
    const expandHtml = _renderExpandSection(a, rowKey, 'taf');

    return `
<div class="ia-row ${rowClass}" id="ia-row-${rowKey}">
    <div class="ia-row-main">
        <span class="ia-cell">${a.airport_4code}</span>
        <span class="ia-cell">${a.taf_type || '—'}</span>
        <span class="ia-cell">${alertTimeStr}</span>
        <span class="ia-cell">${latestIssueStr}</span>
        <span class="ia-cell">${expectedStr}</span>
        <span class="ia-cell">${handleCell}</span>
    </div>
    ${expandHtml}
</div>`;
}

// ============================================================
// 公用：构建处理结果单元格
// ============================================================
function _buildHandleCell(a, rowKey, isUnhandled, tab) {
    if (isUnhandled) {
        return `<span class="ia-handle-btn" data-sqc="${a.sqc}"
            onmouseenter="this.classList.add('hovering');this.textContent='去处理'"
            onmouseleave="this.classList.remove('hovering');this.textContent='未处理'"
            onclick="_onClickHandle('${rowKey}','${tab}')">未处理</span>`;
    }
    const handleTimeStr = _fmtTs(a.import_alert_handle_time);
    return `<span class="ia-handle-time" onclick="_onClickHandleTime('${rowKey}','${tab}')"
        title="点击查看处理详情">${handleTimeStr}</span>`;
}

// ============================================================
// 公用：展开区域（操作 or 只读详情）
// ============================================================
function _renderExpandSection(a, rowKey, tab) {
    const isUnhandled = !a.import_alert_handle_time;

    if (!isUnhandled) {
        return `<div class="ia-detail-expand" id="ia-detail-${rowKey}" style="display:none">
            处理结果：${a.handle_status || ''}
        </div>`;
    }

    return `<div class="ia-expand" id="ia-expand-${rowKey}" style="display:none">
        <div class="ia-expand-options">
            <label><input type="checkbox" name="opt_${rowKey}" value="评估无影响"> 评估无影响</label>
            <label><input type="checkbox" name="opt_${rowKey}" value="通知签派"> 通知签派</label>
            <label><input type="checkbox" name="opt_${rowKey}" value="维护报文" data-mutex="维护报文"> 维护报文</label>
            <label><input type="checkbox" name="opt_${rowKey}" value="其他官方途径未查询到报文" data-mutex="维护报文"> 其他官方途径未查询到报文</label>
        </div>
        <button class="ia-confirm-btn" id="ia-confirm-${rowKey}" disabled
            onclick="_onConfirm('${rowKey}','${a.sqc}','${tab}')">确认</button>
    </div>`;
}

// ============================================================
// 分页渲染（参数化）
// ============================================================
function _renderPagination(container, currentPage, totalPages, tab) {
    if (totalPages <= 1) {
        const count = tab === 'taf' ? tafAlerts.length : importAlerts.length;
        container.innerHTML = `<span style="color:#999">共 ${count} 条</span>`;
        return;
    }
    const fetchFn = tab === 'taf' ? 'fetchTafImportAlerts' : 'fetchImportAlerts';
    let html = '';
    html += `<button class="ia-page-btn" ${currentPage <= 1 ? 'disabled' : ''}
        onclick="${fetchFn}(${currentPage - 1})">&#8249;</button>`;
    for (let p = 1; p <= totalPages; p++) {
        const cls = p === currentPage ? 'current' : '';
        html += `<button class="ia-page-btn ${cls}" onclick="${fetchFn}(${p})">${p}</button>`;
    }
    html += `<button class="ia-page-btn" ${currentPage >= totalPages ? 'disabled' : ''}
        onclick="${fetchFn}(${currentPage + 1})">&#8250;</button>`;
    container.innerHTML = html;
}

// ============================================================
// 行事件绑定（checkbox change）
// ============================================================
function _bindRowEvents(list) {
    list.querySelectorAll('input[type=checkbox]').forEach(cb => {
        cb.addEventListener('change', function () {
            const rowKey = this.name.replace('opt_', '');
            _handleCheckboxChange(rowKey, this);
        });
    });
}

function _handleCheckboxChange(rowKey, changedCb) {
    if (changedCb.checked && changedCb.dataset.mutex) {
        const mutexVal = changedCb.dataset.mutex;
        const container = document.getElementById(`ia-expand-${rowKey}`);
        if (container) {
            container.querySelectorAll(`input[data-mutex="${mutexVal}"]`).forEach(other => {
                if (other !== changedCb) other.checked = false;
            });
        }
    }
    _updateConfirmBtn(rowKey);
}

function _updateConfirmBtn(rowKey) {
    const container = document.getElementById(`ia-expand-${rowKey}`);
    const btn = document.getElementById(`ia-confirm-${rowKey}`);
    if (!container || !btn) return;
    const anyChecked = Array.from(
        container.querySelectorAll('input[type=checkbox]')
    ).some(cb => cb.checked);
    btn.disabled = !anyChecked;
    btn.classList.toggle('active', anyChecked);
}

// ============================================================
// 点击"去处理"：展开操作区
// ============================================================
function _onClickHandle(rowKey, tab) {
    tab = tab || currentAlertTab;
    const expandedRef = tab === 'taf' ? 'tafAlertExpandedId' : 'importAlertExpandedId';

    const prevId = tab === 'taf' ? tafAlertExpandedId : importAlertExpandedId;
    if (prevId && prevId !== rowKey) {
        const prev = document.getElementById(`ia-expand-${prevId}`);
        if (prev) prev.style.display = 'none';
    }
    const expand = document.getElementById(`ia-expand-${rowKey}`);
    if (!expand) return;
    const isOpen = expand.style.display !== 'none';
    expand.style.display = isOpen ? 'none' : 'block';
    const newId = isOpen ? null : rowKey;
    if (tab === 'taf') tafAlertExpandedId = newId;
    else importAlertExpandedId = newId;
}

// ============================================================
// 点击已处理时间：展开/收起只读详情
// ============================================================
function _onClickHandleTime(rowKey, tab) {
    tab = tab || currentAlertTab;
    const prevId = tab === 'taf' ? tafAlertDetailOpenId : importAlertDetailOpenId;
    if (prevId && prevId !== rowKey) {
        const prev = document.getElementById(`ia-detail-${prevId}`);
        if (prev) prev.style.display = 'none';
    }
    const detail = document.getElementById(`ia-detail-${rowKey}`);
    if (!detail) return;
    const isOpen = detail.style.display !== 'none';
    detail.style.display = isOpen ? 'none' : 'block';
    const newId = isOpen ? null : rowKey;
    if (tab === 'taf') tafAlertDetailOpenId = newId;
    else importAlertDetailOpenId = newId;
}

// ============================================================
// 点击"确认"按钮：提交处理结果
// ============================================================
function _onConfirm(rowKey, sqc, tab) {
    tab = tab || currentAlertTab;
    const container = document.getElementById(`ia-expand-${rowKey}`);
    if (!container) return;
    const checked = Array.from(
        container.querySelectorAll('input[type=checkbox]:checked')
    ).map(cb => cb.value);
    if (checked.length === 0) return;

    if (typeof hasAccess === 'function' && !hasAccess('import_alert', 'write')) {
        // 可处理界面，但不写库
        container.style.display = 'none';
        alert('当前角色无入库告警写入权限，处理结果不会保存到数据库');
        return;
    }

    const handleTime = Date.now();
    const handleStatus = checked.join('、');
    const endpoint = tab === 'taf' ? 'taf-import-alerts' : 'import-alerts';

    const headers = { 'Content-Type': 'application/json', ..._authHeaders() };
    fetch(`/${currentTimeMode}/api/${endpoint}/handle/`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ sqc: sqc, import_alert_handle_time: handleTime, handle_status: handleStatus }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            container.style.display = 'none';
            if (tab === 'taf') {
                tafAlertExpandedId = null;
                fetchTafImportAlerts(tafAlertCurrentPage);
            } else {
                importAlertExpandedId = null;
                fetchImportAlerts(importAlertCurrentPage);
            }
            if (typeof applyFilters === 'function') applyFilters();
        } else if (data.error) {
            alert(data.error);
        }
    })
    .catch(() => {});
}

// ============================================================
// 工具函数
// ============================================================
function _authHeaders() {
    if (typeof currentTimeMode !== 'undefined' && currentTimeMode === 'current'
            && typeof currentToken !== 'undefined' && currentToken) {
        return { 'Authorization': `Bearer ${currentToken}` };
    }
    return {};
}

/**
 * 毫秒 UTC 时间戳（数字或字符串均可）→ 时间字符串。
 * 跟随 window.displayTimezone：
 *   'UTC' → 显示 UTC 时间并附加 " UTC" 后缀
 *   其他  → 显示 CST（UTC+8）时间
 */
function _fmtTs(ts) {
    if (!ts) return '--';
    try {
        const num = Number(ts);
        if (isNaN(num)) return '--';
        const pad = n => String(n).padStart(2, '0');
        if (window.displayTimezone === 'UTC') {
            const d = new Date(num);
            return `${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} `
                 + `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
        }
        // CST = UTC+8，通过偏移后用 UTC 方法取值，避免依赖浏览器本地时区
        const cst = new Date(num + 8 * 3600 * 1000);
        return `${pad(cst.getUTCMonth()+1)}-${pad(cst.getUTCDate())} `
             + `${pad(cst.getUTCHours())}:${pad(cst.getUTCMinutes())}:${pad(cst.getUTCSeconds())}`;
    } catch (e) { return '--'; }
}

/** 实况应发时间：未处理取当前整点，已处理停在告警发生时的整点。显示时区跟随 UTC/CST 开关。 */
function _floorUtcHour(ts) {
    const num = Number(ts);
    if (!num || isNaN(num)) return null;
    return Math.floor(num / 3600000) * 3600000;
}

function _metarExpectedIssueText(a) {
    const ref = a.import_alert_handle_time ? a.import_alert_time : Date.now();
    return _fmtTs(_floorUtcHour(ref));
}

_bindImportAlertPanel();
