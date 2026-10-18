// ============================================================
// main_metar.js — 实况（METAR）渲染相关函数
// 依赖 main.js 中的全局变量和工具函数：
//   getAlertColor(), formatTimestampByMode()
// ============================================================

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

// 实况告警判断
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
