// 全局变量
let currentTimeMode = window.timeMode || 'current';

// 显示时区模式：'CST'（北京时）或 'UTC'（世界时），默认北京时
window.displayTimezone = localStorage.getItem('mtws_display_timezone') || 'CST';
let airportData = [];
let filteredAirportData = [];
let currentCarriers = [];
let currentAreaOptions = {
    domestic: [],
    international: []
};
let currentTimeRange = 36; // 当前时间范围：36或48
let nwpEnabled = false;    // NWP 温度辅助开关
let _nwpCache = {};        // NWP 数据客户端缓存 { airport_code: [{time, temperature},...] }
let filters = {
    domestic: [], // 将在获取区域选项后动态设置
    international: [], // 将在获取区域选项后动态设置
    alert: ['red', 'yellow', 'green'], // 默认显示红黄绿告警，不显示无告警
    margin: 2
};

// 鉴权相关变量
let currentToken = null;
let currentUserCode = null;
let loginCheckInterval = null;
let qrCodeTimer = null; // 二维码倒计时器
let qrCodeExpired = false; // 二维码是否已过期

// 刷新时间记录（仅供自动更新节流使用）
let lastRefreshTime = 0;
const REFRESH_COOLDOWN = 30000; // 30秒冷却时间（仅用于自动更新节流）
let _parserStatusTimer = null;  // 后端解析状态轮询计时器

// 弹窗开关为席位本地状态，无需请求锁
const POPUP_PREFS_KEY = 'mtws_popup_display_prefs';
const POPUP_SEAT_READY_KEY = 'mtws_popup_seat_ready';
const POPUP_DISMISSED_KEY = 'mtws_popup_dismissed_sqc';

// 数据更新时间记录
let dataUpdateTimes = {
    metar: '--:--:--',    // 实况数据最后更新时间
    taf: '--:--:--',      // 预报数据最后更新时间
    flight: '--:--:--'    // 航班数据最后更新时间
};

// 数据更新原始时间戳（用于时区切换后重新格式化）
let dataUpdateTimestamps = {
    metar: null,
    taf: null,
    flight: null
};

// 实况入库告警相关变量
let importAlerts = [];
let alertedAirports = new Set();   // import_alert_handle_time=NULL 的机场集合
let importAlertUnhandledCount = 0;
let importAlertCurrentPage = 1;
let importAlertTotalPages = 1;
let importAlertExpandedId = null;   // 当前展开处理选项的告警 ID
let importAlertDetailOpenId = null; // 当前展开处理详情（只读）的告警 ID

// 弹窗相关变量
let popupCheckInterval = null;
let popupAirports = {}; // 按机场分组的弹窗数据
let currentActiveAirport = null; // 当前选中的机场
let snoozeEndTime = null; // 稍后处理的结束时间
let snoozedPopups = []; // 稍后处理的弹窗列表
let tabScrollOffset = 0; // 标签页滚动偏移量
let popupTimeUpdateInterval = null; // 弹窗时间更新定时器
let originalTitle = document.title; // 页面原始标题
let originalFavicon = null; // 页面原始favicon
let isShowingPopupAlert = false; // 是否正在显示弹窗提醒

// 格式化ISO时间为北京时间的时分秒格式
function formatTimeToBeijing(isoTimeString) {
    if (!isoTimeString) return '--:--:--';
    try {
        const date = new Date(isoTimeString);
        return date.toLocaleTimeString('zh-CN', {
            hour12: false,
            timeZone: 'Asia/Shanghai'
        });
    } catch (error) {
        return '--:--:--';
    }
}

// 根据当前时区模式将时间戳格式化为 HH:mm:ss
function formatTimestampByMode(timestamp) {
    if (!timestamp) return '--:--:--';
    try {
        const date = new Date(timestamp);
        if (window.displayTimezone === 'UTC') {
            return `${String(date.getUTCHours()).padStart(2, '0')}:${String(date.getUTCMinutes()).padStart(2, '0')}:${String(date.getUTCSeconds()).padStart(2, '0')}`;
        }
        return date.toLocaleTimeString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' });
    } catch (e) {
        return '--:--:--';
    }
}

// 根据当前时区模式将时间戳格式化为 { date, time }
function formatTimestampPartsByMode(timestamp) {
    if (!timestamp) return { date: '', time: '' };
    try {
        const date = new Date(timestamp);
        if (window.displayTimezone === 'UTC') {
            return {
                date: `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`,
                time: `${String(date.getUTCHours()).padStart(2, '0')}:${String(date.getUTCMinutes()).padStart(2, '0')}:${String(date.getUTCSeconds()).padStart(2, '0')}`
            };
        }
        return {
            date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`,
            time: `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`
        };
    } catch (e) {
        return { date: '', time: '' };
    }
}

// 与 window.displayTimezone 一致：主页及网格按 UTC / 北京时刻度切换时使用
function syncDisplayTimezoneBodyClass() {
    document.body.classList.toggle('display-timezone-utc', window.displayTimezone === 'UTC');
}

// 刷新状态栏时间显示
function refreshStatusTimes() {
    ['metar', 'taf', 'flight'].forEach(function (type) {
        const ts = dataUpdateTimestamps[type];
        const timeStr = ts ? formatTimestampByMode(ts) : '--:--:--';
        dataUpdateTimes[type] = timeStr;
        updateStatusTimeDisplay(type, timeStr);
    });
}

// 切换时区后刷新所有受控时间显示
function refreshAllTimezoneDisplays() {
    syncDisplayTimezoneBodyClass();
    generateTimeline();
    applyTimeRangeScaling();

    refreshStatusTimes();
    if (airportData && airportData.length > 0) {
        applyFilters();
    }
    if (document.querySelector('.metar-popup-overlay')) {
        renderPopup();
    }
    if (airportDetailChart.chart && airportDetailChart.airportCode) {
        initAirportDetailChart(airportDetailChart.airportCode, airportDetailChart.hours);
    }
    if (typeof refreshPlainTimezone === 'function') {
        refreshPlainTimezone();
    }
    if (typeof syncAirportDetailTimelineLabel === 'function') {
        syncAirportDetailTimelineLabel();
    }
    // 入库视图打开时，重新渲染以反映新时区
    if (typeof currentView === 'function' && currentView() === 'import' && typeof _renderAlertPanel === 'function') {
        _renderAlertPanel();
    }
}

// 初始化时间模式开关
function initTimezoneModeToggle() {
    const toggleInput = document.getElementById('timezone-toggle-input');
    if (!toggleInput) return;
    toggleInput.checked = (window.displayTimezone === 'UTC');
    toggleInput.addEventListener('change', function () {
        window.displayTimezone = this.checked ? 'UTC' : 'CST';
        localStorage.setItem('mtws_display_timezone', window.displayTimezone);
        refreshAllTimezoneDisplays();
    });
}

// 更新状态时间显示
function updateStatusTimeDisplay(dataType, timeString) {
    const timeElement = document.getElementById(`${dataType}-time`);
    if (timeElement) {
        timeElement.textContent = timeString;
    }
}

// 更新数据时间并刷新显示
function updateDataTime(dataType, success, data = null) {
    let timeString = '--:--:--';

    if (success) {
        const now = new Date();
        dataUpdateTimestamps[dataType] = now.getTime();
        timeString = formatTimestampByMode(now.getTime());
    } else {
        dataUpdateTimestamps[dataType] = null;
    }

    // 更新全局记录和状态显示
    dataUpdateTimes[dataType] = timeString;
    updateStatusTimeDisplay(dataType, timeString);
}

// 机场排序相关变量
let currentSortOption = 'alert-asc'; // 默认告警正序

// 检查是否可以执行刷新
function canRefresh() {
    const now = Date.now();
    return (now - lastRefreshTime) >= REFRESH_COOLDOWN;
}

// 更新最后刷新时间
function updateRefreshTime() {
    lastRefreshTime = Date.now();
    // 同步更新sessionStorage，用于浏览器刷新检测
    sessionStorage.setItem('mtws_last_refresh', lastRefreshTime.toString());
}

// ─────────────────────────────────────────────────────────────────
// 后端解析状态检测（替代固定30秒冷却）
// ─────────────────────────────────────────────────────────────────

const PARSER_DISPLAY_NAMES = {
    'flight':           '航班',
    'metar':            '实况',
    'taf':              '预报',
    'aircraft_parking': '停场',
    'nwp':              '温度辅助'
};

// 查询后端当前正在执行或排队的解析器
function checkRunningParsers(callback) {
    fetch(`/${currentTimeMode}/api/running-parsers/`, {
        headers: getRequestHeaders ? getRequestHeaders() : {}
    })
    .then(r => r.json())
    .then(data => callback(null, data.data || { running: [], queued: [] }))
    .catch(err => callback(err, null));
}

// 根据运行/排队列表构建提示文本
function buildParserStatusMessage(running, queued) {
    const parts = [];
    (running || []).forEach(p => {
        parts.push(`${PARSER_DISPLAY_NAMES[p] || p}解析程序正在执行`);
    });
    (queued || []).forEach(p => {
        parts.push(`${PARSER_DISPLAY_NAMES[p] || p}解析程序排队中`);
    });
    if (!parts.length) return '';
    return `【${parts.join('，')}】，请稍后尝试刷新`;
}

// 显示或更新解析中提示（持续显示直到后端完成）
function showParserRunningMessage(message) {
    let tooltip = document.getElementById('parser-running-tooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'parser-running-tooltip';
        tooltip.style.cssText = [
            'position:fixed', 'top:10px', 'left:50%', 'transform:translateX(-50%)',
            'background-color:#fff3cd', 'color:#856404', 'padding:8px 16px',
            'border:1px solid #ffc107', 'border-radius:4px', 'font-size:12px',
            'z-index:9000', 'box-shadow:0 2px 6px rgba(0,0,0,0.15)',
            'pointer-events:none', 'white-space:nowrap'
        ].join(';');
        document.body.appendChild(tooltip);
    }
    tooltip.textContent = message;
}

// 隐藏解析中提示
function hideParserRunningMessage() {
    const el = document.getElementById('parser-running-tooltip');
    if (el && el.parentNode) el.parentNode.removeChild(el);
}

// 启动轮询，直到所有解析程序完成后自动隐藏提示
function startParserStatusPolling() {
    if (_parserStatusTimer) return;
    _parserStatusTimer = setInterval(() => {
        checkRunningParsers((err, data) => {
            if (err) return;
            const running = data.running || [];
            const queued  = data.queued  || [];
            if (running.length === 0 && queued.length === 0) {
                clearInterval(_parserStatusTimer);
                _parserStatusTimer = null;
                hideParserRunningMessage();
            } else {
                showParserRunningMessage(buildParserStatusMessage(running, queued));
            }
        });
    }, 2000);
}

// 刷新按钮点击：先查后端状态，有解析运行则拦截并提示，否则执行刷新
function handleRefreshButtonClick() {
    // 无激活权限：只重拉已解析数据，不触发后端解析
    if (typeof hasAccess === 'function' && hasAccess('refresh_btn', 'display') && !hasAccess('refresh_btn', 'activate')) {
        updateRefreshTime();
        generateTimeline();
        applyTimeRangeScaling();
        if (typeof loadInitialData === 'function') {
            showLoading();
            loadInitialData();
        }
        return;
    }
    checkRunningParsers((err, data) => {
        if (err) {
            // 接口异常时放行（乐观策略）
            doManualRefresh();
            return;
        }
        const running = data.running || [];
        const queued  = data.queued  || [];
        if (running.length > 0 || queued.length > 0) {
            showParserRunningMessage(buildParserStatusMessage(running, queued));
            startParserStatusPolling();
        } else {
            doManualRefresh();
        }
    });
}

// 执行手动刷新（后端确认无解析运行后调用）
function doManualRefresh() {
    updateRefreshTime();
    generateTimeline();
    applyTimeRangeScaling();

    const manualUpdateTypes = ['flight', 'metar', 'taf'];
    if (nwpEnabled) manualUpdateTypes.push('nwp');
    console.log('手动刷新:', manualUpdateTypes);

    showLoading();
    loadParameterizedData(manualUpdateTypes);
}

// 检查是否为浏览器刷新
function checkBrowserRefresh() {
    // 使用sessionStorage检测浏览器刷新
    const isRefresh = sessionStorage.getItem('mtws_page_loaded');

    // 浏览器页面刷新时直接放行，刷新按钮的限制已由后端解析状态检测替代

    // 标记页面已加载
    sessionStorage.setItem('mtws_page_loaded', 'true');
    // 更新刷新时间
    updateRefreshTime();
    sessionStorage.setItem('mtws_last_refresh', lastRefreshTime.toString());

    return true;
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function () {
    initializeFilters();
    syncDisplayTimezoneBodyClass();
    generateTimeline();
    applyTimeRangeScaling(); // 应用时间范围缩放
    bindEvents();
    initializeSorting(); // 初始化排序功能
    initTimezoneModeToggle(); // 初始化时间模式开关

    const startApp = () => {
        // 视图导航必须在权限就绪后再定视图：非本机先过角色选择，
        // 拿到权限才知道地址里的 ?view= 能不能进（见 views_nav.js）
        if (typeof initViewNav === 'function') initViewNav();

        const canLoad = checkBrowserRefresh();
        if (!canLoad) return;
        if (currentTimeMode === 'current') {
            const id = window.__accessIdentity;
            if (id && !id.is_local) {
                // 非本机：不走本机 CAS 登录墙，直接加载主数据（使用服务端已有解析结果）
                if (id.needs_role_select) return;
                showUserInfo();
                loadInitialData();
                if (hasAccess('metar_popup', 'display')) {
                    setTimeout(() => { if (typeof startPopupCheck === 'function') startPopupCheck(); }, 2000);
                }
                return;
            }
            initCurrentModeAuth();
        } else {
            loadInitialData();
        }
    };

    if (typeof bootstrapAccess === 'function') {
        bootstrapAccess().then(() => {
            window.onAccessReady = startApp;
            const id = window.__accessIdentity;
            if (!id || !id.needs_role_select) startApp();
        }).catch(() => startApp());
    } else {
        startApp();
    }

    loadCarrierData();
});

// 检测是否清除了缓存
function checkIfCacheCleared() {
    // 通过检查页面加载标记来检测缓存清除
    // 如果是清除缓存，sessionStorage中的页面加载标记也会被清除
    const pageLoaded = sessionStorage.getItem('mtws_page_loaded');
    const hasFilters = localStorage.getItem('mtws_filters');

    // 如果没有页面加载标记且没有筛选状态，可能是清除了缓存或首次访问
    // 但如果是首次访问，我们也应该使用默认状态
    if (!pageLoaded && !hasFilters) {
        return true;
    }

    // 另一种检测方法：检查localStorage中是否有一个特殊的标记
    const cacheTimestamp = localStorage.getItem('mtws_cache_timestamp');
    if (!cacheTimestamp) {
        // 设置缓存时间戳
        localStorage.setItem('mtws_cache_timestamp', Date.now().toString());
        return true; // 第一次设置，说明可能是清除了缓存
    }

    return false;
}

// 保存筛选状态到localStorage
function saveFiltersToStorage() {
    localStorage.setItem('mtws_filters', JSON.stringify(filters));
    localStorage.setItem('mtws_cache_timestamp', Date.now().toString());
}

// 保存时间范围到localStorage
function saveTimeRangeToStorage() {
    localStorage.setItem('mtws_time_range', currentTimeRange);
    localStorage.setItem('mtws_cache_timestamp', Date.now().toString());
}

// 重置为默认筛选状态
function resetToDefaultFilters() {
    // 恢复默认筛选设置
    filters = {
        domestic: currentAreaOptions.domestic ? [...currentAreaOptions.domestic] : [], // 所有国内区域勾选
        international: currentAreaOptions.international ? [...currentAreaOptions.international] : [], // 所有国际区域勾选
        alert: ['red', 'yellow', 'green'], // 红黄绿勾选，无告警不勾选
        margin: 2 // 告警裕度为2
    };

    // 恢复默认时间范围
    currentTimeRange = 36;

    // 清除localStorage中的状态
    localStorage.removeItem('mtws_filters');
    localStorage.removeItem('mtws_time_range');

    // 标记需要在区域选项加载后更新区域筛选
    sessionStorage.setItem('mtws_reset_regions', 'true');
}

// 初始化筛选器状态
function initializeFilters() {
    // 检查是否为强制刷新或清除缓存
    const isForceRefresh = sessionStorage.getItem('mtws_force_refresh');
    const isCacheCleared = checkIfCacheCleared();

    if (isForceRefresh || isCacheCleared) {
        // 强制刷新或清除缓存时恢复默认状态
        resetToDefaultFilters();
        // 清除强制刷新标记
        sessionStorage.removeItem('mtws_force_refresh');
    } else {
        // 普通刷新时从localStorage恢复筛选状态
        const savedFilters = localStorage.getItem('mtws_filters');
        if (savedFilters) {
            filters = JSON.parse(savedFilters);
        }

        // 从localStorage加载时间范围状态
        const savedTimeRange = localStorage.getItem('mtws_time_range');
        if (savedTimeRange) {
            currentTimeRange = parseInt(savedTimeRange);
        }
    }

    // 从localStorage加载NWP温度辅助开关状态
    const savedNwp = localStorage.getItem('mtws_nwp_enabled');
    if (savedNwp !== null) {
        nwpEnabled = savedNwp === 'true';
    }

    // 应用筛选状态到按钮
    applyFilterStates();
}

// 应用筛选状态到按钮
function applyFilterStates() {
    // 国内区域按钮状态
    updateRegionButtonState('domestic');

    // 国际区域按钮状态
    updateRegionButtonState('international');

    // 告警等级按钮状态
    updateAlertButtonState();

    // 告警裕度滑块状态
    updateMarginSelectState();

    // 时间范围 toggle 状态
    updateTimeRangeSelectState();

    // NWP 温度辅助按钮状态
    updateNwpButtonState();

    // 地图告警按钮状态（map.js 加载后才可用）
    if (typeof updateMapButtonState === 'function') updateMapButtonState();
}

// 更新告警裕度竖向轨道状态（将绿色滑块移到对应位置）
function updateMarginSelectState() {
    setMarginThumbPosition(filters.margin);
}

// 设置告警裕度滑块位置（value 0→左，4→右）
// translateX(%) 是相对于 thumb 自身宽度，thumb=20%，每步移动 100% 自身宽 = 20% 轨道宽
function setMarginThumbPosition(value) {
    const thumb = document.getElementById('margin-v-thumb');
    if (thumb) {
        const pos = parseInt(value) * 100;
        thumb.style.transform = `translateX(${pos}%)`;
    }
}

// 更新时间范围 toggle 状态
function updateTimeRangeSelectState() {
    const timeRangeToggle = document.getElementById('time-range-toggle-input');
    if (timeRangeToggle) {
        timeRangeToggle.checked = (currentTimeRange === 48);
    }
}

// 更新按钮组状态
function updateButtonGroupState(group, selectedValues) {
    const buttons = document.querySelectorAll(`[data-group="${group}"]`);

    buttons.forEach(button => {
        const value = button.getAttribute('data-value');
        if (selectedValues.includes(value)) {
            button.classList.add('selected');
        } else {
            button.classList.remove('selected');
        }
    });
}

// 应用时间范围缩放
function applyTimeRangeScaling() {
    // 移除旧的样式
    const existingStyle = document.getElementById('time-range-48-style');
    if (existingStyle) {
        existingStyle.remove();
    }

    if (currentTimeRange === 48) {
        // 48小时模式：调整格子最小宽度以适应更多格子
        // marks 连续轴不用 timeline-container 的半格平移，否则顶轴与内容竖线错位
        const marksMode = typeof isFlightMarksMode === 'function' && isFlightMarksMode();
        const style = document.createElement('style');
        style.id = 'time-range-48-style';
        style.textContent = `
            /* 48小时模式：减小格子最小宽度 - 统一处理所有区域 */
            .timeline-cell,
            .timeline-slot,
            .taf-cell,
            .timeline-background-slot {
                min-width: 30px !important;
            }
            ${marksMode ? '' : `
            /* 48小时模式：调整时间刻度偏移量（三段式等宽格） */
            .timeline-container {
                transform: translateX(calc(-100% / 48 / 2)) !important;
            }
            `}
        `;

        document.head.appendChild(style);
    }
}

// 旧的00时线加粗函数已被新的网格系统替代

// 生成时间轴
function fillMarksHourTicks(beijingTimeline, utcTimeline) {
    beijingTimeline.innerHTML = '';
    utcTimeline.innerHTML = '';
    beijingTimeline.style.position = 'relative';
    utcTimeline.style.position = 'relative';
    beijingTimeline.style.transform = 'none';
    utcTimeline.style.transform = 'none';
    const winStart = getMarksWindowStartMs();
    const dur = getMarksWindowDurationMs();
    const winEnd = winStart + dur;
    const makeTick = (parent, ms, text) => {
        const pct = ((ms - winStart) / dur) * 100;
        if (pct < -0.1 || pct > 100.1) return;
        const el = document.createElement('div');
        el.className = 'timeline-slot timeline-slot-abs';
        el.style.left = `${pct}%`;
        el.textContent = text;
        parent.appendChild(el);
    };
    const firstHour = new Date(winStart);
    firstHour.setSeconds(0, 0);
    firstHour.setMinutes(0, 0, 0);
    if (firstHour.getTime() <= winStart) firstHour.setHours(firstHour.getHours() + 1);
    for (let t = firstHour.getTime(); t <= winEnd; t += 3600000) {
        const dt = new Date(t);
        let bjH, utcH;
        if (currentTimeMode === 'test') {
            utcH = dt.getUTCHours().toString().padStart(2, '0');
            bjH = new Date(dt.getTime() + 8 * 3600000).getUTCHours().toString().padStart(2, '0');
        } else {
            bjH = dt.getHours().toString().padStart(2, '0');
            utcH = new Date(dt.getTime() - 8 * 3600000).getHours().toString().padStart(2, '0');
        }
        makeTick(beijingTimeline, t, bjH);
        makeTick(utcTimeline, t, utcH);
    }
    return { winStart, dur };
}

function generateTimeline() {
    const beijingTimeline = document.getElementById('beijing-timeline');
    const utcTimeline = document.getElementById('utc-timeline');

    if (!beijingTimeline || !utcTimeline) return;

    // 清空现有内容
    beijingTimeline.innerHTML = '';
    utcTimeline.innerHTML = '';

    // 获取当前时间（根据时间模式）
    const currentTime = getCurrentTime();

    // 创建底层背景时间轴
    const titleTimeline = document.querySelector('.title-timeline');
    let backgroundTimeline = titleTimeline.querySelector('.timeline-background');

    // 如果背景时间轴已存在，先删除（因为时间范围可能已改变）
    if (backgroundTimeline) {
        backgroundTimeline.remove();
        backgroundTimeline = null;
    }

    if (!backgroundTimeline) {
        backgroundTimeline = document.createElement('div');
        backgroundTimeline.className = 'timeline-background';

        // 仅保留与当前展示模式对应的一层背景刻度
        const bgRowClass = window.displayTimezone === 'UTC' ? 'utc-time' : 'beijing-time';
        const bgRow = document.createElement('div');
        bgRow.className = `timeline-background-row ${bgRowClass}`;
        const bgContainer = document.createElement('div');
        bgContainer.className = 'timeline-background-container';
        bgRow.appendChild(bgContainer);

        backgroundTimeline.appendChild(bgRow);
        titleTimeline.appendChild(backgroundTimeline);
    }

    // 生成动态数量的时间段
    const marksMode = typeof isFlightMarksMode === 'function' && isFlightMarksMode();
    if (marksMode && typeof fillMarksHourTicks === 'function') {
        // 连续轴刻度：取消三段式半格平移，否则数字相对下方竖线整体偏左
        // 若上次误包了 slide 层，先拆回，避免时刻行结构被破坏
        if (typeof unwrapMarksTitleSlideLayer === 'function') {
            unwrapMarksTitleSlideLayer(titleTimeline);
        }
        const { winStart, dur } = fillMarksHourTicks(beijingTimeline, utcTimeline);
        if (typeof updateMarksNowBadge === 'function') {
            updateMarksNowBadge(titleTimeline, winStart, dur);
        }
    } else {
        beijingTimeline.style.transform = '';
        utcTimeline.style.transform = '';
        if (typeof removeMarksNowBadge === 'function') removeMarksNowBadge();
        if (typeof unwrapMarksTitleSlideLayer === 'function') unwrapMarksTitleSlideLayer(titleTimeline);
    for (let i = 0; i < currentTimeRange; i++) {
        let beijingHour, utcHour;

        if (currentTimeMode === 'test') {
            // test模式：currentTime是UTC时间
            const utcTime = new Date(currentTime.getTime() + i * 60 * 60 * 1000);
            utcHour = utcTime.getUTCHours().toString().padStart(2, '0');

            // 北京时（UTC + 8小时）
            const beijingTime = new Date(utcTime.getTime() + 8 * 60 * 60 * 1000);
            beijingHour = beijingTime.getUTCHours().toString().padStart(2, '0');
        } else {
            // current模式：currentTime是本地时间
            const localTime = new Date(currentTime.getTime() + i * 60 * 60 * 1000);
            beijingHour = localTime.getHours().toString().padStart(2, '0');

            // UTC时间（本地时间 - 8小时）
            const utcTime = new Date(localTime.getTime() - 8 * 60 * 60 * 1000);
            utcHour = utcTime.getHours().toString().padStart(2, '0');
        }

        // 创建时间槽（第一个位置不显示刻度数字）
        const beijingSlot = document.createElement('div');
        beijingSlot.className = 'timeline-slot';
        beijingSlot.textContent = i === 0 ? '' : beijingHour;
        if (i === 0) {
            beijingSlot.classList.add('current-time');
        }
        beijingTimeline.appendChild(beijingSlot);

        const utcSlot = document.createElement('div');
        utcSlot.className = 'timeline-slot';
        utcSlot.textContent = i === 0 ? '' : utcHour;
        if (i === 0) {
            utcSlot.classList.add('current-time');
        }
        utcTimeline.appendChild(utcSlot);
    }
    }
}

// 获取当前时间（根据时间模式）
function getCurrentTime() {
    if (currentTimeMode === 'test') {
        // 测试模式：使用后端传递的测试时间（UTC）
        if (window.testTimeISO) {
            return new Date(window.testTimeISO);
        } else {
            // fallback: 使用默认测试时间（UTC）
            return new Date('2025-05-10T03:25:00Z');
        }
    } else {
        // 当前时间模式：直接使用系统当前时间
        return new Date();
    }
}

// 加载初始数据
function loadInitialData() {
    showLoading();
    if (typeof ensurePopupSeatSession === 'function') ensurePopupSeatSession();
    initializePopupSettings();
    triggerParsingAndLoadData();
}

// 手动刷新入口（保留兼容，实际由 handleRefreshButtonClick 驱动）
function refreshManualData() {
    doManualRefresh();
}

// 触发解析并加载数据
function triggerParsingAndLoadData() {
    const parsingUrl = `/${currentTimeMode}/api/trigger-parsing/`;
    const dataUrl = `/${currentTimeMode}/api/airports/overview/`;

    console.log('🚀 开始执行解析程序...');

    // 设置解析进行中标志
    window.isParsingInProgress = true;

    // 第一步：触发解析
    const headers = {
        'Content-Type': 'application/json',
    };

    // 在current模式下添加认证头
    if (currentTimeMode === 'current' && currentToken) {
        headers['Authorization'] = `Bearer ${currentToken}`;
        if (currentUserCode) {
            headers['X-User-Code'] = currentUserCode;
        }
    }

    // 在test模式下添加测试用户代码
    if (currentTimeMode === 'test') {
        headers['X-User-Code'] = 'test';
    }

    fetch(parsingUrl, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ nwpEnabled: nwpEnabled })
    })
        .then(response => {
            if (response.status === 401) {
                throw new Error('TOKEN_INVALID');
            }
            return response.json();
        })
        .then(parsingResult => {
            if (parsingResult.success) {
                console.log('✅ 解析完成:', parsingResult.message);
                console.log('📊 解析结果详情:', parsingResult.data);

                // 显示解析的机场信息
                if (parsingResult.data && parsingResult.data.active_airports) {
                    console.log(`🏢 解析了 ${parsingResult.data.active_airports.length} 个有航班的机场:`, parsingResult.data.active_airports);
                }

                // 显示各解析器的执行情况
                if (parsingResult.data && parsingResult.data.parsers) {
                    console.log('📈 各解析器执行情况:');
                    Object.keys(parsingResult.data.parsers).forEach(parser => {
                        const result = parsingResult.data.parsers[parser];
                        const status = result.success ? '✅成功' : '❌失败';
                        const records = result.record_count || result.success_count || 0;
                        console.log(`  - ${parser}: ${status} (${records}条记录)`);

                        // 如果失败，显示详细错误信息
                        if (!result.success) {
                            console.log(`    失败原因: ${result.message || '未知错误'}`);
                            if (result.errors && result.errors.length > 0) {
                                console.log(`    错误详情:`, result.errors);
                            }
                        }

                        // 显示更多统计信息
                        if (result.total_processed) {
                            console.log(`    处理总数: ${result.total_processed}, 成功: ${result.success_count || 0}, 失败: ${result.error_count || 0}`);
                        }
                    });
                }

                // 保存解析结果
                console.log('💾 保存解析结果:', parsingResult.data);

                console.log('📡 开始获取最新数据...');
                // 第二步：获取最新数据
                return fetch(dataUrl, { headers: headers });
            } else {
                console.warn('⚠️ 解析失败，继续尝试获取现有数据:', parsingResult.message);
                console.error('❌ 解析错误详情:', parsingResult);

                // 设置解析状态为错误
                updateParsingStatus('error');

                // 即使解析失败，也尝试获取现有数据
                return fetch(dataUrl, { headers: headers });
            }
        })
        .then(response => {
            if (response.status === 401) {
                throw new Error('TOKEN_INVALID');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log('✅ 数据获取成功');
                console.log(`📋 获取到 ${data.data.airports.length} 个机场的数据`);
                console.log(`🏛️ 获取到 ${data.data.carriers.length} 个承运人`);

                airportData = data.data.airports;
                currentCarriers = data.data.carriers;

                // 从 metar 数据同步入库告警状态
                if (typeof syncAlertStateFromMetarData === 'function') {
                    syncAlertStateFromMetarData(airportData);
                }

                if (typeof syncAlertStateFromTafData === 'function') {
                    syncAlertStateFromTafData(airportData);
                }

                // 注意：数据时间已在解析完成时更新，这里不再重复更新

                // 更新航班状态警告
                updateFlightStatusWarning(data.data.flight_status);

                // 更新区域选项
                if (data.data.area_options) {
                    currentAreaOptions = data.data.area_options;

                    // 检查是否需要重置区域筛选（强制刷新或清除缓存时）
                    const needResetRegions = sessionStorage.getItem('mtws_reset_regions');
                    if (needResetRegions) {
                        // 重置为所有区域选中
                        filters.domestic = currentAreaOptions.domestic.map(region => region.area);
                        filters.international = currentAreaOptions.international.map(region => region.area);
                        sessionStorage.removeItem('mtws_reset_regions');
                    } else if (!filters.domestic.length && !filters.international.length) {
                        // 初始化时默认选中所有区域（兼容原有逻辑）
                        filters.domestic = currentAreaOptions.domestic.map(region => region.area);
                        filters.international = currentAreaOptions.international.map(region => region.area);
                    }

                    console.log(`🌍 获取到区域选项: 国内${currentAreaOptions.domestic.length}个, 国际${currentAreaOptions.international.length}个`);

                    // 动态生成区域按钮
                    generateRegionButtons();

                    // 更新区域按钮状态
                    updateRegionButtonState('domestic');
                    updateRegionButtonState('international');
                }

                updateCarrierDisplay();
                applyFilters();
                updateStatusFromPollResult(data.data.parsing_status || {}, true);
                if (data.data.seat_identity) {
                    window.__seatIdentity = data.data.seat_identity;
                    paintSeatUserInfo();
                }
                if (maybeHandleAuthExpired(data)) {
                    return;
                }

                // 如果 NWP 温度辅助已开启，触发 NWP 解析并渲染
                if (nwpEnabled) {
                    fetchNwpDataAndRender();
                }

                console.log('🎉 页面数据更新完成');

                // 数据更新完成，不需要额外设置状态
                // 状态应该已经在解析完成时被正确设置了
            } else {
                console.error('❌ 数据获取失败:', data.error);
                // 数据获取失败时重置所有时间
                dataUpdateTimes.metar = '--:--:--';
                dataUpdateTimes.taf = '--:--:--';
                dataUpdateTimes.flight = '--:--:--';
                showError('加载数据失败：' + data.error);
            }
        })
        .catch(error => {
            console.error('❌ 数据加载过程失败:', error);
            if (error.message === 'TOKEN_INVALID') {
                handleSessionExpired('initial load 401');
            } else {
                handleApiError(error);
            }
        })
        .finally(() => {
            hideLoading();
            // 清除解析进行中标志
            window.isParsingInProgress = false;
        });
}

// 显示加载状态
function showLoading() {
    const contentMain = document.getElementById('content-main');
    contentMain.innerHTML = `
        <div class="loading-message">
            <div class="loading-spinner"></div>
            正在加载数据...
        </div>
    `;
}

// 隐藏加载状态
function hideLoading() {
    // 由其他函数负责更新内容
}

// 显示错误信息
function showError(message) {
    const contentMain = document.getElementById('content-main');
    contentMain.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">⚠️</div>
            <div class="empty-state-message">${message}</div>
        </div>
    `;
}

/**
 * 服务器恢复后静默触发一次 trigger-parsing，将前端 token 重新注入后端调度器。
 * 仅在 current 模式且持有有效 token 时执行，不更新任何 UI 元素。
 * 下一次 30 秒轮询会自动刷新状态指示器，用户无感知。
 */
function silentTokenReinjection() {
    if (currentTimeMode !== 'current' || !currentToken) return;

    console.log('🔑 服务器重启后静默重注入 token...');
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`,
    };
    if (currentUserCode) {
        headers['X-User-Code'] = currentUserCode;
    }

    fetch(`/${currentTimeMode}/api/trigger-parsing/`, {
        method: 'POST',
        headers: headers,
    })
    .then(response => {
        if (response.ok) {
            console.log('✅ Token 重注入成功，后端调度器已恢复 token 缓存');
        } else {
            console.warn('⚠️ Token 重注入请求返回非正常状态:', response.status);
        }
    })
    .catch(err => {
        console.warn('⚠️ Token 重注入请求失败:', err.message || err);
    });
}

// 显示服务器断连横幅（连续轮询失败时调用，不替换页面内容）
function showServerOfflineBanner(failCount) {
    const banner = document.getElementById('server-offline-banner');
    if (!banner) return;
    banner.textContent = `⚠ 服务器连接已断开（已失败 ${failCount} 次），正在等待重连...`;
    banner.classList.add('visible');
}

// 隐藏服务器断连横幅（轮询恢复后调用）
function hideServerOfflineBanner() {
    const banner = document.getElementById('server-offline-banner');
    if (banner) banner.classList.remove('visible');
}

function hideMetarPopupsForLogin() {
    if (typeof stopPopupCheck === 'function') {
        stopPopupCheck();
    }
    if (typeof hideMetarPopupOverlay === 'function') {
        hideMetarPopupOverlay();
    }
}

function ensureLoginModalOnTop() {
    const loginModal = document.getElementById('login-modal');
    if (!loginModal) return;
    hideMetarPopupsForLogin();
    document.body.appendChild(loginModal);
    loginModal.style.zIndex = '40000';
}

function handleSessionExpired(reason) {
    if (window.tokenInvalidDetected) {
        ensureLoginModalOnTop();
        const loginModal = document.getElementById('login-modal');
        if (loginModal && loginModal.style.display !== 'block') {
            showLoginModal();
        }
        return;
    }
    if (reason) {
        console.warn('登录已过期：', reason);
    }
    stopUnifiedAuthWatch();
    clearAuthState();
    stopAllAutoRefresh();
    showTokenInvalidError();
}

function maybeHandleAuthExpired(data) {
    const authStatus = data && data.data && data.data.auth_status;
    if (authStatus && authStatus.expired) {
        handleSessionExpired('AuthBroker expired');
        return true;
    }
    return false;
}

// 显示token失效错误信息
function showTokenInvalidError() {
    const contentMain = document.getElementById('content-main');
    if (contentMain) {
        contentMain.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">⚠️</div>
                <div class="empty-state-message">登录过期或异地登录，数据加载失败</div>
                <button onclick="handleRelogin()" class="relogin-btn">重新登录</button>
            </div>
        `;
    }

    // 重置所有数据时间为--:--:--
    dataUpdateTimes.metar = '--:--:--';
    dataUpdateTimes.taf = '--:--:--';
    dataUpdateTimes.flight = '--:--:--';
    updateStatusTimeDisplay('metar', '--:--:--');
    updateStatusTimeDisplay('taf', '--:--:--');
    updateStatusTimeDisplay('flight', '--:--:--');

    // 隐藏用户信息
    hideUserInfo();
    hideMetarPopupsForLogin();
    showLoginModal();
}

// 处理重新登录
function handleRelogin() {
    // 清除token失效标志
    window.tokenInvalidDetected = false;
    // 清除认证状态
    clearAuthState();
    // 显示登录模态框
    showLoginModal();
}

// 统一的API错误处理函数
function handleApiError(error) {
    if (currentTimeMode === 'current' && currentToken) {
        // current模式下验证token状态
        validateTokenAndShowError();
    } else {
        // test模式或无token，显示通用错误
        showGeneralError();
    }
}

// Token验证和错误显示
function validateTokenAndShowError() {
    fetch(`/${currentTimeMode}/api/validate-token/`, {
        headers: getRequestHeaders()
    })
        .then(response => {
            if (response.status === 401) {
                handleSessionExpired('validate-token 401');
            } else {
                // 其他错误：显示通用提示 + 继续自动刷新
                showGeneralError();
            }
        })
        .catch(() => {
            // 验证接口本身失败，当作通用错误处理
            showGeneralError();
        });
}

// 显示通用错误（无按钮）
function showGeneralError() {
    const contentMain = document.getElementById('content-main');
    contentMain.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">⚠️</div>
            <div class="empty-state-message">数据处理失败，请刷新页面重试</div>
        </div>
    `;

    // 重置所有数据时间为--:--:--
    dataUpdateTimes.metar = '--:--:--';
    dataUpdateTimes.taf = '--:--:--';
    dataUpdateTimes.flight = '--:--:--';
    updateStatusTimeDisplay('metar', '--:--:--');
    updateStatusTimeDisplay('taf', '--:--:--');
    updateStatusTimeDisplay('flight', '--:--:--');
}

// 停止所有自动刷新
function stopAllAutoRefresh() {
    // 清除数据轮询计时器
    if (window.autoRefreshTimer) {
        clearInterval(window.autoRefreshTimer);
        window.autoRefreshTimer = null;
    }

    // 清除时间轴独立刷新计时器
    if (window.timelineRefreshTimer) {
        clearInterval(window.timelineRefreshTimer);
        window.timelineRefreshTimer = null;
    }

    // 清除所有待处理的更新请求
    pendingRequests.clear();

    // 设置token失效标志
    window.tokenInvalidDetected = true;

    console.log('🛑 检测到token失效，已停止所有自动刷新');
}

// 更新承运人显示
// updateCarrierDisplay → 已迁移至 main_flight.js

// 绑定事件处理器
function bindEvents() {
    // 筛选按钮点击事件
    document.addEventListener('click', function (e) {
        if (e.target.classList.contains('filter-btn')) {
            // 检查是否是弹窗开关按钮
            if (e.target.classList.contains('popup-toggle-btn')) {
                handleToggleClick(e.target);
            } else {
                handleFilterClick(e.target);
            }
        }

        // 机场代码点击事件
        if (e.target.classList.contains('airport-code')) {
            const airportCode = e.target.textContent;
            showAirportDetail(airportCode);
        }
    });

    // 筛选按钮右键点击事件
    document.addEventListener('contextmenu', function (e) {
        if (e.target.classList.contains('filter-btn')) {
            e.preventDefault(); // 阻止默认右键菜单
            handleFilterRightClick(e.target);
        }
    });

    // 功能按钮事件
    document.getElementById('settings-btn').addEventListener('click', function () {
        if (window.SettingsModal) {
            window.SettingsModal.open();
        }
    });

    document.getElementById('monitor-btn').addEventListener('click', function () {
        showModal('monitor-modal');
    });

    document.getElementById('search-btn').addEventListener('click', function () {
        const searchValue = document.getElementById('search-input').value.trim();
        if (searchValue) {
            handleSearchClick(searchValue);
        }
    });

    const nwpBtn = document.getElementById('nwp-btn');
    if (nwpBtn) {
        nwpBtn.addEventListener('click', handleNwpToggle);
    }

    document.getElementById('refresh-btn').addEventListener('click', function () {
        refreshData();
    });

    // 搜索框回车事件
    document.getElementById('search-input').addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            const searchValue = this.value.trim();
            if (searchValue) {
                handleSearchClick(searchValue);
            }
        }
    });

    // 搜索框输入时控制清除按钮的显隐
    const searchInput = document.getElementById('search-input');
    const searchClearBtn = document.getElementById('search-clear-btn');
    if (searchInput && searchClearBtn) {
        searchInput.addEventListener('input', function () {
            if (this.value.length > 0) {
                searchClearBtn.classList.add('visible');
            } else {
                searchClearBtn.classList.remove('visible');
            }
        });
        searchClearBtn.addEventListener('click', function () {
            searchInput.value = '';
            searchClearBtn.classList.remove('visible');
            searchInput.focus();
        });
    }

    // 点击弹窗背景（.modal 本身）关闭可关闭的弹窗（仅当该弹窗是最顶层时）
    document.querySelectorAll('.modal').forEach(function (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target !== modal) return;
            // 确认当前 modal 是 z-index 最高的可见弹窗
            if (getTopmostModal() === modal && canDismissModal(modal)) {
                hideModal(modal.id);
            }
        });
    });

    // 告警裕度横向轨道点击事件
    const marginTrack = document.getElementById('margin-v-track');
    if (marginTrack) {
        marginTrack.addEventListener('click', function (e) {
            const rect = this.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const fraction = Math.min(1, Math.max(0, clickX / rect.width));
            const newValue = Math.min(4, Math.floor(fraction * 5));
            handleMarginSliderChange(newValue);
        });
    }

    // 时间范围 toggle 事件
    document.getElementById('time-range-toggle-input').addEventListener('change', function (e) {
        handleTimeRangeToggleChange(e.target.checked);
    });

    function canDismissModal(modal) {
        // 登录二维码是强制登录态入口：不能点遮罩或按 ESC 关闭，避免未登录时弹码消失。
        // 设置弹窗：只能通过自带的关闭按钮关闭，不可通过点击遮罩或按 ESC 关闭。
        return modal && modal.id !== 'login-modal' && modal.id !== 'settings-modal';
    }

    /** 返回当前所有可见弹窗中 z-index 最高的那个（即视觉最顶层） */
    function getTopmostModal() {
        const visible = Array.from(document.querySelectorAll('.modal')).filter(
            m => m.style.display === 'block'
        );
        if (!visible.length) return null;
        return visible.reduce((top, m) => {
            const zTop = parseInt(window.getComputedStyle(top).zIndex) || 0;
            const zM   = parseInt(window.getComputedStyle(m).zIndex)   || 0;
            return zM > zTop ? m : top;
        });
    }

    // 弹窗关闭事件
    document.querySelectorAll('.modal-close').forEach(closeBtn => {
        closeBtn.addEventListener('click', function () {
            const modal = this.closest('.modal');
            if (canDismissModal(modal)) hideModal(modal.id);
        });
    });

    // ESC键关闭弹窗 & Ctrl+Shift+R检测
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            // 按 z-index 排序，取最顶层的可见弹窗关闭
            const openModal = getTopmostModal();
            if (canDismissModal(openModal)) {
                hideModal(openModal.id);
            }
        }

        // 检测Ctrl+Shift+R (强制刷新)
        if (e.ctrlKey && e.shiftKey && e.key === 'R') {
            // 标记为强制刷新，重置为默认状态
            sessionStorage.setItem('mtws_force_refresh', 'true');
        }
    });

    // 点击模态背景关闭弹窗
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function (e) {
            if (e.target === this && canDismissModal(this)) {
                hideModal(this.id);
            }
        });
    });

    // 登出按钮事件
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function () {
            showModal('logout-confirm-modal');
        });
    }

    // 登出确认按钮事件
    const logoutConfirmBtn = document.getElementById('logout-confirm-btn');
    if (logoutConfirmBtn) {
        logoutConfirmBtn.addEventListener('click', function () {
            hideModal('logout-confirm-modal');
            const logoutBtn = document.getElementById('logout-btn');
            if (logoutBtn && logoutBtn.dataset.seatLogout === '1' && typeof accessSeatLogout === 'function') {
                accessSeatLogout();
            } else {
                logout();
            }
        });
    }

    // 登出取消按钮事件
    const logoutCancelBtn = document.getElementById('logout-cancel-btn');
    if (logoutCancelBtn) {
        logoutCancelBtn.addEventListener('click', function () {
            hideModal('logout-confirm-modal');
        });
    }

    // 设置自动登出处理
    if (currentTimeMode === 'current') {
        setupAutoLogout();
    }
}

// 初始化弹窗设置（席位本地）
function loadPopupDisplayPrefs() {
    const defaults = {
        operation: false,
        parking: false,
        intercept: true,
        operationSince: 0,
        parkingSince: 0
    };
    try {
        const raw = sessionStorage.getItem(POPUP_PREFS_KEY);
        if (!raw) return defaults;
        return { ...defaults, ...JSON.parse(raw) };
    } catch (e) {
        return defaults;
    }
}

function savePopupDisplayPrefs(prefs) {
    sessionStorage.setItem(POPUP_PREFS_KEY, JSON.stringify(prefs));
}

function ensurePopupSeatSession() {
    if (typeof hasAccess === 'function' && window.__accessIdentity
        && !hasAccess('metar_popup', 'display')) {
        return;
    }
    if (sessionStorage.getItem(POPUP_SEAT_READY_KEY) === '1') return;
    const now = Date.now();
    savePopupDisplayPrefs({
        operation: true,
        parking: true,
        intercept: true,
        operationSince: now,
        parkingSince: now
    });
    sessionStorage.setItem(POPUP_SEAT_READY_KEY, '1');
}

function clearPopupSeatSession() {
    try { sessionStorage.removeItem(POPUP_PREFS_KEY); } catch (e) { /* ignore */ }
    try { sessionStorage.removeItem(POPUP_SEAT_READY_KEY); } catch (e) { /* ignore */ }
    try { localStorage.removeItem(POPUP_DISMISSED_KEY); } catch (e) { /* ignore */ }
    try { localStorage.removeItem(POPUP_PREFS_KEY); } catch (e) { /* ignore */ }
}
window.ensurePopupSeatSession = ensurePopupSeatSession;
window.clearPopupSeatSession = clearPopupSeatSession;

function getDismissedPopupSqcSet() {
    try {
        const raw = localStorage.getItem(POPUP_DISMISSED_KEY);
        const list = raw ? JSON.parse(raw) : [];
        return new Set(Array.isArray(list) ? list.map(String) : []);
    } catch (e) {
        return new Set();
    }
}

function markPopupsDismissedLocally(sqcList) {
    const set = getDismissedPopupSqcSet();
    (sqcList || []).forEach(sqc => set.add(String(sqc)));
    const list = Array.from(set);
    if (list.length > 3000) {
        list.splice(0, list.length - 3000);
    }
    localStorage.setItem(POPUP_DISMISSED_KEY, JSON.stringify(list));
}

function popupMatchesLocalPrefs(popup) {
    const prefs = loadPopupDisplayPrefs();
    if (getDismissedPopupSqcSet().has(String(popup.sqc))) {
        return false;
    }
    const allowed = prefs.intercept ? ['Y'] : ['Y', 'I'];
    const traceHours = Number(window.__popupTraceHours);
    const Tms = (Number.isFinite(traceHours) ? Math.max(0, Math.min(9, traceHours)) : 6) * 3600000;
    const now = Date.now();
    const inTraceWindow = (since) => {
        if (!since) return false;
        const pt = popup.popup_time || 0;
        return pt >= (since - Tms) && pt <= now;
    };
    const opOk = prefs.operation
        && allowed.includes(popup.operation_popup)
        && inTraceWindow(prefs.operationSince);
    const pkOk = prefs.parking
        && allowed.includes(popup.parking_popup)
        && inTraceWindow(prefs.parkingSince);
    return opOk || pkOk;
}

function initializePopupSettings() {
    const prefs = loadPopupDisplayPrefs();
    updateToggleState('operation-toggle', prefs.operation);
    updateToggleState('parking-toggle', prefs.parking);
    updateToggleState('intercept-toggle', prefs.intercept);
}

window.updateToggleState = updateToggleState;
window.loadPopupDisplayPrefs = loadPopupDisplayPrefs;
window.popupMatchesLocalPrefs = popupMatchesLocalPrefs;
window.markPopupsDismissedLocally = markPopupsDismissedLocally;

// 更新开关状态
function updateToggleState(toggleId, isActive) {
    const toggle = document.getElementById(toggleId);
    if (toggle) {
        if (isActive) {
            toggle.classList.add('selected');
        } else {
            toggle.classList.remove('selected');
        }
    }
}

// 处理开关点击（仅本机，不写库）
function handleToggleClick(toggle) {
    const field = toggle.getAttribute('data-field');
    const prefs = loadPopupDisplayPrefs();
    const nowOn = !toggle.classList.contains('selected');
    const now = Date.now();

    if (field === 'operation') {
        prefs.operation = nowOn;
        prefs.operationSince = nowOn ? now : 0;
    } else if (field === 'parking') {
        prefs.parking = nowOn;
        prefs.parkingSince = nowOn ? now : 0;
    } else if (field === 'intercept') {
        prefs.intercept = nowOn;
    }

    savePopupDisplayPrefs(prefs);
    updateToggleState(toggle.id, nowOn);
    if (typeof checkAndShowPopups === 'function') {
        checkAndShowPopups();
    }
}

// 处理筛选按钮点击
// 处理告警裕度滑块变化
function handleMarginSliderChange(newValue) {
    const oldMargin = filters.margin;
    newValue = parseInt(newValue);

    if (oldMargin !== newValue) {
        filters.margin = newValue;
        setMarginThumbPosition(newValue);
        saveFiltersToStorage();

        if (airportData && airportData.length > 0) {
            applyFilters();
        } else {
            loadInitialData();
        }
    }
}

// 处理时间范围 toggle 变化（false=36h, true=48h）
function handleTimeRangeToggleChange(checked) {
    const newTimeRange = checked ? 48 : 36;
    const oldTimeRange = currentTimeRange;

    if (oldTimeRange !== newTimeRange) {
        currentTimeRange = newTimeRange;
        saveTimeRangeToStorage();
        generateTimeline();
        applyTimeRangeScaling();

        if (airportData && airportData.length > 0) {
            applyFilters();
            setTimeout(() => {
                updateAllAirportGrids();
            }, 100);
        }
    }
}

function handleFilterClick(button) {
    const group = button.getAttribute('data-group');
    const value = button.getAttribute('data-value');

    if (group === 'margin') {
        // 告警裕度：单选（兜底分支，统一走 handleMarginSliderChange）
        handleMarginSliderChange(value);
    } else if (group === 'time-range') {
        // 时间范围：单选
        const oldTimeRange = currentTimeRange;
        const newTimeRange = parseInt(value);

        // 只有当时间范围发生变化时才触发刷新
        if (oldTimeRange !== newTimeRange) {
            currentTimeRange = newTimeRange;
            updateButtonGroupState('time-range', [value]);

            // 保存时间范围状态
            saveTimeRangeToStorage();

            // 重新生成时间轴和重新渲染页面
            generateTimeline();

            // 应用48小时模式的宽度压缩
            applyTimeRangeScaling();

            if (airportData && airportData.length > 0) {
                applyFilters(); // 重新应用筛选和重新渲染

                // 更新网格系统
                setTimeout(() => {
                    updateAllAirportGrids();
                }, 100);
            }
        }
    } else if (group === 'alert' || group === 'domestic' || group === 'international') {
        if (document.body.classList.contains('trend-alert-locked')) return;
        if (group !== 'alert') {
            if (group === 'domestic') {
                handleRegionFilter('domestic', value);
            } else {
                handleRegionFilter('international', value);
            }
            saveFiltersToStorage();
            applyFilters();
            return;
        }
        // 告警等级筛选：特殊逻辑
        handleAlertFilter(value);

        // 保存筛选状态
        saveFiltersToStorage();

        // 应用筛选
        applyFilters();
    } else {
        // 其他筛选：多选逻辑
        handleMultiSelectFilter(group, value);

        // 保存筛选状态
        saveFiltersToStorage();

        // 应用筛选
        applyFilters();
    }
}

// 处理筛选按钮右键点击
function handleFilterRightClick(button) {
    const group = button.getAttribute('data-group');
    const value = button.getAttribute('data-value');

    // 只处理区域筛选按钮的右键点击
    if (group === 'domestic' || group === 'international') {
        if (value === 'all') {
            // 【全部】按钮右键点击：单选该分类下的所有区域
            handleAllButtonRightClick(group);
        } else {
            // 普通区域按钮右键点击：单选模式
            handleRegionRightClick(group, value);

            // 保存筛选状态
            saveFiltersToStorage();

            // 应用筛选
            applyFilters();
        }
    }
    // 其他按钮的右键点击不做处理
}

// 处理【全部】按钮右键点击（单选该分类下的所有区域）
function handleAllButtonRightClick(clickedGroup) {
    // 清空所有区域筛选
    filters.domestic = [];
    filters.international = [];

    // 获取被点击分类下的所有区域
    const allRegions = currentAreaOptions[clickedGroup] || [];
    const allRegionNames = allRegions.map(region => region.area);

    // 选中该分类下的所有区域
    filters[clickedGroup] = [...allRegionNames];

    // 更新所有区域按钮状态
    updateRegionButtonState('domestic');
    updateRegionButtonState('international');

    // 保存筛选状态
    saveFiltersToStorage();

    // 应用筛选
    applyFilters();
}

// 处理区域按钮右键点击（单选模式）
function handleRegionRightClick(clickedGroup, clickedValue) {
    // 清空所有区域筛选
    filters.domestic = [];
    filters.international = [];

    // 只选中被右键点击的区域
    filters[clickedGroup] = [clickedValue];

    // 更新所有区域按钮状态
    updateRegionButtonState('domestic');
    updateRegionButtonState('international');
}

// 处理告警等级筛选
function handleAlertFilter(value) {
    if (value === 'all') {
        // 点击"全部"按钮
        const allAlertLevels = ['red', 'yellow', 'green', 'none'];

        if (allAlertLevels.every(level => filters.alert.includes(level))) {
            // 如果当前全部选中，则取消全选
            filters.alert = [];
        } else {
            // 否则全选
            filters.alert = [...allAlertLevels];
        }
    } else {
        // 点击具体告警级别
        if (filters.alert.includes(value)) {
            // 取消选择
            filters.alert = filters.alert.filter(v => v !== value);
        } else {
            // 添加选择
            filters.alert.push(value);
        }
    }

    // 更新按钮状态
    updateAlertButtonState();
}

// 处理区域筛选（国内/国际）
function handleRegionFilter(group, value) {
    const allRegions = currentAreaOptions[group] || [];
    const allRegionNames = allRegions.map(region => region.area);

    if (value === 'all') {
        // 点击"全部"按钮
        if (allRegionNames.every(regionName => filters[group].includes(regionName))) {
            // 如果当前全部选中，则取消全选
            filters[group] = [];
        } else {
            // 否则全选
            filters[group] = [...allRegionNames];
        }
    } else {
        // 点击具体区域
        if (filters[group].includes(value)) {
            // 取消选择
            filters[group] = filters[group].filter(v => v !== value);
        } else {
            // 添加选择
            filters[group].push(value);
        }
    }

    // 更新按钮状态
    updateRegionButtonState(group);
}

// 动态生成区域按钮
function generateRegionButtons() {
    // 生成国内区域按钮
    const domesticContainer = document.getElementById('domestic-button-group');
    if (domesticContainer && currentAreaOptions.domestic) {
        domesticContainer.innerHTML = '';

        // 添加全部按钮
        const allButton = document.createElement('button');
        allButton.className = 'filter-btn domestic-all';
        allButton.setAttribute('data-group', 'domestic');
        allButton.setAttribute('data-value', 'all');
        allButton.textContent = '全部';
        allButton.appendChild(document.createElement('span'));
        allButton.lastElementChild.className = 'region-alert-dot';
        domesticContainer.appendChild(allButton);

        // 添加各个区域按钮
        currentAreaOptions.domestic.forEach(region => {
            const button = document.createElement('button');
            button.className = 'filter-btn domestic-area';
            button.setAttribute('data-group', 'domestic');
            button.setAttribute('data-value', region.area);
            button.textContent = region.area;
            button.appendChild(document.createElement('span'));
            button.lastElementChild.className = 'region-alert-dot';
            domesticContainer.appendChild(button);
        });
    }

    // 生成国际区域按钮
    const internationalContainer = document.getElementById('international-button-group');
    if (internationalContainer && currentAreaOptions.international) {
        internationalContainer.innerHTML = '';

        // 添加全部按钮
        const allButton = document.createElement('button');
        allButton.className = 'filter-btn international-all';
        allButton.setAttribute('data-group', 'international');
        allButton.setAttribute('data-value', 'all');
        allButton.textContent = '全部';
        allButton.appendChild(document.createElement('span'));
        allButton.lastElementChild.className = 'region-alert-dot';
        internationalContainer.appendChild(allButton);

        // 添加各个区域按钮
        currentAreaOptions.international.forEach(region => {
            const button = document.createElement('button');
            button.className = 'filter-btn international-area';
            button.setAttribute('data-group', 'international');
            button.setAttribute('data-value', region.area);
            button.textContent = region.area;
            button.appendChild(document.createElement('span'));
            button.lastElementChild.className = 'region-alert-dot';
            internationalContainer.appendChild(button);
        });
    }

    updateRegionAlertDots();
}

function setRegionAlertDot(button, level) {
    if (!button) return;
    const dot = button.querySelector('.region-alert-dot');
    if (!dot) return;
    if (level === 'R' || level === 'Y' || level === 'G') {
        dot.className = `region-alert-dot visible region-alert-dot-${level}`;
    } else {
        dot.className = 'region-alert-dot';
    }
}

function getMaxAlertLevelForAirports(airports) {
    const rank = { R: 3, Y: 2, G: 1, N: 0 };
    let maxLevel = 'N';
    let maxRank = 0;
    (airports || []).forEach(airport => {
        const level = getHighestAlertLevel(airport);
        const current = rank[level] || 0;
        if (current > maxRank) {
            maxRank = current;
            maxLevel = level;
        }
    });
    return maxLevel;
}

function updateRegionAlertDots() {
    const sources = airportData || [];
    ['domestic', 'international'].forEach(group => {
        const regions = currentAreaOptions[group] || [];
        const regionNames = regions.map(region => region.area);
        const groupAirports = sources.filter(airport => regionNames.includes(airport.area || ''));
        setRegionAlertDot(
            document.querySelector(`[data-group="${group}"][data-value="all"]`),
            getMaxAlertLevelForAirports(groupAirports)
        );
        regions.forEach(region => {
            const areaAirports = sources.filter(airport => (airport.area || '') === region.area);
            setRegionAlertDot(
                document.querySelector(`[data-group="${group}"][data-value="${region.area}"]`),
                getMaxAlertLevelForAirports(areaAirports)
            );
        });
    });
}

// 更新区域按钮状态
function updateRegionButtonState(group) {
    const allRegions = currentAreaOptions[group] || [];
    const allRegionNames = allRegions.map(region => region.area);
    const allSelected = allRegionNames.every(regionName => filters[group].includes(regionName));

    // 更新全部按钮
    const allButton = document.querySelector(`[data-group="${group}"][data-value="all"]`);
    if (allButton) {
        if (allSelected) {
            allButton.classList.add('selected');
        } else {
            allButton.classList.remove('selected');
        }
    }

    // 更新各个区域按钮
    allRegions.forEach(region => {
        const button = document.querySelector(`[data-group="${group}"][data-value="${region.area}"]`);
        if (button) {  // 确保按钮存在
            if (filters[group].includes(region.area)) {
                button.classList.add('selected');
            } else {
                button.classList.remove('selected');
            }
        }
    });
}

// 更新告警按钮状态
function updateAlertButtonState() {
    const allAlertLevels = ['red', 'yellow', 'green', 'none'];
    const allSelected = allAlertLevels.every(level => filters.alert.includes(level));

    // 更新全部按钮（可能已不存在，需判断）
    const allButton = document.querySelector('[data-group="alert"][data-value="all"]');
    if (allButton) {
        if (allSelected) {
            allButton.classList.add('selected');
        } else {
            allButton.classList.remove('selected');
        }
    }

    // 更新各个告警级别按钮
    allAlertLevels.forEach(level => {
        const button = document.querySelector(`[data-group="alert"][data-value="${level}"]`);
        if (button) {
            if (filters.alert.includes(level)) {
                button.classList.add('selected');
            } else {
                button.classList.remove('selected');
            }
        }
    });
}

// 处理多选筛选器
function handleMultiSelectFilter(group, value) {
    if (value === 'all') {
        // 点击"全部"按钮
        if (filters[group].includes('all')) {
            // 如果当前是全选状态，切换为全不选
            filters[group] = [];
        } else {
            // 否则切换为全选
            filters[group] = ['all'];
            // 同时选中所有具体选项
            const allButtons = document.querySelectorAll(`[data-group="${group}"]`);
            const allValues = Array.from(allButtons)
                .map(btn => btn.getAttribute('data-value'))
                .filter(val => val !== 'all');
            filters[group] = ['all', ...allValues];
        }
    } else {
        // 点击具体选项
        if (filters[group].includes(value)) {
            // 取消选择
            filters[group] = filters[group].filter(v => v !== value);
            // 如果没有选中任何具体选项，也取消"全部"
            if (filters[group].length === 1 && filters[group][0] === 'all') {
                filters[group] = [];
            } else {
                filters[group] = filters[group].filter(v => v !== 'all');
            }
        } else {
            // 添加选择
            filters[group].push(value);
            // 检查是否所有具体选项都被选中
            const allButtons = document.querySelectorAll(`[data-group="${group}"]`);
            const allValues = Array.from(allButtons)
                .map(btn => btn.getAttribute('data-value'))
                .filter(val => val !== 'all');

            if (allValues.every(val => filters[group].includes(val))) {
                if (!filters[group].includes('all')) {
                    filters[group].push('all');
                }
            }
        }
    }

    updateButtonGroupState(group, filters[group]);
}

// 应用筛选
// 按当前视图把筛选结果交给对应渲染器：地图由 updateMapAlert 自行取数，
// 中文模式走 plain_view.js，其余为列表主页
function renderCurrentView(airports) {
    if (window._viewMode === 'map') return;
    if (window._viewMode === 'plain') {
        if (typeof renderPlainView === 'function') renderPlainView(airports);
        return;
    }
    displayAirports(airports);
}

function applyFilters() {
    if (typeof window.syncTrendHomeFilter === 'function') window.syncTrendHomeFilter();
    if (!airportData || airportData.length === 0) {
        renderCurrentView([]);
        return;
    }

    filteredAirportData = airportData.filter(airport => {
        // 未配置机场系统置顶：不受任何筛选限制，始终显示
        if (airport.is_configured === false) {
            return true;
        }

        // 区域筛选：地图模式下忽略区域筛选，展示全部区域机场
        if (window._viewMode !== 'map' && !isRegionMatch(airport)) {
            return false;
        }

        // 用户置顶机场不受告警等级筛选限制
        if (isAirportPinned(airport.airport_4code)) {
            return true;
        }

        // 告警等级筛选
        if (!isAlertMatch(airport)) {
            return false;
        }

        return true;
    });

    // 应用排序
    applySorting();

    renderCurrentView(filteredAirportData);

    updateRegionAlertDots();

    // 地图模式同步更新地图散点
    if (typeof updateMapAlert === 'function') updateMapAlert();
}

// 检查区域筛选匹配
function isRegionMatch(airport) {
    const airportArea = airport.area || '';

    // 获取当前的区域选项
    const knownDomesticRegions = (currentAreaOptions.domestic || []).map(region => region.area);
    const knownInternationalRegions = (currentAreaOptions.international || []).map(region => region.area);

    // 检查国内区域
    if (knownDomesticRegions.includes(airportArea)) {
        if (filters.domestic.length === 0) return false;
        return filters.domestic.includes(airportArea);
    }

    // 检查国际区域
    if (knownInternationalRegions.includes(airportArea)) {
        if (filters.international.length === 0) return false;
        return filters.international.includes(airportArea);
    }

    // 区域不在已知列表中（未配置机场已在 applyFilters 中提前放行，此处不会到达）
    return false;
}

// 检查告警等级筛选匹配
function isAlertMatch(airport) {
    if (filters.alert.length === 0) return false;

    // 获取最高告警等级
    const highestAlert = getHighestAlertLevel(airport);

    const alertMapping = {
        'red': 'R',
        'yellow': 'Y',
        'green': 'G',
        'none': 'N'
    };

    return filters.alert.some(filter => alertMapping[filter] === highestAlert);
}

// 获取最高告警等级 - 使用后端预计算结果
function getHighestAlertLevel(airport) {
    try {
        // 获取当前选中的告警裕度
        const currentMargin = getSelectedAlertMargin();

        // 从预计算结果中获取对应margin的告警等级
        const computedAlerts = airport.computed_alerts || {};
        const marginKey = `margin_${currentMargin}`;
        const marginResults = computedAlerts[marginKey];

        if (marginResults && marginResults.highest_alert) {
            return marginResults.highest_alert;
        }

        // 如果预计算结果不存在，返回默认值
        return 'N';

    } catch (error) {
        console.error('获取告警等级失败:', error);
        return 'N';
    }
}

// 机场排序功能
function applySorting() {
    if (!filteredAirportData || filteredAirportData.length === 0) {
        return;
    }

    // 先按照原有逻辑排序
    switch (currentSortOption) {
        case 'alert-asc':
            filteredAirportData.sort(sortByAlertAsc);
            break;
        case 'alert-desc':
            filteredAirportData.sort(sortByAlertDesc);
            break;
        case 'region-asc':
            filteredAirportData.sort(sortByRegionAsc);
            break;
        case 'region-desc':
            filteredAirportData.sort(sortByRegionDesc);
            break;
    }

    // 应用置顶排序：置顶机场优先显示
    applyPinnedSorting();
}

function applyPinnedSorting() {
    const pinnedAirports = getPinnedAirports();

    // 分离三类：未配置机场（系统置顶）、用户置顶、普通
    const unconfigured = [];
    const pinned = [];
    const unpinned = [];

    filteredAirportData.forEach(airport => {
        if (airport.is_configured === false) {
            // 未配置机场：系统置顶，排在绝对最前
            unconfigured.push(airport);
        } else if (pinnedAirports.hasOwnProperty(airport.airport_4code)) {
            pinned.push({
                airport: airport,
                pinnedTime: pinnedAirports[airport.airport_4code]
            });
        } else {
            unpinned.push(airport);
        }
    });

    // 用户置顶机场按置顶时间排序（最旧的在前）
    pinned.sort((a, b) => a.pinnedTime - b.pinnedTime);

    // 重新组合：未配置（系统置顶）→ 用户置顶 → 普通
    filteredAirportData = unconfigured.concat(pinned.map(item => item.airport)).concat(unpinned);
}

// 获取区域排序优先级
function getRegionSortPriority(airport) {
    const area = airport.area || '';

    // 先查找国内区域
    if (currentAreaOptions.domestic) {
        const domesticRegion = currentAreaOptions.domestic.find(region => region.area === area);
        if (domesticRegion) {
            // 国内区域：直接返回sequence（1, 2, 3...）
            return domesticRegion.sequence || 999;
        }
    }

    // 再查找国际区域
    if (currentAreaOptions.international) {
        const internationalRegion = currentAreaOptions.international.find(region => region.area === area);
        if (internationalRegion) {
            // 国际区域：返回1000 + sequence，确保在所有国内区域之后
            return 1000 + (internationalRegion.sequence || 999);
        }
    }

    // 未找到的区域排在最后
    return 9999;
}

// 获取告警等级排序优先级
function getAlertSortPriority(airport, reverse = false) {
    const alertLevel = getHighestAlertLevel(airport);
    const priorities = reverse
        ? { 'N': 1, 'G': 2, 'Y': 3, 'R': 4 }  // 逆序：无告警 > 绿色 > 黄色 > 红色
        : { 'R': 1, 'Y': 2, 'G': 3, 'N': 4 }; // 正序：红色 > 黄色 > 绿色 > 无告警

    return priorities[alertLevel] || 999;
}

// 告警正序排序函数
function sortByAlertAsc(a, b) {
    // 主排序：告警等级（红色 > 黄色 > 绿色 > 无告警）
    const alertDiff = getAlertSortPriority(a, false) - getAlertSortPriority(b, false);
    if (alertDiff !== 0) return alertDiff;

    // 次排序：区域正序
    const regionDiff = getRegionSortPriority(a) - getRegionSortPriority(b);
    if (regionDiff !== 0) return regionDiff;

    // 三级排序：保持当前顺序（通过原始索引）
    return airportData.indexOf(a) - airportData.indexOf(b);
}

// 告警逆序排序函数
function sortByAlertDesc(a, b) {
    // 主排序：告警等级（无告警 > 绿色 > 黄色 > 红色）
    const alertDiff = getAlertSortPriority(a, true) - getAlertSortPriority(b, true);
    if (alertDiff !== 0) return alertDiff;

    // 次排序：区域正序
    const regionDiff = getRegionSortPriority(a) - getRegionSortPriority(b);
    if (regionDiff !== 0) return regionDiff;

    // 三级排序：保持当前顺序
    return airportData.indexOf(a) - airportData.indexOf(b);
}

// 区域正序排序函数
function sortByRegionAsc(a, b) {
    // 主排序：区域正序
    const regionDiff = getRegionSortPriority(a) - getRegionSortPriority(b);
    if (regionDiff !== 0) return regionDiff;

    // 次排序：告警等级（红色 > 黄色 > 绿色 > 无告警）
    const alertDiff = getAlertSortPriority(a, false) - getAlertSortPriority(b, false);
    if (alertDiff !== 0) return alertDiff;

    // 三级排序：保持当前顺序
    return airportData.indexOf(a) - airportData.indexOf(b);
}

// 区域逆序排序函数
function sortByRegionDesc(a, b) {
    // 主排序：区域逆序
    const regionDiff = getRegionSortPriority(b) - getRegionSortPriority(a);
    if (regionDiff !== 0) return regionDiff;

    // 次排序：告警等级（红色 > 黄色 > 绿色 > 无告警）
    const alertDiff = getAlertSortPriority(a, false) - getAlertSortPriority(b, false);
    if (alertDiff !== 0) return alertDiff;

    // 三级排序：保持当前顺序
    return airportData.indexOf(a) - airportData.indexOf(b);
}

// 初始化排序功能
function initializeSorting() {
    // 从localStorage恢复排序选项
    const savedSortOption = localStorage.getItem('mtws_airport_sort');
    if (savedSortOption) {
        currentSortOption = savedSortOption;
    }

    // 设置下拉菜单的值
    const sortSelect = document.getElementById('airport-sort-select');
    if (sortSelect) {
        sortSelect.value = currentSortOption;

        // 绑定事件监听器
        sortSelect.addEventListener('change', function () {
            currentSortOption = this.value;
            // 保存到localStorage
            localStorage.setItem('mtws_airport_sort', currentSortOption);
            // 重新应用筛选和排序
            applyFilters();
        });
    }
}

// 旧的全局竖线函数已被新的网格系统替代

// 显示机场数据
function displayAirports(airports) {
    const contentMain = document.getElementById('content-main');

    if (!airports || airports.length === 0) {
        contentMain.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📊</div>
                <div class="empty-state-message">暂无符合条件的机场数据</div>
            </div>
        `;
        // 过去 2 小时竖条挂在 body 上，筛选清空当前页时要马上收起，不能等 30 秒轮询
        if (typeof ensureFlightPastHandleFloat === 'function') {
            ensureFlightPastHandleFloat();
        }
        return;
    }

    const airportRows = airports.map(airport => createAirportRow(airport)).join('');
    contentMain.innerHTML = airportRows;

    // 应用时间范围缩放到新生成的内容
    applyTimeRangeScaling();

    // 初始化新的网格系统
    setTimeout(() => {
        updateAllAirportGrids();
        observeAirportHeightChanges();
        // 网格初始化完成后，如果 NWP 开启且有缓存数据则重新渲染覆盖层
        if (nwpEnabled && Object.keys(_nwpCache).length > 0) {
            renderAllNwpOverlays(_nwpCache);
        }
        if (typeof ensureFlightPastHandleFloat === 'function') {
            ensureFlightPastHandleFloat();
        }
    }, 100);
}

// 置顶功能相关函数
function createPinIcon(airportCode) {
    const isPinned = isAirportPinned(airportCode);

    // 只有置顶时才显示图标
    if (!isPinned) {
        return '';
    }

    return `
        <div class="pin-icon" data-airport="${airportCode}" style="position: absolute; top: 0px; left: 0px; z-index: 100; width: 15px; height: 15px; font-size: 15px; line-height: 15px;">
            🔝
        </div>
    `;
}

function isAirportPinned(airportCode) {
    const pinnedAirports = getPinnedAirports();
    return pinnedAirports.hasOwnProperty(airportCode);
}

function getPinnedAirports() {
    const stored = localStorage.getItem('mtws_pinned_airports');
    return stored ? JSON.parse(stored) : {};
}

function setPinnedAirports(pinnedAirports) {
    localStorage.setItem('mtws_pinned_airports', JSON.stringify(pinnedAirports));
}

function toggleAirportPin(airportCode) {
    const pinnedAirports = getPinnedAirports();

    if (pinnedAirports.hasOwnProperty(airportCode)) {
        // 取消置顶
        delete pinnedAirports[airportCode];
    } else {
        // 添加置顶
        pinnedAirports[airportCode] = Date.now();
    }

    setPinnedAirports(pinnedAirports);

    // 重新渲染机场列表
    applyFilters();
}

// 创建右键菜单
function createContextMenu(airportCode, x, y) {
    // 移除已存在的菜单
    const existingMenu = document.getElementById('airport-context-menu');
    if (existingMenu) {
        existingMenu.remove();
    }

    // 判断是否为未配置机场（系统置顶，不可手动操作置顶）
    const airportObj = airportData ? airportData.find(a => a.airport_4code === airportCode) : null;
    const isUnconfigured = airportObj && airportObj.is_configured === false;
    const isPinned = isAirportPinned(airportCode);

    const menu = document.createElement('div');
    menu.id = 'airport-context-menu';
    menu.style.cssText = `
        position: fixed;
        top: ${y}px;
        left: ${x}px;
        background: white;
        border: 1px solid #ccc;
        border-radius: 4px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        z-index: 1000;
        min-width: 100px;
        font-size: 14px;
    `;

    const menuItemStyle = `
        padding: 8px 14px;
        cursor: pointer;
        transition: background-color 0.2s;
        white-space: nowrap;
    `;

    function makeItem(text, onClick) {
        const item = document.createElement('div');
        item.textContent = text;
        item.style.cssText = menuItemStyle;
        item.addEventListener('mouseenter', () => { item.style.backgroundColor = '#f0f0f0'; });
        item.addEventListener('mouseleave', () => { item.style.backgroundColor = 'transparent'; });
        item.addEventListener('click', () => { onClick(); menu.remove(); });
        return item;
    }

    // 置顶/取消置顶：未配置机场不显示此选项（系统置顶不可手动取消）
    if (!isUnconfigured) {
        const pinText = isPinned ? '取消置顶' : '置顶';
        menu.appendChild(makeItem(pinText, () => toggleAirportPin(airportCode)));
    }

    // 机场信息配置：等同于在设置里输入该四字代码并查询，再进入配置页
    menu.appendChild(makeItem('机场信息配置', () => {
        if (!window.SettingsModal || !window.SettingsModal.openAndEdit) return;
        window.SettingsModal.openAndEdit(airportCode);
    }));
    menu.appendChild(makeItem('预报入库告警', () => {
        if (!window.SettingsModal || !window.SettingsModal.openAndEditTaf) return;
        window.SettingsModal.openAndEditTaf(airportCode);
    }));

    document.body.appendChild(menu);

    // 点击其他地方关闭菜单
    const closeMenu = (e) => {
        if (!menu.contains(e.target)) {
            menu.remove();
            document.removeEventListener('click', closeMenu);
        }
    };

    setTimeout(() => {
        document.addEventListener('click', closeMenu);
    }, 0);
}

// 处理机场信息区域的右键点击
function handleAirportRightClick(event, airportCode) {
    event.preventDefault();
    createContextMenu(airportCode, event.clientX, event.clientY);
}

// 创建机场行
function createAirportRow(airport) {
    const flightData = airport.flight_data || {};
    const latestMetar = airport.metar_data && airport.metar_data.length > 0 ? airport.metar_data[0] : null;
    const tafData = airport.taf_data || [];

    // 获取机场最高告警等级
    const airportAlertLevel = getHighestAlertLevel(airport);
    const alertColor = getAlertColor(airportAlertLevel);
    const airportCodeContainerStyle = airportAlertLevel !== 'N' ?
        `background-color: ${alertColor};` : '';

    const noTafData = (!tafData || tafData.length === 0) || (tafData[0].data_status === 'C');
    const tafAlertClass = (tafData && tafData.length > 0 && tafData[0].import_alert === 'Y') ? ' taf-import-alerted' : '';
    const marksMode = typeof isFlightMarksMode === 'function' && isFlightMarksMode();
    const timelineInner = `
                ${noTafData ? '<div class="no-taf-data">没有有效的TAF数据</div>' : ''}
                <div class="forecast-row main-forecast${tafAlertClass}">
                    ${createTafForecastRow(tafData, 'main')}
                </div>
                <div class="forecast-row change-forecast${tafAlertClass}">
                    ${createTafForecastRow(tafData, 'change')}
                </div>
                <div class="forecast-row flight-row">
                    ${createFlightTimeline(flightData, tafData, airport.metar_data, airport)}
                </div>`;

    return `
        <div class="airport-row">
            <div class="airport-info" style="position: relative;" oncontextmenu="handleAirportRightClick(event, '${airport.airport_4code}')">
                ${createPinIcon(airport.airport_4code)}
                <div class="airport-code-container" style="${airportCodeContainerStyle}">
                    <div class="airport-code">${airport.airport_4code}</div>
                </div>
                <div class="airport-name">${airport.airport_name || '机场名称未配置'}</div>
                ${(airport.config_gaps && airport.config_gaps.length) ? `<div class="airport-config-gap" style="color:#c0392b;font-size:12px;line-height:1.35;margin-top:2px;">${airport.config_gaps.join('；')}</div>` : ''}
            </div>
            ${buildWeatherInfoDiv(airport.airport_4code, latestMetar)}
            <div class="forecast-timeline">
                ${marksMode ? `<div class="marks-slide-layer">${timelineInner}</div>` : timelineInner}
            </div>
        </div>
    `;
}

// 为机场详情弹窗创建专用的机场行（不包含airport-info）
function createAirportRowForDetail(airport, opts) {
    const code = airport && airport.airport_4code
        ? String(airport.airport_4code).toUpperCase()
        : '';
    let scope = (opts && opts.marksScope) || window._marksRenderScope || 'detail';
    if (scope === 'home' || !scope) scope = 'detail';
    if (scope !== 'detail' && !(typeof scope === 'string' && scope.indexOf('search:') === 0)) {
        scope = code ? ('search:' + code) : 'detail';
    }
    if (typeof withMarksRenderScope === 'function') {
        return withMarksRenderScope(scope, () => createAirportRowForDetailUnforced(airport));
    }
    return createAirportRowForDetailUnforced(airport);
}

function createAirportRowForDetailUnforced(airport) {
    const flightData = airport.flight_data || {};
    const latestMetar = airport.metar_data && airport.metar_data.length > 0 ? airport.metar_data[0] : null;
    const tafData = airport.taf_data || [];

    const noTafData = (!tafData || tafData.length === 0) || (tafData[0].data_status === 'C');
    const tafAlertClass = (tafData && tafData.length > 0 && tafData[0].import_alert === 'Y') ? ' taf-import-alerted' : '';

    const isPlain = window._viewMode === 'plain';
    const weatherBox = isPlain
        ? ''
        : buildWeatherInfoDiv(airport.airport_4code, latestMetar);
    const rowLabels = isPlain
        ? `<div class="plain-row-labels">
            <div class="plain-row-label">长效预报</div>
            <div class="plain-row-label">短时变化</div>
            <div class="plain-row-label">航班信息</div>
          </div>`
        : '';
    const rowClass = isPlain
        ? 'airport-row airport-row-detail airport-row-plain'
        : 'airport-row airport-row-detail';
    const marksMode = typeof isFlightMarksMode === 'function' && isFlightMarksMode();
    const timelineInner = `
                ${noTafData ? '<div class="no-taf-data">没有有效的TAF数据</div>' : ''}
                <div class="forecast-row main-forecast${tafAlertClass}">
                    ${createTafForecastRow(tafData, 'main')}
                </div>
                <div class="forecast-row change-forecast${tafAlertClass}">
                    ${createTafForecastRow(tafData, 'change')}
                </div>
                <div class="forecast-row flight-row">
                    ${createFlightTimeline(flightData, tafData, airport.metar_data, airport)}
                </div>`;

    return `
        <div class="${rowClass}">
            ${weatherBox}
            ${rowLabels}
            <div class="forecast-timeline">
                ${marksMode ? `<div class="marks-slide-layer">${timelineInner}</div>` : timelineInner}
            </div>
        </div>
    `;
}



// createTafForecastRow 及以下TAF甘特图相关函数 → 已迁移至 main_taf.js


// getWeatherInfoStyle / createWeatherInfo / formatMetarTime /
// buildWindTempContent / buildVisibilityRvrContent → 已迁移至 main_metar.js




// createFlightTimeline → 已迁移至 main_flight.js

// ==============================================================================
// 机场四字代码搜索
// ==============================================================================

/**
 * 从用户输入中解析 ICAO 四字代码列表。
 * 规则：
 *  - 整体只允许字母和分隔符（空格 / , / ，），首位可以是字母或分隔符
 *  - 以分隔符拆分后，取长度恰好为 4 的字母串作为有效代码
 *  - 返回去重后的大写代码数组；若输入含非法字符则返回 null
 */
function parseIcaoCodes(input) {
    if (!input || !input.trim()) return [];

    // 只允许字母与分隔符（空格 / , / ，），首位无限制
    if (/[^a-zA-Z\s,，]/.test(input)) return null;

    // 按分隔符拆分，取恰好 4 个字母的片段
    const tokens = input.split(/[\s,，]+/).filter(t => t.length > 0);
    const codes = [];
    const seen = new Set();
    for (const token of tokens) {
        if (/^[a-zA-Z]{4}$/.test(token)) {
            const upper = token.toUpperCase();
            if (!seen.has(upper)) {
                seen.add(upper);
                codes.push(upper);
            }
        }
        // 非 4 字母的片段跳过（不视为错误）
    }
    return codes;
}

/**
 * 搜索入口（含解析器状态检查）：逻辑与刷新按钮保持一致。
 * 若后端解析器正在执行，则显示等待提示并拦截本次搜索；
 * 接口异常时乐观放行。
 */
function handleSearchClick(searchValue) {
    if (!searchValue) return;
    if (typeof hasAccess === 'function' && !hasAccess('search', 'display')) return;

    // 无激活权限时仍允许搜索读数，但不因解析占用而强拦（后端外呼可能仍受限）
    const needActivateGate = typeof hasAccess !== 'function' || hasAccess('search', 'activate');
    if (!needActivateGate) {
        performSearch(searchValue);
        return;
    }
    checkRunningParsers((err, data) => {
        if (err) {
            performSearch(searchValue);
            return;
        }
        const running = data.running || [];
        const queued  = data.queued  || [];
        if (running.length > 0 || queued.length > 0) {
            showParserRunningMessage(buildParserStatusMessage(running, queued));
            startParserStatusPolling();
        } else {
            performSearch(searchValue);
        }
    });
}

// 执行搜索入口
function performSearch(searchValue) {
    const codes = parseIcaoCodes(searchValue);

    if (codes === null) {
        alert('输入格式有误：只允许字母和分隔符（空格、逗号）');
        return;
    }
    if (codes.length === 0) {
        alert('未识别到有效的四字代码（每个代码须为连续4个英文字母）');
        return;
    }

    if (codes.length === 1) {
        // 单个代码：优先从已加载数据中直接展示
        const existing = (typeof airportData !== 'undefined') &&
            airportData.find(a => a.airport_4code === codes[0]);
        if (existing) {
            showAirportDetailModal(existing, 'search');
            return;
        }
        // 不在已加载数据中，需要从后端获取
        fetchAndShowAirportSearch(codes);
    } else {
        // 多个代码：始终调接口
        fetchAndShowAirportSearch(codes);
    }
}

// 调后端搜索接口，然后根据结果数量选择展示方式
// 注意：搜索不应影响主页当前已展示的内容，因此不调用 showLoading()/hideLoading()
// （它们会清空 #content-main），仅在搜索按钮上给出轻量的加载中提示。
function fetchAndShowAirportSearch(codes) {
    const searchBtn = document.getElementById('search-btn');
    const originalBtnText = searchBtn ? searchBtn.textContent : null;
    if (searchBtn) {
        searchBtn.disabled = true;
        searchBtn.textContent = '搜索中...';
    }

    const headers = { 'Content-Type': 'application/json' };
    if (typeof currentToken !== 'undefined' && currentToken) {
        headers['Authorization'] = `Bearer ${currentToken}`;
    }

    const url = `/${currentTimeMode}/api/airport-search/?codes=${codes.join(',')}`;

    fetch(url, { headers })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                alert('搜索失败：' + (data.error || '未知错误'));
                return;
            }
            const airports = data.data || [];
            if (airports.length === 0) {
                alert('未找到机场数据');
                return;
            }
            if (airports.length === 1) {
                // 单个机场：走完整详情页流程
                if (typeof showAirportSearchSingle === 'function') {
                    showAirportSearchSingle(airports[0]);
                }
            } else {
                // 多个机场：走简化展示流程
                if (typeof showAirportSearchMulti === 'function') {
                    showAirportSearchMulti(airports);
                }
            }
        })
        .catch(err => {
            console.error('机场搜索请求失败:', err);
            alert('搜索请求失败，请重试');
        })
        .finally(() => {
            if (searchBtn) {
                searchBtn.disabled = false;
                searchBtn.textContent = originalBtnText;
            }
        });
}

// 刷新数据（刷新按钮入口）
function refreshData() {
    handleRefreshButtonClick();
}

// loadCarrierData → 已迁移至 main_flight.js

// 显示弹窗
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'block';
        // 不设置 body.overflow：hidden/auto 都会让 body 成为滚动容器，sticky 吸顶失效。

        // 层级规则：实况弹窗（.metar-popup-overlay，z-index 30000）默认应始终显示在
        // 机场详情/搜索结果弹窗之上；从实况弹窗内点击"查看详情"时详情临时高于实况弹窗，
        // 一旦有新的未处理实况弹窗进入，详情回落到实况弹窗之下（见 restoreDetailBelowMetarPopup）。
        if (modalId === 'airport-detail-modal') {
            if (window._openDetailAboveMetarPopup) {
                modal.style.zIndex = '30010';
                window._openDetailAboveMetarPopup = false;
            } else {
                modal.style.zIndex = '';
            }
        }
    }
}

// 隐藏弹窗
function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        // 不可设为 auto：body 会变成垂直滚动容器，导致 sticky 吸顶失效。
        // 仅在没有其它弹窗仍打开时清除内联样式，恢复 CSS 默认 visible。
        const stillOpen = Array.from(document.querySelectorAll('.modal'))
            .some(m => m.style.display === 'block');
        if (!stillOpen) {
            document.body.style.overflow = '';
        }

        if (modalId === 'airport-detail-modal') {
            modal.style.zIndex = '';
            if (typeof removeMarksPastHandle === 'function') removeMarksPastHandle('detail');
        }
        if (modalId === 'airport-search-modal') {
            document.querySelectorAll('.flight-past-handle-float.scope-search').forEach((el) => el.remove());
        }
    }
}

function restoreDetailBelowMetarPopup() {
    const modal = document.getElementById('airport-detail-modal');
    if (modal) {
        modal.style.zIndex = '';
    }
}

// 格式化时间
function formatTime(date, format = 'HH:mm') {
    if (!date) return '';

    const d = new Date(date);
    const hours = d.getHours().toString().padStart(2, '0');
    const minutes = d.getMinutes().toString().padStart(2, '0');

    if (format === 'HH:mm') {
        return `${hours}:${minutes}`;
    } else if (format === 'HH') {
        return hours;
    }

    return d.toLocaleString('zh-CN');
}

// 获取告警等级名称
function getAlertLevelName(level) {
    const levelNames = {
        'R': '红色',
        'Y': '黄色',
        'G': '绿色',
        'N': '无告警'
    };
    return levelNames[level] || '未知';
}

// 获取告警颜色（0.8透明度）
function getAlertColorSpec(level) {
    const fallback = {
        R: { hex: '#e74c3c', rgb: '231, 76, 60' },
        Y: { hex: '#f39c12', rgb: '243, 156, 18' },
        G: { hex: '#27ae60', rgb: '39, 174, 96' },
        N: { hex: '#95a5a6', rgb: '149, 165, 166' }
    };
    const all = window.MTWS_ALERT_COLORS;
    const spec = (all && all[level]) || fallback[level] || fallback.N;
    if (!spec || !spec.rgb || !spec.hex) {
        return fallback[level] || fallback.N;
    }
    return spec;
}

function getAlertColor(level) {
    return `rgba(${getAlertColorSpec(level).rgb}, 0.8)`;
}

function getAlertColorHex(level) {
    return getAlertColorSpec(level).hex;
}

// 获取当前选中的告警裕度值
function getSelectedAlertMargin() {
    return filters.margin !== undefined ? filters.margin : 2;
}





// calculateMetarAlert → 已迁移至 main_metar.js




// 智能分时自动刷新功能
let timerConfigs = {}; // 存储从数据库获取的定时器配置
let pendingRequests = new Set(); // 跟踪正在进行的请求
let lastUpdateTriggers = {}; // 记录每种数据类型的最后触发时间

// 获取请求头（复用认证逻辑）
function getRequestHeaders() {
    const headers = {};

    // 在current模式下添加认证头
    if (currentTimeMode === 'current' && currentToken) {
        headers['Authorization'] = `Bearer ${currentToken}`;
        if (currentUserCode) {
            headers['X-User-Code'] = currentUserCode;
        }
    }

    // 在test模式下添加测试用户代码
    if (currentTimeMode === 'test') {
        headers['X-User-Code'] = 'test';
    }
    if (window.__settingsScope === 'default') {
        headers['X-Settings-Scope'] = 'default';
    }

    return headers;
}

// 处理fetch响应（统一错误处理）
function handleFetchResponse(response) {
    if (response.status === 401) {
        throw new Error('TOKEN_INVALID');
    }
    return response.json();
}

// 处理fetch错误（统一错误处理）
function handleFetchError(error, dataType, retryCallback) {
    console.error(`${dataType}数据更新失败:`, error);
    if (error.message === 'TOKEN_INVALID') {
        handleSessionExpired('fetch 401');
    } else if (retryCallback) {
        retryCallback();
    } else {
        // 如果没有重试回调，显示服务器错误提示
        showError('数据加载失败，请刷新页面重试或检查服务器运行情况');
    }
}

// 加载定时器配置
function loadTimerConfigs() {
    fetch(`/${currentTimeMode}/api/timer-configs/`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                timerConfigs = data.data;
                console.log('定时器配置加载成功:', timerConfigs);
            } else {
                console.error('定时器配置加载失败:', data.error);
                // 使用默认配置
                timerConfigs = {
                    metar: { init_time: 5.0, interval: 5.0 },
                    taf: { init_time: 5.0, interval: 15.0 },
                    flight: { init_time: 5.0, interval: 15.0 },
                    aircraft_parking: { init_time: 28.0, interval: 30.0 }
                };
            }
        })
        .catch(error => {
            console.error('定时器配置加载失败:', error);
            // 使用默认配置
            timerConfigs = {
                metar: { init_time: 5.0, interval: 5.0 },
                taf: { init_time: 5.0, interval: 15.0 },
                flight: { init_time: 5.0, interval: 15.0 }
            };
        });
}

// 参数化数据更新函数
function loadParameterizedData(updateTypes) {
    if (pendingRequests.has('parameterized')) {
        console.log('跳过重复的参数化请求');
        return;
    }

    pendingRequests.add('parameterized');

    fetch(`/${currentTimeMode}/api/trigger-parsing/`, {
        method: 'POST',
        headers: getRequestHeaders(),
        body: JSON.stringify({
            updateTypes: updateTypes,
            nwpEnabled: nwpEnabled
        })
    })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success) {
                console.log('参数化更新成功:', updateTypes);

                // 获取解析结果
                const parsers = data.data.parsers || {};

                updateTypes.forEach(dataType => {
                    const parseResult = parsers[dataType];
                    if (parseResult) {
                        console.log(`${dataType}解析器结果:`, parseResult);
                    } else {
                        console.warn(`⚠️ 参数化更新中未找到${dataType}的解析结果`);
                    }
                });

                // 获取最新数据
                return fetch(`/${currentTimeMode}/api/airports/overview/`, {
                    headers: getRequestHeaders()
                });
            } else {
                console.error('参数化更新失败:', data.error);
                // 更新失败时设置所有相关数据类型的状态
                updateTypes.forEach(dataType => {
                    updateDataTime(dataType, false);
                    updateSingleParsingStatus(dataType, false);
                });
                throw new Error(data.error);
            }
        })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success) {
                console.log('✅ 参数化数据获取成功');
                console.log(`📋 获取到 ${data.data.airports.length} 个机场的数据`);
                console.log(`🏛️ 获取到 ${data.data.carriers.length} 个承运人`);

                // 更新前端数据
                if (updateTypes.includes('flight')) {
                    // 如果包含航班数据更新，完全替换数据
                    airportData = data.data.airports;
                } else {
                    // 如果只是部分数据更新，选择性更新对应字段
                    if (data.data.airports && data.data.airports.length > 0) {
                        data.data.airports.forEach(newAirport => {
                            const existingIndex = airportData.findIndex(a => a.airport_4code === newAirport.airport_4code);
                            if (existingIndex !== -1) {
                                // 更新告警相关数据
                                airportData[existingIndex].computed_alerts = newAirport.computed_alerts;

                                // 根据更新类型选择性更新数据
                                updateTypes.forEach(dataType => {
                                    if (dataType === 'metar') {
                                        airportData[existingIndex].metar_data = newAirport.metar_data;
                                    } else if (dataType === 'taf') {
                                        airportData[existingIndex].taf_data = newAirport.taf_data;
                                    }
                                });
                            }
                        });
                    }
                }
                currentCarriers = data.data.carriers;


                // 更新航班状态警告
                updateFlightStatusWarning(data.data.flight_status);

                // 更新区域选项
                if (data.data.area_options) {
                    currentAreaOptions = data.data.area_options;

                    // 检查是否需要重置区域筛选（强制刷新或清除缓存时）
                    const needResetRegions = sessionStorage.getItem('mtws_reset_regions');
                    if (needResetRegions) {
                        // 初始化时默认选中所有区域（兼容原有逻辑）
                        filters.domestic = currentAreaOptions.domestic.map(region => region.area);
                        filters.international = currentAreaOptions.international.map(region => region.area);
                    }

                    console.log(`🌍 获取到区域选项: 国内${currentAreaOptions.domestic.length}个, 国际${currentAreaOptions.international.length}个`);

                    // 动态生成区域按钮
                    generateRegionButtons();

                    // 更新区域按钮状态
                    updateRegionButtonState('domestic');
                    updateRegionButtonState('international');
                }

                updateCarrierDisplay();

                // 从 metar 数据同步入库告警状态（alertedAirports / importAlertUnhandledCount）
                if (typeof syncAlertStateFromMetarData === 'function') {
                    syncAlertStateFromMetarData(airportData);
                }

                if (typeof syncAlertStateFromTafData === 'function') {
                    syncAlertStateFromTafData(airportData);
                }

                applyFilters();
                updateStatusFromPollResult(data.data.parsing_status || {}, true);
                if (maybeHandleAuthExpired(data)) {
                    return;
                }

                // 如果 NWP 温度辅助已开启，获取并渲染最新 NWP 数据
                if (nwpEnabled) {
                    fetchNwpDataAndRender();
                }

                console.log('🎉 参数化页面数据更新完成');

                updateAllAirportGrids();
            } else {
                console.error('❌ 参数化数据获取失败:', data.error);
                // 数据获取失败时重置相关数据类型的时间
                updateTypes.forEach(dataType => {
                    dataUpdateTimes[dataType] = '--:--:--';
                    updateStatusTimeDisplay(dataType, '--:--:--');
                });
                showError('加载数据失败：' + data.error);
            }
        })
        .catch(error => {
            console.error('❌ 参数化数据加载过程失败:', error);
            if (error.message === 'TOKEN_INVALID') {
                handleSessionExpired('parameterized 401');
            } else {
                handleApiError(error);
                // 网络错误时也更新状态为失败
                updateTypes.forEach(dataType => {
                    updateSingleParsingStatus(dataType, false);
                });
            }
        })
        .finally(() => {
            pendingRequests.delete('parameterized');
        });
}

// 部分数据更新函数（保留用于手动调用）
function loadPartialData(dataType) {
    if (pendingRequests.has(dataType)) {
        console.log(`跳过重复请求: ${dataType}`);
        return;
    }

    pendingRequests.add(dataType);

    // 使用新的参数化API
    fetch(`/${currentTimeMode}/api/trigger-parsing/`, {
        method: 'POST',
        headers: getRequestHeaders(),
        body: JSON.stringify({
            updateTypes: [dataType]
        })
    })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success) {
                console.log(`${dataType}数据更新成功`);
                console.log('完整的API响应数据:', data);

                // 获取解析结果
                const parsers = data.data.parsers || {};
                console.log('解析器数据:', parsers);

                const parseResult = parsers[dataType];
                console.log(`${dataType}的解析结果:`, parseResult);

                if (parseResult) {
                    console.log(`${dataType}解析器结果:`, parseResult);
                } else {
                    console.warn(`⚠️ 未找到${dataType}的解析结果`);
                }

                // 获取最新数据
                return fetch(`/${currentTimeMode}/api/airports/overview/`, {
                    headers: getRequestHeaders()
                });
            } else {
                console.error(`${dataType}数据更新失败:`, data.error);
                updateDataTime(dataType, false);
                updateSingleParsingStatus(dataType, false);
                throw new Error(data.error);
            }
        })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success) {
                console.log(`${dataType}数据获取成功`);

                // 更新前端数据
                airportData = data.data.airports;
                currentCarriers = data.data.carriers;

                // 从 metar 数据同步入库告警状态
                if (typeof syncAlertStateFromMetarData === 'function') {
                    syncAlertStateFromMetarData(airportData);
                }

                if (typeof syncAlertStateFromTafData === 'function') {
                    syncAlertStateFromTafData(airportData);
                }

                // 更新航班状态警告
                updateFlightStatusWarning(data.data.flight_status);

                applyFilters();
                updateStatusFromPollResult(data.data.parsing_status || {}, true);
                if (maybeHandleAuthExpired(data)) {
                    return;
                }

                updateAllAirportGrids();
            } else {
                console.error(`${dataType}数据获取失败:`, data.error);
                // 重试机制
                setTimeout(() => {
                    loadPartialDataWithRetry(dataType, 1);
                }, 5000);
            }
        })
        .catch(error => {
            if (error.message === 'TOKEN_INVALID') {
                handleSessionExpired(`${dataType} 401`);
            } else {
                handleApiError(error);
                // 网络错误时也更新状态为失败
                updateSingleParsingStatus(dataType, false);
            }
        })
        .finally(() => {
            pendingRequests.delete(dataType);
        });
}

// 带重试的部分数据更新
function loadPartialDataWithRetry(dataType, retryCount) {
    const maxRetries = 3;

    if (retryCount > maxRetries) {
        console.error(`${dataType}数据更新重试失败，已达到最大重试次数`);
        return;
    }

    if (pendingRequests.has(dataType)) {
        return;
    }

    pendingRequests.add(dataType);

    // 使用新的参数化API
    fetch(`/${currentTimeMode}/api/trigger-parsing/`, {
        method: 'POST',
        headers: getRequestHeaders(),
        body: JSON.stringify({
            updateTypes: [dataType]
        })
    })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success) {
                console.log(`${dataType}数据重试更新成功 (第${retryCount}次重试)`);
                console.log('重试完整的API响应数据:', data);

                // 获取解析结果
                const parsers = data.data.parsers || {};
                console.log('重试解析器数据:', parsers);

                const parseResult = parsers[dataType];
                console.log(`${dataType}的重试解析结果:`, parseResult);

                if (parseResult) {
                    console.log(`${dataType}解析器重试结果:`, parseResult);
                } else {
                    console.warn(`⚠️ 重试时未找到${dataType}的解析结果`);
                }

                // 获取最新数据
                return fetch(`/${currentTimeMode}/api/airports/overview/`, {
                    headers: getRequestHeaders()
                });
            } else {
                console.error(`${dataType}数据重试更新失败:`, data.error);
                updateDataTime(dataType, false);
                updateSingleParsingStatus(dataType, false);
                if (retryCount < maxRetries) {
                    setTimeout(() => {
                        loadPartialDataWithRetry(dataType, retryCount + 1);
                    }, 5000 * retryCount);
                }
                throw new Error(data.error);
            }
        })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success) {
                console.log(`${dataType}重试数据获取成功`);

                // 更新前端数据
                airportData = data.data.airports;
                currentCarriers = data.data.carriers;

                // 从 metar 数据同步入库告警状态
                if (typeof syncAlertStateFromMetarData === 'function') {
                    syncAlertStateFromMetarData(airportData);
                }

                if (typeof syncAlertStateFromTafData === 'function') {
                    syncAlertStateFromTafData(airportData);
                }

                // 更新航班状态警告
                updateFlightStatusWarning(data.data.flight_status);

                applyFilters();
                updateStatusFromPollResult(data.data.parsing_status || {}, true);
                if (maybeHandleAuthExpired(data)) {
                    return;
                }

                updateAllAirportGrids();
            } else {
                console.error(`${dataType}重试数据获取失败:`, data.error);
            }
        })
        .catch(error => {
            if (error.message === 'TOKEN_INVALID') {
                handleSessionExpired(`${dataType} retry 401`);
            } else {
                handleApiError(error);
                // 网络错误时也更新状态为失败
                updateSingleParsingStatus(dataType, false);
            }
        })
        .finally(() => {
            pendingRequests.delete(dataType);
        });
}

// 更新前端数据
function updateFrontendData(data, dataType) {
    // 注意：时间更新已在调用此函数前处理，这里不再重复更新

    // 根据数据类型更新对应的前端显示
    if (dataType === 'flight') {
        // 航班数据更新：同时更新基础信息和告警颜色
        airportData = data.airports || [];
        filteredAirportData = airportData;

        // 更新航班状态警告
        updateFlightStatusWarning(data.flight_status);

        applyFilters();
        updateAllAirportGrids();
    } else {
        // 实况或预报数据更新：只更新告警颜色，保持基础信息不变
        if (data.airports && data.airports.length > 0) {
            data.airports.forEach(newAirport => {
                const existingIndex = airportData.findIndex(a => a.airport_4code === newAirport.airport_4code);
                if (existingIndex !== -1) {
                    // 更新告警相关数据
                    airportData[existingIndex].computed_alerts = newAirport.computed_alerts;

                    // 根据数据类型更新对应的数据
                    if (dataType === 'metar') {
                        airportData[existingIndex].metar_data = newAirport.metar_data;
                    } else if (dataType === 'taf') {
                        airportData[existingIndex].taf_data = newAirport.taf_data;
                    }
                }
            });

            // 重新应用筛选
            applyFilters();
            updateAllAirportGrids();
        }
    }
}

// 自动更新处理
function autoUpdate(needUpdate) {
    const updateQueue = [];

    // 按优先级排序：停场 > 航班 > 实况 > 预报
    if (needUpdate.aircraft_parking) updateQueue.push('aircraft_parking');
    if (needUpdate.flight) updateQueue.push('flight');
    if (needUpdate.metar) updateQueue.push('metar');
    if (needUpdate.taf) updateQueue.push('taf');

    if (updateQueue.length === 0) return;

    // 检查是否在冷却时间内
    if (!canRefresh()) {
        console.log(`智能更新跳过 - 30秒冷却时间内, 需要更新:`, updateQueue);
        return;
    }

    // 统一使用参数化更新，不再区分整体和部分更新
    console.log('自动刷新参数化更新:', updateQueue);
    updateRefreshTime();

    if (updateQueue.length > 1) {
        // 多种数据更新时需要重新生成时间轴
        generateTimeline();
        applyTimeRangeScaling();
    }

    // 调用统一的参数化更新
    loadParameterizedData(updateQueue);
}

// 启动自动刷新
// 解析任务由后端 APScheduler 独立定时执行，前端仅每 30 秒轮询一次
// GET /airports/overview/ 获取最新数据并刷新展示，与客户端数量无关。
// 手动刷新（刷新按钮 / 页面加载）仍通过 POST trigger-parsing 驱动后端立即解析。
function startAutoRefresh() {
    // 加载定时器配置（仅用于 UI 显示刷新间隔信息）
    loadTimerConfigs();

    // 连续轮询失败计数（网络错误 / 服务器关闭）
    window.pollFailureCount = 0;
    // 触发断连横幅的连续失败阈值
    const OFFLINE_THRESHOLD = 2;

    // 独立的时间轴刷新计时器：每 60 秒重绘一次时间轴标签及午夜刻度加粗竖线，
    // 确保即使数据不变，当前整点刻度也能随真实时间滚动更新。
    window.timelineRefreshTimer = setInterval(function () {
        generateTimeline();
        updateAllAirportGrids();
    }, 60 * 1000);

    // 每 30 秒轮询一次后端最新数据
    window.autoRefreshTimer = setInterval(function () {
        if (window.tokenInvalidDetected) {
            console.log('Token失效，停止自动轮询');
            clearInterval(window.autoRefreshTimer);
            window.autoRefreshTimer = null;
            return;
        }

        // 避免与手动刷新（parameterized）请求重叠
        if (pendingRequests.has('parameterized') || pendingRequests.has('overview_poll')) {
            return;
        }
        pendingRequests.add('overview_poll');

        fetch(`/${currentTimeMode}/api/airports/overview/`, {
            headers: getRequestHeaders()
        })
        .then(response => {
            if (response.status === 401) {
                throw new Error('TOKEN_INVALID');
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data) {
                updateStatusFromPollResult(data.data.parsing_status || {}, true);
                if (data.data.seat_identity) {
                    window.__seatIdentity = data.data.seat_identity;
                    paintSeatUserInfo();
                }
                if (maybeHandleAuthExpired(data)) {
                    return;
                }
            }
            if (data.success && data.data && data.data.airports) {
                // 轮询成功：重置断连计数，隐藏横幅
                if (window.pollFailureCount > 0) {
                    console.log('服务器连接已恢复');
                    hideServerOfflineBanner();
                    window.pollFailureCount = 0;
                    // 静默重注入 token，使调度器在服务重启后立即恢复定时解析
                    silentTokenReinjection();
                }
                airportData = data.data.airports;
                if (!window.__carrierMenuOpen && Array.isArray(data.data.carriers)) {
                    currentCarriers = data.data.carriers;
                    window.carriers = currentCarriers;
                    if (typeof updateCarrierDisplay === 'function') updateCarrierDisplay();
                }
                // 从 metar 数据同步入库告警状态
                if (typeof syncAlertStateFromMetarData === 'function') {
                    syncAlertStateFromMetarData(airportData);
                }

                if (typeof syncAlertStateFromTafData === 'function') {
                    syncAlertStateFromTafData(airportData);
                }
                // 先更新时间轴标签（当前整点刻度随真实时间滚动）
                generateTimeline();
                applyFilters();
                updateAllAirportGrids();
            }
        })
        .catch(error => {
            if (error.message === 'TOKEN_INVALID') {
                handleSessionExpired('overview poll 401');
            } else {
                // 网络错误 / 服务器关闭：累计失败次数
                window.pollFailureCount = (window.pollFailureCount || 0) + 1;
                console.warn(`自动轮询数据失败（第 ${window.pollFailureCount} 次）:`, error.message || error);
                if (window.pollFailureCount >= OFFLINE_THRESHOLD) {
                    showServerOfflineBanner(window.pollFailureCount);
                }
                // 轮询失败时不修改状态指示器，保留上次结果
            }
        })
        .finally(() => {
            pendingRequests.delete('overview_poll');
        });

    }, 30 * 1000); // 每30秒轮询一次
}

// 更新解析状态显示
function updateParsingStatus(status) {
    const indicators = {
        flight: document.getElementById('flight-indicator'),
        metar: document.getElementById('metar-indicator'),
        taf: document.getElementById('taf-indicator')
    };

    Object.values(indicators).forEach(indicator => {
        if (indicator) {
            // 清除之前的状态类
            indicator.classList.remove('status-success', 'status-error', 'status-loading', 'status-pending');

            switch (status) {
                case 'loading':
                    indicator.textContent = '解析中...';
                    indicator.classList.add('status-loading');
                    break;
                case 'error':
                    indicator.textContent = '解析失败';
                    indicator.classList.add('status-error');
                    break;
                case 'pending':
                    indicator.textContent = '等待中...';
                    indicator.classList.add('status-pending');
                    break;
                default:
                    indicator.textContent = '等待中...';
                    indicator.classList.add('status-pending');
            }

            // 在等待中、解析中、解析失败状态时显示--:--:--
            if (status !== 'success') {
                const dataType = indicator.id.replace('-indicator', '');
                updateStatusTimeDisplay(dataType, '--:--:--');
            }
        }
    });
}

// 更新单个数据类型的解析状态
function updateSingleParsingStatus(dataType, success) {
    const statusMap = {
        flight: { element: document.getElementById('flight-indicator'), name: '航班' },
        metar: { element: document.getElementById('metar-indicator'), name: '实况' },
        taf: { element: document.getElementById('taf-indicator'), name: '预报' }
    };

    const statusInfo = statusMap[dataType];
    if (!statusInfo || !statusInfo.element) {
        console.log(`⚠️ ${dataType} 状态更新失败: 找不到对应的状态元素`);
        return;
    }

    const indicator = statusInfo.element;

    console.log(`🔧 更新 ${dataType} 状态:`, {
        success: success,
        element: 'Found'
    });

    // 清除之前的状态类
    indicator.classList.remove('status-success', 'status-error', 'status-loading', 'status-pending');

    if (success) {
        indicator.textContent = '解析成功';
        indicator.classList.add('status-success');
        console.log(`✅ ${dataType} 状态已更新为: 解析成功`);
        // 解析成功时显示对应的数据时间
        const currentTime = dataUpdateTimes[dataType] || '--:--:--';
        updateStatusTimeDisplay(dataType, currentTime);
    } else {
        indicator.textContent = '解析失败';
        indicator.classList.add('status-error');
        console.log(`❌ ${dataType} 状态已更新为: 解析失败`);
        // 解析失败时显示--:--:--
        updateStatusTimeDisplay(dataType, '--:--:--');
    }
}

/**
 * 根据自动轮询结果更新解析状态指示器（仅由 startAutoRefresh 轮询调用）
 *
 * 规则：
 *   - 后端解析成功 AND 本次轮询成功 → 绿色"解析成功"，时间显示后端最近解析时间
 *   - 后端解析失败（无论轮询结果）    → 红色"解析失败"，时间显示 --:--:--
 *   - 后端尚未运行（success===null）  → 灰色"等待解析"，时间显示 --:--:--
 *   - 本次轮询网络失败，不更新指示器（保留上次状态）
 *
 * @param {Object} parsingStatus  来自 overview 响应的 data.parsing_status
 * @param {boolean} pollSuccess   本次 GET overview 是否成功
 */
function updateStatusFromPollResult(parsingStatus, pollSuccess) {
    if (!pollSuccess) return; // 轮询失败不更新，保留上次显示

    const dataTypes = ['flight', 'metar', 'taf'];
    dataTypes.forEach(dataType => {
        const indicatorEl = document.getElementById(`${dataType}-indicator`);
        if (!indicatorEl) return;

        const bs = parsingStatus && parsingStatus[dataType]; // backend status
        const backendSuccess = bs && bs.success === true;
        const backendFailed  = bs && bs.success === false;
        const backendTime    = bs && bs.time;   // ISO 字符串或 null

        indicatorEl.classList.remove('status-success', 'status-error', 'status-loading', 'status-pending');

        if (backendSuccess) {
            // 后端解析成功 + 本次轮询成功 → 绿色
            indicatorEl.textContent = '解析成功';
            indicatorEl.classList.add('status-success');
            // 将后端解析时间格式化后显示
            if (backendTime) {
                try {
                    const t = new Date(backendTime);
                    if (isNaN(t.getTime())) {
                        dataUpdateTimestamps[dataType] = null;
                        updateStatusTimeDisplay(dataType, '--:--:--');
                    } else {
                        dataUpdateTimestamps[dataType] = t.getTime();
                        const pad = n => String(n).padStart(2, '0');
                        let displayStr;
                        if (window.displayTimezone === 'UTC') {
                            displayStr = `${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}:${pad(t.getUTCSeconds())}`;
                        } else {
                            displayStr = `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
                        }
                        dataUpdateTimes[dataType] = displayStr;
                        updateStatusTimeDisplay(dataType, displayStr);
                    }
                } catch (_) {
                    dataUpdateTimestamps[dataType] = null;
                    updateStatusTimeDisplay(dataType, '--:--:--');
                }
            } else {
                dataUpdateTimestamps[dataType] = null;
                updateStatusTimeDisplay(dataType, '--:--:--');
            }
        } else if (backendFailed) {
            // 后端解析失败 → 红色
            indicatorEl.textContent = '解析失败';
            indicatorEl.classList.add('status-error');
            dataUpdateTimestamps[dataType] = null;
            dataUpdateTimes[dataType] = '--:--:--';
            updateStatusTimeDisplay(dataType, '--:--:--');
        } else {
            // 尚未运行（null）→ 灰色等待
            indicatorEl.textContent = '等待解析';
            indicatorEl.classList.add('status-pending');
            dataUpdateTimestamps[dataType] = null;
            dataUpdateTimes[dataType] = '--:--:--';
            updateStatusTimeDisplay(dataType, '--:--:--');
        }
    });
}







/**
 * 判断time1是否早于或等于time2（DDHH格式时间比较）
 * 
 * 专门针对航空气象数据的时间比较，智能处理跨日和跨月情况
 * 支持5天内数据的完全覆盖，包括月末到月初的跨月场景
 * 
 * 设计原理：
 * - 航空气象数据时间跨度通常在5天内
 * - DDHH格式只包含日期和小时，不包含月份信息  
 * - 通过日期差值判断是否跨月：差值>15天认为是跨月
 * - 15天阈值为5天内数据提供充足的安全边界
 * 
 * 覆盖能力：
 * - 3天内数据：100%覆盖
 * - 5天内数据：100%覆盖  
 * - 支持所有月末月初跨月场景（如本月28日-下月3日）
 * 
 * @param {string} time1 - DDHH格式时间字符串（如'0606'表示6日06时）
 * @param {string} time2 - DDHH格式时间字符串（如'0611'表示6日11时）
 * @returns {boolean} True表示time1早于或等于time2，False表示time1晚于time2
 * 
 * @example
 * // 正常同月比较
 * isTimeBeforeOrEqual('0606', '0611') // → true (6日06时 <= 6日11时)
 * 
 * @example  
 * // 正常跨日比较
 * isTimeBeforeOrEqual('0523', '0611') // → true (5日23时 <= 6日11时)
 * 
 * @example
 * // 跨月情况比较
 * isTimeBeforeOrEqual('0106', '3023') // → false (下月1日06时 > 本月30日23时)
 * 
 * @example
 * // 5天跨月比较
 * isTimeBeforeOrEqual('2823', '0305') // → true (本月28日23时 < 下月3日05时)
 */
function isTimeBeforeOrEqual(time1, time2) {
    try {
        // 输入验证：确保时间格式正确
        if (!time1 || !time2 || time1.length !== 4 || time2.length !== 4) {
            return false;
        }

        // 解析DDHH格式：前两位是日期，后两位是小时
        const day1 = parseInt(time1.substr(0, 2));
        const hour1 = parseInt(time1.substr(2, 2));
        const day2 = parseInt(time2.substr(0, 2));
        const hour2 = parseInt(time2.substr(2, 2));

        // 核心算法：基于日期差值判断是否跨月
        // 计算两个日期的绝对差值
        const dayDiff = Math.abs(day1 - day2);

        // 跨月判断逻辑：日期差值大于15天认为是跨月情况
        // 原理：5天内的数据不可能有超过15天的日期差，除非跨月
        // 15天阈值为5天内数据提供充足安全边界
        // 例如：本月30日 vs 下月1日，差值=29>15，判定为跨月
        if (dayDiff > 15) {
            // 跨月情况处理：较小的日期数字对应下个月
            if (day1 < day2) {
                // day1较小 → day1是下个月，day2是本月
                // 例如：'0106'(下月1日) vs '3023'(本月30日)
                // 实际时间关系：下月1日 > 本月30日 → 返回false
                return false;
            } else {
                // day2较小 → day2是下个月，day1是本月
                // 例如：'3023'(本月30日) vs '0106'(下月1日)  
                // 实际时间关系：本月30日 < 下月1日 → 返回true
                return true;
            }
        } else {
            // 同月情况处理：按正常日期时间顺序比较
            if (day1 < day2) {
                // day1 < day2：不同日期，day1较早
                return true;
            } else if (day1 > day2) {
                // day1 > day2：不同日期，day1较晚
                return false;
            } else { // day1 == day2
                // day1 == day2：同一天，比较小时
                return hour1 <= hour2;
            }
        }
    } catch (e) {
        // 异常处理：记录错误日志并返回false作为安全默认值
        console.error('时间比较失败:', time1, 'vs', time2, e);
        return false;
    }
}


// ==================== 动态网格系统 ====================

function isMarksDisplayMidnight(ms) {
    const dt = new Date(ms);
    const utcMode = window.displayTimezone === 'UTC';
    if (utcMode) {
        return dt.getUTCHours() === 0 && dt.getUTCMinutes() === 0;
    }
    if (typeof currentTimeMode !== 'undefined' && currentTimeMode === 'test') {
        const bj = new Date(dt.getTime() + 8 * 3600000);
        return bj.getUTCHours() === 0 && bj.getUTCMinutes() === 0;
    }
    const beijingFmt = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Shanghai',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });
    const hm = {};
    beijingFmt.formatToParts(dt).forEach(function (part) {
        if (part.type === 'hour') hm.hour = parseInt(part.value, 10);
        if (part.type === 'minute') hm.minute = parseInt(part.value, 10);
    });
    return hm.hour === 0 && hm.minute === 0;
}

function getMarksAxisLineSpecs() {
    const winStart = getMarksWindowStartMs();
    const dur = getMarksWindowDurationMs();
    const winEnd = winStart + dur;
    const specs = [{ pct: 0, ms: winStart }];
    const firstHour = new Date(winStart);
    firstHour.setSeconds(0, 0);
    firstHour.setMinutes(0, 0, 0);
    if (firstHour.getTime() <= winStart) {
        firstHour.setHours(firstHour.getHours() + 1);
    }
    for (let t = firstHour.getTime(); t <= winEnd + 1000; t += 3600000) {
        const pct = (t - winStart) / dur;
        if (pct >= 0 && pct <= 1.0001) {
            specs.push({ pct, ms: t });
        }
    }
    if (specs[specs.length - 1].pct < 0.999) {
        specs.push({ pct: 1, ms: winEnd });
    }
    return specs;
}

// 计算与时间模式对应的「午夜刻度」竖线索引（与既有 UTC 刻度步进方式一致）
function findMidnightBoldLineIndexes(currentTime) {
    const indexes = [];
    const utcMode = window.displayTimezone === 'UTC';
    let beijingFmt = null;

    if (!utcMode) {
        beijingFmt = new Intl.DateTimeFormat('en-GB', {
            timeZone: 'Asia/Shanghai',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    const baseHourUtc = currentTime.getUTCHours();

    for (let i = 0; i <= currentTimeRange; i++) {
        const targetTime = new Date(currentTime.getTime());
        targetTime.setUTCHours(baseHourUtc + i, 0, 0, 0);

        let isMidnight = false;

        if (utcMode) {
            isMidnight = targetTime.getUTCHours() === 0;
        } else {
            const hm = {};
            beijingFmt.formatToParts(targetTime).forEach(function (part) {
                if (part.type === 'hour') hm.hour = parseInt(part.value, 10);
                if (part.type === 'minute') hm.minute = parseInt(part.value, 10);
                if (part.type === 'second') hm.second = parseInt(part.value, 10);
            });

            if (hm.hour !== undefined && hm.minute !== undefined
                && hm.hour === 0 && hm.minute === 0) {
                isMidnight = true;
            }
        }

        if (isMidnight) {
            indexes.push(i);
        }
    }

    return indexes;
}

// 计算竖线位置
function calculateVerticalLinePositions(horizontalLineWidth, timeSlots) {
    // marks 连续轴：整点竖线按分钟比例放置
    if (typeof isFlightMarksMode === 'function' && isFlightMarksMode()
        && typeof getMarksWindowStartMs === 'function'
        && typeof getMarksWindowDurationMs === 'function') {
        return getMarksAxisLineSpecs().map((s) => s.pct * horizontalLineWidth);
    }

    const cellWidth = horizontalLineWidth / timeSlots; // 每个格子宽度
    const positions = [];

    for (let i = 0; i <= timeSlots; i++) { // timeSlots+1条线
        positions.push(i * cellWidth);
    }

    return positions;
}

// 计算横线位置
function calculateHorizontalLinePositions(airportRowHeight) {
    const rowHeight = airportRowHeight / 3; // 平均分配为3行

    return {
        line1: 0,                    // 顶部（时间轴下方）
        line2: rowHeight,            // 1/3处（预报区下方）
        line3: rowHeight * 2,        // 2/3处（航班区下方）
        line4: rowHeight * 3         // 底部
    };
}

// 计算横线宽度
// 注意：必须传入具体的机场行元素，在其自身范围内查找 .forecast-timeline，
// 不能用全局 document.querySelector（会导致所有机场行都错误地共用同一个机场的宽度）
function calculateHorizontalWidth(airportElement) {
    const minWidth = 1680 - 80 - 200; // 1400px
    // marks 模式：全站共用同一宽度，避免各行 scrollWidth 微小差异导致竖线/顶轴错位
    if (typeof isFlightMarksMode === 'function' && isFlightMarksMode()) {
        const main = document.getElementById('content-main');
        const sample = (main && main.querySelector('.forecast-timeline'))
            || (airportElement && airportElement.querySelector('.forecast-timeline'));
        const w = sample ? sample.clientWidth : minWidth;
        return Math.max(minWidth, w);
    }
    const scopedTimeline = airportElement ? airportElement.querySelector('.forecast-timeline') : null;
    const contentWidth = scopedTimeline?.scrollWidth || minWidth;
    return Math.max(minWidth, contentWidth);
}

// 创建横线
function createHorizontalLines(airportElement, airportHeight, horizontalWidth) {
    // 移除旧的横线
    airportElement.querySelectorAll('.grid-horizontal-line').forEach(line => line.remove());

    const positions = calculateHorizontalLinePositions(airportHeight);
    // 优化：只保留第4条横线（底部），删除第1条，第2-3条不加粗
    const lineData = [
        // 第1条不绘制
        { position: positions.line2, className: 'forecast-bottom', bold: false },
        { position: positions.line3, className: 'flight-bottom', bold: false },
        { position: positions.line4, className: 'airport-bottom', bold: false }
    ];

    // 检测是否有airport-info元素，如果没有说明是详情页布局
    const hasAirportInfo = airportElement.querySelector('.airport-info') !== null;
    const leftOffset = hasAirportInfo ? 280 : 200; // 有airport-info时280px，否则200px

    lineData.forEach((data, index) => {
        const line = document.createElement('div');
        line.className = `grid-horizontal-line ${data.className}`;
        line.style.cssText = `
            position: absolute;
            left: ${leftOffset}px;
            top: ${data.position}px;
            width: ${horizontalWidth}px;
            height: 1px;
            background-color: #ddd;
            z-index: 0;
            pointer-events: none;
        `;
        airportElement.appendChild(line);
    });
}

// 创建竖线
function createVerticalLines(airportElement, airportHeight, horizontalWidth, timeSlots) {
    airportElement.querySelectorAll('.grid-vertical-line').forEach(line => line.remove());

    const marksMode = typeof isFlightMarksMode === 'function' && isFlightMarksMode();
    if (marksMode) {
        appendMarksVerticalLines(airportElement, { dark: false });
        return;
    }

    const positions = calculateVerticalLinePositions(horizontalWidth, timeSlots);
    const midnightIndexes = findMidnightBoldLineIndexes(getCurrentTime());

    const hasAirportInfo = airportElement.querySelector('.airport-info') !== null;
    const leftOffset = hasAirportInfo ? 280 : 200;

    positions.forEach((position, index) => {
        const line = document.createElement('div');
        line.className = 'grid-vertical-line';

        const isMidnightLine = midnightIndexes.includes(index);

        line.style.cssText = `
            position: absolute;
            left: ${leftOffset + position}px;
            top: 0;
            width: ${isMidnightLine ? '3px' : '1px'};
            height: ${airportHeight}px;
            background-color: ${isMidnightLine ? '#666' : '#ddd'};
            z-index: 0;
            pointer-events: none;
        `;

        if (isMidnightLine) {
            line.classList.add('utc-00-line');
        }

        airportElement.appendChild(line);
    });
}

function appendMarksVerticalLines(airportElement, options) {
    const dark = !!(options && options.dark);
    const timeline = airportElement.querySelector('.forecast-timeline');
    const host = (timeline && timeline.querySelector(':scope > .marks-slide-layer')) || timeline || airportElement;
    const specs = getMarksAxisLineSpecs();
    specs.forEach((spec) => {
        const line = document.createElement('div');
        const isMidnightLine = isMarksDisplayMidnight(spec.ms);
        line.className = 'grid-vertical-line' + (isMidnightLine ? ' utc-00-line' : '');
        const color = isMidnightLine
            ? (dark ? '#ffffff' : '#666')
            : (dark ? 'rgba(255, 255, 255, 0.3)' : '#ddd');
        line.style.cssText = `
            position: absolute;
            left: ${spec.pct * 100}%;
            top: 0;
            width: ${isMidnightLine ? '3px' : '1px'};
            height: 100%;
            background-color: ${color};
            z-index: 0;
            pointer-events: none;
            transform: translateX(-50%);
        `;
        host.appendChild(line);
    });
}

// 创建无TAF数据覆盖层
// createNoTafDataOverlay → 已迁移至 main_taf.js

// 更新机场网格
function updateAirportGrid(airportElement) {
    // 必须先移除旧的网格线，再测量高度/宽度，否则上一轮网格线（绝对定位、可能贴边1px）
    // 会被计入 scrollHeight/scrollWidth，导致每次刷新都基于"虚高"的尺寸重绘，越刷越往下偏移
    airportElement.querySelectorAll('.grid-horizontal-line, .grid-vertical-line').forEach(line => line.remove());

    const airportHeight = airportElement.scrollHeight;
    const horizontalWidth = calculateHorizontalWidth(airportElement);
    const timeSlots = currentTimeRange;

    // 创建横线
    createHorizontalLines(airportElement, airportHeight, horizontalWidth);

    // 创建竖线
    createVerticalLines(airportElement, airportHeight, horizontalWidth, timeSlots);

    // 检查是否需要覆盖层（只在预报区域）
    const tafRowContainer = airportElement.querySelector('.taf-row-container');
    const hasTafData = tafRowContainer && !tafRowContainer.textContent.includes('没有有效的TAF数据');

    if (!hasTafData && tafRowContainer) {
        const forecastHeight = airportHeight / 3; // 只覆盖预报区域
        const overlay = createNoTafDataOverlay(airportElement, forecastHeight, horizontalWidth);
        overlay.style.top = '0px'; // 从顶部开始
        tafRowContainer.appendChild(overlay);
    }
}

// 更新所有机场网格
function updateAllAirportGrids() {
    const airportRows = document.querySelectorAll('.airport-row');
    airportRows.forEach(airportRow => {
        // 机场详情弹窗内的行使用弹窗专用网格逻辑（用自身容器宽度），避免自动更新时误用主页面宽度导致网格间距变短
        // 注意：必须用 class 选择器 .airport-detail-main，不能用 id 选择器 #airport-detail-main——
        // 多机场搜索结果弹窗中的行容器 id 是 search-block-main-${code}，只共用了这个 class，
        // 用 id 选择器会匹配失败，导致搜索结果弹窗被自动刷新定时器误判为主页行，
        // 从而用浅色主题（#ddd/#666）重绘网格线，覆盖掉原本正确的深色主题（半透明白/纯白加粗线）
        const isInDetailModal = airportRow.closest('.airport-detail-main') !== null;
        if (isInDetailModal) {
            updateAirportGridForModal(airportRow);
        } else {
            updateAirportGrid(airportRow);
        }
    });
    if (typeof ensureFlightPastHandleFloat === 'function') {
        ensureFlightPastHandleFloat();
    }
}

// updateFlightStatusWarning → 已迁移至 main_flight.js

// 弹窗使用相同的网格更新函数，CSS缩放会自动处理

// 监听机场高度变化
function observeAirportHeightChanges() {
    // 每次 displayAirports 重建DOM后都会调用本函数，若不断开旧的 observer，
    // 旧实例会持续堆积（虽然旧行已从DOM移除，但观察者对象本身未被回收）
    if (window._airportRowResizeObserver) {
        window._airportRowResizeObserver.disconnect();
    }

    const observer = new ResizeObserver(entries => {
        entries.forEach(entry => {
            if (entry.target.classList.contains('airport-row')) {
                // 同上，使用 class 选择器以同时覆盖机场详情弹窗与多机场搜索结果弹窗
                const isInDetailPage = entry.target.closest('.airport-detail-main') !== null;
                if (!isInDetailPage) {
                    updateAirportGrid(entry.target);
                }
            }
        });
    });

    // 观察所有机场行
    document.querySelectorAll('.airport-row').forEach(airportRow => {
        observer.observe(airportRow);
    });

    window._airportRowResizeObserver = observer;
    return observer;
}

// 弹窗专用函数已删除，使用通用函数+CSS缩放

// 弹窗专用竖线函数已删除

// 弹窗专用覆盖层函数已删除

// 启动自动刷新（检查token状态）
if (!window.tokenInvalidDetected) {
    startAutoRefresh();
}

// 生成机场详情弹窗的时间轴
function generateAirportDetailTimeline() {
    const beijingTimeline = document.getElementById('airport-detail-beijing-timeline');
    const utcTimeline = document.getElementById('airport-detail-utc-timeline');
    if (!beijingTimeline || !utcTimeline) return;

    if (typeof syncMarksPastOpenClass === 'function') {
        syncMarksPastOpenClass('detail');
    }

    const paint = () => {
        if (typeof isFlightMarksMode === 'function' && isFlightMarksMode()
            && typeof fillMarksHourTicks === 'function') {
            const { winStart, dur } = fillMarksHourTicks(beijingTimeline, utcTimeline);
            const titleTimeline = beijingTimeline.closest('.title-timeline');
            if (typeof updateMarksNowBadge === 'function') {
                updateMarksNowBadge(titleTimeline, winStart, dur);
            }
            return true;
        }
        return false;
    };
    if (typeof withMarksRenderScope === 'function') {
        if (withMarksRenderScope('detail', paint)) return;
    } else if (paint()) {
        return;
    }

    const currentTime = getCurrentTime();
    let beijingCells = '';
    let utcCells = '';

    for (let i = 0; i < currentTimeRange; i++) {
        let beijingHour, utcHour;

        if (currentTimeMode === 'test') {
            const utcTime = new Date(currentTime.getTime() + i * 60 * 60 * 1000);
            utcHour = utcTime.getUTCHours().toString().padStart(2, '0');
            const beijingTime = new Date(utcTime.getTime() + 8 * 60 * 60 * 1000);
            beijingHour = beijingTime.getUTCHours().toString().padStart(2, '0');
        } else {
            const localTime = new Date(currentTime.getTime() + i * 60 * 60 * 1000);
            beijingHour = localTime.getHours().toString().padStart(2, '0');
            const utcTime = new Date(localTime.getTime() - 8 * 60 * 60 * 1000);
            utcHour = utcTime.getHours().toString().padStart(2, '0');
        }

        beijingCells += `<div class="timeline-cell" data-time="${i}"><span class="time-text">${i === 0 ? '' : beijingHour}</span></div>`;
        utcCells += `<div class="timeline-cell" data-time="${i}"><span class="time-text">${i === 0 ? '' : utcHour}</span></div>`;
    }

    beijingTimeline.innerHTML = beijingCells;
    utcTimeline.innerHTML = utcCells;
}

// 显示机场详情数据
function displayAirportDetailData(airportData) {
    const detailMain = document.getElementById('airport-detail-main');

    // 使用专门的详情页函数（不包含airport-info）
    const airportDataHTML = createAirportRowForDetail(airportData);

    detailMain.innerHTML = airportDataHTML;
    if (typeof paintPlainDetailMetar === 'function') {
        paintPlainDetailMetar(airportData);
    }

    if (window._viewMode === 'plain' && typeof ensurePlainForAirports === 'function') {
        ensurePlainForAirports([airportData]);
    }

    // 等待DOM渲染和缩放完成后应用网格线
    setTimeout(() => {
        const airportRow = detailMain.querySelector('.airport-row');
        if (airportRow) {
            updateAirportGridForModal(airportRow);
        }
        if (typeof ensureMarksPastHandle === 'function') {
            ensureMarksPastHandle('detail');
        }
    }, 150);
}

// 弹窗专用网格更新函数（考虑85%缩放）
function updateAirportGridForModal(airportElement) {
    const run = () => updateAirportGridForModalInner(airportElement);
    const scope = (typeof marksScopeFromElement === 'function')
        ? marksScopeFromElement(airportElement)
        : 'detail';
    if (typeof withMarksRenderScope === 'function') {
        return withMarksRenderScope(scope, run);
    }
    return run();
}

function updateAirportGridForModalInner(airportElement) {
    // 必须先移除旧的网格线，再测量高度/宽度，原因同 updateAirportGrid：
    // 避免把上一轮网格线的绝对定位偏移计入尺寸测量，形成越刷新越往下/往右偏移的累积误差
    airportElement.querySelectorAll('.grid-vertical-line, .grid-horizontal-line').forEach(line => line.remove());

    const forecastTimeline = airportElement.querySelector('.forecast-timeline');
    const hasAirportInfo = airportElement.querySelector('.airport-info') !== null;
    const hasWeather = airportElement.querySelector('.weather-info') !== null;
    const labelCol = airportElement.querySelector('.plain-row-labels');
    const leftOffset = hasAirportInfo ? 280 : (hasWeather ? 200 : (labelCol ? labelCol.offsetWidth : 0));
    const airportHeight = forecastTimeline
        ? forecastTimeline.offsetHeight
        : airportElement.scrollHeight;

    let horizontalWidth;
    if (forecastTimeline) {
        horizontalWidth = forecastTimeline.clientWidth || forecastTimeline.scrollWidth;
    } else {
        horizontalWidth = calculateHorizontalWidth(airportElement);
    }

    const timeSlots = currentTimeRange;
    const marksMode = typeof isFlightMarksMode === 'function' && isFlightMarksMode();

    if (marksMode) {
        appendMarksVerticalLines(airportElement, { dark: true });
    } else {
        const positions = calculateVerticalLinePositions(horizontalWidth, timeSlots);
        const midnightIndexes = findMidnightBoldLineIndexes(getCurrentTime());

        positions.forEach((position, index) => {
            const line = document.createElement('div');
            line.className = 'grid-vertical-line';
            const isMidnightLine = midnightIndexes.includes(index);

            line.style.cssText = `
                position: absolute;
                left: ${leftOffset + position}px;
                top: 0;
                width: ${isMidnightLine ? '3px' : '1px'};
                height: ${airportHeight}px;
                background-color: ${isMidnightLine ? '#ffffff' : 'rgba(255, 255, 255, 0.3)'};
                z-index: 0;
                pointer-events: none;
            `;

            if (isMidnightLine) {
                line.classList.add('utc-00-line');
            }
            airportElement.appendChild(line);
        });
    }

    // 创建横线
    const horizontalPositions = calculateHorizontalLinePositions(airportHeight);
    const lineData = [
        { position: horizontalPositions.line2, className: 'forecast-bottom' },
        { position: horizontalPositions.line3, className: 'flight-bottom' },
        { position: horizontalPositions.line4, className: 'airport-bottom' }
    ];

    lineData.forEach((data) => {
        const line = document.createElement('div');
        line.className = `grid-horizontal-line ${data.className}`;
        line.style.cssText = `
            position: absolute;
            left: ${leftOffset}px;
            top: ${data.position}px;
            width: ${horizontalWidth}px;
            height: 1px;
            background-color: rgba(255, 255, 255, 0.3);
            z-index: 0;
            pointer-events: none;
        `;
        airportElement.appendChild(line);
    });

    // 检查是否需要覆盖层
    const tafRowContainer = airportElement.querySelector('.taf-row-container');
    const hasTafData = tafRowContainer && !tafRowContainer.textContent.includes('没有有效的TAF数据');

    if (!hasTafData && tafRowContainer) {
        const forecastHeight = airportHeight / 3;
        const overlay = document.createElement('div');
        overlay.className = 'no-taf-data-overlay';
        overlay.style.cssText = `
            position: absolute;
            top: 0;
            left: ${leftOffset}px;
            width: ${horizontalWidth}px;
            height: ${forecastHeight}px;
            background: #2c3e50;
            z-index: 10;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.3);
            box-sizing: border-box;
        `;
        overlay.textContent = '没有有效的TAF数据';
        tafRowContainer.appendChild(overlay);
    }
}

// 注意：原generateSingleAirportTimeline函数已删除，因为现在直接复用createAirportRow函数

// ============== 鉴权相关函数 ==============

function isLocalBrowserHost() {
    const h = String(location.hostname || "").toLowerCase();
    return h === "127.0.0.1" || h === "localhost" || h === "::1";
}

const UNIFIED_AUTH_STATUS_URL = '/auth/status';
const UNIFIED_AUTH_UPDATE_URL = '/auth/update';
const UNIFIED_AUTH_CLEAR_URL = '/auth/clear';

function isRealUserCode(userCode) {
    const code = String(userCode || '').trim();
    if (!code) return false;
    return !['--', '-', 'OFFLINE', 'UNKNOWN', 'UNDEFINED', 'NULL', 'NONE'].includes(code.toUpperCase());
}

function isUsableAuthToken(token) {
    const value = String(token || '').trim();
    if (!value) return false;
    return !['--', '-', 'UNDEFINED', 'NULL', 'NONE'].includes(value.toUpperCase());
}

async function fetchUnifiedAuthStatus() {
    try {
        const response = await fetch(UNIFIED_AUTH_STATUS_URL, { cache: 'no-store' });
        const data = await response.json();
        return data.success ? data : null;
    } catch (error) {
        console.warn('读取 Nginx 统一登录态失败', error);
        return null;
    }
}

async function updateUnifiedAuth(token, userCode) {
    if (!isUsableAuthToken(token) || !isRealUserCode(userCode)) return;
    try {
        await fetch(UNIFIED_AUTH_UPDATE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token, userCode, source: 'MTWS' })
        });
    } catch (error) {
        console.warn('同步 MTWS 登录态到 Nginx 失败', error);
    }
}

async function clearUnifiedAuth() {
    try {
        await fetch(UNIFIED_AUTH_CLEAR_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: 'MTWS' })
        });
    } catch (error) {
        console.warn('清空 Nginx 统一登录态失败', error);
    }
}

// 监听控制台统一登录态：控制台后台会定期校验 token，过期时清空统一态。
// MTWS 轮询发现统一态被清空（且自身仍认为已登录）时，自动登出并提示重新登录。
let unifiedAuthWatchTimer = null;
function startUnifiedAuthWatch() {
    if (unifiedAuthWatchTimer) return;
    unifiedAuthWatchTimer = setInterval(async () => {
        if (currentTimeMode !== 'current' || !currentToken) return;
        const unified = await fetchUnifiedAuthStatus();
        if (!unified) return; // 接口异常不误判
        if (!unified.logged_in) {
            if (unified.expired) {
                handleSessionExpired('统一登录态 expired');
            } else if (isUsableAuthToken(currentToken) && isRealUserCode(currentUserCode)) {
                // 控制台重启后状态丢失（非过期）-> 把本地 token 回灌统一态，无需刷新页面
                console.info('检测到控制台统一登录态为空（可能刚重启），回灌本地 token');
                await updateUnifiedAuth(currentToken, currentUserCode);
            }
        }
    }, 5000);
}
function stopUnifiedAuthWatch() {
    if (unifiedAuthWatchTimer) {
        clearInterval(unifiedAuthWatchTimer);
        unifiedAuthWatchTimer = null;
    }
}

// 初始化current模式的鉴权
async function checkTokenStillValid(token, userCode) {
    if (!token) return false;
    try {
        const headers = {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
        if (userCode) headers['X-User-Code'] = userCode;
        const response = await fetch(`/${currentTimeMode}/api/validate-token/`, {
            method: 'GET',
            headers,
            cache: 'no-store'
        });
        return response.status !== 401;
    } catch (error) {
        // 验证接口异常时保守放行，避免网络抖动误弹登录。
        return true;
    }
}

async function initCurrentModeAuth() {
    const unified = await fetchUnifiedAuthStatus();
    const localToken = localStorage.getItem('mtws_token') || localStorage.getItem('sf_weather_token');
    const localUserCode = localStorage.getItem('mtws_userCode') || localStorage.getItem('sf_userId');
    const savedToken = (unified && unified.logged_in && unified.token)
        ? unified.token
        : localToken;
    const savedUserCode = (unified && unified.logged_in && unified.userCode)
        ? unified.userCode
        : localUserCode;

    if (unified && unified.expired) {
        clearAuthState();
        showLoginModal();
        return;
    }

    if (unified && unified.logged_in && (!isUsableAuthToken(unified.token) || !isRealUserCode(unified.userCode))) {
        console.warn('统一登录态工号或 token 无效，忽略并要求重新扫码');
        clearAuthState();
        showLoginModal();
        return;
    }

    if (savedToken && isUsableAuthToken(savedToken) && isRealUserCode(savedUserCode)) {
        const stillValid = await checkTokenStillValid(savedToken, savedUserCode);
        if (!stillValid) {
            clearAuthState();
            showLoginModal();
            return;
        }

        currentToken = savedToken;
        currentUserCode = savedUserCode;
        localStorage.setItem('mtws_token', currentToken);
        localStorage.setItem('mtws_userCode', currentUserCode);
        localStorage.setItem('sf_weather_token', currentToken);
        localStorage.setItem('sf_userId', currentUserCode);
        // 启动器/Nginx 统一登录态在重启后会清空（仅存内存）。
        // 浏览器本地仍有可用 token 时，主动回灌统一登录态，
        // 让启动器信息框和控制台立即识别为已登录，无需重新扫码。
        if (!(unified && unified.logged_in && unified.token)) {
            await updateUnifiedAuth(currentToken, currentUserCode);
        }
        showUserInfo();
        startUnifiedAuthWatch();
        loadInitialData();
    } else {
        showLoginModal();
    }
}



// 显示登录模态框
function showLoginModal() {
    const loginModal = document.getElementById('login-modal');
    if (!loginModal) return;
    ensureLoginModalOnTop();
    loginModal.style.display = 'block';
    getQRCode();
}

// 获取二维码
function getQRCode() {
    const statusDiv = document.getElementById('login-status');
    const qrcodeContainer = document.getElementById('qrcode-container');
    statusDiv.textContent = '正在获取二维码...';

    // 重置二维码过期状态
    qrCodeExpired = false;

    // 清除之前的定时器
    if (qrCodeTimer) {
        clearTimeout(qrCodeTimer);
        qrCodeTimer = null;
    }

    fetch(`/${currentTimeMode}/api/auth/get-qrcode/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 显示二维码
                qrcodeContainer.innerHTML = `<img id="qrcode-image" src="data:image/png;base64,${data.data.qr_img_base64}" alt="二维码" style="width: 200px; height: auto;">`;
                statusDiv.textContent = '请使用手机扫码登录';

                // 开始轮询检查登录状态
                startLoginCheck();

                // 启动120秒倒计时
                startQRCodeTimer();
            } else {
                statusDiv.textContent = '获取二维码失败: ' + data.error;
            }
        })
        .catch(error => {
            console.error('获取二维码失败:', error);
            statusDiv.textContent = '获取二维码失败，请重试';
        });
}

// 启动二维码倒计时器
function startQRCodeTimer() {
    // 120秒后二维码过期
    qrCodeTimer = setTimeout(function () {
        expireQRCode();
    }, 120000); // 120秒 = 120000毫秒
}

// 二维码过期处理
function expireQRCode() {
    qrCodeExpired = true;

    // 停止登录检查
    if (loginCheckInterval) {
        clearInterval(loginCheckInterval);
        loginCheckInterval = null;
    }

    // 清除倒计时器
    if (qrCodeTimer) {
        clearTimeout(qrCodeTimer);
        qrCodeTimer = null;
    }

    // 更新UI显示过期提示
    const qrcodeContainer = document.getElementById('qrcode-container');
    const statusDiv = document.getElementById('login-status');

    qrcodeContainer.innerHTML = `
        <div class="qrcode-expired" style="
            width: 200px; 
            height: 200px; 
            border: 2px dashed #ccc; 
            display: flex; 
            flex-direction: column; 
            justify-content: center; 
            align-items: center; 
            cursor: pointer;
            background-color: #f9f9f9;
            color: #666;
            font-size: 14px;
            text-align: center;
        " onclick="handleQRCodeClick()">
            <div>二维码已过期</div>
            <div style="margin-top: 8px;">点击获取</div>
        </div>
    `;

    statusDiv.textContent = '二维码已过期，请点击重新获取';
}

// 处理二维码区域点击事件
function handleQRCodeClick() {
    if (qrCodeExpired) {
        // 重新获取二维码
        getQRCode();
    }
}

// 将handleQRCodeClick函数添加到全局作用域，以便HTML onclick可以访问
window.handleQRCodeClick = handleQRCodeClick;



// 开始检查登录状态
function startLoginCheck() {
    if (loginCheckInterval) {
        clearInterval(loginCheckInterval);
    }

    loginCheckInterval = setInterval(function () {
        // 如果二维码已过期，停止检查
        if (qrCodeExpired) {
            clearInterval(loginCheckInterval);
            loginCheckInterval = null;
            return;
        }

        fetch(`/${currentTimeMode}/api/auth/check-login/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 登录成功
                    clearInterval(loginCheckInterval);
                    loginCheckInterval = null;

                    // 清除二维码倒计时器
                    if (qrCodeTimer) {
                        clearTimeout(qrCodeTimer);
                        qrCodeTimer = null;
                    }

                    currentToken = data.data.token;
                    currentUserCode = data.data.userCode;

                    // 存储到localStorage
                    localStorage.setItem('mtws_token', currentToken);
                    localStorage.setItem('mtws_userCode', currentUserCode);
                    // 同源部署下同步给 OMICS，避免两个程序重复扫码互相挤下线
                    localStorage.setItem('sf_weather_token', currentToken);
                    localStorage.setItem('sf_userId', currentUserCode);
                    updateUnifiedAuth(currentToken, currentUserCode);

                    hideLoginModal();
                    showUserInfo();

                    // 重置token失效标志并重新启动自动刷新
                    window.tokenInvalidDetected = false;
                    startUnifiedAuthWatch();
                    if (!window.autoRefreshTimer) {
                        startAutoRefresh();
                    }

                    // 启动弹窗轮询
                    startPopupCheck();

                    loadInitialData();
                } else if (data.message === '等待扫码') {
                    // 继续等待
                    if (!qrCodeExpired) {
                        document.getElementById('login-status').textContent = '等待扫码...';
                    }
                } else {
                    // 其他错误（包括验证失败）
                    document.getElementById('login-status').textContent = '登录失败: ' + data.error;
                    clearInterval(loginCheckInterval);
                    loginCheckInterval = null;

                    // 验证失败也触发二维码过期
                    expireQRCode();
                }
            })
            .catch(error => {
                console.error('检查登录状态失败:', error);
                clearInterval(loginCheckInterval);
                loginCheckInterval = null;

                // 网络错误也触发二维码过期
                expireQRCode();
            });
    }, 2000); // 每2秒检查一次
}

// 隐藏登录模态框
function hideLoginModal() {
    const loginModal = document.getElementById('login-modal');
    loginModal.style.display = 'none';

    // 清理所有定时器
    if (loginCheckInterval) {
        clearInterval(loginCheckInterval);
        loginCheckInterval = null;
    }

    if (qrCodeTimer) {
        clearTimeout(qrCodeTimer);
        qrCodeTimer = null;
    }

    // 重置二维码过期状态
    qrCodeExpired = false;
}

// 显示用户信息
function showUserInfo() {
    const userInfoSection = document.getElementById('user-info-section');
    if (userInfoSection) userInfoSection.style.display = 'flex';
    paintSeatUserInfo();
    refreshSeatIdentity();
}

function paintSeatUserInfo() {
    const userCodeSpan = document.getElementById('user-code');
    const logoutBtn = document.getElementById('logout-btn');
    const ident = window.__seatIdentity || window.__accessIdentity;
    let role = ident && ident.role;
    if (!role) role = isLocalBrowserHost() ? 'local' : 'guest';

    if (role === 'local' || (ident && ident.is_local)) {
        if (userCodeSpan) userCodeSpan.textContent = currentUserCode || '未知用户';
        if (logoutBtn) {
            logoutBtn.style.display = '';
            delete logoutBtn.dataset.seatLogout;
        }
        return;
    }

    if (role === 'non_local' || (ident && !ident.is_local && !ident.needs_role_select)) {
        if (userCodeSpan) {
            userCodeSpan.textContent = (ident && ident.label) || (ident && ident.group_name) || '';
        }
        if (logoutBtn) {
            logoutBtn.style.display = (ident && ident.show_logout) ? '' : 'none';
            logoutBtn.dataset.seatLogout = '1';
        }
        return;
    }

    if (logoutBtn) logoutBtn.style.display = 'none';
    if (userCodeSpan) {
        userCodeSpan.textContent = role === 'authorized' ? '授权用户' : '共享用户';
    }
}

async function refreshSeatIdentity() {
    try {
        const res = await fetch(`/${currentTimeMode}/api/seat-identity/`, { cache: 'no-store' });
        const data = await res.json();
        if (data && data.success && data.data) {
            window.__seatIdentity = data.data;
            paintSeatUserInfo();
        }
    } catch (_) {
        /* 接口不可用时按本机/共享兜底 */
    }
}

// 隐藏用户信息
function hideUserInfo() {
    const userInfoSection = document.getElementById('user-info-section');
    userInfoSection.style.display = 'none';
}

// 登出
function logout() {
    if (!currentToken) {
        return;
    }

    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
    };

    if (currentUserCode) {
        headers['X-User-Code'] = currentUserCode;
    }

    fetch(`/${currentTimeMode}/api/auth/logout/`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
            token: currentToken
        })
    })
        .then(response => response.json())
        .then(data => {
            // 无论成功与否都清除本地状态
            clearAuthState();

            if (data.success) {
                console.log('登出成功');
            } else {
                console.error('登出失败:', data.message);
            }

            // 重新显示登录界面
            showLoginModal();
        })
        .catch(error => {
            console.error('登出请求失败:', error);
            // 即使请求失败也清除本地状态
            clearAuthState();
            showLoginModal();
        });
}

// 清除认证状态
function clearAuthState() {
    currentToken = null;
    currentUserCode = null;

    stopUnifiedAuthWatch();
    clearUnifiedAuth();

    // 清除localStorage
    localStorage.removeItem('mtws_token');
    localStorage.removeItem('mtws_userCode');
    localStorage.removeItem('sf_weather_token');
    localStorage.removeItem('sf_userId');

    hideUserInfo();
    if (typeof clearPopupSeatSession === 'function') clearPopupSeatSession();
}

// 自动登出处理
function setupAutoLogout() {
    // 只在浏览器完全关闭时自动登出
    window.addEventListener('beforeunload', function (e) {
        if (currentToken && currentTimeMode === 'current') {
            // 使用fetch而不是sendBeacon，因为需要设置Authorization头
            const headers = {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentToken}`
            };

            if (currentUserCode) {
                headers['X-User-Code'] = currentUserCode;
            }

            fetch(`/${currentTimeMode}/api/auth/logout/`, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    token: currentToken
                }),
                keepalive: true  // 确保在页面卸载时仍能发送请求
            }).catch(() => { }); // 忽略错误，因为页面即将关闭
        }
    });

    // 删除visibilitychange事件监听，避免切换标签页就登出
}

// ========================================
// 实况弹窗相关函数
// ========================================
// 注意：弹窗相关代码位于 popup.js，以下仅保留必要的工具函数

// 将毫秒级时间戳转换为UTC时间字符串 YYYY DDMM HHMMSS格式
function formatTimestampToUTC(timestamp) {
    if (!timestamp) return '';

    try {
        const date = new Date(timestamp);
        const year = date.getUTCFullYear();
        const day = String(date.getUTCDate()).padStart(2, '0');
        const month = String(date.getUTCMonth() + 1).padStart(2, '0');
        const hours = String(date.getUTCHours()).padStart(2, '0');
        const minutes = String(date.getUTCMinutes()).padStart(2, '0');
        const seconds = String(date.getUTCSeconds()).padStart(2, '0');

        return `${year} ${day}${month} ${hours}${minutes}${seconds}`;
    } catch (error) {
        console.error('时间格式转换失败:', error);
        return '';
    }
}

// ========================================
// NWP 温度辅助功能位于 NWP.js
// ========================================

// 在页面加载完成后启动弹窗检查
document.addEventListener('DOMContentLoaded', function () {
    // 延迟启动弹窗检查，等待数据加载完成
    setTimeout(() => {
        if (currentTimeMode === 'current') {
            // current模式：只有在登录且token有效时才启动弹窗轮询
            if (currentToken && currentUserCode && !window.tokenInvalidDetected) {
                startPopupCheck();
            }
        } else {
            // test模式：无条件启动
            startPopupCheck();
        }
    }, 5000);
});


