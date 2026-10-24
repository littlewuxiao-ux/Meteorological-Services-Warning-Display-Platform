// ==================================
// 机场详情功能模块
// ==================================
// 依赖：main.js 中的 airportData, currentTimeMode, currentToken, currentUserCode

// 搜索结果临时缓存（不写入主页 airportData，关闭弹窗后清除）
const searchAirportCache = {};
window.searchAirportCache = searchAirportCache;

function airportDetailThemeIsLight() {
  return document.body.classList.contains('airport-detail-theme-light');
}
window.airportDetailThemeIsLight = airportDetailThemeIsLight;

function airportDetailChartInk() {
  if (airportDetailThemeIsLight()) {
    return {
      muted: '#000000',
      faint: 'rgba(0, 0, 0, 0.22)',
      split: 'rgba(0, 0, 0, 0.10)',
      empty: '#333333',
      emptySub: '#555555',
      weather: '#000000',
    };
  }
  return {
    muted: 'rgba(255, 255, 255, 0.75)',
    faint: 'rgba(255, 255, 255, 0.3)',
    split: 'rgba(255, 255, 255, 0.12)',
    empty: '#cccccc',
    emptySub: '#999999',
    weather: '#dddddd',
  };
}

function applyAirportDetailTheme(theme) {
  const light = String(theme || 'dark') === 'light';
  document.body.classList.toggle('airport-detail-theme-light', light);
  document.body.classList.toggle('airport-detail-theme-dark', !light);
  document.querySelectorAll('#airport-detail-main .airport-row, .airport-search-block .airport-row').forEach((row) => {
    if (typeof updateAirportGridForModal === 'function') updateAirportGridForModal(row);
  });
  if (airportDetailChart.chart && airportDetailChart.airportCode) {
    updateAirportDetailChart(airportDetailChart.airportCode);
  }
  if (typeof renderNwpOverlayForAirportDetail === 'function') {
    renderNwpOverlayForAirportDetail();
  }
  if (typeof renderNwpOverlayForAirportSearch === 'function') {
    document.querySelectorAll('.airport-search-block').forEach((block) => {
      const code = block.getAttribute('data-code');
      if (code) renderNwpOverlayForAirportSearch(code);
    });
  }
}
window.applyAirportDetailTheme = applyAirportDetailTheme;

function loadAirportDetailTheme() {
  const mode = (typeof currentTimeMode !== 'undefined' ? currentTimeMode : null)
    || window.currentTimeMode || window.timeMode || 'current';
  const headers = typeof getRequestHeaders === 'function' ? getRequestHeaders() : {};
  fetch(`/${mode}/api/map-style/config/`, { headers })
    .then((r) => r.json())
    .then((data) => {
      if (data && data.success && data.airport_detail) {
        applyAirportDetailTheme(data.airport_detail.theme);
      }
    })
    .catch(() => {});
}

// 当前详情弹窗展示中的机场代码（用于温度辅助覆盖层随数据刷新重绘）
let currentDetailAirportCode = null;
// 联系方式权限上下文：点四字码进详情为 'detail'；搜索打开（含单机场详情弹窗）为 'search'
let headerInfoContext = 'detail';

function reportsArePlain() {
  return typeof usePlainReports === 'function' ? usePlainReports() : (window._viewMode === 'plain');
}

function ensurePlainScriptIfNeeded() {
  if (typeof syncPlainReportsClass === 'function') syncPlainReportsClass();
  if (!reportsArePlain()) return Promise.resolve();
  if (typeof ensureViewScript !== 'function') return Promise.resolve();
  return ensureViewScript('js/plain_view.js').catch((err) => {
    console.error(err);
  });
}

function headerInfoMode() {
  return window._viewMode === 'plain' ? 'plain' : 'home';
}

function canShowContactInfo() {
  if (typeof hasAccess !== 'function') return true;
  if (!window.__accessIdentity) return true;
  const page = headerInfoContext === 'search' ? 'search' : 'detail';
  return hasAccess(`${page}_contact_${headerInfoMode()}`, 'display');
}

function airportDetailTimelineCornerLabel() {
  if (reportsArePlain()) {
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
const AIRPORT_CHART_MIN_HOURS = 3;
const AIRPORT_CHART_MAX_HOURS = 72;
const AIRPORT_CHART_DEFAULT_HOURS = 24;
const AIRPORT_CHART_WEATHER_HOURLY_HOURS = 12;
const AIRPORT_CHART_WEATHER_TILT_HOURS = 30;

function defaultAirportChartSelectedSeries() {
  return {
    '平均风': false,
    '阵风': false,
    '能见度': false,
    'RVR': false,
    '云底高': false,
    '气温': false,
    '露点温度': false,
    '气压': false,
    '天气现象': false,
  };
}

function clampAirportChartHours(hours) {
  const n = Number(hours);
  if (!Number.isFinite(n)) return AIRPORT_CHART_DEFAULT_HOURS;
  return Math.min(AIRPORT_CHART_MAX_HOURS, Math.max(AIRPORT_CHART_MIN_HOURS, n));
}

function airportChartUsesHourlyWeather() {
  return clampAirportChartHours(airportDetailChart.hours) >= AIRPORT_CHART_WEATHER_HOURLY_HOURS;
}

function airportChartUsesTiltedWeather() {
  return clampAirportChartHours(airportDetailChart.hours) >= AIRPORT_CHART_WEATHER_TILT_HOURS;
}

function airportChartWeatherGridBottom(weatherOn) {
  if (!weatherOn) return 70;
  if (airportChartUsesTiltedWeather()) return 92;
  return airportChartUsesHourlyWeather() ? 118 : 100;
}

function formatAirportChartHours(hours) {
  const n = clampAirportChartHours(hours);
  const shown = Math.abs(n - Math.round(n)) < 0.05 ? String(Math.round(n)) : n.toFixed(1);
  return `过去 ${shown} 小时`;
}

function paintAirportChartRangeHint(hours, flash) {
  const text = formatAirportChartHours(hours);
  const hint = document.getElementById('airport-chart-range-hint');
  if (hint) hint.textContent = text;
  const flashEl = document.getElementById('airport-chart-range-flash');
  if (!flashEl) return;
  flashEl.textContent = text;
  if (!flash) return;
  flashEl.classList.remove('is-pop');
  void flashEl.offsetWidth;
  flashEl.classList.add('is-pop');
}

const AIRPORT_CHART_LEGEND_GROUPS = [
  { id: 'wind', items: [{ name: '平均风', color: '#3498db' }, { name: '阵风', color: '#3498db' }] },
  { id: 'vis', items: [{ name: '能见度', color: '#e74c3c' }, { name: 'RVR', color: '#e74c3c' }] },
  { id: 'cloud', items: [{ name: '云底高', color: '#9b59b6' }] },
  { id: 'temp', items: [{ name: '气温', color: '#f39c12' }] },
  { id: 'dew', items: [{ name: '露点温度', color: '#27ae60' }] },
  { id: 'pressure', items: [{ name: '气压', color: '#00cec9' }] },
  { id: 'weather', items: [{ name: '天气现象', color: '#95a5a6' }] },
];

const AIRPORT_CHART_AXIS_SLOT_PX = 56;
const AIRPORT_CHART_AXIS_PAD_PX = 14;
const AIRPORT_CHART_AXIS_GROUPS = {
  wind: { name: 'W(mps)', color: '#3498db', seriesNames: ['平均风', '阵风'] },
  vis: { name: 'V(m)', color: '#e74c3c', seriesNames: ['能见度', 'RVR'] },
  cloud: { name: 'H(30m)', color: '#9b59b6', seriesNames: ['云底高'] },
  temp: { name: 'T(℃)', color: '#f39c12', seriesNames: ['气温', '露点温度'] },
  pressure: { name: 'P(hPa)', color: '#00cec9', seriesNames: ['气压'] },
};
const AIRPORT_CHART_AXIS_GROUP_IDS = ['wind', 'vis', 'cloud', 'temp', 'pressure'];

function airportChartAxisGroupOn(selected, groupId) {
  const group = AIRPORT_CHART_AXIS_GROUPS[groupId];
  return !!(group && group.seriesNames.some((name) => selected && selected[name]));
}

function syncAirportChartAxisOrder(selected) {
  const prev = Array.isArray(airportDetailChart.axisOrder) ? airportDetailChart.axisOrder : [];
  const next = prev.filter((id) => airportChartAxisGroupOn(selected, id));
  AIRPORT_CHART_AXIS_GROUP_IDS.forEach((id) => {
    if (airportChartAxisGroupOn(selected, id) && next.indexOf(id) < 0) next.push(id);
  });
  airportDetailChart.axisOrder = next;
  return next;
}

function formatAirportChartAxisLabel(value) {
  if (value == null || !Number.isFinite(Number(value))) return '';
  const number = Number(value);
  if (Math.abs(number) >= 1000) return String(Math.round(number));
  if (Math.abs(number - Math.round(number)) < 1e-6) return String(Math.round(number));
  return String(Number(number.toFixed(1)));
}

function buildAirportChartYAxes(order, ink, hasSeries) {
  if (!order.length) {
    return [{
      type: 'value',
      show: false,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    }];
  }
  return order.map((id, index) => {
    const meta = AIRPORT_CHART_AXIS_GROUPS[id];
    const side = index % 2 === 0 ? 'left' : 'right';
    const axis = {
      type: 'value',
      show: true,
      name: meta.name,
      nameLocation: 'end',
      nameGap: 16,
      nameRotate: 0,
      nameTextStyle: {
        color: meta.color,
        fontSize: 10,
        width: AIRPORT_CHART_AXIS_SLOT_PX,
        overflow: 'none',
      },
      position: side,
      offset: Math.floor(index / 2) * AIRPORT_CHART_AXIS_SLOT_PX,
      axisLabel: {
        show: true,
        hideOverlap: false,
        showMinLabel: true,
        showMaxLabel: true,
        color: ink.muted,
        fontSize: 10,
        margin: 8,
        formatter: formatAirportChartAxisLabel,
      },
      axisLine: { show: true, lineStyle: { color: ink.faint } },
      axisTick: { show: true, lineStyle: { color: ink.faint } },
      splitLine: index === 0 ? {
        show: !!hasSeries,
        lineStyle: { color: ink.split, type: 'solid', width: 1 },
      } : { show: false },
      splitNumber: 5,
    };
    if (id === 'pressure') {
      axis.min = (value) => (value.min == null ? null : Math.floor(value.min - 2));
      axis.max = (value) => (value.max == null ? null : Math.ceil(value.max + 2));
    }
    if (id === 'temp' || id === 'pressure') axis.scale = true;
    return axis;
  });
}

function buildAirportChartGrid(order, weatherBottom) {
  let leftCount = 0;
  let rightCount = 0;
  order.forEach((_, index) => {
    if (index % 2 === 0) leftCount += 1;
    else rightCount += 1;
  });
  return {
    left: leftCount ? AIRPORT_CHART_AXIS_PAD_PX + leftCount * AIRPORT_CHART_AXIS_SLOT_PX : 16,
    right: rightCount ? AIRPORT_CHART_AXIS_PAD_PX + rightCount * AIRPORT_CHART_AXIS_SLOT_PX : 16,
    top: 36,
    bottom: weatherBottom,
    containLabel: false,
  };
}

function parseMetarDewPoint(value) {
  if (value == null || value === '') return null;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  let text = String(value).trim().toUpperCase().replace('−', '-');
  if (!text || text === '//' || text === 'M//' || text === 'NONE') return null;
  if (text.startsWith('M') && !text.startsWith('M-')) text = `-${text.slice(1)}`;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

function renderAirportChartLegend() {
  const el = document.getElementById('airport-chart-legend');
  if (!el) return;
  const selected = airportDetailChart.selectedSeries || defaultAirportChartSelectedSeries();
  el.innerHTML = AIRPORT_CHART_LEGEND_GROUPS.map((group) => {
    const groupOn = group.items.some((item) => !!selected[item.name]);
    const buttons = group.items.map((item) => {
      const on = !!selected[item.name];
      const color = on ? item.color : '';
      return `<button type="button" class="airport-chart-legend-item${on ? ' is-on' : ''}" data-series="${item.name}"${color ? ` style="color:${color}"` : ''}><i></i><span>${item.name}</span></button>`;
    }).join('');
    return `<div class="airport-chart-legend-group${groupOn ? ' is-on' : ''}" data-group="${group.id}">${buttons}</div>`;
  }).join('');
}

function bindAirportChartLegend() {
  const el = document.getElementById('airport-chart-legend');
  if (!el || el.dataset.bound === '1') return;
  el.dataset.bound = '1';
  el.addEventListener('click', (event) => {
    const btn = event.target.closest('.airport-chart-legend-item');
    if (!btn) return;
    const name = btn.getAttribute('data-series');
    if (!name) return;
    const selected = Object.assign(defaultAirportChartSelectedSeries(), airportDetailChart.selectedSeries);
    const next = !selected[name];
    if (name === '平均风' || name === '阵风') {
      selected['平均风'] = next;
      selected['阵风'] = next;
    } else if (name === '能见度' || name === 'RVR') {
      selected['能见度'] = next;
      selected['RVR'] = next;
    } else {
      selected[name] = next;
    }
    airportDetailChart.selectedSeries = selected;
    syncAirportChartAxisOrder(selected);
    if (airportDetailChart.airportCode) updateAirportDetailChart(airportDetailChart.airportCode);
    else renderAirportChartLegend();
  });
}

function bindAirportChartWheel(chartDom) {
  const wrap = document.querySelector('#airport-chart-section .airport-chart-body') || chartDom;
  if (!wrap || wrap.dataset.wheelBound === '1') return;
  wrap.dataset.wheelBound = '1';
  wrap.addEventListener('wheel', onAirportChartWheel, { passive: false });
}

function onAirportChartWheel(event) {
  if (!airportDetailChart.chart) return;
  event.preventDefault();
  event.stopPropagation();
  const factor = Math.exp(event.deltaY * 0.0018);
  const next = clampAirportChartHours((airportDetailChart.hours || AIRPORT_CHART_DEFAULT_HOURS) * factor);
  if (Math.abs(next - airportDetailChart.hours) < 0.01) {
    airportDetailChart.hours = next;
    paintAirportChartRangeHint(next, true);
    return;
  }
  airportDetailChart.hours = next;
  paintAirportChartRangeHint(next, true);
  if (airportDetailChart._zoomRaf) cancelAnimationFrame(airportDetailChart._zoomRaf);
  airportDetailChart._zoomRaf = requestAnimationFrame(() => {
    airportDetailChart._zoomRaf = 0;
    applyAirportChartTimeWindow(true);
  });
}

function applyAirportChartTimeWindow(animate) {
  const chart = airportDetailChart.chart;
  if (!chart || !airportDetailChart.latestTime) return;
  const hours = clampAirportChartHours(airportDetailChart.hours);
  const latestTime = airportDetailChart.latestTime;
  const startTime = latestTime - hours * 3600000;
  const weatherOn = !!(airportDetailChart.selectedSeries && airportDetailChart.selectedSeries['天气现象']);
  chart.setOption({
    animationDurationUpdate: animate ? 180 : 0,
    animationEasingUpdate: 'cubicOut',
    xAxis: { min: startTime, max: latestTime },
    grid: { bottom: airportChartWeatherGridBottom(weatherOn) },
  });
  const source = airportDetailChart.allData || airportDetailChart.historyData || [];
  const visible = source.filter((item) => {
    const t = item && item.metar_observation_time;
    return t >= startTime && t <= latestTime;
  });
  airportDetailChart.filteredData = visible;
  setTimeout(() => {
    if (airportDetailChart.chart) {
      renderWeatherLabels(airportDetailChart.chart);
    }
  }, animate ? 200 : 0);
}

const airportDetailChart = {
  chart: null,
  hours: AIRPORT_CHART_DEFAULT_HOURS,
  selectedSeries: defaultAirportChartSelectedSeries(),
  axisOrder: [],
  airportCode: null,
  historyData: null,        // 历史 METAR 接口返回的解析数据
  filteredData: null,       // 当前时段过滤后的数据点（用于天气标签重绘）
  weatherLabelCount: 0,     // 上次渲染的天气标签数量（用于清除多余标签）
  hourlyWeather: [],
  latestTime: null,
};

const airportDetailHistory = {
  airportCode: null,
  promise: null,
};

function airportDetailAuthHeaders() {
  const headers = {};
  if (typeof currentTimeMode !== 'undefined' && currentTimeMode === 'current' && currentToken) {
    headers['Authorization'] = `Bearer ${currentToken}`;
    if (currentUserCode) headers['X-User-Code'] = currentUserCode;
  }
  if (typeof currentTimeMode !== 'undefined' && currentTimeMode === 'test') {
    headers['X-User-Code'] = 'test';
  }
  return headers;
}

function scheduleAirportDetailHistory(airportCode, waitFor) {
  airportDetailHistory.airportCode = airportCode;
  airportDetailHistory.promise = Promise.all((waitFor || []).map((item) => (
    item && typeof item.then === 'function' ? item.catch(() => null) : Promise.resolve()
  ))).then(() => {
    if (currentDetailAirportCode !== airportCode) return { success: false };
    return fetch(`/${currentTimeMode}/api/airport/${airportCode}/metar-history-ensure/`, {
      headers: airportDetailAuthHeaders(),
    }).then((response) => response.json());
  }).catch((error) => {
    console.error('补齐历史实况失败:', error);
    return { success: false };
  });
  return airportDetailHistory.promise;
}

function waitAirportDetailHistory(airportCode) {
  if (airportDetailHistory.airportCode === airportCode && airportDetailHistory.promise) {
    return airportDetailHistory.promise;
  }
  return scheduleAirportDetailHistory(airportCode, []);
}

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
function pinAirportDetailModalForChartCenter() {
  const box = document.querySelector('#airport-detail-modal .airport-detail-content');
  const modal = document.getElementById('airport-detail-modal');
  if (!box || !modal || modal.style.display === 'none') return;
  const extra = document.getElementById('airport-detail-extra');
  const reports = extra && extra.querySelector('[data-extra-pane-panel="reports"]');
  const currentH = box.getBoundingClientRect().height;
  const reportsH = reports ? reports.getBoundingClientRect().height : 0;
  const estimated = Math.max(currentH, currentH - reportsH + 420);
  const viewH = window.innerHeight;
  const top = Math.max(24, Math.round((viewH - Math.min(estimated, viewH - 48)) / 2));
  box.style.top = `${top}px`;
  box.style.maxHeight = `${Math.max(200, viewH - top - 24)}px`;
}

function bindAirportDetailModalPin() {
  if (bindAirportDetailModalPin.bound) return;
  bindAirportDetailModalPin.bound = true;
  window.addEventListener('resize', () => {
    pinAirportDetailModalForChartCenter();
  });
}

async function showAirportDetailModal(airportData, source) {
  await ensurePlainScriptIfNeeded();
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
  const showContact = canShowContactInfo();
  const contactsEl = document.querySelector('#airport-detail-modal .airport-info-contacts');
  const dividerEl = document.querySelector('#airport-detail-modal .airport-info-divider');
  const infoRow = document.querySelector('#airport-detail-modal .airport-info-row');

  if (contactsEl) {
    contactsEl.style.display = showContact ? '' : 'none';
    if (showContact) {
      document.getElementById('area-code').textContent = airport.area_code || 'N/A';
      document.getElementById('forecast-phone').textContent = airport.forecast_phone || 'N/A';
      document.getElementById('observation-phone').textContent = airport.observation_phone || 'N/A';
      document.getElementById('other-phone').textContent = airport.other_phone || 'N/A';
    }
  }
  if (dividerEl) dividerEl.style.display = showContact ? '' : 'none';
  if (infoRow) {
    infoRow.classList.toggle('header-info-only', !showContact);
    infoRow.style.justifyContent = '';
  }

  const extraInfoPromise = loadAirportExtraInfo(airport.airport_4code);

  const extra = document.getElementById('airport-detail-extra');
  const chartBtn = document.getElementById('airport-extra-chart-btn');
  const tableBtn = document.getElementById('airport-extra-table-btn');
  const chartSection = document.getElementById('airport-chart-section');
  if (chartBtn) chartBtn.style.display = '';
  if (tableBtn) tableBtn.style.display = '';
  if (chartSection) chartSection.style.display = '';
  if (extra) extra.classList.remove('no-chart');

  // 生成时间轴
  generateAirportDetailTimeline();

  // 显示弹窗（需在渲染温度辅助覆盖层前显示，以便可见性判断准确）
  showModal('airport-detail-modal');

  // 显示机场数据
  displayAirportDetailData(airportData);

  // 若温度辅助已开启，为详情页机场行叠加温度标记（与主页同一位置）
  renderNwpOverlayForAirportDetail();

  // 图表默认折叠且不初始化；时间范围固定从 24 小时起，用滚轮缩放，不记忆上次时段
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
  airportDetailChart.hours = AIRPORT_CHART_DEFAULT_HOURS;
  airportDetailChart.selectedSeries = defaultAirportChartSelectedSeries();
  airportDetailChart.axisOrder = [];
  paintAirportChartRangeHint(AIRPORT_CHART_DEFAULT_HOURS, false);
  setAirportTrendTableMessage('过去 24 小时实况表将在报文加载完成后准备');
  resetAirportDetailExtraPane();
  bindAirportDetailModalPin();
  requestAnimationFrame(() => {
    pinAirportDetailModalForChartCenter();
    requestAnimationFrame(pinAirportDetailModalForChartCenter);
  });

  if (typeof syncAirportDetailTimelineLabel === 'function') {
    syncAirportDetailTimelineLabel();
  }

  const reportsSection = document.querySelector('#airport-detail-modal .airport-reports-section');
  let reportsPromise = Promise.resolve();
  if (reportsArePlain()) {
    if (reportsSection) reportsSection.style.display = 'none';
  } else {
    if (reportsSection) reportsSection.style.display = '';
    reportsPromise = loadHistoryReports(airport.airport_4code);
  }
  scheduleAirportDetailHistory(airport.airport_4code, [extraInfoPromise, reportsPromise]);
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

  return fetch(`/${currentTimeMode}/api/airport/${airportCode}/extra-info/`, {
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
  if (reportsContent) reportsContent.style.marginBottom = '';
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
  const url = reportsArePlain()
    ? `/${currentTimeMode}/api/plain/airport/${airportCode}/report-text/`
    : `/${currentTimeMode}/api/airport/${airportCode}/report-text/`;

  return fetch(url, {
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

function resetAirportDetailExtraPane() {
  setAirportDetailExtraPane('reports', { skipLoad: true });
}

function startAirportDetailChartIfNeeded() {
  if (!airportDetailChart.initialized) {
    airportDetailChart.initialized = true;
    initAirportDetailChart(airportDetailChart.airportCode, airportDetailChart.hours);
    loadMetarHistoryData(airportDetailChart.airportCode);
  } else if (airportDetailChart.chart) {
    setTimeout(() => airportDetailChart.chart.resize(), 50);
  }
}

function setAirportDetailExtraPane(pane, opts) {
  const extra = document.getElementById('airport-detail-extra');
  const section = document.getElementById('airport-chart-section');
  const next = (pane === 'chart' || pane === 'table') ? pane : 'reports';
  if (extra) {
    extra.dataset.pane = next;
    extra.querySelectorAll('.airport-extra-switch-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-extra-pane') === next);
    });
  }
  if (section) {
    section.classList.toggle('collapsed', next !== 'chart');
  }
  if (typeof positionAllMarksPastHandles === 'function') {
    requestAnimationFrame(() => positionAllMarksPastHandles());
  }
  if (next === 'reports' || (opts && opts.skipLoad)) return;

  const openPane = () => {
    if (next === 'table') {
      loadAirportTrendTable(airportDetailChart.airportCode);
      return;
    }
    waitAirportDetailHistory(airportDetailChart.airportCode).finally(() => {
      if (airportDetailChart.airportCode) startAirportDetailChartIfNeeded();
    });
  };

  if (typeof checkRunningParsers === 'function') {
    checkRunningParsers((err, data) => {
      if (!err) {
        const running = (data && data.running) || [];
        const queued = (data && data.queued) || [];
        if (running.length > 0 || queued.length > 0) {
          resetAirportDetailExtraPane();
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
      openPane();
    });
  } else {
    openPane();
  }
}

function bindAirportDetailExtraSwitch() {
  const extra = document.getElementById('airport-detail-extra');
  if (!extra || extra.dataset.bound === '1') return;
  extra.dataset.bound = '1';
  extra.querySelectorAll('.airport-extra-switch-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      setAirportDetailExtraPane(btn.getAttribute('data-extra-pane'));
    });
  });
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
  airportDetailChart.hours = clampAirportChartHours(hours || AIRPORT_CHART_DEFAULT_HOURS);
  airportDetailChart.selectedSeries = defaultAirportChartSelectedSeries();
  airportDetailChart.axisOrder = [];
  airportDetailChart.airportCode = airportCode;
  bindAirportChartWheel(chartDom);
  bindAirportChartLegend();
  renderAirportChartLegend();
  paintAirportChartRangeHint(airportDetailChart.hours, false);
  airportDetailChart.historyData = null;
  airportDetailChart.filteredData = null;
  airportDetailChart.hourlyWeather = [];
  airportDetailChart.weatherLabelCount = 0;

  // 监听容器大小变化（仅在尺寸有效时 resize，避免主页面自动更新导致 reflow 时误用错误尺寸）
  const resizeObserver = new ResizeObserver(() => {
    const w = chartDom.getBoundingClientRect().width;
    const h = chartDom.getBoundingClientRect().height;
    if (w >= 50 && h >= 50) {
      chart.resize();
      if (airportDetailChart.chart) {
        renderWeatherLabels(chart);
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
      metar_temp_val: airport.metar_temp_val,
      dewPoint: parseMetarDewPoint(airport.dewPoint != null ? airport.dewPoint : airport.metar_dew_point),
      airPressure: airport.airPressure
    };

    // 检查是否有有效的观测时间
    if (tempData.metar_observation_time) {
      console.log('使用机场自身数据作为单点数据');
      // 将当前数据作为单个数据点使用
      metarData.push(tempData);
    } else {
      console.log('机场没有有效的观测数据');
      const ink = airportDetailChartInk();
      airportDetailChart.chart.setOption({
        title: {
          text: '暂无历史数据',
          subtext: '需要等待系统收集更多METAR数据',
          left: 'center',
          top: 'center',
          textStyle: { color: ink.empty, fontSize: 14 },
          subtextStyle: { color: ink.emptySub, fontSize: 11 }
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
    const ink = airportDetailChartInk();
    airportDetailChart.chart.setOption({
      title: {
        text: '暂无历史数据',
        subtext: '无法获取有效的观测时间',
        left: 'center',
        top: 'center',
        textStyle: { color: ink.empty, fontSize: 14 },
        subtextStyle: { color: ink.emptySub, fontSize: 11 }
      }
    });
    return;
  }

  airportDetailChart.latestTime = latestTime;
  const startTime = latestTime - clampAirportChartHours(hours) * 3600000;
  paintAirportChartRangeHint(airportDetailChart.hours, false);

  console.log('时间范围:', new Date(startTime), '到', new Date(latestTime));
  console.log('latestTime:', latestTime, 'startTime:', startTime);

  const allData = metarData.filter(item => item.metar_observation_time)
    .sort((a, b) => a.metar_observation_time - b.metar_observation_time);
  const filteredData = allData.filter(item =>
    item.metar_observation_time >= startTime && item.metar_observation_time <= latestTime
  );

  console.log('过滤后数据条数:', filteredData.length);
  console.log('过滤后数据示例:', filteredData.slice(0, 2));

  if (allData.length === 0) {
    const ink = airportDetailChartInk();
    airportDetailChart.chart.setOption({
      title: {
        text: '暂无历史数据',
        subtext: '需要等待系统收集更多METAR数据',
        left: 'center',
        top: 'center',
        textStyle: { color: ink.empty, fontSize: 14 },
        subtextStyle: { color: ink.emptySub, fontSize: 11 }
      }
    });
    return;
  }

  // 准备图表数据
  const timeData = allData.map(item => item.metar_observation_time);
  const windSpeedData = allData.map(item => item.metar_wind_speed_val);
  const gustData = allData.map(item => item.metar_gust_val);
  const visibilityData = allData.map(item => item.metar_visibility_val);
  const rvrData = allData.map(item => item.rvr_min_val);
  const cloudHeightData = allData.map(item => item.metar_min_cloud_height);
  const tempData = allData.map(item => item.metar_temp_val);
  const dewData = allData.map(item => (
    item.dewPoint != null ? item.dewPoint : parseMetarDewPoint(item.metar_dew_point)
  ));
  const pressureData = allData.map(item => item.airPressure);

  if (!airportDetailChart.selectedSeries || Object.keys(airportDetailChart.selectedSeries).length === 0) {
    airportDetailChart.selectedSeries = defaultAirportChartSelectedSeries();
  }

  const sel = airportDetailChart.selectedSeries;
  const showWeather = !!sel['天气现象'];
  const axisOrder = syncAirportChartAxisOrder(sel);
  const yIndexByGroup = {};
  axisOrder.forEach((id, index) => { yIndexByGroup[id] = index; });
  const hasAnySeriesSelected = axisOrder.length > 0 || showWeather;
  const ink = airportDetailChartInk();
  const singlePoint = allData.length === 1;

  function pushAirportChartSeries(list, name, groupId, data, style) {
    if (!sel[name]) return;
    const yAxisIndex = yIndexByGroup[groupId];
    if (yAxisIndex == null) return;
    if (singlePoint || style.forceScatter) {
      list.push({
        name,
        type: 'scatter',
        data,
        yAxisIndex,
        symbol: style.symbol || 'circle',
        symbolSize: style.symbolSize || (singlePoint ? 10 : 8),
        symbolRotate: style.symbolRotate,
        itemStyle: { color: style.color },
      });
      return;
    }
    list.push({
      name,
      type: 'line',
      data,
      smooth: true,
      yAxisIndex,
      showSymbol: true,
      symbol: style.symbol || 'circle',
      symbolSize: style.symbolSize || 6,
      itemStyle: { color: style.color },
      lineStyle: { color: style.color, width: 2, type: style.lineType },
    });
  }

  const series = [];
  pushAirportChartSeries(series, '平均风', 'wind', timeData.map((t, i) => [t, windSpeedData[i]]), { color: '#3498db' });
  pushAirportChartSeries(series, '阵风', 'wind', timeData.map((t, i) => [t, gustData[i]]), {
    color: '#3498db', forceScatter: true, symbol: 'triangle', symbolSize: 14, symbolRotate: 180,
  });
  pushAirportChartSeries(series, '能见度', 'vis', timeData.map((t, i) => [t, visibilityData[i]]), { color: '#e74c3c', lineType: 'dashed' });
  pushAirportChartSeries(series, 'RVR', 'vis', timeData.map((t, i) => [t, rvrData[i]]), { color: '#e74c3c' });
  pushAirportChartSeries(series, '云底高', 'cloud', timeData.map((t, i) => [t, cloudHeightData[i]]), { color: '#9b59b6' });
  pushAirportChartSeries(series, '气温', 'temp', timeData.map((t, i) => [t, tempData[i]]), { color: '#f39c12' });
  pushAirportChartSeries(series, '露点温度', 'temp', timeData.map((t, i) => [t, dewData[i]]), { color: '#27ae60' });
  pushAirportChartSeries(series, '气压', 'pressure', timeData.map((t, i) => [t, pressureData[i]]), { color: '#00cec9' });

  // 配置图表选项
  const option = {
    title: !hasAnySeriesSelected ? {
      text: '点击图例显示实况要素',
      left: 'center',
      top: 'middle',
      textStyle: { color: ink.empty, fontSize: 13, fontWeight: 'normal' }
    } : (allData.length === 1 ? {
      text: '数据点较少，趋势图待更多数据后显示',
      left: 'center',
      top: 'middle',
      textStyle: { color: '#f39c12', fontSize: 11 }
    } : { text: '' }),
    tooltip: {
      trigger: 'axis',
      formatter: function (params) {
        if (!params || !params.length) return '';
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
      show: false,
      selected: airportDetailChart.selectedSeries,
    },
    grid: buildAirportChartGrid(axisOrder, airportChartWeatherGridBottom(showWeather)),
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
        color: ink.muted,
        fontSize: 10
      },
      axisTick: {
        show: true
      },
      axisLine: { lineStyle: { color: ink.faint } },
      splitLine: { show: true, lineStyle: { color: ink.split } }
    },
    yAxis: buildAirportChartYAxes(axisOrder, ink, hasAnySeriesSelected),
    series
  };

  // 保存当前过滤数据，供天气标签渲染和 resize 时使用
  airportDetailChart.allData = allData;
  airportDetailChart.filteredData = filteredData;
  airportDetailChart.chart.setOption(option, { replaceMerge: ['yAxis', 'series'] });
  renderAirportChartLegend();

  // 在图表处理完新选项后渲染天气现象标签
  setTimeout(() => {
    if (airportDetailChart.chart) {
      renderWeatherLabels(airportDetailChart.chart);
    }
  }, 0);

  // 监听图例选择变化
  airportDetailChart.chart.off('legendselectchanged');
  airportDetailChart.chart.on('legendselectchanged', function (params) {
    if (params.name === '平均风' || params.name === '阵风') {
      const isSelected = params.selected[params.name];
      params.selected['平均风'] = isSelected;
      params.selected['阵风'] = isSelected;
    }
    if (params.name === '能见度' || params.name === 'RVR') {
      const isSelected = params.selected[params.name];
      params.selected['能见度'] = isSelected;
      params.selected['RVR'] = isSelected;
    }

    airportDetailChart.selectedSeries = Object.assign(defaultAirportChartSelectedSeries(), params.selected);
    syncAirportChartAxisOrder(airportDetailChart.selectedSeries);
    updateAirportDetailChart(airportCode);
  });
}

function splitWeatherCodes(text) {
  if (!text) return [];
  if (Array.isArray(text)) return text.filter(Boolean);
  return String(text).split(/[,\s]+/).map((item) => item.trim()).filter(Boolean);
}

function pushWeatherLabel(graphicItems, idx, xPixel, y, text, tilted) {
  graphicItems.push({
    id: `wl_${idx}`,
    type: 'text',
    z: 5,
    x: xPixel,
    y,
    rotation: tilted ? Math.PI / 4 : 0,
    style: {
      text,
      fontSize: tilted ? 12 : 11,
      fill: airportDetailChartInk().weather,
      align: tilted ? 'right' : 'center',
      verticalAlign: 'top',
    },
  });
}

function renderWeatherLabels(chart) {
  const chartDom = document.getElementById('airport-detail-chart');
  if (!chartDom || !chart) return;

  const selected = airportDetailChart.selectedSeries || defaultAirportChartSelectedSeries();
  const graphicItems = [];
  let idx = 0;
  if (selected['天气现象']) {
    const containerHeight = chartDom.offsetHeight;
    const bottom = airportChartWeatherGridBottom(true);
    const tilted = airportChartUsesTiltedWeather();
    const hourly = airportChartUsesHourlyWeather();
    const anchorY = containerHeight - bottom + (tilted ? 16 : 28);
    const latestTime = airportDetailChart.latestTime;
    const startTime = latestTime - clampAirportChartHours(airportDetailChart.hours) * 3600000;
    const lineHeight = 13;
    if (hourly) {
      (airportDetailChart.hourlyWeather || []).forEach((slot) => {
        const hour = slot && slot.hour;
        const codes = splitWeatherCodes(slot && slot.weather);
        if (hour == null || !codes.length) return;
        if (latestTime && (hour < startTime || hour > latestTime)) return;
        const xPixel = chart.convertToPixel({ xAxisIndex: 0 }, hour);
        if (xPixel == null || isNaN(xPixel)) return;
        if (tilted) {
          pushWeatherLabel(graphicItems, idx++, xPixel, anchorY, codes.join(' '), true);
        } else {
          codes.forEach((code, line) => {
            pushWeatherLabel(graphicItems, idx++, xPixel, anchorY + line * lineHeight, code, false);
          });
        }
      });
    } else {
      const source = airportDetailChart.filteredData || airportDetailChart.historyData || [];
      source.forEach((item) => {
        const codes = splitWeatherCodes(item && item.metar_weather);
        const time = item && item.metar_observation_time;
        if (!codes.length || time == null) return;
        if (latestTime && (time < startTime || time > latestTime)) return;
        const xPixel = chart.convertToPixel({ xAxisIndex: 0 }, time);
        if (xPixel == null || isNaN(xPixel)) return;
        codes.forEach((code, line) => {
          pushWeatherLabel(graphicItems, idx++, xPixel, anchorY + line * lineHeight, code, false);
        });
      });
    }
  }

  // 清除上次渲染中多余的标签（切换到更短时段时数量可能减少）
  const prevCount = airportDetailChart.weatherLabelCount || 0;
  for (let i = idx; i < prevCount; i++) {
    graphicItems.push({ id: `wl_${i}`, $action: 'remove' });
  }
  airportDetailChart.weatherLabelCount = idx;

  chart.setOption({ graphic: graphicItems });
}


function formatTrendTableHour(ms) {
  const date = new Date(ms);
  const hour = window.displayTimezone === 'UTC' ? date.getUTCHours() : date.getHours();
  return String(hour).padStart(2, '0');
}

function formatTrendTableNum(value, digits) {
  if (value == null || value === '') return '';
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  if (digits === 0) return String(Math.round(number));
  return String(Number(number.toFixed(digits)));
}

function trendTableWindHtml(dir) {
  if (dir == null || dir === '') return '';
  const text = String(dir).toUpperCase();
  if (text === 'VRB') {
    return '<span class="airport-trend-wind" title="VRB"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-dasharray="2.2 2.2"/></svg></span>';
  }
  const deg = Number(text);
  if (!Number.isFinite(deg)) return '';
  const rotate = (deg + 180) % 360;
  return `<span class="airport-trend-wind" title="${text}"><svg viewBox="0 0 24 24" style="transform:rotate(${rotate}deg)" aria-hidden="true"><path d="M12 3 L16 11 H13 V21 H11 V11 H8 Z" fill="currentColor"/></svg></span>`;
}

function setAirportTrendTableMessage(text) {
  const wrap = document.getElementById('airport-trend-table-wrap');
  if (wrap) wrap.innerHTML = `<div class="airport-trend-table-empty">${text}</div>`;
}

function renderAirportTrendTable(payload) {
  const wrap = document.getElementById('airport-trend-table-wrap');
  if (!wrap) return;
  const hours = (payload && payload.hours) || [];
  const rows = (payload && payload.rows) || {};
  if (!hours.length) {
    setAirportTrendTableMessage('暂无过去 24 小时实况');
    return;
  }
  const weatherCols = rows.weather || hours.map(() => []);
  const weatherMinRows = 5;
  const weatherRowCount = Math.max(weatherMinRows, ...weatherCols.map((item) => (item || []).length));
  const cell = (values, index, digits) => formatTrendTableNum((values || [])[index], digits);
  let html = '<table class="airport-trend-table"><thead><tr><th class="trend-table-label"></th>';
  hours.forEach((hour) => {
    html += `<th>${formatTrendTableHour(hour)}</th>`;
  });
  html += '</tr></thead><tbody>';
  const line = (label, values, digits) => {
    let out = `<tr><th class="trend-table-label">${label}</th>`;
    hours.forEach((_, index) => {
      out += `<td>${cell(values, index, digits)}</td>`;
    });
    out += '</tr>';
    return out;
  };
  html += line('能见度 (m)', rows.visibility, 0);
  html += line('RVR (m)', rows.rvr, 0);
  html += line('温度 (℃)', rows.temp, 1);
  html += line('露点温度 (℃)', rows.dewpoint, 1);
  html += '<tr><th class="trend-table-label">风向 (°)</th>';
  hours.forEach((_, index) => {
    html += `<td>${trendTableWindHtml((rows.wind_dir || [])[index])}</td>`;
  });
  html += '</tr>';
  html += line('平均风速 (mps)', rows.wind_speed, 1);
  html += line('阵风风速 (mps)', rows.gust, 1);
  html += line('气压 (hPa)', rows.pressure, 1);
  for (let rowIndex = 0; rowIndex < weatherRowCount; rowIndex += 1) {
    html += '<tr>';
    if (rowIndex === 0) {
      html += `<th class="trend-table-label" rowspan="${weatherMinRows}">天气现象</th>`;
    } else if (rowIndex >= weatherMinRows) {
      html += '<th class="trend-table-label"></th>';
    }
    hours.forEach((_, index) => {
      html += `<td>${((weatherCols[index] || [])[rowIndex] || '')}</td>`;
    });
    html += '</tr>';
  }
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function loadAirportTrendTable(airportCode) {
  if (!airportCode) return;
  setAirportTrendTableMessage('正在准备过去 24 小时实况表...');
  waitAirportDetailHistory(airportCode).finally(() => {
    if (currentDetailAirportCode !== airportCode) return;
    fetch(`/${currentTimeMode}/api/airport/${airportCode}/metar-trend-table/`, {
      headers: airportDetailAuthHeaders(),
    })
      .then((response) => response.json())
      .then((data) => {
        if (currentDetailAirportCode !== airportCode) return;
        if (data.success && data.data) {
          renderAirportTrendTable(data.data);
        } else {
          setAirportTrendTableMessage('读取实况趋势表失败');
        }
      })
      .catch((error) => {
        console.error('请求实况趋势表失败:', error);
        setAirportTrendTableMessage('读取实况趋势表失败');
      });
  });
}

// 异步加载历史 METAR 数据并刷新图表
function loadMetarHistoryData(airportCode) {
  waitAirportDetailHistory(airportCode).finally(() => {
    if (airportDetailChart.airportCode !== airportCode) return;
    fetch(`/${currentTimeMode}/api/airport/${airportCode}/metar-history/`, {
      headers: airportDetailAuthHeaders(),
    })
      .then(response => response.json())
      .then(data => {
        if (data.success && Array.isArray(data.data) && data.data.length > 0) {
          airportDetailChart.historyData = data.data;
          airportDetailChart.hourlyWeather = data.hourly_weather || [];
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
  const showContact = canShowContactInfo();

  const leftHtml = `
        <div class="airport-info-left">
          <div class="info-item">
            <span class="info-label">日出:</span>
            <span class="info-value" id="search-sunrise-${code}">--:--</span>
          </div>
          <div class="info-item">
            <span class="info-label">日落:</span>
            <span class="info-value" id="search-sunset-${code}">--:--</span>
          </div>
          <div class="info-item">
            <span class="info-label">跑道:</span>
            <span class="info-value" id="search-runway-${code}">--</span>
          </div>
        </div>`;
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

  const metarHTML = (reportsArePlain() && typeof plainDetailMetarRow === 'function')
    ? plainDetailMetarRow(airport)
    : '';

  return `
    <div class="airport-data-section">
      <div id="search-block-metar-${code}" class="plain-detail-metar-wrap"${reportsArePlain() ? '' : ' hidden'}>${metarHTML}</div>
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
async function showAirportSearchMulti(airports) {
  const container = document.getElementById('airport-search-list');
  if (!container) return;
  await ensurePlainScriptIfNeeded();

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
    if (reportsArePlain() && typeof ensurePlainForAirports === 'function') {
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
    loadAirportDetailTheme();
    bindAirportDetailExtraSwitch();
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
