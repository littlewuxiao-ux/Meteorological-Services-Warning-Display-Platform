// ==================================
// 实况弹窗功能模块
// ==================================
// 注意：本文件依赖main.js中的全局变量：
// - popupCheckInterval, popupAirports, currentActiveAirport
// - snoozeEndTime, snoozedPopups, tabScrollOffset
// - originalTitle, originalFavicon, isShowingPopupAlert
// - currentToken, currentUserCode, currentTimeMode

// ==================================
// 页面提示和Favicon相关
// ==================================

function getDefaultFaviconHref() {
    const link = document.getElementById('mtws-favicon') || document.querySelector("link[rel*='icon']");
    if (link && link.getAttribute('href')) return link.href;
    return '/static/svg/mtws-favicon.svg';
}

function initDefaultFavicon() {
    let link = document.getElementById('mtws-favicon') || document.querySelector("link[rel*='icon']");
    if (!link) {
        link = document.createElement('link');
        link.rel = 'icon';
        link.type = 'image/svg+xml';
        link.id = 'mtws-favicon';
        link.href = getDefaultFaviconHref();
        document.head.appendChild(link);
    }
    originalFavicon = link.href || getDefaultFaviconHref();
}
initDefaultFavicon();

// 生成红色方框+白色NEW的favicon
function generateNewPopupFavicon() {
    const canvas = document.createElement('canvas');
    canvas.width = 32;
    canvas.height = 32;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = (typeof getAlertColorHex === 'function') ? getAlertColorHex('R') : '#e74c3c';
    ctx.fillRect(0, 0, 32, 32);

    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 14px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('NEW', 16, 16);

    return canvas.toDataURL();
}

let _titleFlashTimer = null;
let _titleFlashOn = true;

function applyPopupAlertVisual(alertOn) {
    document.title = alertOn ? `【新弹窗】${originalTitle}` : originalTitle;
    const link = document.getElementById('mtws-favicon') || document.querySelector("link[rel*='icon']");
    if (!link) return;
    link.href = alertOn ? generateNewPopupFavicon() : (originalFavicon || getDefaultFaviconHref());
}

function stopTitleFlash() {
    if (_titleFlashTimer) {
        clearInterval(_titleFlashTimer);
        _titleFlashTimer = null;
    }
}

function startTitleFlash() {
    if (_titleFlashTimer) return;
    _titleFlashOn = true;
    _titleFlashTimer = setInterval(() => {
        _titleFlashOn = !_titleFlashOn;
        applyPopupAlertVisual(_titleFlashOn);
    }, 800);
}

function updatePopupAlert() {
    const hasPopups = Object.keys(popupAirports).length > 0;
    const isPageHidden = document.hidden;

    if (hasPopups && isPageHidden) {
        if (!isShowingPopupAlert) {
            applyPopupAlertVisual(true);
            isShowingPopupAlert = true;
            startTitleFlash();
        }
    } else {
        if (isShowingPopupAlert) {
            stopTitleFlash();
            applyPopupAlertVisual(false);
            isShowingPopupAlert = false;
        }
    }
}

document.addEventListener('visibilitychange', updatePopupAlert);

// ==================================
// 稍后处理功能
// ==================================

// 从localStorage加载稍后处理状态
function loadSnoozeState() {
    const snoozeData = localStorage.getItem('mtws_popup_snooze');
    if (snoozeData) {
        try {
            const data = JSON.parse(snoozeData);
            snoozeEndTime = data.endTime;
            snoozedPopups = data.sqcList || [];

            // 检查是否已过期
            if (snoozeEndTime && Date.now() > snoozeEndTime) {
                clearSnoozeState();
            } else {
                updateSnoozeRestoreBtn();
            }
        } catch (e) {
            console.error('加载稍后处理状态失败:', e);
            clearSnoozeState();
        }
    }
}

// 清除稍后处理状态
function clearSnoozeState() {
    snoozeEndTime = null;
    snoozedPopups = [];
    localStorage.removeItem('mtws_popup_snooze');
    updateSnoozeRestoreBtn();
}

// 保存稍后处理状态
function saveSnoozeState(endTime, sqcList) {
    snoozeEndTime = endTime;
    snoozedPopups = sqcList;
    localStorage.setItem('mtws_popup_snooze', JSON.stringify({
        endTime: endTime,
        sqcList: sqcList
    }));
    updateSnoozeRestoreBtn();
}

// 检查弹窗是否应该被隐藏（稍后处理）
function shouldHidePopup(sqc) {
    if (!snoozeEndTime) return false;

    // 检查是否过期
    if (Date.now() > snoozeEndTime) {
        clearSnoozeState();
        return false;
    }

    return true; // 在稍后处理期间，隐藏所有弹窗
}

// 更新稍后处理恢复按钮状态
function updateSnoozeRestoreBtn() {
    const btn = document.getElementById('snooze-restore-btn');
    if (!btn) return;
    const hasSnooze = snoozeEndTime && Date.now() < snoozeEndTime && snoozedPopups.length > 0;
    if (hasSnooze) {
        btn.classList.add('snooze-restore-active');
        btn.classList.remove('snooze-restore-inactive');
        btn.title = '恢复被暂时关闭的实况弹窗';
    } else {
        btn.classList.add('snooze-restore-inactive');
        btn.classList.remove('snooze-restore-active');
        btn.title = '没有可恢复的实况弹窗';
    }
}

// 处理稍后处理恢复按钮点击
async function handleSnoozeRestore() {
    const hasSnooze = snoozeEndTime && Date.now() < snoozeEndTime && snoozedPopups.length > 0;
    if (!hasSnooze) {
        await showInfoDialog('没有可恢复的实况弹窗');
        return;
    }
    clearSnoozeState();
    await checkAndShowPopups();
}

// 显示信息对话框（单按钮）
function showInfoDialog(message) {
    return new Promise((resolve) => {
        const overlayHTML = `
            <div class="popup-confirm-overlay">
                <div class="popup-confirm-modal">
                    <div class="popup-confirm-message">${message}</div>
                    <div class="popup-confirm-buttons">
                        <button class="popup-confirm-btn popup-confirm-btn-ok">确定</button>
                    </div>
                </div>
            </div>
        `;
        const div = document.createElement('div');
        div.innerHTML = overlayHTML;
        const overlay = div.firstElementChild;
        overlay.querySelector('.popup-confirm-btn-ok').onclick = () => {
            overlay.remove();
            resolve();
        };
        document.body.appendChild(overlay);
    });
}

// ==================================
// 弹窗数据处理
// ==================================

// 按机场分组弹窗数据
function groupPopupsByAirport(popupList) {
    const grouped = {};

    popupList.forEach(popup => {
        const airport = popup.airport_4code;
        if (!grouped[airport]) {
            grouped[airport] = [];
        }
        grouped[airport].push(popup);
    });

    // 对每个机场的弹窗按popup_time排序（最新在前）
    Object.keys(grouped).forEach(airport => {
        grouped[airport].sort((a, b) => b.popup_time - a.popup_time);
    });

    return grouped;
}

// 获取机场的最新弹窗
function getLatestPopup(airportPopups) {
    if (!airportPopups || airportPopups.length === 0) return null;
    return airportPopups[0]; // 已经排序过，第一个就是最新的
}

function metarObservationTime(metar) {
    if (!metar || metar.metar_observation_time == null || metar.metar_observation_time === '') return -Infinity;
    const t = Number(metar.metar_observation_time);
    return Number.isFinite(t) ? t : -Infinity;
}

// 主页天气类型为 {代码: 等级} 或 JSON 字符串；弹窗为 {代码: {alert_level, cn_name}}
function normalizeWeatherTypeForBadges(weather, nameLookupPopups) {
    if (!weather) return {};
    let raw = weather;
    if (typeof raw === 'string') {
        try {
            raw = JSON.parse(raw) || {};
        } catch (e) {
            return {};
        }
    }
    const result = {};
    Object.entries(raw).forEach(([code, value]) => {
        if (value && typeof value === 'object' && !Array.isArray(value)) {
            result[code] = {
                alert_level: value.alert_level,
                cn_name: weatherTypeBadgeName(code, value)
            };
            return;
        }
        let cnName = code;
        (nameLookupPopups || []).some(p => {
            const info = p.metar_weather_type && p.metar_weather_type[code];
            if (info && info.cn_name) {
                cnName = info.cn_name;
                return true;
            }
            return false;
        });
        result[code] = { alert_level: value, cn_name: weatherTypeBadgeName(code, { cn_name: cnName }) };
    });
    return result;
}

const WEATHER_TYPE_CN_FALLBACK = { R: '近时天气' };
const ALERT_LEVEL_LETTERS = { R: 1, Y: 1, G: 1, N: 1 };

function weatherTypeBadgeName(code, info) {
    const name = info && info.cn_name != null ? String(info.cn_name).trim() : '';
    if (name && !ALERT_LEVEL_LETTERS[name]) return name;
    if (WEATHER_TYPE_CN_FALLBACK[code]) return WEATHER_TYPE_CN_FALLBACK[code];
    if (code && !ALERT_LEVEL_LETTERS[code]) return code;
    return code === 'R' ? '近时天气' : (code || '天气现象');
}

// 实心：主页最新实况与未处理弹窗中观测时间最大的一份；空心：观测时间更早的未处理弹窗
function resolveBadgeSources(popupData, airportPopups) {
    let homepageLatest = null;
    const airportCode = popupData && popupData.airport_4code;
    if (airportCode && typeof airportData !== 'undefined' && airportData) {
        const airport = airportData.find(a => a.airport_4code === airportCode);
        if (airport && airport.metar_data && airport.metar_data.length > 0) {
            homepageLatest = airport.metar_data[0];
        }
    }

    const popups = airportPopups || [];
    const candidates = homepageLatest ? [homepageLatest].concat(popups) : popups.slice();
    if (popupData && candidates.indexOf(popupData) === -1) {
        candidates.push(popupData);
    }

    let solidSource = null;
    let solidTime = -Infinity;
    candidates.forEach(m => {
        const t = metarObservationTime(m);
        if (t > solidTime) {
            solidTime = t;
            solidSource = m;
        }
    });

    const historyPopups = popups.filter(p => metarObservationTime(p) < solidTime);
    return { solidSource, historyPopups };
}

// ==================================
// HTML生成函数
// ==================================

// 告警等级序：R>Y>G
function warningLevelRank(level) {
    if (!level || level === 'N') return 0;
    if (level === 'R') return 3;
    if (level === 'Y') return 2;
    if (level === 'G') return 1;
    return 0;
}
function warningMaxLevel(levels) {
    const r = Math.max(0, ...levels.map(warningLevelRank));
    return r === 3 ? 'R' : r === 2 ? 'Y' : r === 1 ? 'G' : null;
}

// 生成告警徽章HTML（实心=最新实况，空心=其他未处理弹窗的历史最高等级）
function generateWarningBadgesHTML(popupData, airportPopups) {
    const { solidSource, historyPopups } = resolveBadgeSources(popupData, airportPopups);
    if (!solidSource) return '';

    const warningItems = [
        { label: '风速', field: 'metar_wind_warning' },
        { label: '能见度', field: 'metar_visibility_warning' },
        { label: 'RVR', field: 'metar_rvr_warning' },
        { label: '云底高', field: 'metar_cloud_warning' },
        { label: '气温', field: 'metar_temperature_warning' },
        { label: '风切变', field: 'metar_ws_warning' },
        { label: '趋势', field: 'metar_change_trend_warning' }
    ];

    const row1Left = [];
    const row1Rest = [];
    warningItems.forEach(item => {
        const currentLevel = solidSource[item.field];
        const historyLevels = historyPopups.map(p => p[item.field]).filter(Boolean);
        const historyMax = warningMaxLevel(historyLevels);
        const currentRank = warningLevelRank(currentLevel);
        const historyRank = historyMax ? warningLevelRank(historyMax) : 0;
        const hasCurrent = currentLevel && currentLevel !== 'N';
        const historyOnly = historyMax && !hasCurrent;
        const historyHigher = historyMax && hasCurrent && historyRank > currentRank;
        if (historyOnly) {
            row1Left.push(`<span class="warning-badge warning-border-${historyMax}">${item.label}</span>`);
        }
        if (historyHigher) {
            row1Rest.push(`<span class="warning-badge warning-border-${historyMax}">${item.label}</span>`);
        }
        if (hasCurrent) {
            row1Rest.push(`<span class="warning-badge warning-${currentLevel}">${item.label}</span>`);
        }
    });
    const row1 = row1Left.concat(row1Rest);

    const row2 = [];
    const currentWeather = normalizeWeatherTypeForBadges(solidSource.metar_weather_type, airportPopups);
    const currentWeatherEntries = Object.entries(currentWeather);
    const historyWeatherCodes = new Set();
    historyPopups.forEach(p => {
        const wt = p.metar_weather_type || {};
        Object.keys(wt).forEach(code => historyWeatherCodes.add(code));
    });
    const historyOnlyCodes = [...historyWeatherCodes].filter(code => !currentWeather[code]).sort();
    historyOnlyCodes.forEach(code => {
        const levels = historyPopups.map(p => (p.metar_weather_type && p.metar_weather_type[code]) ? p.metar_weather_type[code].alert_level : null).filter(Boolean);
        const historyMax = warningMaxLevel(levels);
        if (!historyMax) return;
        const firstWith = historyPopups.find(p => p.metar_weather_type && p.metar_weather_type[code]);
        const name = firstWith && firstWith.metar_weather_type[code]
            ? weatherTypeBadgeName(code, firstWith.metar_weather_type[code])
            : weatherTypeBadgeName(code);
        row2.push(`<span class="warning-badge warning-border-${historyMax}">${name}</span>`);
    });
    currentWeatherEntries.forEach(([code, info]) => {
        const currentLevel = info.alert_level;
        const name = weatherTypeBadgeName(code, info);
        const historyLevels = historyPopups.map(p => (p.metar_weather_type && p.metar_weather_type[code]) ? p.metar_weather_type[code].alert_level : null).filter(Boolean);
        const historyMax = warningMaxLevel(historyLevels);
        const currentRank = warningLevelRank(currentLevel);
        const historyRank = historyMax ? warningLevelRank(historyMax) : 0;
        const showHistory = historyMax && historyRank > currentRank;
        if (showHistory) {
            row2.push(`<span class="warning-badge warning-border-${historyMax}">${name}</span>`);
        }
        if (currentLevel && currentLevel !== 'N') {
            row2.push(`<span class="warning-badge warning-${currentLevel}">${name}</span>`);
        }
    });

    let html = '<div class="popup-warning-badges">';
    html += '<div class="popup-warning-row">' + row1.join('') + '</div>';
    html += '<div class="popup-warning-row">' + row2.join('') + '</div>';
    html += '</div>';

    return html;
}

// 生成航班信息卡片HTML
function generateFlightInfoCardsHTML(popupData) {
    const currentTime = popupData.current_time || Date.now();
    const arrivingTime = popupData.closest_departure_time_of_arriving_flight;
    const landingTime = popupData.closest_landing_time_of_arriving_flight;
    const departingTime = popupData.closest_departure_time_at_this_airport;
    const enRoute = popupData.en_route;
    const hasParking = popupData.has_parking;

    // 格式化时间；timeClass: '' | 'soon' | 'past'（TT≤CC 为 past，CC<TT≤CC+30min 为 soon）
    const thresholdMs = 1800000;
    function formatFlightTime(timestamp) {
        if (!timestamp) return { time: '--:--:--', date: '', timeClass: '' };
        const parts = formatTimestampPartsByMode(timestamp);
        let timeClass = '';
        if (timestamp <= currentTime) timeClass = 'past';
        else if (timestamp <= currentTime + thresholdMs) timeClass = 'soon';
        return { time: parts.time, date: parts.date, timeClass };
    }

    const arrivingTimeInfo = formatFlightTime(arrivingTime);
    const landingTimeInfo = formatFlightTime(landingTime);
    const departingTimeInfo = formatFlightTime(departingTime);
    const flightInfoLabel = (ts, overdueText, normalText) => {
        const overdue = ts && ts <= currentTime;
        const cls = overdue ? 'flight-info-icon-label is-overdue' : 'flight-info-icon-label';
        return `<div class="${cls}">${overdue ? overdueText : normalText}</div>`;
    };

    const staticBase = (typeof window !== 'undefined' && window.STATIC_URL) ? window.STATIC_URL : '/static/';
    const svg = function (name) { return staticBase + 'svg/' + name; };

    return `
        <div class="flight-info-card">
            <div class="flight-info-card-upper">
                <div class="flight-info-icon">
                    <img src="${svg('previous_airport.svg')}" alt="" class="flight-info-icon-img" />
                </div>
                <div class="flight-info-content">
                    <div class="flight-info-time ${arrivingTimeInfo.timeClass}">${arrivingTimeInfo.time}</div>
                    <div class="flight-info-date ${arrivingTimeInfo.timeClass}">${arrivingTimeInfo.date}</div>
                </div>
            </div>
            ${flightInfoLabel(arrivingTime, '航班上一站超时未起飞', '上一站最近起飞时间')}
        </div>
        <div class="flight-info-card">
            <div class="flight-info-card-upper">
                <div class="flight-info-icon">
                    <img src="${svg('landing.svg')}" alt="" class="flight-info-icon-img" />
                </div>
                <div class="flight-info-content">
                    <div class="flight-info-time ${landingTimeInfo.timeClass}">${landingTimeInfo.time}</div>
                    <div class="flight-info-date ${landingTimeInfo.timeClass}">${landingTimeInfo.date}</div>
                </div>
            </div>
            ${flightInfoLabel(landingTime, '航班超时未落地', '本场最近着陆时间')}
        </div>
        <div class="flight-info-card">
            <div class="flight-info-card-upper">
                <div class="flight-info-icon">
                    <img src="${svg('departure.svg')}" alt="" class="flight-info-icon-img" />
                </div>
                <div class="flight-info-content">
                    <div class="flight-info-time ${departingTimeInfo.timeClass}">${departingTimeInfo.time}</div>
                    <div class="flight-info-date ${departingTimeInfo.timeClass}">${departingTimeInfo.date}</div>
                </div>
            </div>
            ${flightInfoLabel(departingTime, '航班本站超时未起飞', '本场最近起飞时间')}
        </div>
        <div class="flight-info-card">
            <div class="flight-info-card-upper">
                <div class="flight-info-icon">
                    <img src="${svg('inflight.svg')}" alt="" class="flight-info-icon-img" />
                </div>
                <div class="flight-info-content">
                    <div class="flight-info-status ${enRoute ? 'yes' : 'no'}">${enRoute ? '是' : '否'}</div>
                </div>
            </div>
            <div class="flight-info-icon-label">已有航班起飞前往本场</div>
        </div>
        <div class="flight-info-card">
            <div class="flight-info-card-upper">
                <div class="flight-info-icon">
                    <img src="${svg('parking.svg')}" alt="" class="flight-info-icon-img" />
                </div>
                <div class="flight-info-content">
                    <div class="flight-info-status ${hasParking ? 'yes' : 'no'}">${hasParking ? '是' : '否'}</div>
                </div>
            </div>
            <div class="flight-info-icon-label">是否有飞机停场</div>
        </div>
    `;
}

// 生成报文内容HTML（同源原始历史实况，最新3条，告警着色后填入）
function generateMetarContentHTML(airportCode) {
    // 返回一个占位符，将在异步获取历史报文后更新
    return `<span class="popup-value" id="metar-content-${airportCode}">
        <span style="color: #999;">加载中...</span>
    </span>`;
}

// 加载并显示历史报文
function loadAndDisplayHistoryMetarContent(airportCode) {
    const contentElement = document.getElementById(`metar-content-${airportCode}`);
    if (!contentElement) return;

    // 获取时间模式
    const currentPath = window.location.pathname;
    const timeMode = currentPath.startsWith('/test/') ? 'test' : 'current';

    // 准备请求头
    const headers = {};
    if (timeMode === 'current' && currentToken) {
        headers['Authorization'] = `Bearer ${currentToken}`;
        if (currentUserCode) {
            headers['X-User-Code'] = currentUserCode;
        }
    }
    if (timeMode === 'test') {
        headers['X-User-Code'] = 'test';
    }

    fetch(`/${timeMode}/api/airport/${airportCode}/popup-metar-text/`, {
        headers: headers
    })
        .then(response => response.json())
        .then(data => {
            if (data.success && Array.isArray(data.data) && data.data.length > 0) {
                contentElement.innerHTML = data.data.map(report => {
                    const html = report.html || report.content || '';
                    return `<span class="metar-content-item">${html}</span>`;
                }).join('');
            } else {
                contentElement.innerHTML = '<span style="color: #999;">暂无历史报文</span>';
            }
        })
        .catch(error => {
            console.error('加载历史报文失败:', error);
            contentElement.innerHTML = '<span style="color: #999;">加载失败</span>';
        });
}

// 生成弹窗时间文本
function generatePopupTimeText(popupData, currentTime) {
    if (!popupData.popup_time) return '';

    const popupTime = popupData.popup_time;
    const initialCurrentTime = currentTime;

    let actualTimeDiff = initialCurrentTime - popupTime;
    if (actualTimeDiff < 0) {
        actualTimeDiff = 0;
    }

    const { timeText } = formatPopupTime(actualTimeDiff);

    return `<span class="popup-time-value" data-popup-time="${popupTime}" data-current-time="${currentTime}">${timeText}</span>`;
}

// 创建标签页HTML
function createTabsHTML() {
    const airports = Object.keys(popupAirports).sort((a, b) => {
        // 按最新popup_time排序
        const latestA = getLatestPopup(popupAirports[a]);
        const latestB = getLatestPopup(popupAirports[b]);
        return latestB.popup_time - latestA.popup_time;
    });

    if (airports.length === 0) return '';

    // 如果当前选中的机场不存在了，选择第一个
    if (!currentActiveAirport || !popupAirports[currentActiveAirport]) {
        currentActiveAirport = airports[0];
    }

    let tabsHTML = '<div class="popup-tabs-container">';

    // 左翻页按钮（单击仍翻页；按下拖拽见 attachPopupTabBarDrag）
    tabsHTML += '<button type="button" class="popup-tab-nav popup-tab-nav-left" ' +
        (tabScrollOffset <= 0 ? 'disabled' : '') + '>«</button>';

    tabsHTML += '<div class="popup-tabs-wrapper"><div class="popup-tabs" id="popup-tabs-list" style="transform: translateX(-' + tabScrollOffset + 'px)">';

    airports.forEach(airport => {
        const airportPopups = popupAirports[airport];
        const latestPopup = getLatestPopup(airportPopups);
        const warningLevel = latestPopup.metar_warning || 'N';
        const count = airportPopups.length;
        const isActive = airport === currentActiveAirport;

        const badgeHTML = count >= 2 ? `<span class="popup-tab-badge">${count}</span>` : '';

        tabsHTML += `<div class="popup-tab ${isActive ? 'active' : ''} warning-${warningLevel}" 
                          data-airport="${airport}">
                        ${airport}${badgeHTML}
                    </div>`;
    });

    tabsHTML += '</div></div>';

    // 右翻页按钮
    tabsHTML += '<button type="button" class="popup-tab-nav popup-tab-nav-right" id="popup-tab-nav-right">»</button>';

    tabsHTML += '</div>';

    return tabsHTML;
}

// 创建弹窗内容HTML
function createPopupContentHTML(airport) {
    const airportPopups = popupAirports[airport];
    if (!airportPopups || airportPopups.length === 0) return '';

    const latestPopup = getLatestPopup(airportPopups);
    const currentTime = latestPopup.current_time || Date.now();

    // 报文类型
    const metarType = latestPopup.metar_type || '';
    let metarTypeLabel = '';
    if (metarType === 'SA') {
        metarTypeLabel = '例行';
    } else if (metarType === 'SP') {
        metarTypeLabel = '特殊';
    }
    const metarTypeHTML = metarType === 'SP'
        ? `<span class="popup-value-highlight">${metarType}</span>`
        : metarType;

    // 格式化时间：分离时分秒和年月日
    const timeObj = formatTimestampToBeijingParts(latestPopup.metar_observation_time);

    // 生成告警徽章（实心=观测时间最新的实况，空心=更早的未处理弹窗）
    const warningBadgesHTML = generateWarningBadgesHTML(latestPopup, airportPopups);

    // 生成航班信息卡片
    const flightInfoCardsHTML = generateFlightInfoCardsHTML(latestPopup);

    // 生成报文内容（显示历史报文）
    const metarContentHTML = generateMetarContentHTML(airport);

    // 生成弹窗时间文本
    const popupTimeText = generatePopupTimeText(latestPopup, currentTime);

    // 获取所有sqc用于批量操作
    const sqcList = airportPopups.map(p => p.sqc);
    const sqcListStr = JSON.stringify(sqcList).replace(/"/g, '&quot;');

    return `
        <div class="metar-popup-modal" data-airport="${airport}">
            <div class="metar-popup-header">
                <div class="metar-popup-airport">
                    <div class="airport-code">${latestPopup.airport_4code}</div>
                    <div class="airport-name">${latestPopup.airport_name || '机场名称未配置'}</div>
                </div>
                <div class="popup-header-divider"></div>
                ${warningBadgesHTML}
                ${warningBadgesHTML ? '<div class="popup-header-divider"></div>' : ''}
                <div class="popup-header-info">
                    <div class="metar-time">${timeObj.time}</div>
                    <div class="metar-date">${timeObj.date}</div>
                </div>
                <div class="popup-header-divider"></div>
                <div class="popup-metar-type-wrap">
                    <div class="popup-metar-type">
                        <div class="metar-type">${metarTypeHTML}</div>
                        ${metarTypeLabel ? `<div class="metar-type-label">${metarTypeLabel}</div>` : ''}
                    </div>
                    <span class="popup-section-info-icon" title="本部分告警徽章为过去6小时内所有对应机场未处理报文的告警徽章，其中仅带背景色的徽章为当前最新实况报文，其他为历史未处理报文徽章。">ⓘ</span>
                </div>
            </div>
            <div class="metar-popup-body">
                <div class="metar-popup-lower">
                    <div class="popup-info-item">
                        ${metarContentHTML}
                        <span class="popup-section-info-icon" title="本部分报文为对应机场最新的3份实况报文，不一定是告警徽章区域的徽章对应的报文。">ⓘ</span>
                    </div>
                </div>
                <div class="metar-popup-flight-section">
                    ${flightInfoCardsHTML}
                </div>
            </div>
            <div class="metar-popup-footer">
                <div class="popup-footer-left">
                    <span>弹窗时间：</span>${popupTimeText}
                </div>
                <div class="popup-footer-right">
                    <button class="popup-btn popup-btn-ignore">一键忽略</button>
                    <button class="popup-btn popup-btn-snooze">一键稍后处理</button>
                    <button class="popup-btn popup-btn-handle" data-airport="${airport}" data-sqc-list='${sqcListStr}'>查看详情</button>
                    <button class="popup-btn popup-btn-received" data-airport="${airport}" data-sqc-list='${sqcListStr}'>收到</button>
                </div>
            </div>
        </div>
    `;
}

// ==================================
// 弹窗渲染和交互
// ==================================

// 渲染弹窗
function renderPopup() {
    // 移除旧的弹窗
    const oldOverlay = document.querySelector('.metar-popup-overlay');
    if (oldOverlay) {
        oldOverlay.remove();
    }

    // 如果没有弹窗数据，返回
    if (Object.keys(popupAirports).length === 0) {
        _popupDragLeft = null;
        _popupDragTop = null;
        updatePopupAlert();
        return;
    }

    // 创建新弹窗
    const tabsHTML = createTabsHTML();
    const contentHTML = createPopupContentHTML(currentActiveAirport);

    const overlayHTML = `
        <div class="metar-popup-overlay">
            ${tabsHTML}
            ${contentHTML}
        </div>
    `;

    const div = document.createElement('div');
    div.innerHTML = overlayHTML;
    const overlayElement = div.firstElementChild;

    document.body.appendChild(overlayElement);

    // 如果之前拖动过，恢复弹窗位置
    if (_popupDragLeft !== null && _popupDragTop !== null) {
        overlayElement.style.left = _popupDragLeft + 'px';
        overlayElement.style.top = _popupDragTop + 'px';
        overlayElement.style.transform = 'none';
    }

    // 加载并显示历史报文
    loadAndDisplayHistoryMetarContent(currentActiveAirport);

    // 绑定按钮事件
    attachPopupButtonEvents();

    // 标签栏：左键按下拖拽平移；松开后无位移则视为单击（选机场 / 翻页）
    attachPopupTabBarDrag(overlayElement);

    // 更新滚动按钮状态
    updateScrollButtons();

    // 更新弹窗时间
    updatePopupTimes();

    // 启动弹窗时间更新定时器
    startPopupTimeUpdater();

    // 更新页面提示状态
    updatePopupAlert();
}

// 绑定弹窗按钮事件
function attachPopupButtonEvents() {
    // 一键忽略按钮 - 处理所有机场
    const ignoreBtn = document.querySelector('.popup-btn-ignore');
    if (ignoreBtn) {
        ignoreBtn.addEventListener('click', handleBatchIgnoreAll);
    }

    // 一键稍后处理按钮
    const snoozeBtn = document.querySelector('.popup-btn-snooze');
    if (snoozeBtn) {
        snoozeBtn.addEventListener('click', handleSnooze);
    }

    // 收到按钮 - 只处理当前机场
    const receivedBtn = document.querySelector('.popup-btn-received');
    if (receivedBtn) {
        receivedBtn.addEventListener('click', function () {
            const airport = this.getAttribute('data-airport');
            const sqcListStr = this.getAttribute('data-sqc-list');
            const sqcList = JSON.parse(sqcListStr);
            handleBatchReceived(airport, sqcList);
        });
    }

    // 去处理按钮 - 只处理当前机场
    const handleBtn = document.querySelector('.popup-btn-handle');
    if (handleBtn) {
        handleBtn.addEventListener('click', function () {
            const airport = this.getAttribute('data-airport');
            const sqcListStr = this.getAttribute('data-sqc-list');
            const sqcList = JSON.parse(sqcListStr);
            handleBatchHandle(airport, sqcList);
        });
    }
}

// 弹窗拖动位置存储（跨 renderPopup 调用保留）
let _popupDragLeft = null;
let _popupDragTop = null;

// 获取 overlay 的当前左上角像素坐标（首次拖动时用 getBoundingClientRect 初始化）
function _getOverlayInitPos(overlay) {
    if (_popupDragLeft !== null && _popupDragTop !== null) {
        return { left: _popupDragLeft, top: _popupDragTop };
    }
    const rect = overlay.getBoundingClientRect();
    return { left: rect.left, top: rect.top };
}

// 将 overlay 移动到指定位置并记忆（限制在视口内）
function _applyOverlayPos(overlay, left, top) {
    const w = overlay.offsetWidth || 720;
    const h = overlay.offsetHeight || 430;
    const clampedLeft = Math.max(0, Math.min(window.innerWidth - w, left));
    const clampedTop = Math.max(0, Math.min(window.innerHeight - h, top));
    overlay.style.left = clampedLeft + 'px';
    overlay.style.top = clampedTop + 'px';
    overlay.style.transform = 'none';
    _popupDragLeft = clampedLeft;
    _popupDragTop = clampedTop;
}

// 标签栏：鼠标左键按下拖动 → 移动整个弹窗；松开无位移 → 选机场 / 翻页
function attachPopupTabBarDrag(overlay) {
    const container = overlay.querySelector('.popup-tabs-container');
    if (!container) return;

    const DRAG_THRESHOLD_PX = 4;
    let suppressSyntheticClickOnce = false;

    function eventToElement(t) {
        if (!t) return null;
        return t.nodeType === Node.ELEMENT_NODE ? t : t.parentElement;
    }

    container.addEventListener('click', function (ev) {
        if (suppressSyntheticClickOnce) {
            ev.preventDefault();
            ev.stopPropagation();
            suppressSyntheticClickOnce = false;
        }
    }, true);

    container.addEventListener('pointerdown', function (e) {
        if (!e.isPrimary) return;
        if (e.pointerType === 'mouse' && e.button !== 0) return;

        const downEl = eventToElement(e.target);
        const startMouseX = e.clientX;
        const startMouseY = e.clientY;
        const initPos = _getOverlayInitPos(overlay);
        const startLeft = initPos.left;
        const startTop = initPos.top;
        let draggedBeyondThreshold = false;

        function cleanupListeners() {
            container.removeEventListener('pointermove', onMove);
            container.removeEventListener('pointerup', onPointerUpEnd);
            container.removeEventListener('pointercancel', onPointerCancel);
        }

        function finish(ev, fromCancel) {
            cleanupListeners();
            try { if (container.releasePointerCapture) container.releasePointerCapture(e.pointerId); } catch (_) {}

            if (draggedBeyondThreshold || fromCancel) {
                suppressSyntheticClickOnce = true;
                return;
            }

            // 无位移：视为单击，识别目标
            const hitNode = typeof document.elementFromPoint === 'function' && ev.clientX != null
                ? document.elementFromPoint(ev.clientX, ev.clientY)
                : ev.target;
            const upEl = eventToElement(hitNode || ev.target);

            const tabDown = downEl && downEl.closest ? downEl.closest('.popup-tab') : null;
            const tabUp = upEl && upEl.closest ? upEl.closest('.popup-tab') : null;
            if (tabDown && tabUp && tabDown === tabUp && tabDown.getAttribute('data-airport')) {
                switchToAirport(tabDown.getAttribute('data-airport'));
                return;
            }

            const navLeftDown = downEl && downEl.closest ? downEl.closest('.popup-tab-nav-left') : null;
            const navLeftUp = upEl && upEl.closest ? upEl.closest('.popup-tab-nav-left') : null;
            if (navLeftDown && navLeftUp && navLeftDown === navLeftUp && !navLeftDown.disabled) {
                scrollTabsLeft();
                return;
            }

            const navRightDown = downEl && downEl.closest ? downEl.closest('.popup-tab-nav-right') : null;
            const navRightUp = upEl && upEl.closest ? upEl.closest('.popup-tab-nav-right') : null;
            if (navRightDown && navRightUp && navRightDown === navRightUp && !navRightDown.disabled) {
                scrollTabsRight();
                return;
            }
        }

        function onMove(ev) {
            if (!ev.isPrimary) return;
            const dx = ev.clientX - startMouseX;
            const dy = ev.clientY - startMouseY;
            if (!draggedBeyondThreshold && Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
                draggedBeyondThreshold = true;
            }
            if (draggedBeyondThreshold) {
                _applyOverlayPos(overlay, startLeft + dx, startTop + dy);
            }
            ev.preventDefault();
        }

        function onPointerUpEnd(ev) {
            if (!ev.isPrimary) return;
            finish(ev, false);
        }

        function onPointerCancel(ev) {
            if (!ev.isPrimary) return;
            finish(ev, true);
        }

        try { container.setPointerCapture(e.pointerId); } catch (_) {}

        container.addEventListener('pointermove', onMove);
        container.addEventListener('pointerup', onPointerUpEnd);
        container.addEventListener('pointercancel', onPointerCancel);

        e.preventDefault();
    }, true);
}

// 更新滚动按钮状态
function updateScrollButtons() {
    const tabsList = document.getElementById('popup-tabs-list');
    const wrapper = tabsList ? tabsList.parentElement : null;
    const leftBtn = document.querySelector('.popup-tab-nav-left');
    const rightBtn = document.getElementById('popup-tab-nav-right');

    if (!tabsList || !wrapper || !leftBtn || !rightBtn) return;

    const tabsWidth = tabsList.scrollWidth;
    const wrapperWidth = wrapper.offsetWidth;

    // 左按钮状态
    if (tabScrollOffset <= 0) {
        leftBtn.disabled = true;
    } else {
        leftBtn.disabled = false;
    }

    // 右按钮状态
    if (tabsWidth <= wrapperWidth) {
        // 所有标签页都能显示，禁用右按钮
        rightBtn.disabled = true;
    } else {
        // 检查是否已经滚动到最右侧
        const maxScroll = tabsWidth - wrapperWidth;
        if (tabScrollOffset >= maxScroll) {
            rightBtn.disabled = true;
        } else {
            rightBtn.disabled = false;
        }
    }
}

// 切换到指定机场
function switchToAirport(airport) {
    if (currentActiveAirport === airport) return;

    // 保存当前机场的图表状态
    const currentAirport = currentActiveAirport;

    currentActiveAirport = airport;
    renderPopup();
}

// 标签页向左滚动
function scrollTabsLeft() {
    const tabWidth = 60;
    const step = tabWidth * 3;
    tabScrollOffset = Math.max(0, tabScrollOffset - step);
    renderPopup();
}

// 标签页向右滚动
function scrollTabsRight() {
    const tabsList = document.getElementById('popup-tabs-list');
    const wrapper = tabsList ? tabsList.parentElement : null;

    if (!tabsList || !wrapper) return;

    const tabWidth = 60;
    const step = tabWidth * 3;
    const tabsWidth = tabsList.scrollWidth;
    const wrapperWidth = wrapper.offsetWidth;
    const maxScroll = tabsWidth - wrapperWidth;

    // 计算新的滚动位置
    let newOffset = tabScrollOffset + step;

    // 确保不超过最大滚动距离
    if (newOffset > maxScroll) {
        newOffset = maxScroll;
    }

    tabScrollOffset = newOffset;
    renderPopup();
}

// ==================================
// 按钮操作处理
// ==================================

// 处理批量忽略所有机场
async function handleBatchIgnoreAll() {
    console.log('handleBatchIgnoreAll called');

    // 收集所有机场的所有sqc
    const allSqc = [];
    Object.values(popupAirports).forEach(airportPopups => {
        airportPopups.forEach(popup => {
            allSqc.push(popup.sqc);
        });
    });

    if (allSqc.length === 0) return;

    console.log('Total sqc count:', allSqc.length);

    const confirmed = await showConfirmDialog('全部弹窗的报文将视作已处理且不再弹出');
    console.log('User confirmed:', confirmed);

    if (!confirmed) return;

    if (window.markPopupsDismissedLocally) {
        window.markPopupsDismissedLocally(allSqc);
    }

    try {
        const headers = {
            'Content-Type': 'application/json'
        };

        if (currentToken) {
            headers['Authorization'] = `Bearer ${currentToken}`;
        }
        if (currentUserCode) {
            headers['X-User-Code'] = currentUserCode;
        }

        const response = await fetch(`/${currentTimeMode}/api/popup-batch-ignore/`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ sqc_list: allSqc })
        });
    } catch (error) {
        console.error('批量忽略出错:', error);
    }

    popupAirports = {};
    currentActiveAirport = null;
    tabScrollOffset = 0;
    renderPopup();
}

// 处理批量忽略（单个机场）
async function handleBatchIgnore(airport, sqcList) {
    console.log('handleBatchIgnore called', airport, sqcList);

    // 显示确认对话框
    const confirmed = await showConfirmDialog('全部弹窗的报文将视作已处理且不再弹出');
    console.log('User confirmed:', confirmed);

    if (!confirmed) return;

    try {
        const headers = {
            'Content-Type': 'application/json'
        };

        if (currentToken) {
            headers['Authorization'] = `Bearer ${currentToken}`;
        }
        if (currentUserCode) {
            headers['X-User-Code'] = currentUserCode;
        }

        const response = await fetch(`/${currentTimeMode}/api/popup-batch-ignore/`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ sqc_list: sqcList })
        });

        if (response.ok) {
            // 移除该机场的弹窗数据
            delete popupAirports[airport];

            // 重置滚动偏移
            tabScrollOffset = 0;

            // 切换到最新的机场
            const airports = Object.keys(popupAirports);
            if (airports.length > 0) {
                const sorted = airports.sort((a, b) => {
                    const latestA = getLatestPopup(popupAirports[a]);
                    const latestB = getLatestPopup(popupAirports[b]);
                    return latestB.popup_time - latestA.popup_time;
                });
                currentActiveAirport = sorted[0];
            } else {
                currentActiveAirport = null;
            }

            renderPopup();
        } else {
            console.error('批量忽略失败:', response.status);
        }
    } catch (error) {
        console.error('批量忽略出错:', error);
    }
}

// 处理批量收到
async function handleBatchReceived(airport, sqcList) {
    if (window.markPopupsDismissedLocally) {
        window.markPopupsDismissedLocally(sqcList);
    }
    try {
        const headers = {
            'Content-Type': 'application/json'
        };

        if (currentToken) {
            headers['Authorization'] = `Bearer ${currentToken}`;
        }
        if (currentUserCode) {
            headers['X-User-Code'] = currentUserCode;
        }

        await fetch(`/${currentTimeMode}/api/popup-batch-received/`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ sqc_list: sqcList })
        });
    } catch (error) {
        console.error('批量收到出错:', error);
    }

    delete popupAirports[airport];
    tabScrollOffset = 0;
    const airports = Object.keys(popupAirports);
    if (airports.length > 0) {
        const sorted = airports.sort((a, b) => {
            const latestA = getLatestPopup(popupAirports[a]);
            const latestB = getLatestPopup(popupAirports[b]);
            return latestB.popup_time - latestA.popup_time;
        });
        currentActiveAirport = sorted[0];
    } else {
        currentActiveAirport = null;
    }
    renderPopup();
}

// 处理批量去处理
async function handleBatchHandle(airport, sqcList) {
    if (window.markPopupsDismissedLocally) {
        window.markPopupsDismissedLocally(sqcList);
    }
    try {
        const headers = {
            'Content-Type': 'application/json'
        };

        if (currentToken) {
            headers['Authorization'] = `Bearer ${currentToken}`;
        }
        if (currentUserCode) {
            headers['X-User-Code'] = currentUserCode;
        }

        await fetch(`/${currentTimeMode}/api/popup-batch-received/`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ sqc_list: sqcList })
        });
    } catch (error) {
        console.error('批量去处理出错:', error);
    }

    window._openDetailAboveMetarPopup = true;
    await showAirportDetail(airport);

    delete popupAirports[airport];
    tabScrollOffset = 0;
    const airports = Object.keys(popupAirports);
    if (airports.length > 0) {
        const sorted = airports.sort((a, b) => {
            const latestA = getLatestPopup(popupAirports[a]);
            const latestB = getLatestPopup(popupAirports[b]);
            return latestB.popup_time - latestA.popup_time;
        });
        currentActiveAirport = sorted[0];
    } else {
        currentActiveAirport = null;
    }

    setTimeout(() => {
        renderPopup();
    }, 50);
}

// 处理稍后处理
async function handleSnooze() {
    // 获取配置的延迟时间（分钟）
    let snoozeDuration = 10; // 默认10分钟

    try {
        const response = await fetch(`/${currentTimeMode}/api/timer-configs/`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success && result.data && result.data.popup_snooze_duration) {
                snoozeDuration = result.data.popup_snooze_duration;
            }
        }
    } catch (error) {
        console.error('获取配置失败:', error);
    }

    // 显示确认对话框
    const confirmed = await showConfirmDialog(
        `以上弹窗及新弹窗${snoozeDuration}分钟内不再显示，${snoozeDuration}分钟后一并弹出`
    );
    if (!confirmed) return;

    // 收集所有sqc
    const allSqc = [];
    Object.values(popupAirports).forEach(airportPopups => {
        airportPopups.forEach(popup => {
            allSqc.push(popup.sqc);
        });
    });

    // 计算结束时间
    const endTime = Date.now() + snoozeDuration * 60 * 1000;

    // 保存状态
    saveSnoozeState(endTime, allSqc);

    // 清空弹窗数据
    popupAirports = {};
    currentActiveAirport = null;
    tabScrollOffset = 0;

    // 重新渲染（会移除弹窗）
    renderPopup();
}

// 显示确认对话框
function showConfirmDialog(message) {
    return new Promise((resolve) => {
        const overlayHTML = `
            <div class="popup-confirm-overlay">
                <div class="popup-confirm-modal">
                    <div class="popup-confirm-message">${message}</div>
                    <div class="popup-confirm-buttons">
                        <button class="popup-confirm-btn popup-confirm-btn-cancel">取消</button>
                        <button class="popup-confirm-btn popup-confirm-btn-ok">确定</button>
                    </div>
                </div>
            </div>
        `;

        const div = document.createElement('div');
        div.innerHTML = overlayHTML;
        const overlay = div.firstElementChild;

        const cancelBtn = overlay.querySelector('.popup-confirm-btn-cancel');
        const okBtn = overlay.querySelector('.popup-confirm-btn-ok');

        cancelBtn.onclick = () => {
            overlay.remove();
            resolve(false);
        };

        okBtn.onclick = () => {
            overlay.remove();
            resolve(true);
        };

        document.body.appendChild(overlay);
    });
}

// ==================================
// 弹窗检查和轮询
// ==================================

// 检查并显示弹窗
async function checkAndShowPopups() {
    try {
        if (typeof hasAccess === 'function' && !hasAccess('metar_popup', 'display')) {
            dismissMetarPopupsForAccess();
            return;
        }
        // 如果检测到token失效，停止弹窗检查
        if (currentTimeMode === 'current' && window.tokenInvalidDetected) {
            console.log('Token失效，停止弹窗检查');
            stopPopupCheck();
            return;
        }

        const headers = {
            'Content-Type': 'application/json'
        };

        if (currentToken) {
            headers['Authorization'] = `Bearer ${currentToken}`;
        }

        const userCode = currentUserCode || 'default';
        const response = await fetch(`/${currentTimeMode}/api/metar-popups/?user_code=${userCode}&time_mode=${currentTimeMode}`, {
            method: 'GET',
            headers: headers
        });

        if (response.ok) {
            const result = await response.json();
            if (!result.success) {
                return;
            }
            if (result.trace_time != null) {
                window.__popupTraceHours = result.trace_time;
            }

            const currentTime = result.current_time;
            const matcher = window.popupMatchesLocalPrefs || (() => true);
            const filtered = (result.data || []).filter(popupData => {
                popupData.current_time = currentTime;
                return matcher(popupData);
            });

            if (shouldHidePopup()) {
                console.log('稍后处理期间，不显示弹窗');
                return;
            }

            const prevSqc = new Set();
            Object.keys(popupAirports).forEach(airport => {
                popupAirports[airport].forEach(p => prevSqc.add(p.sqc));
            });

            popupAirports = groupPopupsByAirport(filtered);
            Object.keys(popupAirports).forEach(airport => {
                popupAirports[airport].sort((a, b) => b.popup_time - a.popup_time);
            });

            const nextSqc = new Set();
            Object.keys(popupAirports).forEach(airport => {
                popupAirports[airport].forEach(p => nextSqc.add(p.sqc));
            });
            let hasNewPopup = false;
            nextSqc.forEach(sqc => {
                if (!prevSqc.has(sqc)) hasNewPopup = true;
            });

            if (hasNewPopup) {
                restoreDetailBelowMetarPopup();
            }

            if (!currentActiveAirport || !popupAirports[currentActiveAirport]) {
                const airports = Object.keys(popupAirports).sort((a, b) => {
                    const latestA = getLatestPopup(popupAirports[a]);
                    const latestB = getLatestPopup(popupAirports[b]);
                    return latestB.popup_time - latestA.popup_time;
                });
                currentActiveAirport = airports.length > 0 ? airports[0] : null;
            }

            renderPopup();
        } else {
            console.error('获取弹窗数据失败:', response.status);
        }
    } catch (error) {
        console.error('检查弹窗失败:', error);
    }
}

// 启动弹窗检查
function startPopupCheck() {
    if (typeof hasAccess === 'function' && !hasAccess('metar_popup', 'display')) {
        return;
    }
    // 加载稍后处理状态
    loadSnoozeState();

    // 绑定稍后处理恢复按钮
    const snoozeRestoreBtn = document.getElementById('snooze-restore-btn');
    if (snoozeRestoreBtn) {
        snoozeRestoreBtn.onclick = handleSnoozeRestore;
    }

    // 立即检查一次
    checkAndShowPopups();

    // 每30秒检查一次
    if (popupCheckInterval) {
        clearInterval(popupCheckInterval);
    }
    popupCheckInterval = setInterval(checkAndShowPopups, 30000);
}

// 停止弹窗检查
function stopPopupCheck() {
    if (popupCheckInterval) {
        clearInterval(popupCheckInterval);
        popupCheckInterval = null;
    }
}

// 移除已显示的实况弹窗及其确认框，避免挡住扫码登录层
function hideMetarPopupOverlay() {
    document.querySelectorAll('.metar-popup-overlay, .popup-confirm-overlay').forEach((el) => el.remove());
}

function dismissMetarPopupsForAccess() {
    stopPopupCheck();
    if (typeof stopPopupTimeUpdater === 'function') stopPopupTimeUpdater();
    stopTitleFlash();
    isShowingPopupAlert = false;
    if (typeof originalTitle === 'string') document.title = originalTitle;
    const fav = document.getElementById('mtws-favicon') || document.querySelector("link[rel*='icon']");
    if (fav && originalFavicon) fav.href = originalFavicon;
    popupAirports = {};
    currentActiveAirport = null;
    hideMetarPopupOverlay();
}
window.dismissMetarPopupsForAccess = dismissMetarPopupsForAccess;

// ==================================
// 时间相关工具函数
// ==================================

// 格式化弹窗时间
function formatPopupTime(timeDiff) {
    const hours = Math.floor(timeDiff / 3600000);
    const minutes = Math.floor((timeDiff % 3600000) / 60000);
    const seconds = Math.floor((timeDiff % 60000) / 1000);

    let timeText = '';
    if (hours > 0) {
        timeText = `${hours}小时${minutes}分${seconds}秒前`;
    } else if (minutes > 0) {
        timeText = `${minutes}分${seconds}秒前`;
    } else {
        timeText = `${seconds}秒前`;
    }

    return { timeText, timeDiff };
}

// 更新所有弹窗时间显示
function updatePopupTimes() {
    const timeElements = document.querySelectorAll('.popup-time-value');
    const now = Date.now();

    timeElements.forEach(element => {
        const popupTime = parseInt(element.getAttribute('data-popup-time'));
        const initialCurrentTime = parseInt(element.getAttribute('data-current-time'));

        if (popupTime) {
            // 计算实际时间差（从初始currentTime开始算）
            let actualTimeDiff = initialCurrentTime - popupTime;

            // 如果初始时间差为负，从0开始计算
            if (actualTimeDiff < 0) {
                actualTimeDiff = 0;
            }

            // 加上从弹窗显示到现在经过的时间
            const elapsedSinceDisplay = now - initialCurrentTime;
            const totalTimeDiff = actualTimeDiff + elapsedSinceDisplay;

            // 确保不小于0
            const displayTimeDiff = Math.max(0, totalTimeDiff);

            const { timeText, timeDiff } = formatPopupTime(displayTimeDiff);

            // 如果超过30分钟，高亮显示
            if (displayTimeDiff > 1800000) {
                element.innerHTML = `<span class="popup-value-highlight">${timeText}</span>`;
            } else {
                element.textContent = timeText;
            }
        }
    });
}

// 注意：popupTimeUpdateInterval 已在 main.js 中声明

// 启动弹窗时间更新定时器
function startPopupTimeUpdater() {
    if (!popupTimeUpdateInterval) {
        popupTimeUpdateInterval = setInterval(updatePopupTimes, 1000);
    }
}

// 停止弹窗时间更新定时器
function stopPopupTimeUpdater() {
    if (popupTimeUpdateInterval) {
        clearInterval(popupTimeUpdateInterval);
        popupTimeUpdateInterval = null;
    }
}

// 检查并停止弹窗时间更新定时器
function checkAndStopPopupTimeUpdater() {
    if (Object.keys(popupAirports).length === 0) {
        stopPopupTimeUpdater();
    }
}

// 格式化时间戳（遵从 window.displayTimezone 时区模式）
function formatTimestampToBeijing(timestamp) {
    if (!timestamp) return '';
    try {
        const parts = formatTimestampPartsByMode(timestamp);
        return parts.date ? `${parts.date} ${parts.time}` : '';
    } catch (error) {
        console.error('时间格式转换失败:', error);
        return '';
    }
}

// 格式化时间戳（分离年月日和时分秒，遵从 window.displayTimezone 时区模式）
function formatTimestampToBeijingParts(timestamp) {
    if (!timestamp) return { date: '', time: '' };
    try {
        return formatTimestampPartsByMode(timestamp);
    } catch (error) {
        console.error('时间格式转换失败:', error);
        return { date: '', time: '' };
    }
}

