// ==================================
// 机场详情功能模块
// ==================================
// 依赖：main.js 中的 airportData, currentTimeMode, currentToken, currentUserCode

// 搜索结果临时缓存（不写入主页 airportData，关闭弹窗后清除）
const searchAirportCache = {};
window.searchAirportCache = searchAirportCache;

// 当前详情弹窗展示中的机场代码（用于温度辅助覆盖层随数据刷新重绘）
let currentDetailAirportCode = null;
// 头部信息权限上下文：点四字码进详情为 'detail'；搜索打开（含单机场详情弹窗）为 'search'
let headerInfoContext = 'detail';

function headerInfoMode() {
  return window._viewMode === 'plain' ? 'plain' : 'home';
}

function canShowHeaderInfo(kind) {
  if (typeof hasAccess !== 'function') return true;
  if (!window.__accessIdentity) return true;
  const page = headerInfoContext === 'search' ? 'search' : 'detail';
  return hasAccess(`${page}_${kind}_${headerInfoMode()}`, 'display');
}

function airportDetailTimelineCornerLabel() {
  if (window._viewMode === 'plain') {
    return window.displayTimezone === 'UTC' ? '世界时' : '北京时';
  }
  return '实况信息';
}

function syncAirportDetailTimelineLabel() {
  const label = airportDetailTimelineCornerLabel();
  document.querySelectorAll('.airport-detail-title-row .title-text').forEach((el) => {
    el.textContent = label;
  });
}
window.syncAirportDetailTimelineLabel = syncAirportDetailTimelineLabel;

// 存储图表实例和状态
const airportDetailChart = {
  chart: null,
  hours: 3,
  selectedSeries: {},
  airportCode: null,
  historyData: null,        // 历史 METAR 接口返回的解析数据
  filteredData: null,       // 当前时段过滤后的数据点（用于天气标签重绘）
  weatherLabelCount: 0      // 上次渲染的天气标签数量（用于清除多余标签）
};

// 显示机场详细信息
async function showAirportDetail(airportCode) {
  // 主页机场：详情直接用已经拉到前端的 airportData，不再请求。
  const airport = airportData.find(a => a.airport_4code === airportCode);
  if (airport) {
    showAirportDetailModal(airport, 'detail');
    return;
  }

  // 不在主页的机场（典型：无航班、仅停场，但停场实况弹窗仍可能出现）。
  // 该场景很少，不单独做读库详情接口，与搜索「系统外机场」相同：走 airport-search，
  // 后端因 has_flight=False 会调外部 METAR/TAF，结果交给同一套详情页。
  // 注意：此处看到的是实时外网报文，不一定等于弹窗里那份已入库报文。
  await fetchNonHomepageAirportDetail(airportCode);
}

/**
 * 主页无此机场时，复用搜索 API 拉详情（见 showAirportDetail 注释）。
 */
async function fetchNonHomepageAirportDetail(airportCode) {
  const headers = { 'Content-Type': 'application/json' };
  if (typeof currentToken !== 'undefined' && currentToken) {
    headers['Authorization'] = `Bearer ${currentToken}`;
  }

  const url = `/${currentTimeMode}/api/airport-search/?codes=${encodeURIComponent(airportCode)}`;
  try {
    const response = await fetch(url, { headers });
    const payload = await response.json();
    if (!payload.success || !payload.data || !payload.data.length) {
      showError('未找到机场信息：' + airportCode);
      return;
    }
    searchAirportCache[payload.data[0].airport_4code] = payload.data[0];
    showAirportDetailModal(payload.data[0], 'detail');
  } catch (err) {
    console.error('非主页机场详情请求失败:', err);
    showError('获取机场详情失败：' + airportCode);
  }
}

// 显示机场详细信息弹窗
function showAirportDetailModal(airportData, source) {
  // 主页数据是扁平结构，直接使用airportData
  const airport = airportData;
  headerInfoContext = source === 'search' ? 'search' : 'detail';

  // 记录当前展示的机场代码，供温度辅助覆盖层刷新使用
  currentDetailAirportCode = airport.airport_4code;
  if (typeof setMarksPastExpanded === 'function') {
    setMarksPastExpanded('detail', true);
  }

  // 第1行：机场代码和名称（代码在上，名称在下）
  document.getElementById('airport-title-code').textContent = airport.airport_4code;
  document.getElementById('airport-title-name').textContent = airport.airport_name || '机场名称未配置';

  // 联系方式（使用主页已有的字段）
  const showContact = canShowHeaderInfo('contact');
  const showSun = canShowHeaderInfo('sun');
  const showRunway = canShowHeaderInfo('runway');
  const contactsEl = document.querySelector('#airport-detail-modal .airport-info-contacts');
  const sunLeftEl = document.querySelector('#airport-detail-modal .airport-info-left');
  const dividerEl = document.querySelector('#airport-detail-modal .airport-info-divider');
  const infoRow = document.querySelector('#airport-detail-modal .airport-info-row');
  const runwayItem = sunLeftEl
    ? Array.from(sunLeftEl.querySelectorAll('.info-item')).find((item) => {
        const label = item.querySelector('.info-label');
        return label && (label.textContent || '').indexOf('跑道') >= 0;
      })
    : null;

  if (contactsEl) {
    contactsEl.style.display = showContact ? '' : 'none';
    if (showContact) {
      document.getElementById('area-code').textContent = airport.area_code || 'N/A';
      document.getElementById('forecast-phone').textContent = airport.forecast_phone || 'N/A';
      document.getElementById('observation-phone').textContent = airport.observation_phone || 'N/A';
      document.getElementById('other-phone').textContent = airport.other_phone || 'N/A';
    }
  }
  if (sunLeftEl) {
    const sunItems = sunLeftEl.querySelectorAll('.info-item');
    sunItems.forEach((item) => {
      const label = item.querySelector('.info-label');
      if (!label) return;
      const t = label.textContent || '';
      if (t.indexOf('日出') >= 0 || t.indexOf('日落') >= 0) {
        item.style.display = showSun ? '' : 'none';
      }
    });
    if (runwayItem) runwayItem.style.display = showRunway ? '' : 'none';
    sunLeftEl.style.display = (showSun || showRunway) ? '' : 'none';
  }
  const showLeft = showSun || showRunway;
  if (dividerEl) dividerEl.style.display = (showLeft && showContact) ? '' : 'none';
  if (infoRow) {
    infoRow.classList.toggle('header-info-only', !(showLeft && showContact));
    infoRow.style.display = (showLeft || showContact) ? '' : 'none';
    infoRow.style.justifyContent = '';
  }

  if (showSun || showRunway) {
    loadAirportExtraInfo(airport.airport_4code);
  }

  const chartSection = document.getElementById('airport-chart-section');
  if (chartSection) {
    const showTrend = typeof hasAccess !== 'function' || hasAccess('detail_metar_trend', 'display');
    chartSection.style.display = showTrend ? '' : 'none';
  }

  // 生成时间轴
  generateAirportDetailTimeline();

  // 显示弹窗（需在渲染温度辅助覆盖层前显示，以便可见性判断准确）
  showModal('airport-detail-modal');

  // 显示机场数据
  displayAirportDetailData(airportData);

  // 若温度辅助已开启，为详情页机场行叠加温度标记（与主页同一位置）
  renderNwpOverlayForAirportDetail();

  // 图表默认折叠且不初始化，仅记录待用参数，等用户点击展开时再加载（提速弹窗打开、减少无谓请求）
  let defaultHours = window.chartDefaultHours || 3;
  const customInput = document.getElementById('chart-time-input-detail');
  if (customInput && customInput.classList.contains('has-value') && customInput.value) {
    const customVal = parseInt(customInput.value);
    if (!isNaN(customVal)) defaultHours = customVal;
  } else {
    const selectedRadio = document.querySelector('input[name="chart-time-detail"]:checked');
    if (selectedRadio) defaultHours = parseInt(selectedRadio.value);
  }
  // 若上一个机场的图表仍处于展开/已初始化状态，先释放，避免残留实例
  if (airportDetailChart.chart) {
    airportDetailChart.chart.dispose();
    airportDetailChart.chart = null;
  }
  if (airportDetailChart.resizeObserver) {
    airportDetailChart.resizeObserver.disconnect();
    airportDetailChart.resizeObserver = null;
  }
  airportDetailChart.initialized = false;
  airportDetailChart.airportCode = airport.airport_4code;
  airportDetailChart.hours = defaultHours;
  collapseAirportChartSection();
  bindChartTimeSelectorForDetail(airport.airport_4code);

  if (typeof syncAirportDetailTimelineLabel === 'function') {
    syncAirportDetailTimelineLabel();
  }

  const reportsSection = document.querySelector('#airport-detail-modal .airport-reports-section');
  if (window._viewMode === 'plain') {
    if (reportsSection) reportsSection.style.display = 'none';
  } else {
    if (reportsSection) reportsSection.style.display = '';
    loadHistoryReports(airport.airport_4code);
  }
}

/**
 * 为机场详情弹窗渲染温度辅助（NWP）覆盖层。
 * 详情页机场行（.airport-row-detail）不参与主页 renderAllNwpOverlays 的 .airport-code 匹配遍历，
 * 因此需要单独渲染；渲染位置/样式复用 NWP.js 中的 renderNwpOverlayForAirport，与主页保持一致。
 */
function renderNwpOverlayForAirportDetail() {
  if (typeof nwpEnabled === 'undefined' || !nwpEnabled) return;
  if (!currentDetailAirportCode) return;

  const modal = document.getElementById('airport-detail-modal');
  if (!modal || modal.style.display !== 'block') return;

  const temperatures = (typeof _nwpCache !== 'undefined') ? _nwpCache[currentDetailAirportCode] : null;
  if (!temperatures || temperatures.length === 0) return;

  const forecastTimeline = document.querySelector('#airport-detail-main .forecast-timeline');
  if (!forecastTimeline) return;

  renderNwpOverlayForAirport(forecastTimeline, temperatures);
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
        // 更新日出日落时间：北京时间 + 世界时，格式 06:29CST / 22:29UTC
        const sunriseBj = data.data.sunrise || '--:--';
        const sunsetBj = data.data.sunset || '--:--';
        const sunriseUtc = data.data.sunrise_utc != null ? data.data.sunrise_utc : '--:--';
        const sunsetUtc = data.data.sunset_utc != null ? data.data.sunset_utc : '--:--';
        document.getElementById('sunrise-time').textContent = `${sunriseBj}CST / ${sunriseUtc}UTC`;
        document.getElementById('sunset-time').textContent = `${sunsetBj}CST / ${sunsetUtc}UTC`;

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
function compensateReportsContentScale() {
  const reportsContent = document.querySelector('.airport-reports-section .reports-content');
  if (!reportsContent) return;
  const contentHeight = reportsContent.offsetHeight;
  reportsContent.style.marginBottom = `${-(contentHeight * 0.15)}px`;
}

function fillReportGroup(elementId, reports, lineClass, emptyText) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (reports && reports.length > 0) {
    el.innerHTML = reports.map(report => {
      const body = report.html || report.content || '';
      return `<div class="report-line ${lineClass}"><span class="report-content">${body}</span></div>`;
    }).join('');
    return;
  }
  el.innerHTML = `<div class="report-group-empty">${emptyText}</div>`;
}

function loadHistoryReports(airportCode) {
  fillReportGroup('airport-metar-reports', null, 'metar-line', '加载中...');
  fillReportGroup('airport-taf-reports', null, 'taf-line', '加载中...');
  compensateReportsContentScale();

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

  // 中文模式下详情页的实况/预报区一并中文化（实况趋势不变）
  const url = (window._viewMode === 'plain')
    ? `/${currentTimeMode}/api/plain/airport/${airportCode}/report-text/`
    : `/${currentTimeMode}/api/airport/${airportCode}/report-text/`;

  fetch(url, {
    headers: headers
  })
    .then(response => response.json())
    .then(data => {
      if (data.success && data.data) {
        displayHistoryReports(data.data);
      } else {
        console.error('加载历史报文失败:', data.error);
        displayHistoryReports({});
      }
    })
    .catch(error => {
      console.error('请求历史报文失败:', error);
      displayHistoryReports({});
    });
}

function displayHistoryReports(data) {
  const payload = data || {};
  fillReportGroup('airport-metar-reports', payload.metar_reports, 'metar-line', '获取历史实况数据失败');
  fillReportGroup('airport-taf-reports', payload.taf_reports, 'taf-line', '获取历史预报数据失败');
  compensateReportsContentScale();
  if (typeof positionAllMarksPastHandles === 'function') {
    requestAnimationFrame(() => positionAllMarksPastHandles());
  }
}

// ==================================
// 机场详情图表功能
// ==================================

// 将图表折叠面板重置为收起状态（每次打开机场详情弹窗时调用，不记忆上次展开状态）
function collapseAirportChartSection() {
  const section = document.getElementById('airport-chart-section');
  if (section) section.classList.add('collapsed');
  updateChartToggleSwitchText(true);
}

// 更新开关文案：collapsed=true 显示"点击展开"，false 显示"点击收起"
function updateChartToggleSwitchText(collapsed) {
  const textEl = document.getElementById('chart-toggle-switch-text');
  if (!textEl) return;
  textEl.textContent = collapsed ? '>> 点击展开实况趋势图表 <<' : '>> 点击收起实况趋势图表 <<';
}

// 点击图表展开/收起开关：首次展开时才真正初始化图表并请求历史数据
function toggleAirportChartSection() {
  const section = document.getElementById('airport-chart-section');
  if (!section) return;

  if (typeof hasAccess === 'function' && !hasAccess('detail_metar_trend', 'display')) {
    return;
  }

  const collapsed = section.classList.toggle('collapsed');
  updateChartToggleSwitchText(collapsed);
  if (typeof positionAllMarksPastHandles === 'function') {
    requestAnimationFrame(() => positionAllMarksPastHandles());
  }
  if (collapsed) return;

  const startChart = () => {
    if (!airportDetailChart.initialized) {
      airportDetailChart.initialized = true;
      initAirportDetailChart(airportDetailChart.airportCode, airportDetailChart.hours);
      loadMetarHistoryData(airportDetailChart.airportCode);
    } else if (airportDetailChart.chart) {
      setTimeout(() => airportDetailChart.chart.resize(), 50);
    }
  };

  // 打开实况趋势前检查后端是否正在解析
  if (typeof checkRunningParsers === 'function') {
    checkRunningParsers((err, data) => {
      if (!err) {
        const running = (data && data.running) || [];
        const queued = (data && data.queued) || [];
        if (running.length > 0 || queued.length > 0) {
          section.classList.add('collapsed');
          updateChartToggleSwitchText(true);
          if (typeof showParserRunningMessage === 'function') {
            showParserRunningMessage(
              (typeof buildParserStatusMessage === 'function'
                ? buildParserStatusMessage(running, queued)
                : '解析程序正在运行，请稍后再打开实况趋势')
            );
          } else {
            alert('后端解析程序正在运行，请稍后再打开实况趋势');
          }
          return;
        }
      }
      startChart();
    });
  } else {
    startChart();
  }
}

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
  const chart = echarts.init(chartDom);

  // 初始化状态
  airportDetailChart.chart = chart;
  airportDetailChart.hours = hours;
  airportDetailChart.selectedSeries = {};
  airportDetailChart.airportCode = airportCode;
  airportDetailChart.historyData = null;
  airportDetailChart.filteredData = null;
  airportDetailChart.weatherLabelCount = 0;

  // 监听容器大小变化（仅在尺寸有效时 resize，避免主页面自动更新导致 reflow 时误用错误尺寸）
  const resizeObserver = new ResizeObserver(() => {
    const w = chartDom.getBoundingClientRect().width;
    const h = chartDom.getBoundingClientRect().height;
    if (w >= 50 && h >= 50) {
      chart.resize();
      if (airportDetailChart.filteredData) {
        renderWeatherLabels(chart, airportDetailChart.filteredData);
      }
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

  // 优先从主页数据查找，其次从搜索缓存查找
  const airport = (airportData || []).find(a => a.airport_4code === airportCode)
    || searchAirportCache[airportCode];
  if (!airport) {
    console.log('未找到机场数据:', airportCode);
    return;
  }

  console.log('找到机场:', airport.airport_4code);
  console.log('机场对象的所有字段:', Object.keys(airport));

  const hours = airportDetailChart.hours;

  // 优先使用历史接口数据，回退到主页已加载的 metar_data
  const metarData = airportDetailChart.historyData || airport.metar_data || [];

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
          textStyle: { color: '#cccccc', fontSize: 14 },
          subtextStyle: { color: '#999999', fontSize: 11 }
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
        textStyle: { color: '#cccccc', fontSize: 14 },
        subtextStyle: { color: '#999999', fontSize: 11 }
      }
    });
    return;
  }

  const startTime = latestTime - hours * 3600000;

  console.log('时间范围:', new Date(startTime), '到', new Date(latestTime));
  console.log('latestTime:', latestTime, 'startTime:', startTime);

  // 过滤数据
  const filteredData = metarData.filter(item =>
    item.metar_observation_time >= startTime && item.metar_observation_time <= latestTime
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
        textStyle: { color: '#cccccc', fontSize: 14 },
        subtextStyle: { color: '#999999', fontSize: 11 }
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
    } : { text: '' },
    tooltip: {
      trigger: 'axis',
      formatter: function (params) {
        const time = new Date(params[0].axisValue);
        const isUtc = window.displayTimezone === 'UTC';
        const mo = isUtc ? time.getUTCMonth() + 1 : time.getMonth() + 1;
        const d  = isUtc ? time.getUTCDate()       : time.getDate();
        const h  = isUtc ? time.getUTCHours()      : time.getHours();
        const m  = isUtc ? time.getUTCMinutes()    : time.getMinutes();
        const tz = isUtc ? 'UTC' : 'CST';
        let result = `${mo}月${d}日 ${h}:${String(m).padStart(2, '0')} ${tz}<br/>`;
        params.forEach(param => {
          if (param.value !== null && param.value !== undefined) {
            const val = Array.isArray(param.value) ? param.value[1] : param.value;
            if (val !== null && val !== undefined) {
              result += `${param.marker}${param.seriesName}: ${val}<br/>`;
            }
          }
        });
        // 查找对应时刻的天气现象
        let weatherDisplay = '无';
        if (airportDetailChart.filteredData) {
          let hoverTime = null;
          for (const p of params) {
            if (Array.isArray(p.value) && p.value[0] != null) {
              hoverTime = p.value[0];
              break;
            }
          }
          if (hoverTime == null) hoverTime = params[0].axisValue;
          const pt = airportDetailChart.filteredData.find(
            item => item.metar_observation_time === hoverTime
          );
          if (pt && pt.metar_weather) weatherDisplay = pt.metar_weather;
        }
        result += `天气现象: ${weatherDisplay}<br/>`;
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
      left: 'center',
      orient: 'horizontal',
      itemGap: 8,
      textStyle: { fontSize: 10 },
      itemWidth: 12,
      itemHeight: 12
    },
    grid: {
      left: '94px',
      right: '94px',
      top: '35px',
      bottom: '70px'
    },
    xAxis: {
      type: 'time',
      min: startTime,
      max: latestTime,
      axisLabel: {
        formatter: function (value) {
          const date = new Date(value);
          const h = window.displayTimezone === 'UTC' ? date.getUTCHours() : date.getHours();
          const m = window.displayTimezone === 'UTC' ? date.getUTCMinutes() : date.getMinutes();
          return `${h}:${String(m).padStart(2, '0')}`;
        },
        color: 'rgba(255, 255, 255, 0.75)',
        fontSize: 10
      },
      axisTick: {
        show: true
      },
      axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.3)' } },
      splitLine: { show: true, lineStyle: { color: 'rgba(255, 255, 255, 0.12)' } }
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
        axisLabel: { color: 'rgba(255, 255, 255, 0.75)', fontSize: 10 },
        axisLine: { show: showWindAxis, lineStyle: { color: 'rgba(255, 255, 255, 0.3)' } },
        axisTick: { show: showWindAxis },
        splitLine: {
          show: hasAnySeriesSelected,
          lineStyle: {
            color: 'rgba(255, 255, 255, 0.12)',
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
        axisLabel: { color: 'rgba(255, 255, 255, 0.75)', fontSize: 10 },
        axisLine: { show: showTempAxis, lineStyle: { color: 'rgba(255, 255, 255, 0.3)' } },
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
        axisLabel: { color: 'rgba(255, 255, 255, 0.75)', fontSize: 10 },
        axisLine: { show: showVisAxis, lineStyle: { color: 'rgba(255, 255, 255, 0.3)' } },
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
        axisLabel: { color: 'rgba(255, 255, 255, 0.75)', fontSize: 10 },
        axisLine: { show: showCloudAxis, lineStyle: { color: 'rgba(255, 255, 255, 0.3)' } },
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

  // 保存当前过滤数据，供天气标签渲染和 resize 时使用
  airportDetailChart.filteredData = filteredData;
  airportDetailChart.chart.setOption(option);

  // 在图表处理完新选项后渲染天气现象标签
  setTimeout(() => {
    if (airportDetailChart.chart && airportDetailChart.filteredData) {
      renderWeatherLabels(airportDetailChart.chart, airportDetailChart.filteredData);
    }
  }, 0);

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

// 在横坐标轴时间刻度标签正下方渲染天气现象斜向标签
// 文字右端（上端）对齐时间刻度标签下方，向左下方 45° 延伸
function renderWeatherLabels(chart, filteredData) {
  const chartDom = document.getElementById('airport-detail-chart');
  if (!chartDom || !chart) return;

  const containerHeight = chartDom.offsetHeight;
  // grid.bottom = 70px；x 轴刻度文字约 14px 高；再留 2px 间隙
  const anchorY = containerHeight - 70 + 14 + 2;

  const graphicItems = [];
  let idx = 0;

  filteredData.forEach(item => {
    const weather = item.metar_weather;
    if (!weather) return;

    const xPixel = chart.convertToPixel({ xAxisIndex: 0 }, item.metar_observation_time);
    if (xPixel == null || isNaN(xPixel)) return;

    graphicItems.push({
      id: `wl_${idx++}`,
      type: 'text',
      z: 5,
      x: xPixel,
      y: anchorY,
      rotation: Math.PI / 4,
      style: {
        text: weather,
        fontSize: 12,
        fill: '#dddddd',
        align: 'right',
        verticalAlign: 'top',
      },
    });
  });

  // 清除上次渲染中多余的标签（切换到更短时段时数量可能减少）
  const prevCount = airportDetailChart.weatherLabelCount || 0;
  for (let i = idx; i < prevCount; i++) {
    graphicItems.push({ id: `wl_${i}`, $action: 'remove' });
  }
  airportDetailChart.weatherLabelCount = idx;

  chart.setOption({ graphic: graphicItems });
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

  // 记录所选时段；图表尚未展开/初始化时先记录，等展开时会使用该值
  airportDetailChart.hours = value;
  if (airportDetailChart.chart && airportDetailChart.airportCode) {
    updateAirportDetailChart(airportDetailChart.airportCode);
  }
}

// 异步加载历史 METAR 数据并刷新图表
function loadMetarHistoryData(airportCode) {
  const headers = {};
  if (currentTimeMode === 'current' && currentToken) {
    headers['Authorization'] = `Bearer ${currentToken}`;
  }

  fetch(`/${currentTimeMode}/api/airport/${airportCode}/metar-history/`, {
    headers: headers
  })
    .then(response => response.json())
    .then(data => {
      if (data.success && Array.isArray(data.data) && data.data.length > 0) {
        airportDetailChart.historyData = data.data;
        // 仅当当前图表仍属于该机场时才刷新
        if (airportDetailChart.airportCode === airportCode) {
          updateAirportDetailChart(airportCode);
        }
      } else {
        console.log('历史 METAR 数据为空或请求失败:', airportCode, data);
      }
    })
    .catch(error => {
      console.error('请求历史 METAR 数据失败:', error);
    });
}

// 绑定时间选择器事件（机场详情）
function bindChartTimeSelectorForDetail(airportCode) {
  const radios = document.querySelectorAll('input[name="chart-time-detail"]');
  const input = document.getElementById('chart-time-input-detail');

  radios.forEach(radio => {
    radio.addEventListener('change', function () {
      if (this.checked) {
        // 记录所选时段；图表尚未展开/初始化时先记录，等展开时会使用该值
        airportDetailChart.hours = parseInt(this.value);
        if (airportDetailChart.chart) {
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

// ==================================
// 机场搜索结果展示
// ==================================

/**
 * 单个机场搜索结果展示（来自 API，非主页已加载数据）。
 * 将机场数据存入 searchAirportCache，然后调用现有 showAirportDetailModal。
 */
function showAirportSearchSingle(airportData) {
  const code = airportData.airport_4code;

  // 写入缓存（供图表等需要时查找）
  searchAirportCache[code] = airportData;

  // 复用现有完整详情页弹窗
  showAirportDetailModal(airportData, 'search');
}

/**
 * 从多机场搜索结果中点击四字代码，打开该机场的完整详情弹窗。
 * 详情弹窗以更高 z-index 叠加显示，关闭后自动回落到搜索结果弹窗。
 */
function openAirportDetailFromSearchResult(code) {
  const airport = searchAirportCache[code];
  if (!airport) return;
  showAirportDetailModal(airport, 'detail');
}

/**
 * 生成机场详情 header 的 HTML（用于多机场搜索展示，避免复用固定ID元素）。
 */
function _buildSearchAirportHeader(airport) {
  const code = airport.airport_4code;
  const name = airport.airport_name || '机场名称未配置';
  const areaCode = airport.area_code || 'N/A';
  const forecastPhone = airport.forecast_phone || 'N/A';
  const obsPhone = airport.observation_phone || 'N/A';
  const otherPhone = airport.other_phone || 'N/A';
  const showSun = canShowHeaderInfo('sun');
  const showRunway = canShowHeaderInfo('runway');
  const showContact = canShowHeaderInfo('contact');

  const sunHtml = showSun ? `
          <div class="info-item">
            <span class="info-label">日出:</span>
            <span class="info-value" id="search-sunrise-${code}">--:--</span>
          </div>
          <div class="info-item">
            <span class="info-label">日落:</span>
            <span class="info-value" id="search-sunset-${code}">--:--</span>
          </div>` : '';
  const runwayHtml = showRunway ? `
          <div class="info-item">
            <span class="info-label">跑道:</span>
            <span class="info-value" id="search-runway-${code}">--</span>
          </div>` : '';
  const leftHtml = (showSun || showRunway)
    ? `<div class="airport-info-left">${sunHtml}${runwayHtml}</div>`
    : '';
  const contactHtml = showContact ? `
        <div class="airport-info-contacts">
          <div class="contact-item">
            <span class="contact-label">区号:</span>
            <span class="contact-value">${areaCode}</span>
          </div>
          <div class="contact-item">
            <span class="contact-label">预报:</span>
            <span class="contact-value">${forecastPhone}</span>
          </div>
          <div class="contact-item">
            <span class="contact-label">观测:</span>
            <span class="contact-value">${obsPhone}</span>
          </div>
          <div class="contact-item">
            <span class="contact-label">其他:</span>
            <span class="contact-value">${otherPhone}</span>
          </div>
        </div>` : '';

  return `
    <div class="airport-detail-header airport-search-header">
      <div class="airport-title-inline">
        <h2 class="airport-code-clickable" onclick="openAirportDetailFromSearchResult('${code}')"
          title="点击查看机场详情">${code}</h2>
      </div>
      <div class="airport-code-divider"></div>
      <div class="airport-info-row airport-info-row-compact">
        <div class="info-item airport-name-item">
          <span class="info-value">${name}</span>
        </div>
        ${leftHtml}
        ${contactHtml}
      </div>
    </div>
  `;
}

/**
 * 生成机场数据区的 HTML（用于多机场搜索展示）。
 * 内含 airport-data-section，title-row 由 CSS 隐藏（顶部共用时间轴）。
 */
function _buildSearchAirportDataSection(airport) {
  const code = airport.airport_4code;
  const rowHTML = (typeof createAirportRowForDetail === 'function')
    ? createAirportRowForDetail(airport, { marksScope: 'search:' + String(code).toUpperCase() })
    : '<div class="airport-search-empty">无法生成数据行</div>';

  const metarHTML = (window._viewMode === 'plain' && typeof plainDetailMetarRow === 'function')
    ? plainDetailMetarRow(airport)
    : '';

  return `
    <div class="airport-data-section">
      <div id="search-block-metar-${code}" class="plain-detail-metar-wrap"${window._viewMode === 'plain' ? '' : ' hidden'}>${metarHTML}</div>
      <div class="title-row airport-detail-title-row">
        <div class="title-weather"><span class="title-text">${airportDetailTimelineCornerLabel()}</span></div>
        <div class="title-timeline">
          <div class="timeline-row beijing-time">
            <div id="search-block-bj-${code}" class="timeline-container"></div>
          </div>
          <div class="timeline-row utc-time">
            <div id="search-block-utc-${code}" class="timeline-container"></div>
          </div>
        </div>
      </div>
      <div class="airport-detail-main" id="search-block-main-${code}">
        ${rowHTML}
      </div>
    </div>
  `;
}

/**
 * 多机场搜索结果展示。
 * 在 airport-search-modal 中逐一渲染各机场的 header + data section。
 */
function showAirportSearchMulti(airports) {
  const container = document.getElementById('airport-search-list');
  if (!container) return;

  headerInfoContext = 'search';

  // 写入缓存
  airports.forEach(a => { searchAirportCache[a.airport_4code] = a; });

  // 生成各机场 HTML
  const blocksHTML = airports.map(airport => {
    const code = String(airport.airport_4code || '').toUpperCase();
    if (typeof setMarksPastExpanded === 'function') {
      setMarksPastExpanded('search:' + code, true);
    }
    return `
      <div class="airport-search-block flight-marks-past-open" data-code="${code}">
        ${_buildSearchAirportHeader(airport)}
        ${_buildSearchAirportDataSection(airport)}
      </div>
    `;
  }).join('');

  container.innerHTML = blocksHTML;

  // 显示弹窗
  if (typeof showModal === 'function') {
    showModal('airport-search-modal');
  }

  // 弹窗渲染完成后，逐一为每个机场生成时间轴 + 更新网格线 + 绑定点击 + 异步加载额外信息
  requestAnimationFrame(() => {
    airports.forEach(airport => {
      const code = airport.airport_4code;

      // 为各机场独立生成时间轴
      _generateSearchTimeline(`search-block-bj-${code}`, `search-block-utc-${code}`);

      const mainEl = document.getElementById(`search-block-main-${code}`);
      if (mainEl) {
        const airportRow = mainEl.querySelector('.airport-row');
        if (airportRow && typeof updateAirportGridForModal === 'function') {
          updateAirportGridForModal(airportRow);
        }
      }

      // 渲染温度辅助（NWP）覆盖层：搜索结果弹窗不在主页 .airport-row 遍历范围内，需单独渲染
      renderNwpOverlayForAirportSearch(code);

      // 异步加载日出日落/跑道信息
      _loadSearchExtraInfo(code);
    });
    if (window._viewMode === 'plain' && typeof ensurePlainForAirports === 'function') {
      ensurePlainForAirports(airports);
    }
    if (typeof ensureModalMarksPastHandles === 'function') {
      ensureModalMarksPastHandles();
    }
  });
}

/**
 * 为多机场搜索结果中的单个机场渲染温度辅助（NWP）覆盖层。
 * 逻辑与 renderNwpOverlayForAirportDetail 一致，仅容器定位方式不同（按机场代码查找搜索区块）。
 */
function renderNwpOverlayForAirportSearch(code) {
  if (typeof nwpEnabled === 'undefined' || !nwpEnabled) return;

  const temperatures = (typeof _nwpCache !== 'undefined') ? _nwpCache[code] : null;
  if (!temperatures || temperatures.length === 0) return;

  const forecastTimeline = document.querySelector(`#search-block-main-${code} .forecast-timeline`);
  if (!forecastTimeline) return;

  if (typeof renderNwpOverlayForAirport === 'function') {
    renderNwpOverlayForAirport(forecastTimeline, temperatures);
  }
}

/**
 * 为搜索结果的顶部共用时间轴生成内容（复用 generateAirportDetailTimeline 逻辑）。
 */
function _generateSearchTimeline(bjId, utcId) {
  const bjEl = document.getElementById(bjId);
  const utcEl = document.getElementById(utcId);
  if (!bjEl || !utcEl) return;

  const codeMatch = String(bjId || '').match(/^search-block-bj-(.+)$/);
  const scope = codeMatch ? ('search:' + String(codeMatch[1]).toUpperCase()) : 'detail';
  if (typeof syncMarksPastOpenClass === 'function') syncMarksPastOpenClass(scope);

  const paintMarks = () => {
    if (!(typeof isFlightMarksMode === 'function' && isFlightMarksMode()
        && typeof fillMarksHourTicks === 'function')) {
      return false;
    }
    const { winStart, dur } = fillMarksHourTicks(bjEl, utcEl);
    const titleTimeline = bjEl.closest('.title-timeline');
    if (typeof updateMarksNowBadge === 'function') {
      updateMarksNowBadge(titleTimeline, winStart, dur);
    }
    return true;
  };
  if (typeof withMarksRenderScope === 'function') {
    if (withMarksRenderScope(scope, paintMarks)) return;
  } else if (paintMarks()) {
    return;
  }

  const currentTime = (typeof getCurrentTime === 'function') ? getCurrentTime() : new Date();
  const timeRange = (typeof currentTimeRange !== 'undefined') ? currentTimeRange : 36;
  let bjCells = '';
  let utcCells = '';

  for (let i = 0; i < timeRange; i++) {
    let bjHour, utcHour;
    if ((typeof currentTimeMode !== 'undefined') && currentTimeMode === 'test') {
      const utcTime = new Date(currentTime.getTime() + i * 3600000);
      utcHour = utcTime.getUTCHours().toString().padStart(2, '0');
      const bjTime = new Date(utcTime.getTime() + 28800000);
      bjHour = bjTime.getUTCHours().toString().padStart(2, '0');
    } else {
      const localTime = new Date(currentTime.getTime() + i * 3600000);
      bjHour = localTime.getHours().toString().padStart(2, '0');
      const utcTime = new Date(localTime.getTime() - 28800000);
      utcHour = utcTime.getHours().toString().padStart(2, '0');
    }
    bjCells += `<div class="timeline-cell" data-time="${i}"><span class="time-text">${i === 0 ? '' : bjHour}</span></div>`;
    utcCells += `<div class="timeline-cell" data-time="${i}"><span class="time-text">${i === 0 ? '' : utcHour}</span></div>`;
  }

  bjEl.innerHTML = bjCells;
  utcEl.innerHTML = utcCells;
}

/**
 * 为搜索结果中的单个机场异步加载日出日落/跑道信息。
 */
function _loadSearchExtraInfo(airportCode) {
  const sunriseEl = document.getElementById(`search-sunrise-${airportCode}`);
  const sunsetEl = document.getElementById(`search-sunset-${airportCode}`);
  const runwayEl = document.getElementById(`search-runway-${airportCode}`);
  if (!sunriseEl && !sunsetEl && !runwayEl) return;

  const headers = {};
  if ((typeof currentTimeMode !== 'undefined') && currentTimeMode === 'current'
    && (typeof currentToken !== 'undefined') && currentToken) {
    headers['Authorization'] = `Bearer ${currentToken}`;
  }

  fetch(`/${typeof currentTimeMode !== 'undefined' ? currentTimeMode : 'current'}/api/airport/${airportCode}/extra-info/`, { headers })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        const sr = data.data.sunrise || '--:--';
        const ss = data.data.sunset || '--:--';
        const srUtc = data.data.sunrise_utc != null ? data.data.sunrise_utc : '--:--';
        const ssUtc = data.data.sunset_utc != null ? data.data.sunset_utc : '--:--';
        if (sunriseEl) sunriseEl.textContent = `${sr}CST / ${srUtc}UTC`;
        if (sunsetEl) sunsetEl.textContent = `${ss}CST / ${ssUtc}UTC`;
        const runways = data.data.runways || [];
        if (runwayEl) runwayEl.textContent = runways.length > 0 ? runways.join(', ') : '--';
      }
    })
    .catch(() => { /* 忽略额外信息加载失败 */ });
}

// 关闭搜索弹窗时清空搜索缓存
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('airport-search-modal');
    if (!modal) return;
    const closeBtn = modal.querySelector('.modal-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        Object.keys(searchAirportCache).forEach(k => delete searchAirportCache[k]);
        document.querySelectorAll('.flight-past-handle-float.scope-search').forEach((el) => el.remove());
      });
    }
  });
})();
