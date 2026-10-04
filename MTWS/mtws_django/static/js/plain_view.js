/**
 * 中文（明语）模式：机场四字代码 + 名称一列，右侧实况 / 预报两行。
 *
 * 机场清单、区域与告警等级筛选、排序全部沿用主页已有的 filteredAirportData；
 * 翻译分别走 /plain/taf-batch/ 与 /plain/metar-batch/，后端读最小单元 JSON 列现译现返回。
 * 四字代码可点开详情页，详情页里甘特条带与实况/预报报文区同样中文化。
 */

// code → { key, translation }，key 为该机场预报的发报时间，用来判断是否需要重取
const _plainTranslations = {};
const _plainMetars = {};
const _plainInflight = new Set();
const _plainMetarInflight = new Set();
let _plainActive = false;

function startPlainView() {
  _plainActive = true;
  // 数据还没到就保留面板里的「正在加载数据」，等 applyFilters 首次带数据过来
  const hasData = typeof airportData !== 'undefined' && airportData && airportData.length;
  if (hasData && typeof applyFilters === 'function') applyFilters();
}

function stopPlainView() {
  _plainActive = false;
}

function _plainPanel() {
  return document.getElementById('plain-panel');
}

function _plainTz() {
  return window.displayTimezone === 'UTC' ? 'UTC' : 'CST';
}

function _plainApiTz() {
  return `&tz=${encodeURIComponent(_plainTz())}`;
}

function _metarKeyOf(airport) {
  const metar = (airport.metar_data && airport.metar_data.length) ? airport.metar_data[0] : null;
  if (!metar) return '';
  return String(metar.sqc || metar.metar_observation_time || '');
}

function _tafKeyOf(airport) {
  const taf = (airport.taf_data && airport.taf_data.length) ? airport.taf_data[0] : null;
  if (!taf) return '';
  return String(taf.id || taf.taf_observation_time || '');
}

/** 主页筛选/排序后的机场列表 → 中文模式行 */
function renderPlainView(airports) {
  const panel = _plainPanel();
  if (!panel) return;

  if (!airports || !airports.length) {
    panel.innerHTML = '<div class="plain-panel-empty">暂无符合条件的机场数据</div>';
    return;
  }

  panel.innerHTML = airports.map(createPlainRow).join('');
  paintPlainForecasts(airports);
  paintPlainMetars(airports);

  const stale = airports.filter((a) => {
    const cached = _plainTranslations[a.airport_4code];
    return !cached || cached.key !== _tafKeyOf(a) || cached.tz !== _plainTz();
  });
  const staleMetar = airports.filter((a) => {
    const cached = _plainMetars[a.airport_4code];
    return !cached || cached.key !== _metarKeyOf(a) || cached.tz !== _plainTz();
  });
  if (stale.length) {
    fetchPlainTranslations(stale.map((a) => a.airport_4code));
  }
  if (staleMetar.length) {
    fetchPlainMetars(staleMetar.map((a) => a.airport_4code));
  }
}

function createPlainRow(airport) {
  const code = airport.airport_4code;
  const level = (typeof getHighestAlertLevel === 'function') ? getHighestAlertLevel(airport) : 'N';
  const codeStyle = (level && level !== 'N' && typeof getAlertColor === 'function')
    ? ` style="background-color: ${getAlertColor(level)};"` : '';
  const codeClass = (level && level !== 'N') ? ' plain-code-alert' : '';

  return `
    <div class="plain-row" data-code="${code}">
      <div class="plain-airport" oncontextmenu="handleAirportRightClick(event, '${code}')">
        <div class="plain-code${codeClass}"${codeStyle} onclick="showAirportDetail('${code}')">${code}</div>
        <div class="plain-name">${airport.airport_name || '机场名称未配置'}</div>
      </div>
      <div class="plain-body">
        <div class="plain-line plain-line-metar">
          <span class="plain-tag">实况</span>
          <span class="plain-text" data-plain-metar="${code}">
            <span class="plain-loading">翻译中...</span>
          </span>
        </div>
        <div class="plain-line plain-line-taf">
          <span class="plain-tag">预报</span>
          <span class="plain-text" data-plain-taf="${code}">
            <span class="plain-loading">翻译中...</span>
          </span>
        </div>
      </div>
    </div>
  `;
}

/** 用缓存里的翻译填充预报行；缓存未命中时保留“翻译中” */
function paintPlainForecasts(airports) {
  (airports || []).forEach((airport) => {
    const code = airport.airport_4code;
    const cell = document.querySelector(`[data-plain-taf="${code}"]`);
    if (!cell) return;
    const cached = _plainTranslations[code];
    if (!cached || cached.key !== _tafKeyOf(airport) || cached.tz !== _plainTz()) return;
    const translation = cached.translation;
    if (!translation) {
      cell.innerHTML = '<span class="plain-empty">没有有效的TAF数据</span>';
      return;
    }
    cell.innerHTML = translation.html || '<span class="plain-empty">无可翻译要素</span>';
  });
}

function _airportByCode(code) {
  if (typeof searchAirportCache !== 'undefined' && searchAirportCache && searchAirportCache[code]) {
    return searchAirportCache[code];
  }
  if (typeof airportData !== 'undefined' && airportData) {
    return airportData.find((a) => a.airport_4code === code) || null;
  }
  return null;
}

function ensurePlainForAirports(airports) {
  if (window._viewMode !== 'plain' || !airports || !airports.length) return;
  const staleTaf = [];
  const staleMetar = [];
  airports.forEach((airport) => {
    if (!airport || !airport.airport_4code) return;
    const code = airport.airport_4code;
    const tafCached = _plainTranslations[code];
    if (!tafCached || tafCached.key !== _tafKeyOf(airport) || tafCached.tz !== _plainTz()) staleTaf.push(code);
    const metarCached = _plainMetars[code];
    if (!metarCached || metarCached.key !== _metarKeyOf(airport) || metarCached.tz !== _plainTz()) staleMetar.push(code);
  });
  if (staleTaf.length) fetchPlainTranslations(staleTaf);
  if (staleMetar.length) fetchPlainMetars(staleMetar);
}

function paintPlainDetailMetar(airport) {
  const wrap = document.getElementById('airport-detail-plain-metar');
  if (!wrap) return;
  if (window._viewMode !== 'plain' || !airport || typeof plainDetailMetarRow !== 'function') {
    wrap.hidden = true;
    wrap.innerHTML = '';
    return;
  }
  wrap.hidden = false;
  wrap.innerHTML = plainDetailMetarRow(airport);
}

function paintSearchBlockMetar(code, airport) {
  const wrap = document.getElementById(`search-block-metar-${code}`);
  if (!wrap) return;
  if (window._viewMode !== 'plain' || !airport || typeof plainDetailMetarRow !== 'function') {
    wrap.hidden = true;
    wrap.innerHTML = '';
    return;
  }
  wrap.hidden = false;
  wrap.innerHTML = plainDetailMetarRow(airport);
}

function _repaintAirportRow(code) {
  if (window._viewMode !== 'plain' || typeof createAirportRowForDetail !== 'function') return;
  const airport = _airportByCode(code);
  if (!airport) return;

  const detailMain = document.getElementById('airport-detail-main');
  const detailModal = document.getElementById('airport-detail-modal');
  if (detailMain && detailModal && detailModal.style.display === 'block'
      && typeof currentDetailAirportCode !== 'undefined' && currentDetailAirportCode === code) {
    paintPlainDetailMetar(airport);
    const detailScope = 'detail';
    detailMain.innerHTML = createAirportRowForDetail(airport, { marksScope: detailScope });
    const airportRow = detailMain.querySelector('.airport-row');
    if (airportRow && typeof updateAirportGridForModal === 'function') {
      updateAirportGridForModal(airportRow);
    }
    if (typeof renderNwpOverlayForAirportDetail === 'function') {
      renderNwpOverlayForAirportDetail();
    }
  }

  const searchMain = document.getElementById(`search-block-main-${code}`);
  if (searchMain) {
    paintSearchBlockMetar(code, airport);
    searchMain.innerHTML = createAirportRowForDetail(airport, { marksScope: 'search:' + String(code).toUpperCase() });
    const airportRow = searchMain.querySelector('.airport-row');
    if (airportRow && typeof updateAirportGridForModal === 'function') {
      updateAirportGridForModal(airportRow);
    }
    if (typeof renderNwpOverlayForAirportSearch === 'function') {
      renderNwpOverlayForAirportSearch(code);
    }
  }
}

function refreshPlainTimezone() {
  Object.keys(_plainTranslations).forEach((code) => {
    if (_plainTranslations[code]) _plainTranslations[code].tz = '';
  });
  Object.keys(_plainMetars).forEach((code) => {
    if (_plainMetars[code]) _plainMetars[code].tz = '';
  });
  if (window._viewMode !== 'plain') return;
  if (_plainActive && typeof filteredAirportData !== 'undefined') {
    renderPlainView(filteredAirportData);
  }
  const openCodes = [];
  if (typeof currentDetailAirportCode !== 'undefined' && currentDetailAirportCode) {
    const modal = document.getElementById('airport-detail-modal');
    if (modal && modal.style.display === 'block') openCodes.push(currentDetailAirportCode);
  }
  document.querySelectorAll('.airport-search-block[data-code]').forEach((el) => {
    const code = el.getAttribute('data-code');
    if (code) openCodes.push(code);
  });
  if (openCodes.length) {
    const airports = openCodes.map((code) => _airportByCode(code)).filter(Boolean);
    ensurePlainForAirports(airports);
  }
}

async function fetchPlainTranslations(wanted) {
  const codes = (wanted || []).filter((code) => !_plainInflight.has(code));
  if (!codes.length) return;
  codes.forEach((code) => _plainInflight.add(code));
  try {
    const url = `/${currentTimeMode}/api/plain/taf-batch/?codes=${encodeURIComponent(codes.join(','))}${_plainApiTz()}`;
    const response = await fetch(url, { headers: getRequestHeaders(), credentials: 'same-origin' });
    const payload = await response.json();
    if (!payload.success) {
      console.error('预报明语获取失败:', payload.error);
      _markPlainFailed(codes);
      return;
    }
    const data = payload.data || {};
    codes.forEach((code) => {
      const airport = _airportByCode(code);
      _plainTranslations[code] = {
        key: airport ? _tafKeyOf(airport) : '',
        tz: _plainTz(),
        translation: data[code] || null,
      };
    });
    if (_plainActive && typeof filteredAirportData !== 'undefined') {
      paintPlainForecasts(filteredAirportData);
    }
    codes.forEach((code) => _repaintAirportRow(code));
  } catch (err) {
    console.error('请求预报明语失败:', err);
    _markPlainFailed(codes);
  } finally {
    codes.forEach((code) => _plainInflight.delete(code));
  }
}

function _markPlainFailed(codes) {
  (codes || []).forEach((code) => {
    const cell = document.querySelector(`[data-plain-taf="${code}"]`);
    if (cell) cell.innerHTML = '<span class="plain-empty">翻译获取失败</span>';
  });
}

/** 用缓存里的翻译填充实况行 */
function paintPlainMetars(airports) {
  (airports || []).forEach((airport) => {
    const code = airport.airport_4code;
    const cell = document.querySelector(`[data-plain-metar="${code}"]`);
    if (!cell) return;
    const cached = _plainMetars[code];
    if (!cached || cached.key !== _metarKeyOf(airport) || cached.tz !== _plainTz()) return;
    const translation = cached.translation;
    if (!translation) {
      cell.innerHTML = '<span class="plain-empty">没有有效的METAR数据</span>';
      return;
    }
    cell.innerHTML = translation.html || '<span class="plain-empty">无可翻译要素</span>';
  });
}

async function fetchPlainMetars(wanted) {
  const codes = (wanted || []).filter((code) => !_plainMetarInflight.has(code));
  if (!codes.length) return;
  codes.forEach((code) => _plainMetarInflight.add(code));
  try {
    const url = `/${currentTimeMode}/api/plain/metar-batch/?codes=${encodeURIComponent(codes.join(','))}${_plainApiTz()}`;
    const response = await fetch(url, { headers: getRequestHeaders(), credentials: 'same-origin' });
    const payload = await response.json();
    if (!payload.success) {
      console.error('实况明语获取失败:', payload.error);
      _markPlainMetarFailed(codes);
      return;
    }
    const data = payload.data || {};
    codes.forEach((code) => {
      const airport = _airportByCode(code);
      _plainMetars[code] = {
        key: airport ? _metarKeyOf(airport) : '',
        tz: _plainTz(),
        translation: data[code] || null,
      };
    });
    if (_plainActive && typeof filteredAirportData !== 'undefined') {
      paintPlainMetars(filteredAirportData);
    }
    codes.forEach((code) => _repaintAirportRow(code));
  } catch (err) {
    console.error('请求实况明语失败:', err);
    _markPlainMetarFailed(codes);
  } finally {
    codes.forEach((code) => _plainMetarInflight.delete(code));
  }
}

function _markPlainMetarFailed(codes) {
  (codes || []).forEach((code) => {
    const cell = document.querySelector(`[data-plain-metar="${code}"]`);
    if (cell) cell.innerHTML = '<span class="plain-empty">翻译获取失败</span>';
  });
}

function _refreshPlainDetailWeather() {
  if (typeof currentDetailAirportCode === 'undefined' || !currentDetailAirportCode) return;
  _repaintAirportRow(currentDetailAirportCode);
}

function plainDetailMetarRow(airport) {
  const code = airport && airport.airport_4code;
  const latestMetar = airport && airport.metar_data && airport.metar_data[0];
  const cached = code ? _plainMetars[code] : null;
  const inner = (cached && cached.translation && cached.translation.html)
    ? cached.translation.html
    : (latestMetar
      ? '<span class="plain-empty">翻译中...</span>'
      : '<span class="plain-empty">无METAR数据</span>');
  const isAlerted = typeof alertedAirports !== 'undefined' && alertedAirports.has(code);
  const alertClass = isAlerted ? ' import-alerted' : '';
  const alertTitle = isAlerted ? ' title="【过期实况数据，注意提醒】"' : '';
  return `<div class="plain-detail-metar${alertClass}"${alertTitle}>
    <div class="plain-detail-section-title">实况</div>
    <div class="plain-detail-metar-body">${inner}</div>
  </div>
  <div class="plain-detail-section-title plain-detail-taf-title">预报</div>`;
}

/**
 * 甘特条带中文文本：key 为 'SUBJECT' 或 '类型|开始时次'，
 * 与 taf_elements 侧 _bar_key 生成的键一致。
 */
function plainGanttText(taf, key) {
  if (!taf || !key) return '';
  const cached = _plainTranslations[taf.airport_4code];
  const bars = cached && cached.translation ? cached.translation.bars : null;
  if (!bars) return '';
  const bar = bars[key];
  return bar ? (bar.text || '') : '';
}

window.startPlainView = startPlainView;
window.stopPlainView = stopPlainView;
window.renderPlainView = renderPlainView;
window.plainGanttText = plainGanttText;
window.plainDetailMetarRow = plainDetailMetarRow;
window.paintPlainDetailMetar = paintPlainDetailMetar;
window.refreshPlainTimezone = refreshPlainTimezone;
window.fetchPlainMetars = fetchPlainMetars;
window.fetchPlainTranslations = fetchPlainTranslations;
window.ensurePlainForAirports = ensurePlainForAirports;
