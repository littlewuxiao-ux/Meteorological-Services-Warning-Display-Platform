// ========================================
// NWP 温度辅助功能
// 依赖 main.js 中的全局变量/函数：
//   nwpEnabled, _nwpCache, currentTimeMode, currentTimeRange
//   getCurrentTimeForGantt(), getRequestHeaders(), handleFetchResponse()
// ========================================

/**
 * 更新 NWP 按钮的选中/未选中外观
 */
function updateNwpButtonState() {
    const btn = document.getElementById('nwp-btn');
    if (!btn) return;
    if (nwpEnabled) {
        btn.classList.add('selected');
    } else {
        btn.classList.remove('selected');
    }
}

/**
 * NWP 按钮点击处理：切换开关状态
 */
function handleNwpToggle() {
    if (typeof hasAccess === 'function' && !hasAccess('nwp', 'display')) return;

    nwpEnabled = !nwpEnabled;
    localStorage.setItem('fmsa_nwp_enabled', nwpEnabled.toString());
    updateNwpButtonState();

    if (nwpEnabled) {
        // 开启：立即触发 NWP 解析并渲染
        triggerNwpParsingAndRender();
    } else {
        // 关闭：清除所有覆盖层，清空缓存
        _nwpCache = {};
        clearAllNwpOverlays();
    }
}

/**
 * 主动触发 NWP 解析（POST trigger-parsing 含 nwp），然后获取缓存数据渲染
 */
function triggerNwpParsingAndRender() {
    if (!nwpEnabled) return;

    fetch(`/${currentTimeMode}/api/trigger-parsing/`, {
        method: 'POST',
        headers: getRequestHeaders(),
        body: JSON.stringify({ updateTypes: ['nwp'], nwpEnabled: true })
    })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success) {
                console.log('NWP 解析完成');
            } else {
                console.warn('NWP 解析失败:', data.error);
            }
            // 无论成功与否，都尝试获取缓存数据（可能有旧数据可显示）
            return fetchNwpDataAndRender();
        })
        .catch(err => {
            console.error('NWP 触发失败:', err);
        });
}

/**
 * 从后端获取 NWP 缓存数据并渲染覆盖层
 */
function fetchNwpDataAndRender() {
    if (!nwpEnabled) return Promise.resolve();

    return fetch(`/${currentTimeMode}/api/nwp-data/`, {
        headers: getRequestHeaders()
    })
        .then(handleFetchResponse)
        .then(data => {
            if (data.success && data.data) {
                _nwpCache = data.data;
                renderAllNwpOverlays(_nwpCache);
            }
        })
        .catch(err => {
            console.error('NWP 数据获取失败:', err);
        });
}

/**
 * 遍历所有机场行，为有 NWP 数据的机场渲染温度覆盖层
 * @param {Object} nwpData  { airport_code: [{time, temperature}, ...] }
 */
function renderAllNwpOverlays(nwpData) {
    if (!nwpData) return;

    // 先清除旧覆盖层，防止重复
    clearAllNwpOverlays();

    Object.entries(nwpData).forEach(([airportCode, temperatures]) => {
        if (!temperatures || temperatures.length === 0) return;

        // 找到对应机场行（通过机场代码文字匹配）
        const allAirportRows = document.querySelectorAll('.airport-row');
        let targetRow = null;
        allAirportRows.forEach(row => {
            const codeEl = row.querySelector('.airport-code');
            if (codeEl && codeEl.textContent.trim() === airportCode) {
                targetRow = row;
            }
        });

        if (!targetRow) return;

        const forecastTimeline = targetRow.querySelector('.forecast-timeline');
        if (!forecastTimeline) return;

        renderNwpOverlayForAirport(forecastTimeline, temperatures);
    });

    // 机场详情弹窗（若已打开）使用独立的行结构，不在 .airport-row 遍历范围内，需单独渲染
    if (typeof renderNwpOverlayForAirportDetail === 'function') {
        renderNwpOverlayForAirportDetail();
    }

    // 多机场搜索结果弹窗（若已打开）同样使用独立的行结构，需单独渲染
    if (typeof renderNwpOverlayForAirportSearch === 'function') {
        document.querySelectorAll('.airport-search-block').forEach(block => {
            const code = block.getAttribute('data-code');
            if (code) renderNwpOverlayForAirportSearch(code);
        });
    }
}

/**
 * 在单个机场的 forecast-timeline 内渲染 NWP 温度悬浮层
 *
 * 定位逻辑：
 *   - overlay 绝对定位于 forecast-timeline 的 top: calc(100%/3)（即 main 与 change 行的交界处）
 *   - translateY(-50%) 使其垂直居中于该交界线
 *   - 每个温度值的水平中心对齐对应小时刻度线：
 *       left = (hourOffset / currentTimeRange) * 100%，再 translateX(-50%)
 *   - hourOffset 使用 getCurrentTimeForGantt() 对齐到整点，与甘特条带定位保持一致
 *
 * @param {Element} forecastTimeline  .forecast-timeline 容器
 * @param {Array}   temperatures      [{time: unix_sec, temperature: float}, ...]
 */
function renderNwpOverlayForAirport(forecastTimeline, temperatures) {
    // 机场详情/搜索结果：深色主题白字，浅色主题黑字；主页始终黑字
    const inDetail = forecastTimeline.closest('.airport-detail-main') !== null;
    const lightDetail = typeof airportDetailThemeIsLight === 'function' && airportDetailThemeIsLight();
    const textColor = (inDetail && !lightDetail) ? '#fff' : '#000';

    const overlay = document.createElement('div');
    overlay.className = 'nwp-temperature-overlay';
    overlay.style.cssText = [
        'position: absolute',
        forecastTimeline.closest('.airport-row-plain') ? 'top: calc(100% * 4 / 9)' : 'top: calc(100% / 3)',
        'left: 0',
        'right: 0',
        'height: 0',           // 不占流布局空间
        'transform: translateY(-50%)',
        'z-index: 10',
        'pointer-events: none',
        'overflow: visible',
    ].join(';');

    // 使用整点对齐的时间作为时间轴起点，与甘特条带（calculateGanttPosition）保持一致
    const timelineStart = getCurrentTimeForGantt();

    temperatures.forEach(({ time, temperature }) => {
        // 计算相对时间轴起点的小时偏移
        const hourOffset = (time * 1000 - timelineStart.getTime()) / 3600000;

        // 超出当前时间范围则不显示
        if (hourOffset < 0 || hourOffset >= currentTimeRange) return;

        const leftPct = (hourOffset / currentTimeRange) * 100;
        const tempStr = temperature >= 0
            ? `${Math.round(temperature)}°C`
            : `${Math.round(temperature)}°C`;

        const span = document.createElement('span');
        span.className = 'nwp-temp-value';
        span.textContent = tempStr;
        span.style.cssText = [
            'position: absolute',
            `left: ${leftPct.toFixed(3)}%`,
            'transform: translateX(-50%)',
            'font-size: 10px',
            'font-weight: bold',
            `color: ${textColor}`,
            'white-space: nowrap',
            'line-height: 1',
            'background: transparent',
            'user-select: none',
        ].join(';');

        overlay.appendChild(span);
    });

    // 只在有内容时插入，且避免重复
    if (overlay.children.length > 0) {
        forecastTimeline.appendChild(overlay);
    }
}

/**
 * 清除页面上所有 NWP 温度覆盖层
 */
function clearAllNwpOverlays() {
    document.querySelectorAll('.nwp-temperature-overlay').forEach(el => el.remove());
}
