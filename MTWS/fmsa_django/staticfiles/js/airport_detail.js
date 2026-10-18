// ==================================
// 机场详情功能模块
// ==================================
// 依赖：main.js 中的 airportData, currentTimeMode, currentToken, currentUserCode

// 存储图表实例和状态
const airportDetailChart = {
  chart: null,
  hours: 3,
  selectedSeries: {},
  airportCode: null
};

// 显示机场详细信息
function showAirportDetail(airportCode) {
  // 直接从主页已加载的数据中查找机场信息
  const airport = airportData.find(a => a.airport_4code === airportCode);

  if (airport) {
    // 直接使用主页数据显示弹窗
    showAirportDetailModal(airport);
  } else {
    showError('未找到机场信息：' + airportCode);
  }
}

// 显示机场详细信息弹窗
function showAirportDetailModal(airportData) {
  // 主页数据是扁平结构，直接使用airportData
  const airport = airportData;

  // 第1行：机场代码和名称
  document.getElementById('airport-title').textContent =
    `${airport.airport_4code} ${airport.airport_name || ''}`;

  // 联系方式（使用主页已有的字段）
  document.getElementById('area-code').textContent = airport.area_code || 'N/A';
  document.getElementById('forecast-phone').textContent = airport.forecast_phone || 'N/A';
  document.getElementById('observation-phone').textContent = airport.observation_phone || 'N/A';
  document.getElementById('other-phone').textContent = airport.other_phone || 'N/A';

  // 加载机场额外信息（日出日落、跑道）
  loadAirportExtraInfo(airport.airport_4code);

  // 生成时间轴
  generateAirportDetailTimeline();

  // 显示机场数据
  displayAirportDetailData(airportData);

  // 初始化图表
  const defaultHours = window.chartDefaultHours || 3;
  initAirportDetailChart(airport.airport_4code, defaultHours);
  bindChartTimeSelectorForDetail(airport.airport_4code);

  // 加载实况和预报报文
  loadHistoryReports(airport.airport_4code);

  // 显示弹窗
  showModal('airport-detail-modal');
}

// 加载机场额外信息
function loadAirportExtraInfo(airportCode) {
  const headers = {};
  if (currentTimeMode === 'current' && currentToken) {
    headers['Authorization'] = `Bearer ${currentToken}`;
  }

  fetch(`/${currentTimeMode}/api/airport/${airportCode}/extra-info/`, {
    headers: headers
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // 更新日出日落时间：北京时间 + 世界时，格式 06:29BTC / 22:29UTC
        const sunriseBj = data.data.sunrise || '--:--';
        const sunsetBj = data.data.sunset || '--:--';
        const sunriseUtc = data.data.sunrise_utc != null ? data.data.sunrise_utc : '--:--';
        const sunsetUtc = data.data.sunset_utc != null ? data.data.sunset_utc : '--:--';
        document.getElementById('sunrise-time').textContent = `${sunriseBj}BTC / ${sunriseUtc}UTC`;
        document.getElementById('sunset-time').textContent = `${sunsetBj}BTC / ${sunsetUtc}UTC`;

        // 更新跑道信息
        const runways = data.data.runways || [];
        document.getElementById('runway-info').textContent = runways.length > 0 ? runways.join(', ') : '--';
      } else {
        console.error('加载机场额外信息失败:', data.error);
      }
    })
    .catch(error => {
      console.error('请求机场额外信息失败:', error);
    });
}

// 加载历史报文
function loadHistoryReports(airportCode) {
  const reportsContent = document.querySelector('.airport-reports-section .reports-content');

  if (reportsContent) reportsContent.innerHTML = '<div class="loading">加载中...</div>';

  const headers = {};
  if (currentTimeMode === 'current' && currentToken) {
    headers['Authorization'] = `Bearer ${currentToken}`;
    if (currentUserCode) {
      headers['X-User-Code'] = currentUserCode;
    }
  }
  if (currentTimeMode === 'test') {
    headers['X-User-Code'] = 'test';
  }

  fetch(`/${currentTimeMode}/api/airport/${airportCode}/history-reports/`, {
    headers: headers
  })
    .then(response => response.json())
    .then(data => {
      if (data.success && data.data) {
        displayHistoryReports(data.data);
      } else {
        console.error('加载历史报文失败:', data.error);
        if (reportsContent) reportsContent.innerHTML = '<div class="error">加载失败</div>';
      }
    })
    .catch(error => {
      console.error('请求历史报文失败:', error);
      if (reportsContent) reportsContent.innerHTML = '<div class="error">请求失败</div>';
    });
}

// 显示历史报文
function displayHistoryReports(data) {
  const reportsContent = document.querySelector('.airport-reports-section .reports-content');

  if (reportsContent) {
    let html = '';
    
    if (data.metar_reports && data.metar_reports.length > 0) {
      data.metar_reports.forEach(report => {
        html += `<div class="report-line"><span class="report-content">${report.content}</span></div>`;
      });
    }
    
    if (data.taf_reports && data.taf_reports.length > 0) {
      data.taf_reports.forEach(report => {
        html += `<div class="report-line"><span class="report-content">${report.content}</span></div>`;
      });
    }
    
    if (html === '') {
      html = '<div class="no-data">暂无报文</div>';
    }
    
    reportsContent.innerHTML = html;
  }
}

// ==================================
// 机场详情图表功能
// ==================================

// 初始化机场详情图表
function initAirportDetailChart(airportCode, hours) {
  const chartDom = document.getElementById('airport-detail-chart');
  if (!chartDom) return;

  // 销毁旧图表和监听器
  if (airportDetailChart.chart) {
    airportDetailChart.chart.dispose();
  }
  if (airportDetailChart.resizeObserver) {
    airportDetailChart.resizeObserver.disconnect();
  }

  // 创建新图表
  const chart = echarts.init(chartDom, 'dark');

  // 初始化状态
  airportDetailChart.chart = chart;
  airportDetailChart.hours = hours;
  airportDetailChart.selectedSeries = {};
  airportDetailChart.airportCode = airportCode;

  // 监听容器大小变化（仅在尺寸有效时 resize，避免主页面自动更新导致 reflow 时误用错误尺寸）
  const resizeObserver = new ResizeObserver(() => {
    const w = chartDom.getBoundingClientRect().width;
    const h = chartDom.getBoundingClientRect().height;
    if (w >= 50 && h >= 50) {
      chart.resize();
    }
  });
  resizeObserver.observe(chartDom);
  airportDetailChart.resizeObserver = resizeObserver;

  // 使用 setTimeout 确保容器已经完全渲染
  setTimeout(() => {
    chart.resize();
    updateAirportDetailChart(airportCode);
  }, 100);
}

// 更新机场详情图表数据
function updateAirportDetailChart(airportCode) {
  if (!airportDetailChart.chart) {
    console.log('机场详情图表未初始化');
    return;
  }

  // 更新前先按当前容器尺寸 resize，避免自动更新或 reflow 后网格未填满容器
  const chartDom = document.getElementById('airport-detail-chart');
  if (chartDom) {
    airportDetailChart.chart.resize();
  }

  console.log('开始更新机场详情图表:', airportCode);
  console.log('airportData 是否存在:', typeof airportData !== 'undefined');
  console.log('airportData 长度:', airportData ? airportData.length : 0);

  // 从主页数据中查找机场信息
  const airport = airportData.find(a => a.airport_4code === airportCode);
  if (!airport) {
    console.log('未找到机场数据:', airportCode);
    console.log('可用的机场代码:', airportData.map(a => a.airport_4code).slice(0, 10));
    return;
  }

  console.log('找到机场:', airport.airport_4code);
  console.log('机场对象的所有字段:', Object.keys(airport));

  const hours = airportDetailChart.hours;

  // 获取历史数据
  const metarData = airport.metar_data || [];

  console.log('metar_data 长度:', metarData.length);
  console.log('metar_data 示例（前3条）:', metarData.slice(0, 3));

  if (metarData.length === 0) {
    console.log('metar_data为空，尝试使用机场自身数据');
    // 如果没有 metar_data 数组，尝试使用机场自身的数据
    const tempData = {
      metar_observation_time: airport.metar_observation_time,
      metar_wind_speed_val: airport.metar_wind_speed_val,
      metar_gust_val: airport.metar_gust_val,
      metar_visibility_val: airport.metar_visibility_val,
      rvr_min_val: airport.rvr_min_val,
      metar_min_cloud_height: airport.metar_min_cloud_height,
      metar_temp_val: airport.metar_temp_val
    };

    // 检查是否有有效的观测时间
    if (tempData.metar_observation_time) {
      console.log('使用机场自身数据作为单点数据');
      // 将当前数据作为单个数据点使用
      metarData.push(tempData);
    } else {
      console.log('机场没有有效的观测数据');
      airportDetailChart.chart.setOption({
        title: {
          text: '暂无历史数据',
          subtext: '需要等待系统收集更多METAR数据',
          left: 'center',
          top: 'center',
          textStyle: { color: '#95a5a6', fontSize: 14 },
          subtextStyle: { color: '#7f8c8d', fontSize: 11 }
        }
      });
      return;
    }
  }

  console.log('检查 airport.metar_observation_time:', airport.metar_observation_time);

  // 获取最新时间，优先从 metar_data 中获取
  let latestTime;
  if (metarData.length > 0 && metarData[metarData.length - 1].metar_observation_time) {
    latestTime = Math.max(...metarData.map(item => item.metar_observation_time || 0));
  } else {
    latestTime = airport.metar_observation_time;
  }

  console.log('latestTime:', latestTime, new Date(latestTime));

  if (!latestTime) {
    console.error('无法获取有效的观测时间');
    airportDetailChart.chart.setOption({
      title: {
        text: '暂无历史数据',
        subtext: '无法获取有效的观测时间',
        left: 'center',
        top: 'center',
        textStyle: { color: '#95a5a6', fontSize: 14 },
        subtextStyle: { color: '#7f8c8d', fontSize: 11 }
      }
    });
    return;
  }

  const startTime = latestTime - hours * 3600000 - 3600000;

  console.log('时间范围:', new Date(startTime), '到', new Date(latestTime));
  console.log('latestTime:', latestTime, 'startTime:', startTime);

  // 过滤数据
  const filteredData = metarData.filter(item =>
    item.metar_observation_time > startTime && item.metar_observation_time <= latestTime
  ).sort((a, b) => a.metar_observation_time - b.metar_observation_time);

  console.log('过滤后数据条数:', filteredData.length);
  console.log('过滤后数据示例:', filteredData.slice(0, 2));

  if (filteredData.length === 0) {
    airportDetailChart.chart.setOption({
      title: {
        text: '暂无历史数据',
        subtext: '需要等待系统收集更多METAR数据',
        left: 'center',
        top: 'center',
        textStyle: { color: '#95a5a6', fontSize: 14 },
        subtextStyle: { color: '#7f8c8d', fontSize: 11 }
      }
    });
    return;
  }

  // 准备图表数据
  const timeData = filteredData.map(item => item.metar_observation_time);
  const windSpeedData = filteredData.map(item => item.metar_wind_speed_val);
  const gustData = filteredData.map(item => item.metar_gust_val);
  const visibilityData = filteredData.map(item => item.metar_visibility_val);
  const rvrData = filteredData.map(item => item.rvr_min_val);
  const cloudHeightData = filteredData.map(item => item.metar_min_cloud_height);
  const tempData = filteredData.map(item => item.metar_temp_val);

  // 如果没有保存的选择状态，使用默认值（默认显示所有要素）
  if (!airportDetailChart.selectedSeries || Object.keys(airportDetailChart.selectedSeries).length === 0) {
    airportDetailChart.selectedSeries = {
      '平均风': true,
      '阵风': true,
      '能见度': true,
      'RVR': true,
      '云底高': true,
      '气温': true
    };
  }

  // 判断各Y轴是否显示
  const showWindAxis = airportDetailChart.selectedSeries['平均风'] !== false || airportDetailChart.selectedSeries['阵风'] !== false;
  const showTempAxis = airportDetailChart.selectedSeries['气温'] !== false;
  const showVisAxis = airportDetailChart.selectedSeries['能见度'] !== false || airportDetailChart.selectedSeries['RVR'] !== false;
  const showCloudAxis = airportDetailChart.selectedSeries['云底高'] !== false;

  // 判断是否有任意要素被选中
  const hasAnySeriesSelected = showWindAxis || showTempAxis || showVisAxis || showCloudAxis;

  // 计算Y轴位置
  const windAxisOffset = (showWindAxis && showTempAxis) ? 15 : (showWindAxis ? 15 : 0);
  const tempAxisOffset = (showWindAxis && showTempAxis) ? 50 : (showTempAxis ? 15 : 0);
  const visAxisOffset = (showVisAxis && showCloudAxis) ? 15 : (showVisAxis ? 15 : 0);
  const cloudAxisOffset = (showVisAxis && showCloudAxis) ? 50 : (showCloudAxis ? 15 : 0);

  // 配置图表选项
  const option = {
    title: filteredData.length === 1 ? {
      text: '数据点较少，趋势图待更多数据后显示',
      left: 'center',
      top: 'middle',
      textStyle: { color: '#f39c12', fontSize: 11 }
    } : undefined,
    tooltip: {
      trigger: 'axis',
      formatter: function (params) {
        const time = new Date(params[0].axisValue);
        let result = `${time.getMonth() + 1}月${time.getDate()}日 ${time.getHours()}:${String(time.getMinutes()).padStart(2, '0')}<br/>`;
        params.forEach(param => {
          if (param.value !== null && param.value !== undefined) {
            const val = Array.isArray(param.value) ? param.value[1] : param.value;
            if (val !== null && val !== undefined) {
              result += `${param.marker}${param.seriesName}: ${val}<br/>`;
            }
          }
        });
        return result;
      }
    },
    legend: {
      data: [
        { name: '平均风', itemStyle: { color: '#3498db' }, textStyle: { color: '#3498db' } },
        { name: '阵风', itemStyle: { color: '#3498db' }, textStyle: { color: '#3498db' } },
        { name: '能见度', itemStyle: { color: '#f39c12' }, textStyle: { color: '#f39c12' } },
        { name: 'RVR', itemStyle: { color: '#e74c3c' }, textStyle: { color: '#e74c3c' } },
        { name: '云底高', itemStyle: { color: '#9b59b6' }, textStyle: { color: '#9b59b6' } },
        { name: '气温', itemStyle: { color: '#27ae60' }, textStyle: { color: '#27ae60' } }
      ],
      selected: airportDetailChart.selectedSeries,
      top: 13,
      right: '50%',
      orient: 'horizontal',
      itemGap: 8,
      textStyle: { fontSize: 10 },
      itemWidth: 12,
      itemHeight: 12,
      padding: [0, 30, 0, 0]
    },
    grid: {
      left: '94px',
      right: '94px',
      top: '35px',
      bottom: '30px'
    },
    xAxis: {
      type: 'time',
      min: startTime,
      max: latestTime,
      axisLabel: {
        formatter: function (value) {
          const date = new Date(value);
          const h = date.getHours();
          const m = date.getMinutes();
          return `${h}:${String(m).padStart(2, '0')}`;
        },
        color: '#ecf0f1',
        fontSize: 10
      },
      axisTick: {
        show: true
      },
      axisLine: { lineStyle: { color: '#7f8c8d' } },
      splitLine: { show: true, lineStyle: { color: '#34495e' } }
    },
    yAxis: [
      // yAxis[0]: 风速和阵风 - 左侧
      {
        type: 'value',
        name: showWindAxis ? 'W(mps)' : '',
        show: showWindAxis,
        nameLocation: 'end',
        nameGap: 10,
        nameTextStyle: { color: '#3498db', fontSize: 10 },
        position: 'left',
        offset: windAxisOffset,
        axisLabel: { color: '#ecf0f1', fontSize: 10 },
        axisLine: { show: showWindAxis, lineStyle: { color: '#7f8c8d' } },
        axisTick: { show: showWindAxis },
        splitLine: {
          show: hasAnySeriesSelected,
          lineStyle: {
            color: 'rgba(127, 140, 141, 0.3)',
            type: 'solid',
            width: 1
          }
        },
        splitNumber: 12
      },
      // yAxis[1]: 气温 - 左侧
      {
        type: 'value',
        name: showTempAxis ? 'T(℃)' : '',
        show: showTempAxis,
        nameLocation: 'end',
        nameGap: 10,
        nameTextStyle: { color: '#27ae60', fontSize: 10 },
        position: 'left',
        offset: tempAxisOffset,
        axisLabel: { color: '#ecf0f1', fontSize: 10 },
        axisLine: { show: showTempAxis, lineStyle: { color: '#7f8c8d' } },
        axisTick: { show: showTempAxis },
        splitLine: { show: false }
      },
      // yAxis[2]: 能见度和RVR - 右侧
      {
        type: 'value',
        name: showVisAxis ? 'V(m)' : '',
        show: showVisAxis,
        nameLocation: 'end',
        nameGap: 10,
        nameTextStyle: { color: '#f39c12', fontSize: 10 },
        position: 'right',
        offset: visAxisOffset,
        axisLabel: { color: '#ecf0f1', fontSize: 10 },
        axisLine: { show: showVisAxis, lineStyle: { color: '#7f8c8d' } },
        axisTick: { show: showVisAxis },
        splitLine: { show: false }
      },
      // yAxis[3]: 云底高 - 右侧
      {
        type: 'value',
        name: showCloudAxis ? 'H(30m)' : '',
        show: showCloudAxis,
        nameLocation: 'end',
        nameGap: 10,
        nameTextStyle: { color: '#9b59b6', fontSize: 10 },
        position: 'right',
        offset: cloudAxisOffset,
        axisLabel: { color: '#ecf0f1', fontSize: 10 },
        axisLine: { show: showCloudAxis, lineStyle: { color: '#7f8c8d' } },
        axisTick: { show: showCloudAxis },
        splitLine: { show: false }
      }
    ],
    series: filteredData.length === 1 ? [
      // 只有1个数据点时，全部使用散点图
      {
        name: '平均风',
        type: 'scatter',
        data: timeData.map((t, i) => [t, windSpeedData[i]]),
        yAxisIndex: 0,
        symbol: 'circle',
        symbolSize: 10,
        itemStyle: { color: '#3498db' }
      },
      {
        name: '阵风',
        type: 'scatter',
        data: timeData.map((t, i) => [t, gustData[i]]),
        yAxisIndex: 0,
        symbol: 'triangle',
        symbolSize: 8,
        symbolRotate: 180,
        itemStyle: { color: '#3498db' }
      },
      {
        name: '能见度',
        type: 'scatter',
        data: timeData.map((t, i) => [t, visibilityData[i]]),
        yAxisIndex: 2,
        symbol: 'circle',
        symbolSize: 10,
        itemStyle: { color: '#f39c12' }
      },
      {
        name: 'RVR',
        type: 'scatter',
        data: timeData.map((t, i) => [t, rvrData[i]]),
        yAxisIndex: 2,
        symbol: 'circle',
        symbolSize: 10,
        itemStyle: { color: '#e74c3c' }
      },
      {
        name: '云底高',
        type: 'scatter',
        data: timeData.map((t, i) => [t, cloudHeightData[i]]),
        yAxisIndex: 3,
        symbol: 'circle',
        symbolSize: 10,
        itemStyle: { color: '#9b59b6' }
      },
      {
        name: '气温',
        type: 'scatter',
        data: timeData.map((t, i) => [t, tempData[i]]),
        yAxisIndex: 1,
        symbol: 'circle',
        symbolSize: 10,
        itemStyle: { color: '#27ae60' }
      }
    ] : [
      // 2个及以上数据点时，使用平滑曲线
      {
        name: '平均风',
        type: 'line',
        data: timeData.map((t, i) => [t, windSpeedData[i]]),
        smooth: true,
        yAxisIndex: 0,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#3498db' },
        lineStyle: { color: '#3498db', width: 2 }
      },
      {
        name: '阵风',
        type: 'scatter',
        data: timeData.map((t, i) => [t, gustData[i]]),
        yAxisIndex: 0,
        symbol: 'triangle',
        symbolSize: 8,
        symbolRotate: 180,
        itemStyle: { color: '#3498db' }
      },
      {
        name: '能见度',
        type: 'line',
        data: timeData.map((t, i) => [t, visibilityData[i]]),
        smooth: true,
        yAxisIndex: 2,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#f39c12' },
        lineStyle: { color: '#f39c12', width: 2 }
      },
      {
        name: 'RVR',
        type: 'line',
        data: timeData.map((t, i) => [t, rvrData[i]]),
        smooth: true,
        yAxisIndex: 2,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#e74c3c' },
        lineStyle: { color: '#e74c3c', width: 2 }
      },
      {
        name: '云底高',
        type: 'line',
        data: timeData.map((t, i) => [t, cloudHeightData[i]]),
        smooth: true,
        yAxisIndex: 3,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#9b59b6' },
        lineStyle: { color: '#9b59b6', width: 2 }
      },
      {
        name: '气温',
        type: 'line',
        data: timeData.map((t, i) => [t, tempData[i]]),
        smooth: true,
        yAxisIndex: 1,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#27ae60' },
        lineStyle: { color: '#27ae60', width: 2 }
      }
    ]
  };

  airportDetailChart.chart.setOption(option);

  // 监听图例选择变化
  airportDetailChart.chart.off('legendselectchanged');
  airportDetailChart.chart.on('legendselectchanged', function (params) {
    // 平均风和阵风联动
    if (params.name === '平均风' || params.name === '阵风') {
      const isSelected = params.selected[params.name];
      params.selected['平均风'] = isSelected;
      params.selected['阵风'] = isSelected;
    }

    airportDetailChart.selectedSeries = params.selected;
    // 立即重新渲染图表以更新Y轴显示状态
    updateAirportDetailChart(airportCode);
  });
}

// 应用自定义时间范围（机场详情）
function applyCustomChartTimeForDetail() {
  const input = document.getElementById('chart-time-input-detail');
  const value = parseInt(input.value);

  if (isNaN(value) || value < 2 || value > 72) {
    alert('请输入2-72之间的整数');
    return;
  }

  // 取消所有单选按钮
  const radios = document.querySelectorAll('input[name="chart-time-detail"]');
  radios.forEach(radio => {
    if (parseInt(radio.value) === value) {
      radio.checked = true;
    } else {
      radio.checked = false;
    }
  });

  // 更新输入框样式
  input.classList.add('has-value');

  // 更新图表
  if (airportDetailChart.chart && airportDetailChart.airportCode) {
    airportDetailChart.hours = value;
    updateAirportDetailChart(airportDetailChart.airportCode);
  }
}

// 绑定时间选择器事件（机场详情）
function bindChartTimeSelectorForDetail(airportCode) {
  const radios = document.querySelectorAll('input[name="chart-time-detail"]');
  const input = document.getElementById('chart-time-input-detail');

  radios.forEach(radio => {
    radio.addEventListener('change', function () {
      if (this.checked) {
        const hours = parseInt(this.value);
        if (airportDetailChart.chart) {
          airportDetailChart.hours = hours;
          updateAirportDetailChart(airportCode);
        }
        // 清空输入框
        input.value = '';
        input.classList.remove('has-value');
      }
    });
  });

  // 输入框点击时清空灰色状态
  input.addEventListener('focus', function () {
    this.classList.remove('has-value');
  });
}
