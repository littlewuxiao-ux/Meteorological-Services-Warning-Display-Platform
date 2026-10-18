// ============================================================
// main_taf.js — 预报（TAF）渲染相关函数
// 依赖 main.js 中的全局变量和工具函数：
//   currentTimeRange, currentTimeMode, getCurrentTime(),
//   getAlertColor(), isTimeBeforeOrEqual()
// ============================================================

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

/**
 * 甘特条带文本：中文模式下取明语翻译，其余视图仍用报文原文。
 * key 为 'SUBJECT' 或 '变化组类型|开始时次'，与 taf_elements 侧的键一致。
 */
function ganttBarContent(taf, key, raw) {
    const fallback = raw || '';
    if (window._viewMode !== 'plain') return fallback;
    if (typeof plainGanttText !== 'function') return fallback;
    return plainGanttText(taf, key) || fallback;
}

function ganttChangeKey(changeType, startTime) {
    const type = String(changeType || '').trim().toUpperCase();
    if (!type || !startTime) return '';
    return `${type}|${startTime}`;
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
                ganttBarContent(taf, 'SUBJECT', taf.subject_content),
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
                        ganttBarContent(taf, ganttChangeKey(changeType, startTime), content),
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
                        ganttBarContent(taf, ganttChangeKey(changeType, startTime), content),
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
                previousContent = ganttBarContent(
                    taf,
                    ganttChangeKey(prevType, taf[`change_${j}_validity_period_start`]),
                    taf[`change_${j}_content_all`]
                );
                previousWarning = taf[`change_${j}_warning`] || 'N';
                break;
            }
            // 如果时间校验不通过，继续向前查找
        }
    }

    // 如果没有找到前面的变化组，使用主体预报
    if (!previousEndTime) {
        previousEndTime = taf.subject_validity_period_end;
        previousContent = ganttBarContent(taf, 'SUBJECT', taf.subject_content);
        previousWarning = taf.subject_warning || 'N';
    }

    if (!previousEndTime) {
        return '';
    }

    // 获取BECMG变化组的信息
    const becmgContent = ganttBarContent(
        taf,
        ganttChangeKey(taf[`change_${becmgIndex}_type`], becmgStartTime),
        taf[`change_${becmgIndex}_content_all`]
    );
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
    // marks 模式：连续分钟轴，窗口左缘为 now（或展开后 now-2h）
    if (typeof isFlightMarksMode === 'function' && isFlightMarksMode()
        && typeof getMarksWindowStartMs === 'function'
        && typeof getMarksWindowDurationMs === 'function'
        && typeof calculateDDHHOffset === 'function') {
        const startOffsetH = calculateDDHHOffset(startTime, currentTime);
        const endOffsetH = calculateDDHHOffset(endTime, currentTime);
        if (startOffsetH === null || endOffsetH === null) {
            return { left: 0, width: 0 };
        }
        // DDHH 相对「当前时刻整点」的小时差；换算到绝对 ms 时用整点对齐的当前小时
        const aligned = new Date(currentTime.getTime());
        aligned.setMinutes(0, 0, 0);
        const startMs = aligned.getTime() + startOffsetH * 3600000;
        const endMs = aligned.getTime() + endOffsetH * 3600000;
        const winStart = getMarksWindowStartMs();
        const dur = getMarksWindowDurationMs();
        const left = ((startMs - winStart) / dur) * 100;
        const right = ((endMs - winStart) / dur) * 100;
        const clampedLeft = Math.max(0, Math.min(100, left));
        const clampedRight = Math.max(0, Math.min(100, right));
        if (clampedRight <= clampedLeft) return { left: 0, width: 0 };
        return { left: clampedLeft, width: clampedRight - clampedLeft };
    }

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
    const dayDiff = Math.abs(targetDay - currentDay);

    // 跨月判断逻辑：日期差值大于15天认为是跨月情况
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
    return `rgba(${getAlertColorSpec('N').rgb}, 0.8)`;
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
                let left;
                if (typeof isFlightMarksMode === 'function' && isFlightMarksMode()
                    && typeof calculateDDHHOffset === 'function'
                    && typeof getMarksWindowStartMs === 'function'
                    && typeof marksMsToLeftPercent === 'function') {
                    const offH = calculateDDHHOffset(temp.time, currentTime);
                    if (offH === null) return;
                    const aligned = new Date(currentTime.getTime());
                    aligned.setMinutes(0, 0, 0);
                    left = marksMsToLeftPercent(aligned.getTime() + offH * 3600000);
                    if (left < 0 || left > 100) return;
                } else {
                    left = (offset / currentTimeRange) * 100;
                }

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
