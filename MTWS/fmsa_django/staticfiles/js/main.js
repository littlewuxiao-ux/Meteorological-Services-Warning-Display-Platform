// 全局变量
let currentTimeMode = window.timeMode || 'current';

// 显示时区模式：'CST'（北京时）或 'UTC'（世界时），默认北京时
window.displayTimezone = localStorage.getItem('fmsa_display_timezone') || 'CST';
let airportData = [];
let filteredAirportData = [];
let currentCarriers = [];
let currentAreaOptions = {
    domestic: [],
    international: []
};
let currentTimeRange = 36; // 当前时间范围：36或48
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

// 防重复刷新相关变量
let lastRefreshTime = 0;
let lastTooltipTime = 0;
const REFRESH_COOLDOWN = 30000; // 30秒冷却时间
const TOOLTIP_COOLDOWN = 10000; // 10秒提示冷却时间

// 弹窗开关按钮请求锁（防止请求进行中重复点击）
const toggleCooldowns = {
    'operation-toggle': { inCooldown: false },
    'parking-toggle':   { inCooldown: false }
};

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
    // 若告警面板已打开，重新渲染以反映新时区
    const alertPanel = document.getElementById('import-alert-panel');
    if (alertPanel && alertPanel.classList.contains('open')) {
        if (typeof _renderAlertPanel === 'function') _renderAlertPanel();
    }
}

// 初始化时间模式开关
function initTimezoneModeToggle() {
    const toggleInput = document.getElementById('timezone-toggle-input');
    if (!toggleInput) return;
    toggleInput.checked = (window.displayTimezone === 'UTC');
    toggleInput.addEventListener('change', function () {
        window.displayTimezone = this.checked ? 'UTC' : 'CST';
        localStorage.setItem('fmsa_display_timezone', window.displayTimezone);
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
    sessionStorage.setItem('fmsa_last_refresh', lastRefreshTime.toString());
}

// 显示刷新限制提示
function showRefreshLimitTooltip() {
    const now = Date.now();

    // 10秒内不重复显示提示
    if ((now - lastTooltipTime) < TOOLTIP_COOLDOWN) {
        return;
    }

    lastTooltipTime = now;

    // 创建提示元素
    const tooltip = document.createElement('div');
    tooltip.id = 'refresh-limit-tooltip';
    tooltip.textContent = '30秒内不允许重复获取和解析数据，请稍后再试';
    tooltip.style.cssText = `
        position: fixed;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        background-color: white;
        color: black;
        padding: 8px 16px;
        border: 1px solid #ccc;
        border-radius: 4px;
        font-size: 12px;
        z-index: 1000;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        pointer-events: none;
    `;

    // 添加到页面
    document.body.appendChild(tooltip);

    // 10秒后自动移除
    setTimeout(() => {
        if (tooltip && tooltip.parentNode) {
            tooltip.parentNode.removeChild(tooltip);
        }
    }, 10000);
}

// 检查是否为浏览器刷新
function checkBrowserRefresh() {
    // 使用sessionStorage检测浏览器刷新
    const isRefresh = sessionStorage.getItem('fmsa_page_loaded');

    if (isRefresh) {
        // 这是浏览器刷新，检查时间限制
        const lastRefresh = sessionStorage.getItem('fmsa_last_refresh');
        if (lastRefresh) {
            const timeDiff = Date.now() - parseInt(lastRefresh);
            if (timeDiff < REFRESH_COOLDOWN) {
                // 在冷却时间内，显示提示并阻止数据加载
                showRefreshLimitTooltip();
                return false;
            }
        }
    }

    // 标记页面已加载
    sessionStorage.setItem('fmsa_page_loaded', 'true');
    // 更新刷新时间
    updateRefreshTime();
    sessionStorage.setItem('fmsa_last_refresh', lastRefreshTime.toString());

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

    // 检查浏览器刷新限制
    const canLoad = checkBrowserRefresh();

    if (canLoad) {
        // 根据时间模式进行不同的初始化
        if (currentTimeMode === 'current') {
            initCurrentModeAuth();
        } else {
            loadInitialData();
        }
    }

    loadCarrierData();
});

// 检测是否清除了缓存
function checkIfCacheCleared() {
    // 通过检查页面加载标记来检测缓存清除
    // 如果是清除缓存，sessionStorage中的页面加载标记也会被清除
    const pageLoaded = sessionStorage.getItem('fmsa_page_loaded');
    const hasFilters = localStorage.getItem('fmsa_filters');

    // 如果没有页面加载标记且没有筛选状态，可能是清除了缓存或首次访问
    // 但如果是首次访问，我们也应该使用默认状态
    if (!pageLoaded && !hasFilters) {
        return true;
    }

    // 另一种检测方法：检查localStorage中是否有一个特殊的标记
    const cacheTimestamp = localStorage.getItem('fmsa_cache_timestamp');
    if (!cacheTimestamp) {
        // 设置缓存时间戳
        localStorage.setItem('fmsa_cache_timestamp', Date.now().toString());
        return true; // 第一次设置，说明可能是清除了缓存
    }

    return false;
}

// 保存筛选状态到localStorage
function saveFiltersToStorage() {
    localStorage.setItem('fmsa_filters', JSON.stringify(filters));
    localStorage.setItem('fmsa_cache_timestamp', Date.now().toString());
}

// 保存时间范围到localStorage
function saveTimeRangeToStorage() {
    localStorage.setItem('fmsa_time_range', currentTimeRange);
    localStorage.setItem('fmsa_cache_timestamp', Date.now().toString());
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
    localStorage.removeItem('fmsa_filters');
    localStorage.removeItem('fmsa_time_range');

    // 标记需要在区域选项加载后更新区域筛选
    sessionStorage.setItem('fmsa_reset_regions', 'true');
}

// 初始化筛选器状态
function initializeFilters() {
    // 检查是否为强制刷新或清除缓存
    const isForceRefresh = sessionStorage.getItem('fmsa_force_refresh');
    const isCacheCleared = checkIfCacheCleared();

    if (isForceRefresh || isCacheCleared) {
        // 强制刷新或清除缓存时恢复默认状态
        resetToDefaultFilters();
        // 清除强制刷新标记
        sessionStorage.removeItem('fmsa_force_refresh');
    } else {
        // 普通刷新时从localStorage恢复筛选状态
        const savedFilters = localStorage.getItem('fmsa_filters');
        if (savedFilters) {
            filters = JSON.parse(savedFilters);
        }

        // 从localStorage加载时间范围状态
        const savedTimeRange = localStorage.getItem('fmsa_time_range');
        if (savedTimeRange) {
            currentTimeRange = parseInt(savedTimeRange);
        }
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

    // 告警裕度下拉菜单状态
    updateMarginSelectState();

    // 告警裕度按钮状态（保留以防其他地方使用）
    updateButtonGroupState('margin', [filters.margin.toString()]);

    // 时间范围下拉菜单状态
    updateTimeRangeSelectState();

    // 时间范围按钮状态（保留以防其他地方使用）
    updateButtonGroupState('time-range', [currentTimeRange.toString()]);
}

// 更新告警裕度下拉菜单状态
function updateMarginSelectState() {
    const marginSelect = document.getElementById('margin-select');
    if (marginSelect) {
        marginSelect.value = filters.margin.toString();
    }
}

// 更新时间范围下拉菜单状态
function updateTimeRangeSelectState() {
    const timeRangeSelect = document.getElementById('time-range-select');
    if (timeRangeSelect) {
        timeRangeSelect.value = currentTimeRange.toString();
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
            
            /* 48小时模式：调整时间刻度偏移量 */
            .timeline-container {
                transform: translateX(calc(-100% / 48 / 2)) !important;
            }
        `;

        document.head.appendChild(style);
    }
}

// 旧的00时线加粗函数已被新的网格系统替代

// 生成时间轴
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
    initializePopupSettings();
    triggerParsingAndLoadData();
}

// 手动刷新数据（排除停场解析器）
function refreshManualData() {
    // 检查是否在冷却时间内
    if (!canRefresh()) {
        showRefreshLimitTooltip();
        return;
    }

    // 更新刷新时间
    updateRefreshTime();

    generateTimeline(); // 先更新时间轴
    applyTimeRangeScaling(); // 应用时间范围缩放

    // 手动刷新只刷新航班、实况、预报，排除停场解析器
    const manualUpdateTypes = ['flight', 'metar', 'taf'];
    console.log('手动刷新:', manualUpdateTypes);

    showLoading();
    loadParameterizedData(manualUpdateTypes);
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
        headers: headers
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

                // 保存解析结果并更新页面上的解析状态显示
                console.log('💾 保存解析结果:', parsingResult.data);
                window.lastParsingResult = parsingResult.data;
                console.log('🔄 开始更新解析状态显示...');

                // 使用统一的状态更新逻辑
                const parsers = parsingResult.data.parsers || {};
                if (Object.keys(parsers).length > 0) {
                    Object.keys(parsers).forEach(dataType => {
                        const parseResult = parsers[dataType];
                        if (parseResult) {
                            // 先更新时间，再更新状态
                            updateDataTime(dataType, parseResult.success);
                            updateSingleParsingStatus(dataType, parseResult.success);
                        }
                    });
                } else {
                    console.warn('⚠️ 解析结果中没有parsers数据');
                    // 设置默认状态
                    ['flight', 'metar', 'taf'].forEach(dataType => {
                        updateDataTime(dataType, false);
                        updateSingleParsingStatus(dataType, false);
                    });
                }

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
                    const needResetRegions = sessionStorage.getItem('fmsa_reset_regions');
                    if (needResetRegions) {
                        // 重置为所有区域选中
                        filters.domestic = currentAreaOptions.domestic.map(region => region.area);
                        filters.international = currentAreaOptions.international.map(region => region.area);
                        sessionStorage.removeItem('fmsa_reset_regions');
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
                showTokenInvalidError();
                stopAllAutoRefresh();
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

// 显示token失效错误信息
function showTokenInvalidError() {
    const contentMain = document.getElementById('content-main');
    contentMain.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">⚠️</div>
            <div class="empty-state-message">登录过期或异地登录，数据加载失败</div>
            <button onclick="handleRelogin()" class="relogin-btn">重新登录</button>
        </div>
    `;

    // 重置所有数据时间为--:--:--
    dataUpdateTimes.metar = '--:--:--';
    dataUpdateTimes.taf = '--:--:--';
    dataUpdateTimes.flight = '--:--:--';
    updateStatusTimeDisplay('metar', '--:--:--');
    updateStatusTimeDisplay('taf', '--:--:--');
    updateStatusTimeDisplay('flight', '--:--:--');

    // 隐藏用户信息
    hideUserInfo();
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
                // Token失效：显示专门提示 + 停止自动刷新 + 隐藏用户信息
                showTokenInvalidError();
                stopAllAutoRefresh();
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
function updateCarrierDisplay() {
    const carrierDisplay = document.getElementById('carrier-display');
    if (currentCarriers && currentCarriers.length > 0) {
        carrierDisplay.textContent = currentCarriers.join(' ');
    } else {
        carrierDisplay.textContent = '暂无承运人数据';
    }
}

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
        // TODO: 打开设置页面
        window.open('/settings/', '_blank');
    });

    document.getElementById('monitor-btn').addEventListener('click', function () {
        showModal('monitor-modal');
    });

    document.getElementById('search-btn').addEventListener('click', function () {
        const searchValue = document.getElementById('search-input').value.trim();
        if (searchValue) {
            performSearch(searchValue);
        }
    });

    document.getElementById('refresh-btn').addEventListener('click', function () {
        refreshData();
    });

    // 搜索框回车事件
    document.getElementById('search-input').addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            const searchValue = this.value.trim();
            if (searchValue) {
                performSearch(searchValue);
            }
        }
    });

    // 告警裕度下拉菜单事件
    document.getElementById('margin-select').addEventListener('change', function (e) {
        handleMarginSelectChange(e.target);
    });

    // 时间范围下拉菜单事件
    document.getElementById('time-range-select').addEventListener('change', function (e) {
        handleTimeRangeSelectChange(e.target);
    });

    // 弹窗关闭事件
    document.querySelectorAll('.modal-close').forEach(closeBtn => {
        closeBtn.addEventListener('click', function () {
            const modal = this.closest('.modal');
            hideModal(modal.id);
        });
    });

    // ESC键关闭弹窗 & Ctrl+Shift+R检测
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            const openModal = document.querySelector('.modal[style*="display: block"]');
            if (openModal) {
                hideModal(openModal.id);
            }
        }

        // 检测Ctrl+Shift+R (强制刷新)
        if (e.ctrlKey && e.shiftKey && e.key === 'R') {
            // 标记为强制刷新，重置为默认状态
            sessionStorage.setItem('fmsa_force_refresh', 'true');
        }
    });

    // 点击模态背景关闭弹窗
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function (e) {
            if (e.target === this) {
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
            logout();
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

    // 弹窗开关点击事件
    document.querySelectorAll('.popup-toggle-btn').forEach(toggle => {
        toggle.addEventListener('click', function () {
            handleToggleClick(this);
        });
    });
}

// 初始化弹窗设置
async function initializePopupSettings() {
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

        const response = await fetch(`/${currentTimeMode}/api/popup-settings/`, {
            method: 'GET',
            headers: headers
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success && result.data) {
                updateToggleState('operation-toggle', result.data.operation_metar_popup);
                updateToggleState('parking-toggle', result.data.parking_metar_popup);
            }
        }
    } catch (error) {
        console.error('初始化弹窗设置失败:', error);
    }
}

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

// 处理开关点击
async function handleToggleClick(toggle) {
    const toggleId = toggle.id;
    const cooldown = toggleCooldowns[toggleId];

    // 请求进行中时忽略重复点击
    if (cooldown && cooldown.inCooldown) {
        return;
    }

    const field = toggle.getAttribute('data-field');
    const currentState = toggle.classList.contains('selected');
    const newState = !currentState;

    if (cooldown) {
        cooldown.inCooldown = true;
        toggle.style.opacity = '0.6';
        toggle.style.cursor = 'not-allowed';
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

        const response = await fetch(`/${currentTimeMode}/api/popup-settings/update/`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                field: field,
                value: newState
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                if (newState) {
                    toggle.classList.add('selected');
                } else {
                    toggle.classList.remove('selected');
                }
            } else {
                console.error('更新弹窗设置失败:', result.error);
            }
        } else {
            console.error('更新弹窗设置失败, 状态码:', response.status);
        }

        // 5秒后解除冷却
        setTimeout(() => {
            if (cooldown) {
                cooldown.inCooldown = false;
                toggle.style.opacity = '';
                toggle.style.cursor = '';
            }
        }, 5000);

    } catch (error) {
        console.error('更新弹窗设置出错:', error);
        if (cooldown) {
            cooldown.inCooldown = false;
            toggle.style.opacity = '';
            toggle.style.cursor = '';
        }
    }
}

// 处理筛选按钮点击
// 处理告警裕度下拉菜单变化
function handleMarginSelectChange(select) {
    const value = select.value;
    const oldMargin = filters.margin;
    const newMargin = parseInt(value);

    // 只有当裕度值发生变化时才触发刷新
    if (oldMargin !== newMargin) {
        filters.margin = newMargin;
        updateButtonGroupState('margin', [value]);

        // 保存筛选状态
        saveFiltersToStorage();

        // 告警裕度变化只需要重新计算显示，不需要重新加载数据
        if (airportData && airportData.length > 0) {
            applyFilters(); // 重新应用筛选和重新计算告警
        } else {
            loadInitialData(); // 如果没有数据，先加载数据
        }
    }
}

// 处理时间范围下拉菜单变化
function handleTimeRangeSelectChange(select) {
    const value = select.value;
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
}

function handleFilterClick(button) {
    const group = button.getAttribute('data-group');
    const value = button.getAttribute('data-value');

    if (group === 'margin') {
        // 告警裕度：单选（已改为下拉菜单，此分支保留以防其他地方调用）
        const oldMargin = filters.margin;
        const newMargin = parseInt(value);

        // 只有当裕度值发生变化时才触发刷新
        if (oldMargin !== newMargin) {
            filters.margin = newMargin;
            updateButtonGroupState('margin', [value]);

            // 保存筛选状态
            saveFiltersToStorage();

            // 告警裕度变化只需要重新计算显示，不需要重新加载数据
            if (airportData && airportData.length > 0) {
                applyFilters(); // 重新应用筛选和重新计算告警
            } else {
                loadInitialData(); // 如果没有数据，先加载数据
            }
        }
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
    } else if (group === 'alert') {
        // 告警等级筛选：特殊逻辑
        handleAlertFilter(value);

        // 保存筛选状态
        saveFiltersToStorage();

        // 应用筛选
        applyFilters();
    } else if (group === 'domestic') {
        // 国内区域筛选：特殊逻辑
        handleRegionFilter('domestic', value);

        // 保存筛选状态
        saveFiltersToStorage();

        // 应用筛选
        applyFilters();
    } else if (group === 'international') {
        // 国际区域筛选：特殊逻辑
        handleRegionFilter('international', value);

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
        domesticContainer.appendChild(allButton);

        // 添加各个区域按钮
        currentAreaOptions.domestic.forEach(region => {
            const button = document.createElement('button');
            button.className = 'filter-btn domestic-area';
            button.setAttribute('data-group', 'domestic');
            button.setAttribute('data-value', region.area);
            button.textContent = region.area;
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
        internationalContainer.appendChild(allButton);

        // 添加各个区域按钮
        currentAreaOptions.international.forEach(region => {
            const button = document.createElement('button');
            button.className = 'filter-btn international-area';
            button.setAttribute('data-group', 'international');
            button.setAttribute('data-value', region.area);
            button.textContent = region.area;
            internationalContainer.appendChild(button);
        });
    }
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

    // 更新全部按钮
    const allButton = document.querySelector('[data-group="alert"][data-value="all"]');
    if (allSelected) {
        allButton.classList.add('selected');
    } else {
        allButton.classList.remove('selected');
    }

    // 更新各个告警级别按钮
    allAlertLevels.forEach(level => {
        const button = document.querySelector(`[data-group="alert"][data-value="${level}"]`);
        if (filters.alert.includes(level)) {
            button.classList.add('selected');
        } else {
            button.classList.remove('selected');
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
function applyFilters() {
    if (!airportData || airportData.length === 0) {
        displayAirports([]);
        return;
    }

    filteredAirportData = airportData.filter(airport => {
        // 区域筛选
        if (!isRegionMatch(airport)) {
            return false;
        }

        // 置顶机场不受告警等级筛选限制
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

    displayAirports(filteredAirportData);
}

// 检查区域筛选匹配
function isRegionMatch(airport) {
    // 获取机场的实际区域，如果为空则归类为其它
    const airportArea = airport.area || '其它';

    // 获取当前的区域选项
    const knownDomesticRegions = (currentAreaOptions.domestic || []).map(region => region.area);
    const knownInternationalRegions = (currentAreaOptions.international || []).map(region => region.area);

    // 如果是未知区域，归类为其它
    let matchArea = airportArea;
    if (!knownDomesticRegions.includes(airportArea) && !knownInternationalRegions.includes(airportArea)) {
        matchArea = '其它';
    }

    // 检查国内区域
    if (knownDomesticRegions.includes(matchArea)) {
        if (filters.domestic.length === 0) return false;
        return filters.domestic.includes(matchArea);
    }

    // 检查国际区域
    if (knownInternationalRegions.includes(matchArea)) {
        if (filters.international.length === 0) return false;
        return filters.international.includes(matchArea);
    }

    // 未知情况，如果有任何筛选激活则显示
    return filters.domestic.length > 0 || filters.international.length > 0;
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

    // 分离置顶和非置顶机场
    const pinned = [];
    const unpinned = [];

    filteredAirportData.forEach(airport => {
        if (pinnedAirports.hasOwnProperty(airport.airport_4code)) {
            pinned.push({
                airport: airport,
                pinnedTime: pinnedAirports[airport.airport_4code]
            });
        } else {
            unpinned.push(airport);
        }
    });

    // 置顶机场按时间排序（最旧的在前）
    pinned.sort((a, b) => a.pinnedTime - b.pinnedTime);

    // 重新组合：置顶机场在前，非置顶机场在后
    filteredAirportData = pinned.map(item => item.airport).concat(unpinned);
}

// 获取区域排序优先级
function getRegionSortPriority(airport) {
    const area = airport.area || '其它';

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
    const savedSortOption = localStorage.getItem('fmsa_airport_sort');
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
            localStorage.setItem('fmsa_airport_sort', currentSortOption);
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
    }, 100);

    // 更新时间戳和解析状态容器
    // 移除现有的状态信息容器
    const existingContainer = document.querySelector('.status-info-container');
    if (existingContainer) {
        existingContainer.remove();
    }

    // 创建统一的状态信息容器
    const statusContainer = document.createElement('div');
    statusContainer.className = 'status-info-container';

    // 创建解析状态显示
    const parsingStatusDiv = document.createElement('div');
    parsingStatusDiv.className = 'parsing-status-display';
    parsingStatusDiv.innerHTML = `
        <div class="parsing-status-item" id="flight-status">
            <span class="status-label">航班</span>
            <span class="status-indicator" id="flight-indicator">等待中...</span>
            <span class="status-time" id="flight-time">--:--:--</span>
        </div>
        <div class="parsing-status-item" id="metar-status">
            <span class="status-label">实况</span>
            <span class="status-indicator" id="metar-indicator">等待中...</span>
            <span class="status-time" id="metar-time">--:--:--</span>
        </div>
        <div class="parsing-status-item" id="taf-status">
            <span class="status-label">预报</span>
            <span class="status-indicator" id="taf-indicator">等待中...</span>
            <span class="status-time" id="taf-time">--:--:--</span>
        </div>
    `;

    // 将解析状态添加到容器中
    statusContainer.appendChild(parsingStatusDiv);

    // 将容器添加到页面
    document.querySelector('.header-section').appendChild(statusContainer);

    // 检查是否有保存的解析状态需要恢复
    if (window.lastParsingResult && window.lastParsingResult.parsers) {
        // 恢复之前的解析状态，使用统一的状态更新逻辑
        const parsers = window.lastParsingResult.parsers;
        Object.keys(parsers).forEach(dataType => {
            const parseResult = parsers[dataType];
            updateSingleParsingStatus(dataType, parseResult.success);
        });
    } else {
        // 设置初始状态为等待中
        updateParsingStatus('pending');
    }
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
    const stored = localStorage.getItem('fmsa_pinned_airports');
    return stored ? JSON.parse(stored) : {};
}

function setPinnedAirports(pinnedAirports) {
    localStorage.setItem('fmsa_pinned_airports', JSON.stringify(pinnedAirports));
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

    const isPinned = isAirportPinned(airportCode);
    const menuText = isPinned ? '取消置顶' : '置顶';

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
        min-width: 80px;
        font-size: 14px;
    `;

    const menuItem = document.createElement('div');
    menuItem.textContent = menuText;
    menuItem.style.cssText = `
        padding: 8px 12px;
        cursor: pointer;
        transition: background-color 0.2s;
    `;

    menuItem.addEventListener('mouseenter', () => {
        menuItem.style.backgroundColor = '#f0f0f0';
    });

    menuItem.addEventListener('mouseleave', () => {
        menuItem.style.backgroundColor = 'transparent';
    });

    menuItem.addEventListener('click', () => {
        toggleAirportPin(airportCode);
        menu.remove();
    });

    menu.appendChild(menuItem);
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

    // 根据告警等级设置机场代码的字体阴影
    const airportCodeStyle = airportAlertLevel !== 'N' ?
        `text-shadow: 0 0 3px ${alertColor}, 0 0 6px ${alertColor};` : '';

    const noTafData = (!tafData || tafData.length === 0) || (tafData[0].data_status === 'C');
    const tafAlertClass = (tafData && tafData.length > 0 && tafData[0].import_alert === 'Y') ? ' taf-import-alerted' : '';

    return `
        <div class="airport-row">
            <div class="airport-info" style="position: relative;" oncontextmenu="handleAirportRightClick(event, '${airport.airport_4code}')">
                ${createPinIcon(airport.airport_4code)}
                <div class="airport-code-container">
                    <div class="airport-code" style="${airportCodeStyle}">${airport.airport_4code}</div>
                </div>
                <div class="airport-name">${airport.airport_name || ''}</div>
            </div>
            ${buildWeatherInfoDiv(airport.airport_4code, latestMetar)}
            <div class="forecast-timeline">
                ${noTafData ? '<div class="no-taf-data">没有有效的TAF数据</div>' : ''}
                <div class="forecast-row main-forecast${tafAlertClass}">
                    ${createTafForecastRow(tafData, 'main')}
                </div>
                <div class="forecast-row change-forecast${tafAlertClass}">
                    ${createTafForecastRow(tafData, 'change')}
                </div>
                <div class="forecast-row flight-row">
                    ${createFlightTimeline(flightData, tafData, airport.metar_data, airport)}
                </div>
            </div>
        </div>
    `;
}

// 为机场详情弹窗创建专用的机场行（不包含airport-info）
function createAirportRowForDetail(airport) {
    const flightData = airport.flight_data || {};
    const latestMetar = airport.metar_data && airport.metar_data.length > 0 ? airport.metar_data[0] : null;
    const tafData = airport.taf_data || [];

    const noTafData = (!tafData || tafData.length === 0) || (tafData[0].data_status === 'C');
    const tafAlertClass = (tafData && tafData.length > 0 && tafData[0].import_alert === 'Y') ? ' taf-import-alerted' : '';

    return `
        <div class="airport-row airport-row-detail">
            ${buildWeatherInfoDiv(airport.airport_4code, latestMetar)}
            <div class="forecast-timeline">
                ${noTafData ? '<div class="no-taf-data">没有有效的TAF数据</div>' : ''}
                <div class="forecast-row main-forecast${tafAlertClass}">
                    ${createTafForecastRow(tafData, 'main')}
                </div>
                <div class="forecast-row change-forecast${tafAlertClass}">
                    ${createTafForecastRow(tafData, 'change')}
                </div>
                <div class="forecast-row flight-row">
                    ${createFlightTimeline(flightData, tafData, airport.metar_data, airport)}
                </div>
            </div>
        </div>
    `;
}



// 创建TAF预报行
function createTafForecastRow(tafData, rowType) {
    let html = '';

    // 时间格子已被新的网格线系统替代

    if (!tafData || tafData.length === 0) {
        return `<div class="taf-row-container" style="position: relative; height: 100%;">${html}</div>`;
    }

    // 获取最新的TAF数据
    const latestTaf = tafData[0];

    // 在行容器上添加甘特图
    const ganttBars = createTafGanttBars(latestTaf, rowType);

    return `<div class="taf-row-container" style="position: relative; height: 100%;">${html}${ganttBars}</div>`;
}

// 创建TAF甘特图条带
function createTafGanttBars(taf, rowType) {
    let ganttBars = '';


    if (rowType === 'main') {
        // 主预报甘特图
        if (taf.subject_validity_period_start && taf.subject_validity_period_end) {
            ganttBars += createSingleGanttBar(
                taf.subject_validity_period_start,
                taf.subject_validity_period_end,
                taf.subject_content || '',
                taf.subject_warning || 'N',
                'main-forecast'
            );
        }

        // BECMG和FROM变化组
        for (let i = 1; i <= 8; i++) {
            const changeType = taf[`change_${i}_type`];
            if (changeType === 'BECMG' || changeType === 'FROM' || changeType === 'BECMG ' || changeType === 'FROM ') {
                const startTime = taf[`change_${i}_validity_period_start`];
                const endTime = taf[`change_${i}_validity_period_end`];
                const content = taf[`change_${i}_content_all`];
                const warning = taf[`change_${i}_warning`];

                if (startTime && endTime) {
                    ganttBars += createSingleGanttBar(
                        startTime,
                        endTime,
                        content || '',
                        warning || 'N',
                        'change-forecast'
                    );
                }

                // 如果是BECMG变化组，添加过渡条带
                if ((changeType === 'BECMG' || changeType === 'BECMG ') && startTime) {
                    ganttBars += createBecmgTransitionBar(taf, i);
                }
            }
        }
    } else if (rowType === 'change') {
        // TEMPO、PROB30、PROB40、INTER变化组
        for (let i = 1; i <= 8; i++) {
            const changeType = taf[`change_${i}_type`];
            if (changeType === 'TEMPO' || changeType === 'PROB30' || changeType === 'PROB40' || changeType === 'INTER' ||
                changeType === 'TEMPO ' || changeType === 'PROB30 ' || changeType === 'PROB40 ' || changeType === 'INTER ') {
                const startTime = taf[`change_${i}_validity_period_start`];
                const endTime = taf[`change_${i}_validity_period_end`];
                const content = taf[`change_${i}_content_all`];
                const warning = taf[`change_${i}_warning`];

                if (startTime && endTime) {
                    ganttBars += createSingleGanttBar(
                        startTime,
                        endTime,
                        content || '',
                        warning || 'N',
                        'tempo-prob'
                    );
                }
            }
        }
    }

    // 添加温度指示器
    if (rowType === 'main') {
        ganttBars += createTemperatureIndicators(taf);
    }

    return ganttBars;
}

// 获取甘特条带计算专用的当前时间（整点对齐）
function getCurrentTimeForGantt() {
    const currentTime = getCurrentTime();

    if (currentTimeMode === 'current') {
        // current模式下，强制对齐到当前小时的整点，消除分钟秒的舍入边界效应
        const alignedTime = new Date(currentTime);
        alignedTime.setMinutes(0, 0, 0); // 设置为当前小时的00分00秒000毫秒
        return alignedTime;
    } else {
        // test模式保持原有逻辑
        return currentTime;
    }
}

// 创建单个甘特图条带
function createSingleGanttBar(startTime, endTime, content, warning, type) {
    if (!startTime || !endTime) {
        return '';
    }

    const currentTime = getCurrentTime();
    const position = calculateGanttPosition(startTime, endTime, currentTime);

    // 如果甘特图宽度太小或者超出范围，则不显示
    if (position.width <= 0 || position.left >= 100 || position.left + position.width <= 0) {
        return '';
    }

    // 根据告警级别设置背景色
    const alertColor = getAlertColor(warning);
    const backgroundColor = (warning && warning !== 'N' && warning !== '') ? alertColor : getDefaultBackgroundColor(type);

    return `
        <div class="gantt-bar gantt-${type}" 
             style="position: absolute; 
                    left: ${position.left}%; 
                    width: ${position.width}%; 
                    background-color: ${backgroundColor}; 
                    color: white; 
                    z-index: 1;"
             title="${content || ''}">
            ${content || ''}
        </div>
    `;
}

// 创建BECMG过渡条带
function createBecmgTransitionBar(taf, becmgIndex) {
    // 获取BECMG变化组的开始时间
    const becmgStartTime = taf[`change_${becmgIndex}_validity_period_start`];
    if (!becmgStartTime) {
        return '';
    }

    // 查找前面最近的预报段（主体预报或变化组）
    let previousEndTime = null;
    let previousContent = '';
    let previousWarning = 'N';

    // 先检查前面的变化组（从becmgIndex-1往前找，只考虑BECMG和FROM类型，并进行时间校验）
    for (let j = becmgIndex - 1; j >= 1; j--) {
        const prevType = taf[`change_${j}_type`];
        const prevEndTime = taf[`change_${j}_validity_period_end`];
        if (prevEndTime && (prevType === 'BECMG' || prevType === 'FROM' || prevType === 'BECMG ' || prevType === 'FROM ')) {
            // 时间校验：结束时间必须早于或等于BECMG开始时间
            if (isTimeBeforeOrEqual(prevEndTime, becmgStartTime)) {
                previousEndTime = prevEndTime;
                previousContent = taf[`change_${j}_content_all`] || '';
                previousWarning = taf[`change_${j}_warning`] || 'N';
                break;
            }
            // 如果时间校验不通过，继续向前查找
        }
    }

    // 如果没有找到前面的变化组，使用主体预报
    if (!previousEndTime) {
        previousEndTime = taf.subject_validity_period_end;
        previousContent = taf.subject_content || '';
        previousWarning = taf.subject_warning || 'N';
    }

    if (!previousEndTime) {
        return '';
    }

    // 获取BECMG变化组的信息
    const becmgContent = taf[`change_${becmgIndex}_content_all`] || '';
    const becmgWarning = taf[`change_${becmgIndex}_warning`] || 'N';

    // 计算过渡条带的时间范围
    const transitionStartTime = previousEndTime;
    const transitionEndTime = becmgStartTime;

    const currentTime = getCurrentTime();
    const position = calculateGanttPosition(transitionStartTime, transitionEndTime, currentTime);

    // 如果甘特图宽度太小或者超出范围，则不显示
    if (position.width <= 0 || position.left >= 100 || position.left + position.width <= 0) {
        return '';
    }

    // 获取告警颜色（保持与现有告警条带相同的透明度）
    const previousColor = getAlertColor(previousWarning);
    const becmgColor = getAlertColor(becmgWarning);

    // 设置背景样式
    let backgroundStyle;
    if (previousWarning === becmgWarning) {
        // 颜色相同，使用单一颜色
        backgroundStyle = `background-color: ${previousColor};`;
    } else {
        // 颜色不同，使用渐变色
        backgroundStyle = `background: linear-gradient(to right, ${previousColor}, ${becmgColor});`;
    }

    // 创建悬浮提示内容
    const tooltipContent = `${previousContent}➤➤${becmgContent}`;

    return `
        <div class="gantt-bar gantt-becmg-transition" 
             style="position: absolute; 
                    left: ${position.left}%; 
                    width: ${position.width}%; 
                    ${backgroundStyle}
                    color: white; 
                    z-index: 2;
                    display: flex;
                    align-items: center;
                    justify-content: center;"
             title="${tooltipContent}">
            ➤➤
        </div>
    `;
}

// 计算甘特图条带的位置
function calculateGanttPosition(startTime, endTime, currentTime) {
    // 将时间字符串转换为相对当前时间的小时偏移
    const startOffset = calculateTimeOffset(startTime, currentTime);
    const endOffset = calculateTimeOffset(endTime, currentTime);

    // 使用原始偏移量，不再额外偏移
    const adjustedStartOffset = startOffset;
    const adjustedEndOffset = endOffset;

    // 根据项目规划7.3要求：如果开始时间早于当前时间，从当前时间开始显示
    const clampedStart = Math.max(0, Math.min(currentTimeRange - 1, adjustedStartOffset));
    // 结束时间应该可以到达最后一个格子，但不超过
    const clampedEnd = Math.max(clampedStart, Math.min(currentTimeRange, adjustedEndOffset));

    // 如果甘特图宽度为0或负数，不显示
    if (clampedEnd <= clampedStart) {
        return { left: 0, width: 0 };
    }

    // 计算在动态格子数中的位置百分比
    let adjustedStart = clampedStart;
    let adjustedEnd = clampedEnd;

    // 如果原始开始时间早于当前时间，条带从时间轴起始位置开始
    if (startOffset < 0) {
        adjustedStart = 0; // 从第一个格子的左边界开始
        adjustedEnd = clampedEnd;
    }

    const left = (adjustedStart / currentTimeRange) * 100;
    const width = ((adjustedEnd - adjustedStart) / currentTimeRange) * 100;

    return { left, width };
}

/**
 * 统一的DDHH时间偏移计算函数
 * 
 * 专门针对航空气象数据的时间偏移计算，智能处理跨日和跨月情况
 * 支持5天内数据的完全覆盖，包括月末到月初的跨月场景
 * 
 * 设计原理：
 * - 航空气象数据时间跨度通常在5天内
 * - DDHH格式只包含日期和小时，不包含月份信息
 * - 通过日期差值判断是否跨月：差值>15天认为是跨月
 * - 15天阈值为5天内数据提供充足的安全边界
 * - 使用纯数学计算，避免复杂的Date对象操作
 * 
 * @param {string} timeStr - DDHH格式时间字符串（如'0606'表示6日06时）
 * @param {Date} currentTime - 当前时间对象
 * @returns {number|null} 相对当前时间的小时偏移，失败返回null
 * 
 * @example
 * // 同月计算
 * calculateDDHHOffset('1209', currentTime) // 返回相对小时偏移
 * 
 * @example
 * // 跨月计算  
 * calculateDDHHOffset('0209', currentTime) // 智能处理跨月情况
 */
function calculateDDHHOffset(timeStr, currentTime) {
    if (!timeStr || timeStr.length !== 4) {
        return null;
    }

    // 解析DDHH格式：前两位是日期，后两位是小时
    const targetDay = parseInt(timeStr.substr(0, 2));
    const targetHour = parseInt(timeStr.substr(2, 2));
    const currentDay = currentTime.getUTCDate();
    const currentHour = currentTime.getUTCHours();

    // 核心算法：基于日期差值判断是否跨月
    // 计算两个日期的绝对差值
    const dayDiff = Math.abs(targetDay - currentDay);

    // 跨月判断逻辑：日期差值大于15天认为是跨月情况
    // 原理：5天内的数据不可能有超过15天的日期差，除非跨月
    // 15天阈值为5天内数据提供充足安全边界
    if (dayDiff > 15) {
        // 跨月情况处理：较小的日期数字对应下个月
        if (targetDay < currentDay) {
            // target是下个月：计算当前月剩余天数 + target天数
            const currentMonthDays = new Date(Date.UTC(currentTime.getUTCFullYear(), currentTime.getUTCMonth() + 1, 0)).getUTCDate();
            const remainingDays = currentMonthDays - currentDay;
            return (remainingDays + targetDay) * 24 + (targetHour - currentHour);
        } else {
            // target是上个月：计算负偏移
            const prevMonthDays = new Date(Date.UTC(currentTime.getUTCFullYear(), currentTime.getUTCMonth(), 0)).getUTCDate();
            const targetToMonthEnd = prevMonthDays - targetDay;
            return -(targetToMonthEnd + currentDay) * 24 + (targetHour - currentHour);
        }
    } else {
        // 同月情况处理：直接按日期差计算
        return (targetDay - currentDay) * 24 + (targetHour - currentHour);
    }
}

// 计算时间偏移量（相对当前时间的小时数）
function calculateTimeOffset(timeStr, currentTime) {
    // 使用统一的DDHH偏移计算函数
    const offset = calculateDDHHOffset(timeStr, currentTime);

    // 保持原有的返回值格式：失败返回-1，成功返回向上取整的小时数
    return offset === null ? -1 : Math.ceil(offset);
}

// 获取默认背景色（无告警时统一使用浅灰色，0.8透明度）
function getDefaultBackgroundColor(type) {
    // 按照4色规则，无告警统一使用浅灰色，0.8透明度
    return 'rgba(149, 165, 166, 0.8)'; // 浅灰色 - 无告警
}

// 创建温度指示器
function createTemperatureIndicators(taf) {
    let indicators = '';
    const currentTime = getCurrentTime();

    // 检查各个温度时间点
    const tempTimes = [
        { time: taf.subject_max_temp1_time, warning: taf.subject_max_temp1_warning, value: taf.subject_max_temp1, type: '最高温度' },
        { time: taf.subject_max_temp2_time, warning: taf.subject_max_temp2_warning, value: taf.subject_max_temp2, type: '最高温度' },
        { time: taf.subject_min_temp1_time, warning: taf.subject_min_temp1_warning, value: taf.subject_min_temp1, type: '最低温度' },
        { time: taf.subject_min_temp2_time, warning: taf.subject_min_temp2_warning, value: taf.subject_min_temp2, type: '最低温度' }
    ];

    tempTimes.forEach(temp => {
        if (temp.time && temp.value) {  // 只要有时间和温度值就显示
            const offset = calculateTimeOffset(temp.time, currentTime);
            if (offset >= 0 && offset < currentTimeRange) {
                const left = (offset / currentTimeRange) * 100; // 显示在边界线上

                // 根据告警级别确定颜色，无告警或N时使用浅灰色（0.8透明度）
                let triangleColor;
                if (temp.warning && temp.warning !== 'N') {
                    triangleColor = getAlertColor(temp.warning);
                } else {
                    triangleColor = 'rgba(149, 165, 166, 0.8)';  // 浅灰色 - 无告警，0.8透明度
                }

                indicators += `
                    <div class="temperature-triangle" 
                         style="position: absolute; 
                                left: ${left}%; 
                                transform: translateX(-50%); 
                                width: 0; 
                                height: 0; 
                                border-left: 6px solid transparent; 
                                border-right: 6px solid transparent; 
                                border-bottom: 12px solid ${triangleColor}; 
                                z-index: 10; 
                                cursor: pointer; 
                                filter: drop-shadow(0 0 1px white) drop-shadow(0 0 1px white) drop-shadow(0 0 1px white);" 
                         title="${temp.type}: ${temp.value}°C">
                    </div>
                `;
            }
        }
    });

    return indicators;
}

// 原isTimeInRange函数已不再需要，因为我们使用甘特图条带方式

// 获取实况区域样式
function getWeatherInfoStyle(metar) {
    // 边框颜色统一，不再根据告警变色
    return '';
}

// 创建天气信息
function createWeatherInfo(metar) {
    if (!metar) {
        return '<div class="no-data">无有效天气数据</div>';
    }

    const rows = [];

    // 第一行：类型+时间（靠左显示）
    const timeDisplay = formatMetarTime(metar.metar_observation_time);
    const metarType = metar.metar_type || '';
    const alertColor = getAlertColor(metar.metar_warning || 'N');

    // 添加冰块符号逻辑
    const iceFlag = metar.metar_ice_flag;
    const iceSymbol = (iceFlag === 'Y') ? '&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;🧊' : '';

    rows.push(`<div class="weather-row" style="text-align: left;">
        <span style="color: black;">${metarType}&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;${timeDisplay}${iceSymbol}</span>
    </div>`);

    // 第二行：风|温（靠左显示）
    const windTempContent = buildWindTempContent(metar);
    if (windTempContent) {
        rows.push(`<div class="weather-row" style="text-align: left;">
            <span class="weather-label" style="color: black;">风|温：</span>
            <span class="weather-content">${windTempContent}</span>
        </div>`);
    }

    // 第三行：能|视（靠左显示）
    const visRvrContent = buildVisibilityRvrContent(metar);
    if (visRvrContent) {
        rows.push(`<div class="weather-row" style="text-align: left;">
            <span class="weather-label" style="color: black;">能|视：</span>
            <span class="weather-content">${visRvrContent}</span>
        </div>`);
    }

    // 第四行：天气（靠左显示）
    if (metar.metar_weather) {
        const weatherWarning = metar.metar_weather_warning || 'N';
        const weatherColor = weatherWarning !== 'N' ? getAlertColor(weatherWarning) : 'black';
        const weatherStyle = weatherWarning !== 'N' ? `color: ${weatherColor}; font-weight: bold;` : 'color: black;';
        const weatherContent = metar.metar_weather;
        rows.push(`<div class="weather-row" style="text-align: left;">
            <span class="weather-label" style="color: black;">天气：</span>
            <span class="weather-content" style="${weatherStyle}">${weatherContent}</span>
        </div>`);
    }

    // 第五行：云况（靠左显示）
    if (metar.metar_cloud) {
        const cloudWarning = metar.metar_cloud_warning || 'N';
        const cloudColor = cloudWarning !== 'N' ? getAlertColor(cloudWarning) : 'black';
        const cloudStyle = cloudWarning !== 'N' ? `color: ${cloudColor}; font-weight: bold;` : 'color: black;';
        const cloudContent = metar.metar_cloud;
        rows.push(`<div class="weather-row" style="text-align: left;">
            <span class="weather-label" style="color: black;">云况：</span>
            <span class="weather-content" style="${cloudStyle}">${cloudContent}</span>
        </div>`);
    }

    // 第六行：趋势（靠左显示）
    if (metar.metar_change_trend && metar.metar_change_trend.trim()) {
        const trendWarning = metar.metar_change_trend_warning || 'N';
        const trendColor = trendWarning !== 'N' ? getAlertColor(trendWarning) : 'black';
        const trendStyle = trendWarning !== 'N' ? `color: ${trendColor}; font-weight: bold;` : 'color: black;';
        const trendContent = metar.metar_change_trend;
        rows.push(`<div class="weather-row" style="text-align: left;">
            <span class="weather-label" style="color: black;">趋势：</span>
            <span class="weather-content" style="${trendStyle}">${trendContent}</span>
        </div>`);
    }

    return `<div class="weather-info-container" style="position: relative;" title="${metar.metar_content || ''}">
        ${rows.join('')}
        <div style="position: absolute; top: -30px; right: -10px; color: ${alertColor}; font-size: 40px; z-index: 10;">◥</div>
    </div>`;
}

// 格式化METAR时间显示（遵从 window.displayTimezone 时区模式）
function formatMetarTime(timeValue) {
    if (!timeValue) return '';

    const timeStr = timeValue.toString();

    try {
        // 纯数字时间戳
        if (/^\d+$/.test(timeStr)) {
            return formatTimestampByMode(parseInt(timeStr));
        }

        // YYYY-MM-DD HH:mm:ss 格式（数据库存储的UTC时间，加Z解析）
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(timeStr)) {
            return formatTimestampByMode(new Date(timeStr + 'Z').getTime());
        }

        // ISO格式
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(timeStr)) {
            return formatTimestampByMode(new Date(timeStr).getTime());
        }

        return timeStr;
    } catch (e) {
        return timeStr;
    }
}

// 构建风温组合内容
// 构建风和温度内容
function buildWindTempContent(metar) {
    const parts = [];

    // 风组内容
    if (metar.metar_wind_direction && metar.metar_wind_speed_original) {
        const windWarning = metar.metar_wind_warning || 'N';
        const windColor = windWarning !== 'N' ? getAlertColor(windWarning) : 'black';
        const windStyle = windWarning !== 'N' ? `color: ${windColor}; font-weight: bold;` : 'color: black;';
        const windContent = `${metar.metar_wind_direction}${metar.metar_wind_speed_original}`;
        parts.push(`<span style="${windStyle}">${windContent}</span>`);
    }

    // 温度内容
    if (metar.metar_temperature !== null && metar.metar_temperature !== undefined) {
        const tempWarning = metar.metar_temperature_warning || 'N';
        const tempColor = tempWarning !== 'N' ? getAlertColor(tempWarning) : 'black';
        const tempStyle = tempWarning !== 'N' ? `color: ${tempColor}; font-weight: bold;` : 'color: black;';

        // 构建温度/露点显示格式
        let tempContent = `<span style="${tempStyle}">${metar.metar_temperature}</span>`;
        if (metar.metar_dew_point !== null && metar.metar_dew_point !== undefined) {
            tempContent += `<span>/${metar.metar_dew_point}°C</span>`;
        } else {
            tempContent += `<span>°C</span>`;
        }

        parts.push(tempContent);
    }

    return parts.length > 0 ? parts.join(' | ') : null;
}


// 构建能见度和跑道视程组合内容
function buildVisibilityRvrContent(metar) {
    const parts = [];

    // 能见度内容
    if (metar.metar_visibility_original) {
        const visWarning = metar.metar_visibility_warning || 'N';
        const visColor = visWarning !== 'N' ? getAlertColor(visWarning) : 'black';
        const visStyle = visWarning !== 'N' ? `color: ${visColor}; font-weight: bold;` : 'color: black;';
        parts.push(`<span style="${visStyle}">${metar.metar_visibility_original}</span>`);
    }

    // 跑道视程内容
    if (metar.metar_rvr_dsc) {
        const rvrWarning = metar.metar_rvr_warning || 'N';
        const rvrColor = rvrWarning !== 'N' ? getAlertColor(rvrWarning) : 'black';
        const rvrStyle = rvrWarning !== 'N' ? `color: ${rvrColor}; font-weight: bold;` : 'color: black;';
        parts.push(`<span style="${rvrStyle}">${metar.metar_rvr_dsc}</span>`);
    }

    return parts.length > 0 ? parts.join(' | ') : null;
}




// 创建航班时间轴 - 使用新的显示方式
function createFlightTimeline(flightData, tafData = null, metarData = null, airport = null) {
    const timeSlots = flightData.time_slots || [];
    let flightInfos = [];

    // 生成航班信息显示
    for (let i = 0; i < currentTimeRange; i++) {
        const flightInfo = timeSlots[i] || '';

        if (flightInfo && flightInfo.trim() !== '' && flightInfo.trim() !== 'None' && flightInfo.trim() !== 'null') {
            // 计算位置（与竖线对应）
            const leftPercent = (i / currentTimeRange) * 100;
            const widthPercent = (1 / currentTimeRange) * 100;

            // 计算告警级别
            const alertLevel = calculateFlightAlertLevel(i, tafData, metarData, flightData, airport);
            const alertColor = alertLevel ? getAlertColor(alertLevel) : '#333';

            flightInfos.push(`
                <div class="flight-info-item" style="
                    position: absolute;
                    left: ${leftPercent}%;
                    width: ${widthPercent}%;
                    height: 100%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 11px;
                    font-weight: bold;
                    color: ${alertColor};
                    z-index: 2;
                    pointer-events: none;
                ">${flightInfo}</div>
            `);
        }
    }

    return flightInfos.join('');
}

// 执行搜索
function performSearch(searchValue) {
    showLoading();

    // 分割搜索值（支持多个机场代码）
    const airportCodes = searchValue.toUpperCase().split(/[\s,，]+/).filter(code => code.length > 0);

    const apiUrl = `/${currentTimeMode}/api/search/airports/`;

    fetch(apiUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            airport_codes: airportCodes
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showSearchResults(data.data.airports);
            } else {
                showError('搜索失败：' + data.error);
            }
        })
        .catch(error => {
            console.error('搜索失败:', error);
            showError('搜索失败，请重试');
        })
        .finally(() => {
            hideLoading();
        });
}

// 显示搜索结果
function showSearchResults(airports) {
    const searchResults = document.getElementById('search-results');

    if (!airports || airports.length === 0) {
        searchResults.innerHTML = '<div class="empty-state"><div class="empty-state-message">未找到相关机场</div></div>';
        showModal('search-modal');
        return;
    }

    const resultsHTML = airports.map(airport => `
        <div class="search-result-item">
            <div class="search-result-header">
                ${airport.airport_4code} ${airport.airport_name}
            </div>
            <div class="search-result-info">
                <span>区域: ${airport.region || '未知'}</span>
                <span>坐标: ${airport.latitude || 'N/A'}, ${airport.longitude || 'N/A'}</span>
            </div>
            <div class="search-result-content">
                <h4>实况天气 (METAR)</h4>
                ${airport.metar_data && airport.metar_data.length > 0 ?
            airport.metar_data.map(metar => `
                        <div class="original-content">
                            <div style="margin-bottom: 8px;">
                                ${createWeatherInfo(metar)}
                            </div>
                            <div style="font-size: 10px; color: #666; margin-top: 8px;">
                                <strong>原文:</strong> ${metar.metar_content || 'N/A'}
                            </div>
                        </div>
                    `).join('') :
            '<div class="no-data">无METAR数据</div>'
        }
                
                <h4>预报天气 (TAF)</h4>
                ${airport.taf_data && airport.taf_data.length > 0 ?
            airport.taf_data.map(taf => `
                        <div class="original-content">
                            <div style="margin-bottom: 8px;">
                                时间: ${taf.taf_observation_time ? new Date(taf.taf_observation_time).toLocaleString('zh-CN') : 'N/A'}<br>
                                有效期: ${taf.whole_validity_period || 'N/A'}<br>
                                类型: ${taf.taf_type || 'N/A'}
                            </div>
                            <div style="font-size: 10px; color: #666; margin-top: 8px;">
                                <strong>原文:</strong> ${taf.taf_content || 'N/A'}
                            </div>
                        </div>
                    `).join('') :
            '<div class="no-data">无TAF数据</div>'
        }
                
                <h4>航班信息</h4>
                ${airport.flight_data ? `
                    <div class="original-content">
                        是否有航班: ${airport.flight_data.has_flight ? '是' : '否'}<br>
                        总航班数: ${airport.flight_data.total_flights || 0}<br>
                        出发航班: ${airport.flight_data.departure_flights || 0}<br>
                        到达航班: ${airport.flight_data.arrival_flights || 0}<br>
                        更新时间: ${new Date(airport.flight_data.last_updated).toLocaleString('zh-CN')}
                    </div>
                ` : '<div class="no-data">无航班数据</div>'}
            </div>
        </div>
    `).join('');

    searchResults.innerHTML = resultsHTML;
    showModal('search-modal');
}

// 显示机场详细信息
// 刷新数据
function refreshData() {
    refreshManualData(); // 调用新的手动刷新函数
}

// 加载承运人数据
function loadCarrierData() {
    if (window.carriers && window.carriers.length > 0) {
        currentCarriers = window.carriers;
        updateCarrierDisplay();
    }
}

// 显示弹窗
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }
}

// 隐藏弹窗
function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
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
function getAlertColor(level) {
    const colors = {
        'R': 'rgba(231, 76, 60, 0.8)',   // 红色告警，0.8透明度
        'Y': 'rgba(243, 156, 18, 0.8)',  // 黄色告警，0.8透明度
        'G': 'rgba(39, 174, 96, 0.8)',   // 绿色告警，0.8透明度
        'N': 'rgba(149, 165, 166, 0.8)'  // 无告警 - 浅灰色，0.8透明度
    };
    return colors[level] || 'rgba(149, 165, 166, 0.8)';
}

// 获取当前选中的告警裕度值
function getSelectedAlertMargin() {
    return filters.margin !== undefined ? filters.margin : 2;
}





// 计算航班告警级别 - 使用后端预计算结果
function calculateFlightAlertLevel(timeSlotIndex, tafData, metarData, flightData, airport) {
    try {
        // 获取当前选中的告警裕度
        const currentMargin = getSelectedAlertMargin();

        // 从预计算结果中获取对应margin和时段的告警等级
        if (airport && airport.computed_alerts) {
            const marginKey = `margin_${currentMargin}`;
            const marginResults = airport.computed_alerts[marginKey];

            if (marginResults && marginResults.time_slots && timeSlotIndex < marginResults.time_slots.length) {
                return marginResults.time_slots[timeSlotIndex];
            }
        }

        // 如果预计算结果不存在，返回默认值
        return 'N';

    } catch (error) {
        console.error('获取时段告警等级失败:', error);
        return 'N';
    }
}

// 辅助函数：从告警级别列表中获取最高级别
function getMaxAlertFromList(alerts) {
    if (!alerts || alerts.length === 0) return 'N';

    if (alerts.includes('R')) return 'R';
    if (alerts.includes('Y')) return 'Y';
    if (alerts.includes('G')) return 'G';
    return 'N';
}

// 1. 实况告警判断
function calculateMetarAlert(timeSlotIndex, margin, metarData, currentTime) {
    if (!metarData || metarData.length === 0) {
        return 'N';
    }

    // 实况有效时间范围：time_0 到 time_[margin]
    const startIndex = 0;
    const endIndex = margin;

    // 检查当前航班时段是否在实况影响范围内
    if (timeSlotIndex >= startIndex && timeSlotIndex <= endIndex) {
        const latestMetar = metarData[0];
        return latestMetar.metar_warning || 'N';
    }

    return 'N';
}




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
        showTokenInvalidError();
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
            updateTypes: updateTypes
        })
    })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success) {
                console.log('参数化更新成功:', updateTypes);

                // 获取解析结果
                const parsers = data.data.parsers || {};

                // 更新每个数据类型的状态和时间
                updateTypes.forEach(dataType => {
                    const parseResult = parsers[dataType];
                    let parsingSuccess = false; // 默认为失败

                    if (parseResult) {
                        parsingSuccess = parseResult.success;
                        console.log(`${dataType}解析器结果:`, parseResult);
                    } else {
                        console.warn(`⚠️ 参数化更新中未找到${dataType}的解析结果`);
                    }

                    // 更新数据时间和状态
                    updateDataTime(dataType, parsingSuccess);
                    updateSingleParsingStatus(dataType, parsingSuccess);
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
                    const needResetRegions = sessionStorage.getItem('fmsa_reset_regions');
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
                showTokenInvalidError();
                stopAllAutoRefresh();
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

                let parsingSuccess = false; // 默认为失败

                if (parseResult) {
                    parsingSuccess = parseResult.success;
                    console.log(`${dataType}解析器结果:`, parseResult);
                } else {
                    console.warn(`⚠️ 未找到${dataType}的解析结果`);
                }

                // 更新数据时间和状态
                updateDataTime(dataType, parsingSuccess);
                updateSingleParsingStatus(dataType, parsingSuccess);

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

                // 如果包含航班数据更新，需要重新显示
                if (dataType === 'flight') {
                    updateAirportDisplay();
                } else {
                    // 只更新告警数据
                    applyFilters();
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
                showTokenInvalidError();
                stopAllAutoRefresh();
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

                let parsingSuccess = false; // 默认为失败

                if (parseResult) {
                    parsingSuccess = parseResult.success;
                    console.log(`${dataType}解析器重试结果:`, parseResult);
                } else {
                    console.warn(`⚠️ 重试时未找到${dataType}的解析结果`);
                }

                // 更新数据时间和状态
                updateDataTime(dataType, parsingSuccess);
                updateSingleParsingStatus(dataType, parsingSuccess);

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

                // 如果包含航班数据更新，需要重新显示
                if (dataType === 'flight') {
                    updateAirportDisplay();
                } else {
                    // 只更新告警数据
                    applyFilters();
                }

                updateAllAirportGrids();
            } else {
                console.error(`${dataType}重试数据获取失败:`, data.error);
            }
        })
        .catch(error => {
            if (error.message === 'TOKEN_INVALID') {
                showTokenInvalidError();
                stopAllAutoRefresh();
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

        updateAirportDisplay();
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
                // 用后端解析状态 + 本次轮询成功 联合更新左上角状态指示器
                updateStatusFromPollResult(data.data.parsing_status || {}, true);
            }
        })
        .catch(error => {
            if (error.message === 'TOKEN_INVALID') {
                showTokenInvalidError();
                stopAllAutoRefresh();
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
                    const pad = n => String(n).padStart(2, '0');
                    // 遵从页面时区设置
                    let displayStr;
                    if (window.displayTimezone === 'UTC') {
                        displayStr = `${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}:${pad(t.getUTCSeconds())}`;
                    } else {
                        displayStr = `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
                    }
                    updateStatusTimeDisplay(dataType, displayStr);
                } catch (_) {
                    updateStatusTimeDisplay(dataType, '--:--:--');
                }
            } else {
                updateStatusTimeDisplay(dataType, '--:--:--');
            }
        } else if (backendFailed) {
            // 后端解析失败 → 红色
            indicatorEl.textContent = '解析失败';
            indicatorEl.classList.add('status-error');
            updateStatusTimeDisplay(dataType, '--:--:--');
        } else {
            // 尚未运行（null）→ 灰色等待
            indicatorEl.textContent = '等待解析';
            indicatorEl.classList.add('status-pending');
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
function calculateHorizontalWidth() {
    const minWidth = 1680 - 80 - 200; // 1400px
    const contentWidth = document.querySelector('.forecast-timeline')?.scrollWidth || minWidth;
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
    // 移除旧的竖线
    airportElement.querySelectorAll('.grid-vertical-line').forEach(line => line.remove());

    const positions = calculateVerticalLinePositions(horizontalWidth, timeSlots);
    const midnightIndexes = findMidnightBoldLineIndexes(getCurrentTime());

    // 检测是否有airport-info元素，如果没有说明是详情页布局
    const hasAirportInfo = airportElement.querySelector('.airport-info') !== null;
    const leftOffset = hasAirportInfo ? 280 : 200; // 有airport-info时280px，否则200px

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

// 创建无TAF数据覆盖层
function createNoTafDataOverlay(airportElement, airportHeight, horizontalWidth) {
    // 移除旧的覆盖层
    const existingOverlay = airportElement.querySelector('.no-taf-data-overlay');
    if (existingOverlay) {
        existingOverlay.remove();
    }

    // 检测是否有airport-info元素，如果没有说明是详情页布局
    const hasAirportInfo = airportElement.querySelector('.airport-info') !== null;
    const leftOffset = hasAirportInfo ? 280 : 200; // 有airport-info时280px，否则200px

    const overlay = document.createElement('div');
    overlay.className = 'no-taf-data-overlay';
    overlay.style.cssText = `
        position: absolute;
        top: 0;
        left: ${leftOffset}px;
        width: ${horizontalWidth}px;
        height: ${airportHeight}px;
        background: #f8f9fa;
        z-index: 10;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        color: #666;
        border: 1px solid #ddd;
        box-sizing: border-box;
    `;
    overlay.textContent = '没有有效的TAF数据';

    return overlay;
}

// 更新机场网格
function updateAirportGrid(airportElement) {
    const airportHeight = airportElement.scrollHeight;
    const horizontalWidth = calculateHorizontalWidth();
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
        const isInDetailModal = airportRow.closest('#airport-detail-main') !== null;
        if (isInDetailModal) {
            updateAirportGridForModal(airportRow);
        } else {
            updateAirportGrid(airportRow);
        }
    });
}

// 更新航班数据状态警告
function updateFlightStatusWarning(flightStatus) {
    if (!flightStatus) return;

    let warningElement = document.getElementById('flight-status-warning');

    if (!flightStatus.is_available) {
        // 需要显示警告
        if (!warningElement) {
            // 创建警告元素
            warningElement = document.createElement('div');
            warningElement.id = 'flight-status-warning';
            warningElement.innerHTML = '⚠';
            warningElement.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 80px;
                height: 80px;
                background-color: #ffc107;
                color: #212529;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 40px;
                font-weight: bold;
                cursor: pointer;
                z-index: 1000;
                box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                transition: transform 0.2s;
            `;

            // 添加悬浮效果
            warningElement.addEventListener('mouseenter', function () {
                this.style.transform = 'scale(1.1)';
            });

            warningElement.addEventListener('mouseleave', function () {
                this.style.transform = 'scale(1)';
            });

            document.body.appendChild(warningElement);
        }

        // 设置提示文字 - 使用数据库中现有航班数据的创建时间
        if (airportData && airportData.length > 0 && airportData[0].flight_data && airportData[0].flight_data.last_updated) {
            const lastUpdated = new Date(airportData[0].flight_data.last_updated);
            const timeString = lastUpdated.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
            warningElement.title = `未获取到最新航班数据，当前显示的航班数据为${timeString}获取`;
        } else {
            warningElement.title = `未获取到最新航班数据，当前无可用的航班数据`;
        }

    } else {
        // 不需要显示警告，移除元素
        if (warningElement) {
            warningElement.remove();
        }
    }
}

// 弹窗使用相同的网格更新函数，CSS缩放会自动处理

// 监听机场高度变化
function observeAirportHeightChanges() {
    const observer = new ResizeObserver(entries => {
        entries.forEach(entry => {
            if (entry.target.classList.contains('airport-row')) {
                const isInDetailPage = entry.target.closest('#airport-detail-main') !== null;
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

    // 复用主页的时间轴生成逻辑
    const currentTime = getCurrentTime();

    let beijingCells = '';
    let utcCells = '';

    for (let i = 0; i < currentTimeRange; i++) {
        let beijingHour, utcHour;

        if (currentTimeMode === 'test') {
            // test模式：currentTime是UTC时间
            const utcTime = new Date(currentTime.getTime() + i * 60 * 60 * 1000);
            utcHour = utcTime.getUTCHours().toString().padStart(2, '0');

            // 北京时间（UTC+8）
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

    // 等待DOM渲染和缩放完成后应用网格线
    setTimeout(() => {
        const airportRow = detailMain.querySelector('.airport-row');
        if (airportRow) {
            updateAirportGridForModal(airportRow);
        }
    }, 150);
}

// 弹窗专用网格更新函数（考虑85%缩放）
function updateAirportGridForModal(airportElement) {
    const airportHeight = airportElement.scrollHeight;

    // 使用与主页相同的方法：获取原始宽度
    const forecastTimeline = airportElement.querySelector('.forecast-timeline');
    let horizontalWidth;

    if (forecastTimeline) {
        horizontalWidth = forecastTimeline.scrollWidth;
    } else {
        horizontalWidth = calculateHorizontalWidth();
    }

    const timeSlots = currentTimeRange;
    const hasAirportInfo = airportElement.querySelector('.airport-info') !== null;
    const leftOffset = hasAirportInfo ? 280 : 200;

    // 移除旧线
    airportElement.querySelectorAll('.grid-vertical-line, .grid-horizontal-line').forEach(line => line.remove());

    // 创建竖线 - 使用原始宽度平分
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
            background-color: ${isMidnightLine ? '#666' : '#ddd'};
            z-index: 0;
            pointer-events: none;
        `;

        if (isMidnightLine) {
            line.classList.add('utc-00-line');
        }
        airportElement.appendChild(line);
    });

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
            background-color: #ddd;
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
            background: #f8f9fa;
            z-index: 10;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            color: #666;
            border: 1px solid #ddd;
            box-sizing: border-box;
        `;
        overlay.textContent = '没有有效的TAF数据';
        tafRowContainer.appendChild(overlay);
    }
}

// 注意：原generateSingleAirportTimeline函数已删除，因为现在直接复用createAirportRow函数

// ============== 鉴权相关函数 ==============

// 初始化current模式的鉴权
function initCurrentModeAuth() {
    // 先检查localStorage中的token
    const savedToken = localStorage.getItem('fmsa_token');
    const savedUserCode = localStorage.getItem('fmsa_userCode');

    if (savedToken && savedUserCode) {
        // 如果有保存的token，直接使用
        currentToken = savedToken;
        currentUserCode = savedUserCode;
        showUserInfo();
        loadInitialData();
    } else {
        // 没有保存的token，显示登录界面
        showLoginModal();
    }
}



// 显示登录模态框
function showLoginModal() {
    const loginModal = document.getElementById('login-modal');
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
                    localStorage.setItem('fmsa_token', currentToken);
                    localStorage.setItem('fmsa_userCode', currentUserCode);

                    hideLoginModal();
                    showUserInfo();

                    // 重置token失效标志并重新启动自动刷新
                    window.tokenInvalidDetected = false;
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
    const userCodeSpan = document.getElementById('user-code');

    userCodeSpan.textContent = currentUserCode || '未知用户';
    userInfoSection.style.display = 'flex';
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

    // 清除localStorage
    localStorage.removeItem('fmsa_token');
    localStorage.removeItem('fmsa_userCode');

    hideUserInfo();
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
// 注意：弹窗相关代码已迁移到 popup_new.js 和 popup_common.js
// 以下仅保留必要的工具函数

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
// 旧弹窗代码已移除
// 新代码位于 popup_new.js 和 popup_common.js
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


