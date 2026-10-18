/**
 * settings.js — 设置弹窗逻辑
 * 依赖 main.js 中的全局变量：currentTimeMode, currentToken, currentUserCode
 * 依赖 main.js 中的函数：showModal, hideModal
 */
(function () {
  'use strict';

  // ========== 状态 ==========
  let areaOptions = {};          // { '国内': [...], '国际': [...] }
  let airportEditCode = null;    // 正在编辑的机场四字代码，null=新增
  let airportCurrentCode = null; // 当前查询的四字代码
  let airportViewData = null;    // 当前查询结果，取消编辑时回到这一行
  let settingsScope = '';
  let currentSettingsTab = 'airport-info';

  // ========== 工具 ==========
  function apiUrl(path) {
    const mode = (typeof currentTimeMode !== 'undefined' ? currentTimeMode : null) || window.currentTimeMode || 'current';
    return `/${mode}/api/${path}`;
  }

  function getHeaders() {
    const h = { 'Content-Type': 'application/json' };
    const token = (typeof currentToken !== 'undefined' ? currentToken : null) || window.currentToken;
    const userCode = (typeof currentUserCode !== 'undefined' ? currentUserCode : null) || window.currentUserCode;
    if (token) h['Authorization'] = `Bearer ${token}`;
    if (userCode) h['X-User-Code'] = userCode;
    window.__settingsScope = settingsScope;
    if (settingsScope === 'default') h['X-Settings-Scope'] = 'default';
    return h;
  }

  function exitSettingsTemplate() {
    if (settingsScope !== 'default') return;
    settingsScope = '';
    window.__settingsScope = '';
    const toggle = document.getElementById('settings-default-toggle');
    if (toggle) toggle.textContent = '编辑默认模板';
    paintDefaultBanner();
    const modal = document.getElementById('settings-modal');
    if (modal && window.getComputedStyle(modal).display !== 'none') loadTab(currentSettingsTab);
  }
  window.exitSettingsTemplate = exitSettingsTemplate;

  function applyScope(res) {
    if (res && Object.prototype.hasOwnProperty.call(res, 'can_edit_default')) {
      window.__adminUnlocked = !!res.can_edit_default;
    }
    const unlocked = !!window.__adminUnlocked;
    const groupBtn = document.getElementById('superuser-group-btn');
    const toggle = document.getElementById('settings-default-toggle');
    if (groupBtn) groupBtn.style.display = unlocked ? '' : 'none';
    if (toggle) {
      toggle.style.display = unlocked ? '' : 'none';
      toggle.textContent = settingsScope === 'default' ? '返回我的设置' : '编辑默认模板';
    }
    paintDefaultBanner();
    if (res && Object.prototype.hasOwnProperty.call(res, 'allow_restore')) {
      const allow = !!res.allow_restore;
      document.querySelectorAll('.settings-restore-btn').forEach((btn) => {
        btn.style.display = allow ? '' : 'none';
      });
    }
  }
  window.applySettingsScope = applyScope;

  async function apiFetch(url, options) {
    const opts = Object.assign({}, options);
    opts.headers = Object.assign(getHeaders(), (options && options.headers) || {});
    const res = await fetch(url, opts);
    return res.json();
  }

  async function touchAdminSession() {
    if (!window.__adminUnlocked) return;
    try {
      const res = await apiFetch(apiUrl('access/admin/touch/'), { method: 'POST', body: '{}' });
      if (res && res.admin_unlocked === false) {
        window.__adminUnlocked = false;
        applyScope({ can_edit_default: false });
        exitSettingsTemplate();
      }
    } catch (err) { /* 顺延失败时保留当前会话，等下一次操作再试 */ }
  }

  function showMsg(elId, text, type) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = text || '';
    el.className = 'settings-msg' + (text && type ? ' ' + type : '');
    if (text) {
      setTimeout(() => {
        if (el.textContent !== text) return;
        el.textContent = '';
        el.className = 'settings-msg';
      }, 4000);
    }
  }

  function paintDefaultBanner() {
    const banner = document.getElementById('settings-default-banner');
    if (banner) banner.hidden = settingsScope !== 'default';
  }

  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ========== Toggle 3-segment track ==========
  function initTrack(trackEl) {
    const segs = trackEl.querySelectorAll('.settings-track-seg');
    const thumb = trackEl.querySelector('.settings-track-thumb');
    const idx = { R: 0, Y: 1, G: 2 };

    function setVal(val) {
      trackEl.dataset.value = val;
      const i = idx[val] ?? 1;
      const colors = window.MTWS_ALERT_COLORS || {};
      thumb.style.background = (colors[val] && colors[val].hex) || '';
      thumb.style.transform = `translateX(${i * 100}%)`;
    }

    setVal(trackEl.dataset.value || 'Y');

    trackEl.addEventListener('click', function (e) {
      const rect = trackEl.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const seg = Math.floor(x / rect.width * 3);
      const vals = ['R', 'Y', 'G'];
      setVal(vals[Math.min(2, Math.max(0, seg))]);
    });

    return { setVal, getVal: () => trackEl.dataset.value };
  }

  // ========== Tab switching ==========
  function switchTab(tabName) {
    if (tabName !== currentSettingsTab && !confirmLeavePrefixEdit()) return Promise.resolve();
    if (tabName === currentSettingsTab && prefixEditingId) return Promise.resolve();
    document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.settings-tab-pane').forEach(p => p.classList.remove('active'));
    const btn = document.querySelector(`.settings-tab[data-tab="${tabName}"]`);
    const pane = document.getElementById(`settings-pane-${tabName}`);
    if (btn) btn.classList.add('active');
    if (pane) pane.classList.add('active');
    currentSettingsTab = tabName;
    touchAdminSession();
    return loadTab(tabName);
  }

  async function loadTab(tabName) {
    switch (tabName) {
      case 'airport-info': await loadAirportInfo(); break;
      case 'prefix-area': await loadPrefixAreas(); break;
      case 'taf-import': await loadTafImport(); break;
      case 'data-refresh-timer': await loadTimers(); break;
      case 'popup': await loadPopupSettings(); break;
      case 'alert-thresholds': await loadAlertThresholds(); break;
      case 'weather-type': await loadWeatherType(); break;
      case 'weather-alert': await loadWeatherAlert(); break;
      case 'radar-alert': await loadRadarAlertSettings(); break;
      case 'map-style': await loadMapStyleSettings(); break;
      case 'trend-alert':
        if (window.TrendAlertSettings) await window.TrendAlertSettings.load();
        break;
    }
  }

  // ========== Tab1: 机场信息（按四字代码查询） ==========
  async function loadAirportInfo() {
    await refreshAreaOptionsCache();
    const input = document.getElementById('airport-search-input');
    if (input) input.value = '';
    const area = document.getElementById('airport-result-area');
    if (area) area.innerHTML = '';
    airportViewData = null;
    airportEditCode = null;
    airportCurrentCode = null;
  }

  function airportRecordRow(label, valueHtml) {
    return `<div class="airport-record-row"><div class="airport-record-label">${label}</div><div class="airport-record-value">${valueHtml}</div></div>`;
  }

  function airportClassToggle(isIntl, locked) {
    return `<label class="settings-toggle-label">
      <input type="checkbox" id="af-classification-chk" class="settings-toggle-chk"${isIntl ? ' checked' : ''}${locked ? ' disabled' : ''}>
      <span class="settings-toggle-track">
        <span class="settings-toggle-side">国内</span>
        <span class="settings-toggle-side">国际</span>
        <span class="settings-toggle-thumb"></span>
      </span>
    </label>`;
  }

  function renderAirportCard(data, editing, presetCode) {
    const area = document.getElementById('airport-result-area');
    if (!area) return;
    const val = (v) => (v == null ? '' : escHtml(v).replace(/"/g, '&quot;'));
    const lock = editing ? '' : ' disabled';
    const code = data ? data.airport_4code : (presetCode || '');
    const classification = data ? (data.classification || '国内') : '国内';
    const codeLocked = !editing || !!data || !!presetCode;
    const input = (id, attrs, value) => `<input id="${id}" class="settings-input" ${attrs}${lock} value="${value}">`;
    const actions = editing
      ? `<button type="button" class="settings-save-inline-btn" id="airport-save-btn">保存</button>
         <button type="button" class="settings-cancel-inline-btn" id="airport-cancel-btn">取消</button>`
      : `<button type="button" class="settings-edit-btn" onclick="SettingsModal.editAirport('${escHtml(code)}')">编辑</button>
         <button type="button" class="settings-del-btn" onclick="SettingsModal.deleteAirport('${escHtml(code)}')">删除</button>`;
    area.innerHTML = `
      <div class="airport-record${editing ? ' is-editing' : ''}">
        ${airportRecordRow('四字代码', `<input id="af-4code" class="settings-input" maxlength="4" style="text-transform:uppercase;" value="${val(code)}"${codeLocked ? ' disabled' : ''}>`)}
        ${airportRecordRow('名称', input('af-name', 'maxlength="100" placeholder="可留空"', val(data && data.airport_name)))}
        ${airportRecordRow('类别', airportClassToggle(classification === '国际', !editing))}
        ${airportRecordRow('区域', `<select id="af-area" class="settings-input settings-select"${lock}></select>`)}
        ${airportRecordRow('纬度', input('af-lat', 'type="number" step="any" placeholder="十进制度"', data && data.latitude != null ? data.latitude : ''))}
        ${airportRecordRow('经度', input('af-lon', 'type="number" step="any" placeholder="十进制度"', data && data.longitude != null ? data.longitude : ''))}
        ${airportRecordRow('三字代码', input('af-3code', 'maxlength="3" style="text-transform:uppercase;" placeholder="选填"', val(data && data.airport_3code)))}
        ${airportRecordRow('区号', input('af-area-code', 'maxlength="10" placeholder="选填"', val(data && data.area_code)))}
        ${airportRecordRow('预报电话', input('af-forecast-phone', 'maxlength="100" placeholder="选填"', val(data && data.forecast_phone)))}
        ${airportRecordRow('观测电话', input('af-obs-phone', 'maxlength="100" placeholder="选填"', val(data && data.observation_phone)))}
        ${airportRecordRow('其他联系方式', input('af-other-phone', 'maxlength="100" placeholder="选填"', val(data && data.other_phone)))}
        <div class="airport-record-actions">${actions}</div>
      </div>`;
    updateAreaSelect(classification, data ? data.area : '');
    const codeEl = document.getElementById('af-4code');
    if (codeEl && !codeEl.disabled) codeEl.focus();
  }

  function renderAirportResult(a) {
    renderAirportCard(a, false);
  }

  function renderAirportNotFound(code) {
    const area = document.getElementById('airport-result-area');
    if (!area) return;
    area.innerHTML = `
      <div class="loc-not-found">
        未找到 <strong>${escHtml(code)}</strong> 的机场信息
        <button class="settings-add-btn loc-add-inline-btn" onclick="SettingsModal.addAirportForCode('${escHtml(code)}')">+ 新增</button>
      </div>`;
  }

  async function searchAirport(presetCode, openForm) {
    const raw = presetCode != null ? presetCode : document.getElementById('airport-search-input').value;
    const code = String(raw || '').trim().toUpperCase();
    const input = document.getElementById('airport-search-input');
    if (input) input.value = code;
    if (code.length !== 4 || !/^[A-Z]{4}$/.test(code)) {
      showMsg('airport-msg', '请输入4位英文大写四字代码', 'error');
      return;
    }
    airportCurrentCode = code;
    airportEditCode = null;
    const res = await apiFetch(apiUrl(`settings/airport-info/${code}/`));
    if (res.success && res.data) {
      airportViewData = res.data;
      renderAirportResult(res.data);
      if (openForm) {
        airportEditCode = code;
        showAirportForm(res.data);
      }
    } else if (res && res.error && String(res.error).indexOf('未找到') !== 0) {
      airportViewData = null;
      const area = document.getElementById('airport-result-area');
      if (area) area.innerHTML = '';
      showMsg('airport-msg', res.error, 'error');
    } else {
      airportViewData = null;
      renderAirportNotFound(code);
      if (openForm) {
        airportEditCode = null;
        showAirportForm(null, code);
      }
    }
  }

  async function refreshAreaOptionsCache() {
    const res = await apiFetch(apiUrl('settings/prefix-area/'));
    if (!res.success) return;
    areaOptions = {};
    const seen = new Set();
    (res.data || []).forEach(o => {
      const key = `${o.classification}|${o.area}`;
      if (seen.has(key)) return;
      seen.add(key);
      if (!areaOptions[o.classification]) areaOptions[o.classification] = [];
      areaOptions[o.classification].push(o.area);
    });
  }

  function updateAreaSelect(classification, current) {
    const sel = document.getElementById('af-area');
    if (!sel) return;
    const areas = areaOptions[classification] || [];
    sel.innerHTML = '<option value="">请选择</option>' + areas.map(a => `<option value="${escHtml(a)}">${escHtml(a)}</option>`).join('');
    if (current) sel.value = current;
  }

  function showAirportForm(data, presetCode) {
    renderAirportCard(data, true, presetCode);
  }

  function hideAirportForm() {
    airportEditCode = null;
    if (airportViewData) renderAirportResult(airportViewData);
    else if (airportCurrentCode) renderAirportNotFound(airportCurrentCode);
    else {
      const area = document.getElementById('airport-result-area');
      if (area) area.innerHTML = '';
    }
  }

  async function saveAirport() {
    const code = document.getElementById('af-4code').value.trim().toUpperCase();
    const a3 = document.getElementById('af-3code').value.trim().toUpperCase();
    const name = document.getElementById('af-name').value.trim();
    const classificationChk = document.getElementById('af-classification-chk').checked;
    const classification = classificationChk ? '国际' : '国内';
    const area = document.getElementById('af-area').value;
    const lat = document.getElementById('af-lat').value;
    const lon = document.getElementById('af-lon').value;

    if (!code || code.length !== 4 || !/^[A-Z]{4}$/.test(code)) {
      showMsg('airport-msg', '机场四字代码必须为恰好4位英文大写字母', 'error'); return;
    }
    if (a3 && (a3.length !== 3 || !/^[A-Z]{3}$/.test(a3))) {
      showMsg('airport-msg', '机场三字代码必须为恰好3位英文大写字母', 'error'); return;
    }
    if (name.length > 100) {
      showMsg('airport-msg', '机场名称不能超过100个字符', 'error'); return;
    }
    if (lat !== '' && isNaN(lat)) { showMsg('airport-msg', '纬度须为数字', 'error'); return; }
    if (lon !== '' && isNaN(lon)) { showMsg('airport-msg', '经度须为数字', 'error'); return; }

    const payload = {
      airport_4code: code,
      airport_3code: a3 || null,
      airport_name: name,
      classification,
      area,
      latitude: lat === '' ? null : parseFloat(lat),
      longitude: lon === '' ? null : parseFloat(lon),
      area_code: document.getElementById('af-area-code').value.trim() || null,
      forecast_phone: document.getElementById('af-forecast-phone').value.trim() || null,
      observation_phone: document.getElementById('af-obs-phone').value.trim() || null,
      other_phone: document.getElementById('af-other-phone').value.trim() || null,
    };

    const isEdit = !!airportEditCode;
    const url = isEdit
      ? apiUrl(`settings/airport-info/${airportEditCode}/`)
      : apiUrl('settings/airport-info/');
    const method = isEdit ? 'PUT' : 'POST';

    const res = await apiFetch(url, { method, body: JSON.stringify(payload) });
    if (res.success) {
      showMsg('airport-msg', res.message, 'success');
      const savedCode = airportEditCode || code;
      hideAirportForm();
      await searchAirport(savedCode, false);
    } else {
      showMsg('airport-msg', res.error, 'error');
    }
  }

  // ========== Tab3: 数据自动更新 ==========
  let timerEditing = false;

  function paintTimerMode() {
    const pane = document.getElementById('settings-pane-data-refresh-timer');
    const modeBtn = document.getElementById('timer-mode-btn');
    const cancelBtn = document.getElementById('timer-cancel-btn');
    if (pane) pane.classList.toggle('is-editing', timerEditing);
    if (modeBtn) modeBtn.textContent = timerEditing ? '确定' : '编辑';
    if (cancelBtn) cancelBtn.disabled = !timerEditing;
    document.querySelectorAll('#timer-tbody .settings-timer-input').forEach((input) => {
      input.disabled = !timerEditing;
    });
  }

  async function loadTimers() {
    const res = await apiFetch(apiUrl('settings/data-refresh-timer/'));
    applyScope(res);
    if (!res.success) { showMsg('timer-msg', res.error, 'error'); return; }
    timerEditing = false;
    const tbody = document.getElementById('timer-tbody');
    tbody.innerHTML = res.data.map(t => `
      <tr id="timer-row-${t.id}" data-timer-id="${escHtml(t.id)}">
        <td>${escHtml(t.data_name)}</td>
        <td><input type="number" class="settings-timer-input" id="timer-init-${t.id}" value="${t.init_time ?? ''}" min="0" max="50" step="0.5" disabled></td>
        <td><input type="number" class="settings-timer-input" id="timer-interval-${t.id}" value="${t.interval ?? ''}" min="0.5" max="30" step="0.5" disabled></td>
      </tr>`).join('');
    paintTimerMode();
  }

  function readTimerRow(id) {
    const initVal = parseFloat(document.getElementById(`timer-init-${id}`).value);
    const intervalVal = parseFloat(document.getElementById(`timer-interval-${id}`).value);
    if (isNaN(initVal) || initVal < 0 || initVal > 50 || (initVal * 2) % 1 !== 0) {
      return { error: '初始时间需为0–50之间0.5的倍数' };
    }
    if (isNaN(intervalVal) || intervalVal < 0.5 || intervalVal > 30 || (intervalVal * 2) % 1 !== 0) {
      return { error: '更新间隔需为0.5–30之间0.5的倍数' };
    }
    return { init_time: initVal, interval: intervalVal };
  }

  async function saveTimer(id) {
    const row = readTimerRow(id);
    if (row.error) return { success: false, error: row.error };
    return apiFetch(apiUrl(`settings/data-refresh-timer/${id}/`), {
      method: 'PUT',
      body: JSON.stringify({ init_time: row.init_time, interval: row.interval })
    });
  }

  async function saveAllTimers() {
    const rows = [...document.querySelectorAll('#timer-tbody tr')];
    for (const tr of rows) {
      const res = await saveTimer(tr.dataset.timerId);
      if (!res || !res.success) {
        showMsg('timer-msg', (res && res.error) || '保存失败', 'error');
        return;
      }
    }
    timerEditing = false;
    paintTimerMode();
    showMsg('timer-msg', '保存成功', 'success');
  }

  function cancelTimerEdit() {
    timerEditing = false;
    loadTimers();
  }

  // ========== Tab4: 弹窗设置 ==========
  let opLevelTrack, parkLevelTrack;
  let popupEditing = false;

  function paintPopupMode() {
    const pane = document.getElementById('settings-pane-popup');
    const modeBtn = document.getElementById('popup-mode-btn');
    const cancelBtn = document.getElementById('popup-cancel-btn');
    if (pane) pane.classList.toggle('is-editing', popupEditing);
    if (modeBtn) modeBtn.textContent = popupEditing ? '确定' : '编辑';
    if (cancelBtn) cancelBtn.disabled = !popupEditing;
    ['pf-leeway', 'pf-trace-time'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.disabled = !popupEditing;
    });
    document.querySelectorAll('#settings-pane-popup .settings-track').forEach((track) => {
      track.classList.toggle('is-locked', !popupEditing);
    });
  }

  async function loadPopupSettings() {
    opLevelTrack = opLevelTrack || initTrack(document.getElementById('pf-op-level-track'));
    parkLevelTrack = parkLevelTrack || initTrack(document.getElementById('pf-park-level-track'));

    const res = await apiFetch(apiUrl('settings/popup/'));
    applyScope(res);
    if (!res.success) { showMsg('popup-msg', res.error, 'error'); return; }
    popupEditing = false;
    const d = res.data;
    document.getElementById('pf-leeway').value = d.operation_metar_popup_leeway ?? 0;
    document.getElementById('pf-trace-time').value = d.trace_time ?? 6;
    opLevelTrack.setVal(d.operation_metar_popup_level || 'Y');
    parkLevelTrack.setVal(d.parking_metar_popup_level || 'Y');
    paintPopupMode();
  }

  async function savePopupSettings() {
    const payload = {
      operation_metar_popup_leeway: parseInt(document.getElementById('pf-leeway').value) || 0,
      operation_metar_popup_level: opLevelTrack ? opLevelTrack.getVal() : 'Y',
      parking_metar_popup_level: parkLevelTrack ? parkLevelTrack.getVal() : 'Y',
      trace_time: parseInt(document.getElementById('pf-trace-time').value, 10),
    };

    const leeway = payload.operation_metar_popup_leeway;
    if (isNaN(leeway) || leeway < 0 || leeway > 9) {
      showMsg('popup-msg', '告警裕度需为0–9的整数', 'error'); return;
    }
    const traceTime = payload.trace_time;
    if (isNaN(traceTime) || traceTime < 0 || traceTime > 9) {
      showMsg('popup-msg', '追溯时间需为0–9的整数', 'error'); return;
    }

    const res = await apiFetch(apiUrl('settings/popup/'), {
      method: 'PUT',
      body: JSON.stringify(payload)
    });

    if (res.success) {
      popupEditing = false;
      paintPopupMode();
      showMsg('popup-msg', '保存成功', 'success');
      window.__popupTraceHours = traceTime;
    } else {
      showMsg('popup-msg', res.error, 'error');
    }
  }

  // ========== Tab6: 机场告警阈值 ==========
  const TF_FIELDS = [
    ['能见度（米）', 'visibility_m_red', 'visibility_m_yellow', 'visibility_m_green', '0'],
    ['云底高（百英尺）', 'cloud_min_red', 'cloud_min_yellow', 'cloud_min_green', '0'],
    ['平均风速（米/秒）', 'average_wind_speed_mps_red', 'average_wind_speed_mps_yellow', 'average_wind_speed_mps_green', '0'],
    ['阵风（米/秒）', 'gust_mps_red', 'gust_mps_yellow', 'gust_mps_green', '0'],
    ['低温（℃）', 'temperature_cold_red', 'temperature_cold_yellow', 'temperature_cold_green', ''],
    ['高温（℃）', 'temperature_hot_red', 'temperature_hot_yellow', 'temperature_hot_green', '0'],
    ['跑道视程（米）', 'rvr_m_red', 'rvr_m_yellow', 'rvr_m_green', '0'],
  ];
  let thresholdRecords = [];
  let thresholdRemoved = [];
  let thresholdEditing = false;
  let thresholdUid = 1;

  function paintThresholdMode() {
    const pane = document.getElementById('settings-pane-alert-thresholds');
    const modeBtn = document.getElementById('threshold-mode-btn');
    const cancelBtn = document.getElementById('threshold-cancel-btn');
    if (pane) pane.classList.toggle('is-editing', thresholdEditing);
    if (modeBtn) modeBtn.textContent = thresholdEditing ? '保存' : '编辑';
    if (cancelBtn) cancelBtn.disabled = !thresholdEditing;
    document.querySelectorAll('#threshold-list .settings-threshold-input').forEach((el) => {
      el.disabled = !thresholdEditing;
    });
    document.querySelectorAll('#threshold-list .threshold-code').forEach((el) => {
      const card = el.closest('.threshold-card');
      const isNew = card && card.dataset.thresholdNew === '1';
      el.disabled = !thresholdEditing || !isNew;
    });
  }

  function thresholdNum(value) {
    return value == null || value === '' ? '' : value;
  }

  function renderThresholdBoard() {
    const list = document.getElementById('threshold-list');
    if (!list) return;
    const lock = thresholdEditing ? '' : ' disabled';
    const cell = (row, field, min) => `<input type="number" class="settings-threshold-input" data-threshold-field="${field}" ${min} step="1" value="${prefixAttr(thresholdNum(row[field]))}"${lock}>`;
    const cloud = (row) => {
      const current = row.min_cloud_amt || 'SCT';
      return ['FEW', 'SCT', 'BKN', 'OVC'].map((item) => `<option value="${item}"${item === current ? ' selected' : ''}>${item}</option>`).join('');
    };
    list.innerHTML = thresholdRecords.map((row) => {
      const generic = row.airport_4code === 'default';
      const lines = [];
      TF_FIELDS.forEach(([name, red, yellow, green, min], index) => {
        const minAttr = min === '' ? '' : `min="${min}"`;
        lines.push(`<tr><td>${name}</td><td>${cell(row, red, minAttr)}</td><td>${cell(row, yellow, minAttr)}</td><td>${cell(row, green, minAttr)}</td></tr>`);
        if (index === 1) {
          lines.push(`<tr class="threshold-note"><td colspan="4">云量下限 <select class="settings-threshold-input" data-threshold-field="min_cloud_amt"${lock}>${cloud(row)}</select></td></tr>`);
        }
      });
      const codeValue = generic ? '通用' : (row.airport_4code || '');
      const codeLock = (!thresholdEditing || !row.isNew) ? ' disabled' : '';
      const del = generic ? '' : `<button class="settings-del-btn" type="button" data-threshold-delete="${prefixAttr(row.isNew ? row._local : row.airport_4code)}">删除</button>`;
      return `<article class="threshold-card" data-threshold-code="${prefixAttr(row.isNew ? '' : row.airport_4code)}" data-threshold-new="${row.isNew ? '1' : '0'}" data-threshold-local="${prefixAttr(row._local || '')}">
        <div class="threshold-card-head">
          <input class="settings-input threshold-code" maxlength="4" value="${prefixAttr(codeValue)}"${codeLock}${row.isNew && prefixFocus === row._local ? ' data-prefix-focus="1"' : ''}>
          <span>${del}</span>
        </div>
        <table class="settings-table threshold-vert">
          <thead><tr><th>要素</th><th class="th-r">红</th><th class="th-y">黄</th><th class="th-g">绿</th></tr></thead>
          <tbody>${lines.join('')}</tbody>
        </table>
      </article>`;
    }).join('');
    paintThresholdMode();
    const focusEl = list.querySelector('[data-prefix-focus]');
    if (focusEl) focusEl.focus();
  }

  async function loadAlertThresholds() {
    const res = await apiFetch(apiUrl('settings/alert-thresholds/'));
    applyScope(res);
    if (!res.success) { showMsg('threshold-msg', res.error, 'error'); return; }
    thresholdEditing = false;
    thresholdRemoved = [];
    thresholdRecords = (res.data || []).map((row) => Object.assign({ isNew: false }, row));
    renderThresholdBoard();
  }

  function readThresholdDom() {
    return [...document.querySelectorAll('#threshold-list .threshold-card')].map((card) => {
      const isNew = card.dataset.thresholdNew === '1';
      const codeInput = card.querySelector('.threshold-code');
      const item = {
        isNew,
        original: card.dataset.thresholdCode || '',
        _local: card.dataset.thresholdLocal || '',
        airport_4code: isNew ? (codeInput ? codeInput.value.trim().toUpperCase() : '') : (card.dataset.thresholdCode || ''),
        min_cloud_amt: 'SCT',
      };
      card.querySelectorAll('[data-threshold-field]').forEach((el) => {
        item[el.dataset.thresholdField] = el.value;
      });
      return item;
    });
  }

  function addThresholdCard() {
    if (thresholdEditing) thresholdRecords = readThresholdDom();
    thresholdEditing = true;
    const generic = thresholdRecords.find((row) => (row.original || row.airport_4code) === 'default') || {};
    thresholdUid += 1;
    const row = Object.assign({}, generic, {
      airport_4code: '',
      isNew: true,
      original: '',
      label: '',
      _local: 'th' + thresholdUid,
      min_cloud_amt: generic.min_cloud_amt || 'SCT',
    });
    thresholdRecords.push(row);
    prefixFocus = row._local;
    renderThresholdBoard();
    prefixFocus = '';
  }

  async function deleteThresholdCard(key) {
    if (!thresholdEditing) {
      if (!key || key === 'default') return;
      if (!confirm(`确定删除 ${key} 的告警阈值？`)) return;
      const res = await apiFetch(apiUrl(`settings/alert-thresholds/${key}/`), { method: 'DELETE' });
      showMsg('threshold-msg', res.success ? (res.message || '已删除') : (res.error || '删除失败'), res.success ? 'success' : 'error');
      if (res.success) await loadAlertThresholds();
      return;
    }
    thresholdRecords = readThresholdDom();
    const index = thresholdRecords.findIndex((row) => (row.isNew ? row._local : row.airport_4code) === key);
    if (index < 0) return;
    const row = thresholdRecords[index];
    if (row.airport_4code === 'default' || row.original === 'default') return;
    const label = row.isNew ? '这条新增阈值' : row.airport_4code;
    if (!confirm(`确定删除 ${label}？`)) return;
    if (!row.isNew && row.original) thresholdRemoved.push(row.original);
    thresholdRecords.splice(index, 1);
    renderThresholdBoard();
  }

  async function saveAllThresholds() {
    const rows = readThresholdDom();
    for (const row of rows) {
      if (row.isNew && (row.airport_4code.length !== 4 || !/^[A-Z]{4}$/.test(row.airport_4code))) {
        showMsg('threshold-msg', '机场四字代码必须为4位英文大写字母', 'error');
        return;
      }
      if (!['FEW', 'SCT', 'BKN', 'OVC'].includes(row.min_cloud_amt)) {
        showMsg('threshold-msg', '云量下限只能是 FEW、SCT、BKN、OVC', 'error');
        return;
      }
      for (const [, red, yellow, green] of TF_FIELDS) {
        for (const field of [red, yellow, green]) {
          if (row[field] === '' || Number.isNaN(Number(row[field]))) {
            showMsg('threshold-msg', '阈值须为数字', 'error');
            return;
          }
        }
      }
    }
    const modeBtn = document.getElementById('threshold-mode-btn');
    if (modeBtn) modeBtn.disabled = true;
    for (const code of thresholdRemoved) {
      const res = await apiFetch(apiUrl(`settings/alert-thresholds/${code}/`), { method: 'DELETE' });
      if (!res.success) {
        if (modeBtn) modeBtn.disabled = false;
        showMsg('threshold-msg', res.error || '删除失败', 'error');
        return;
      }
    }
    for (const row of rows) {
      const payload = { airport_4code: row.original === 'default' ? 'default' : row.airport_4code, min_cloud_amt: row.min_cloud_amt };
      TF_FIELDS.forEach(([, red, yellow, green]) => {
        [red, yellow, green].forEach((field) => { payload[field] = parseInt(row[field], 10); });
      });
      const url = row.isNew
        ? apiUrl('settings/alert-thresholds/')
        : apiUrl(`settings/alert-thresholds/${row.original}/`);
      const res = await apiFetch(url, { method: row.isNew ? 'POST' : 'PUT', body: JSON.stringify(payload) });
      if (!res.success) {
        if (modeBtn) modeBtn.disabled = false;
        showMsg('threshold-msg', res.error || '保存失败', 'error');
        return;
      }
    }
    if (modeBtn) modeBtn.disabled = false;
    showMsg('threshold-msg', '保存成功', 'success');
    await loadAlertThresholds();
  }

  // ========== Tab7: 天气类型信息 ==========
  let wtypeRows = [];
  let wtypeRemoved = [];
  let wtypeEditing = false;
  let wtypeUid = 1;

  function paintWTypeMode() {
    const pane = document.getElementById('settings-pane-weather-type');
    const modeBtn = document.getElementById('wtype-mode-btn');
    const cancelBtn = document.getElementById('wtype-cancel-btn');
    if (pane) pane.classList.toggle('is-editing', wtypeEditing);
    if (modeBtn) modeBtn.textContent = wtypeEditing ? '保存' : '编辑';
    if (cancelBtn) cancelBtn.disabled = !wtypeEditing;
    document.querySelectorAll('#wtype-tbody .wtype-input').forEach((el) => {
      el.disabled = !wtypeEditing;
    });
  }

  function renderWeatherType() {
    const tbody = document.getElementById('wtype-tbody');
    if (!tbody) return;
    const lock = wtypeEditing ? '' : ' disabled';
    tbody.innerHTML = wtypeRows.map((row) => {
      const key = row.id != null ? String(row.id) : (row._local || '');
      const idAttr = row.id != null
        ? ` data-wtype-id="${row.id}"`
        : ` data-wtype-local="${prefixAttr(row._local || '')}"`;
      return `<tr${idAttr}>
        <td><input class="settings-input wtype-input wtype-code" maxlength="1" value="${prefixAttr(row.weather_type_code || '')}"${lock}></td>
        <td><input class="settings-input wtype-input wtype-cn" maxlength="10" value="${prefixAttr(row.description_cn || '')}"${lock}></td>
        <td><input class="settings-input wtype-input wtype-en" maxlength="20" value="${prefixAttr(row.description_en || '')}"${lock}></td>
        <td><button class="settings-del-btn wtype-del" type="button" data-wtype-delete="${prefixAttr(key)}">删除</button></td>
      </tr>`;
    }).join('');
    paintWTypeMode();
    const focusEl = tbody.querySelector('[data-prefix-focus]');
    if (focusEl) focusEl.focus();
  }

  async function loadWeatherType() {
    const res = await apiFetch(apiUrl('settings/weather-type/'));
    if (!res.success) { showMsg('wtype-msg', res.error, 'error'); return; }
    wtypeEditing = false;
    wtypeRemoved = [];
    wtypeRows = res.data || [];
    renderWeatherType();
  }

  function readWTypeDom() {
    return [...document.querySelectorAll('#wtype-tbody tr')].map((tr) => ({
      id: tr.dataset.wtypeId ? Number(tr.dataset.wtypeId) : null,
      _local: tr.dataset.wtypeLocal || '',
      weather_type_code: tr.querySelector('.wtype-code').value.trim(),
      description_cn: tr.querySelector('.wtype-cn').value.trim(),
      description_en: tr.querySelector('.wtype-en').value.trim(),
    }));
  }

  function addWeatherTypeRow() {
    if (wtypeEditing) wtypeRows = readWTypeDom();
    wtypeEditing = true;
    wtypeUid += 1;
    const row = { _local: 'wt' + wtypeUid, weather_type_code: '', description_cn: '', description_en: '' };
    wtypeRows.push(row);
    renderWeatherType();
    const last = document.querySelector('#wtype-tbody tr:last-child .wtype-code');
    if (last) last.focus();
  }

  function deleteWeatherTypeRow(key) {
    if (!wtypeEditing) return;
    wtypeRows = readWTypeDom();
    const index = wtypeRows.findIndex((row) => String(row.id != null ? row.id : row._local) === String(key));
    if (index < 0) return;
    if (!confirm('确定删除该天气类型？')) return;
    const row = wtypeRows[index];
    if (row.id != null) wtypeRemoved.push(row.id);
    wtypeRows.splice(index, 1);
    renderWeatherType();
  }

  async function saveAllWeatherTypes() {
    const rows = readWTypeDom();
    for (const row of rows) {
      if (!row.weather_type_code || row.weather_type_code.length !== 1) {
        showMsg('wtype-msg', '天气类型代码必须为1位字符', 'error');
        return;
      }
      if (!row.description_cn) { showMsg('wtype-msg', '中文说明为必填项', 'error'); return; }
      if (!row.description_en) { showMsg('wtype-msg', '英文说明为必填项', 'error'); return; }
    }
    const modeBtn = document.getElementById('wtype-mode-btn');
    if (modeBtn) modeBtn.disabled = true;
    for (const id of wtypeRemoved) {
      const res = await apiFetch(apiUrl(`settings/weather-type/${id}/`), { method: 'DELETE' });
      if (!res.success) {
        if (modeBtn) modeBtn.disabled = false;
        showMsg('wtype-msg', res.error || '删除失败', 'error');
        return;
      }
    }
    for (const row of rows) {
      const payload = {
        weather_type_code: row.weather_type_code,
        description_cn: row.description_cn,
        description_en: row.description_en,
      };
      const url = row.id != null ? apiUrl(`settings/weather-type/${row.id}/`) : apiUrl('settings/weather-type/');
      const res = await apiFetch(url, { method: row.id != null ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      if (!res.success) {
        if (modeBtn) modeBtn.disabled = false;
        showMsg('wtype-msg', res.error || '保存失败', 'error');
        return;
      }
    }
    if (modeBtn) modeBtn.disabled = false;
    showMsg('wtype-msg', '保存成功', 'success');
    await loadWeatherType();
  }

  // ========== Tab8: 天气现象告警等级 ==========
  let walertEditId = null;
  let walertLevelTrack = null;
  let weatherTypeCodes = [];

  function buildTypeOptions(selected) {
    const none = `<option value="">（无）</option>`;
    return none + weatherTypeCodes.map(([code, cn]) =>
      `<option value="${escHtml(code)}" ${selected === code ? 'selected' : ''}>${escHtml(code)} - ${escHtml(cn)}</option>`
    ).join('');
  }

  async function loadWeatherAlert() {
    walertLevelTrack = walertLevelTrack || initTrack(document.getElementById('waf-level-track'));
    const res = await apiFetch(apiUrl('settings/weather-alert/'));
    applyScope(res);
    if (!res.success) { showMsg('walert-msg', res.error, 'error'); return; }
    weatherTypeCodes = res.type_codes || [];
    const tbody = document.getElementById('walert-tbody');
    tbody.innerHTML = res.data.map(r => `
      <tr>
        <td>${escHtml(r.weather)}</td>
        <td>${escHtml(r.alert_level)}</td>
        <td>${escHtml(r.type1)}</td>
        <td>${r.type2 || ''}</td>
        <td>${r.type3 || ''}</td>
        <td>${escHtml(r.description)}</td>
        <td>
          <button class="settings-edit-btn" onclick="SettingsModal.editWeatherAlert(${r.id})">编辑</button>
          ${r.from_template ? '' : `<button class="settings-del-btn" onclick="SettingsModal.deleteWeatherAlert(${r.id})">删除</button>`}
        </td>
      </tr>`).join('');
    hideWAlertForm();
  }

  function showWAlertForm(data) {
    const panel = document.getElementById('walert-form-panel');
    panel.style.display = 'flex'; panel.style.flexDirection = 'column';
    document.getElementById('walert-form-title').textContent = data ? '编辑天气现象' : '新增天气现象';
    document.getElementById('waf-weather').value = data ? (data.weather || '') : '';
    if (walertLevelTrack) walertLevelTrack.setVal(data ? (data.alert_level || 'R') : 'R');
    ['waf-type1','waf-type2','waf-type3'].forEach((id, i) => {
      const sel = document.getElementById(id);
      const keys = ['type1','type2','type3'];
      sel.innerHTML = buildTypeOptions(data ? data[keys[i]] : null);
    });
    document.getElementById('waf-description').value = data ? (data.description || '') : '';
  }
  function hideWAlertForm() {
    document.getElementById('walert-form-panel').style.display = 'none';
    walertEditId = null;
  }

  async function saveWeatherAlert() {
    const weather = document.getElementById('waf-weather').value.trim().toUpperCase();
    const level = walertLevelTrack ? walertLevelTrack.getVal() : 'R';
    const type1 = document.getElementById('waf-type1').value;
    const type2 = document.getElementById('waf-type2').value || null;
    const type3 = document.getElementById('waf-type3').value || null;
    const description = document.getElementById('waf-description').value.trim() || null;
    if (!weather) { showMsg('walert-msg', '天气现象代码为必填项', 'error'); return; }
    if (!type1) { showMsg('walert-msg', '类型1为必填项', 'error'); return; }
    const payload = { weather, alert_level: level, type1, type2, type3, description };
    const isEdit = walertEditId !== null;
    const url = isEdit ? apiUrl(`settings/weather-alert/${walertEditId}/`) : apiUrl('settings/weather-alert/');
    const res = await apiFetch(url, { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    if (res.success) { showMsg('walert-msg', res.message, 'success'); await loadWeatherAlert(); }
    else showMsg('walert-msg', res.error, 'error');
  }

  // ========== 雷达告警 ==========
  let _radarCfg = null;
  let radarEditing = false;

  function paintRadarMode() {
    const pane = document.getElementById('settings-pane-radar-alert');
    const modeBtn = document.getElementById('radar-save-btn');
    const cancelBtn = document.getElementById('radar-cancel-btn');
    if (pane) pane.classList.toggle('is-editing', radarEditing);
    if (modeBtn) modeBtn.textContent = radarEditing ? '保存' : '编辑';
    if (cancelBtn) cancelBtn.disabled = !radarEditing;
    document.querySelectorAll('#settings-pane-radar-alert input, #settings-pane-radar-alert select').forEach((el) => {
      if (el.id === 'radar-save-btn' || el.id === 'radar-cancel-btn' || el.id === 'radar-rebuild-btn') return;
      if (el.closest('.settings-restore-btn')) return;
      el.disabled = !radarEditing;
    });
    document.querySelectorAll('.radar-add-bin-btn, #radar-add-ring-btn').forEach((b) => { b.disabled = !radarEditing; });
  }

  function cancelRadarEdit() {
    radarEditing = false;
    if (_radarCfg) fillRadarForm(_radarCfg);
    paintRadarMode();
  }

  async function loadRadarAlertSettings() {
    const res = await apiFetch(apiUrl('radar/config/'));
    applyScope(res);
    if (!res.success) { showMsg('radar-msg', res.error || '加载失败', 'error'); return; }
    _radarCfg = res.config;
    radarEditing = false;
    fillRadarForm(_radarCfg);
    paintRadarMode();
    pollRadarStatusOnce();
  }

  function _radarMaxRadius(rings) {
    let m = 0;
    (rings || []).forEach(r => {
      const v = Number(r && r[1]);
      if (!Number.isNaN(v) && v > m) m = v;
    });
    return m;
  }

  function _updateRadarRadiusDisplay(rings) {
    const el = document.getElementById('radar-radius-display');
    if (!el) return;
    const m = _radarMaxRadius(rings);
    el.textContent = m > 0 ? String(m) : '—';
  }

  function fillRadarForm(cfg) {
    document.getElementById('radar-enabled').checked = !!cfg.enabled;
    document.getElementById('radar-interval').value = cfg.interval_minutes;
    document.getElementById('radar-rate').value = cfg.rate_limit_per_minute;
    document.getElementById('radar-screen-dbz').value = cfg.screen_dbz;
    document.getElementById('radar-z3-min').value = cfg.z3_min_pixels;
    document.getElementById('radar-z3-skip-dbz').value = cfg.z3_skip_dbz != null ? cfg.z3_skip_dbz : 41;
    document.getElementById('radar-z3-skip-min').value = cfg.z3_skip_min_pixels != null ? cfg.z3_skip_min_pixels : 3;
    document.getElementById('radar-z5-dbz').value = cfg.z5_screen_dbz != null ? cfg.z5_screen_dbz : cfg.screen_dbz;
    document.getElementById('radar-z5-min').value = cfg.z5_min_pixels;
    const levels = _radarZ7Levels(cfg);
    levels.forEach((lv, i) => {
      const dbzEl = document.getElementById(`radar-z7-dbz-${i}`);
      const blobEl = document.getElementById(`radar-z7-blob-${i}`);
      if (dbzEl) dbzEl.value = lv.dbz;
      if (blobEl) blobEl.value = lv.min_blob_pixels;
    });
    _updateRadarRadiusDisplay(cfg.rings_km);
    renderRadarRings(cfg.rings_km);
    renderRadarMatrix(cfg);
    _fillRadarAlarmColors(cfg.alarm_colors);
  }

  function _radarZ7Levels(cfg) {
    const raw = (cfg && cfg.z7_levels) || [];
    const fallbackMatrix = cfg.color_matrix || [];
    const fallbackBins = cfg.count_bins || [{ id: 'N0', lo: 1, hi: null, lo_open: false }];
    const ths = cfg.dbz_thresholds || [33, 41];
    const blob = cfg.min_blob_pixels != null ? cfg.min_blob_pixels : 5;
    const out = [];
    for (let i = 0; i < 2; i++) {
      const src = raw[i] || {};
      out.push({
        label: src.label || (i === 0 ? '阈值档A' : '阈值档B'),
        dbz: src.dbz != null ? src.dbz : (ths[i] != null ? ths[i] : (i === 0 ? 33 : 41)),
        min_blob_pixels: src.min_blob_pixels != null ? src.min_blob_pixels : blob,
        count_bins: (src.count_bins && src.count_bins.length) ? src.count_bins : fallbackBins,
        color_matrix: (src.color_matrix && src.color_matrix.length) ? src.color_matrix : fallbackMatrix,
      });
    }
    return out;
  }

  function _colorSelectHtml(v) {
    const options = ['R', 'Y', 'G', 'N'].map((c) => (
      `<option value="${c}" ${c === v ? 'selected' : ''}>${c}</option>`
    )).join('');
    return `<span class="radar-color-pick">
      <select class="radar-color-sel radar-c-${v}" tabindex="-1" aria-hidden="true">${options}</select>
      <button type="button" class="radar-color-btn radar-c-${v}">${v}</button>
    </span>`;
  }

  let _radarColorMenu = null;
  let _radarColorOwner = null;

  function _ensureRadarColorMenu() {
    if (_radarColorMenu) return _radarColorMenu;
    const menu = document.createElement('div');
    menu.className = 'radar-color-menu';
    menu.hidden = true;
    menu.innerHTML = ['R', 'Y', 'G', 'N'].map((c) => (
      `<button type="button" class="radar-color-opt radar-opt-${c}" data-value="${c}">${c}</button>`
    )).join('');
    document.body.appendChild(menu);
    menu.addEventListener('click', (event) => {
      const opt = event.target.closest('.radar-color-opt');
      if (!opt || !_radarColorOwner) return;
      _setRadarColorPick(_radarColorOwner, opt.dataset.value);
      _closeRadarColorMenu();
    });
    document.addEventListener('pointerdown', (event) => {
      if (!_radarColorMenu || _radarColorMenu.hidden) return;
      if (_radarColorMenu.contains(event.target)) return;
      if (_radarColorOwner && _radarColorOwner.contains(event.target)) return;
      _closeRadarColorMenu();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') _closeRadarColorMenu();
    });
    const pane = document.getElementById('settings-pane-radar-alert');
    if (pane) pane.addEventListener('scroll', _closeRadarColorMenu, { passive: true });
    _radarColorMenu = menu;
    return menu;
  }

  function _closeRadarColorMenu() {
    if (_radarColorMenu) _radarColorMenu.hidden = true;
    _radarColorOwner = null;
  }

  function _setRadarColorPick(pick, value) {
    const sel = pick.querySelector('select.radar-color-sel');
    const btn = pick.querySelector('.radar-color-btn');
    if (!sel || !btn) return;
    sel.value = value;
    btn.textContent = value;
    btn.classList.remove('radar-c-R', 'radar-c-Y', 'radar-c-G', 'radar-c-N');
    btn.classList.add('radar-c-' + value);
    sel.classList.remove('radar-c-R', 'radar-c-Y', 'radar-c-G', 'radar-c-N');
    sel.classList.add('radar-c-' + value);
  }

  function _openRadarColorMenu(pick) {
    const btn = pick.querySelector('.radar-color-btn');
    if (!btn) return;
    if (_radarColorOwner === pick && _radarColorMenu && !_radarColorMenu.hidden) {
      _closeRadarColorMenu();
      return;
    }
    const menu = _ensureRadarColorMenu();
    _radarColorOwner = pick;
    const rect = btn.getBoundingClientRect();
    menu.hidden = false;
    menu.style.width = rect.width + 'px';
    const menuHeight = menu.offsetHeight || 88;
    const below = rect.bottom + 2;
    const top = (below + menuHeight > window.innerHeight - 8)
      ? Math.max(8, rect.top - menuHeight - 2)
      : below;
    menu.style.left = rect.left + 'px';
    menu.style.top = top + 'px';
  }

  function _fillRadarAlarmColors(colors) {
    const picked = new Set(Array.isArray(colors) && colors.length ? colors : ['R', 'Y']);
    document.querySelectorAll('#radar-alarm-colors .radar-alarm-color').forEach((el) => {
      el.checked = picked.has(el.value);
    });
  }

  function _readRadarAlarmColors() {
    return ['R', 'Y', 'G'].filter((c) => {
      const el = document.querySelector(`#radar-alarm-colors .radar-alarm-color[value="${c}"]`);
      return el && el.checked;
    });
  }

  function _setRadarAlarmFloor(value) {
    const rank = { R: 3, Y: 2, G: 1 };
    const mine = rank[value];
    if (!mine) return;
    document.querySelectorAll('#radar-alarm-colors .radar-alarm-color').forEach((el) => {
      el.checked = rank[el.value] >= mine;
    });
  }

  function _bindRadarColorSelectStyle(root) {
    (root || document).querySelectorAll('.radar-color-pick').forEach((pick) => {
      const btn = pick.querySelector('.radar-color-btn');
      if (!btn || btn.dataset.bound === '1') return;
      btn.dataset.bound = '1';
      btn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        _openRadarColorMenu(pick);
      });
    });
  }

  function renderRadarRings(rings) {
    const host = document.getElementById('radar-rings-editor');
    if (!host) return;
    const list = (rings && rings.length) ? rings : [[0, 8]];
    host.innerHTML = list.map((r, i) => `
      <div class="radar-ring-chip radar-ring-pair" data-ring="${i}">
        <span>#${i + 1}</span>
        <input type="number" class="settings-input" value="${r[0]}" step="1" title="内半径">
        <span>-</span>
        <input type="number" class="settings-input" value="${r[1]}" step="1" title="外半径">
        <span>km</span>
      </div>`).join('');
    host.querySelectorAll('.radar-ring-pair input').forEach(inp => {
      inp.addEventListener('change', () => {
        try {
          const ringsKm = parseRadarRingsDom();
          _updateRadarRadiusDisplay(ringsKm);
          // 仅刷新表头环标签，保留各档矩阵内容
          const cfg = parseRadarForm();
          renderRadarMatrix(cfg);
        } catch (e) { /* ignore live */ }
      });
    });
  }

  function parseRadarRingsDom() {
    const host = document.getElementById('radar-rings-editor');
    const pairs = host ? host.querySelectorAll('.radar-ring-pair') : [];
    const rings_km = [];
    pairs.forEach(pair => {
      const inputs = pair.querySelectorAll('input');
      const rin = Number(inputs[0] && inputs[0].value);
      const rout = Number(inputs[1] && inputs[1].value);
      if (Number.isNaN(rin) || Number.isNaN(rout)) throw new Error('环半径须为数字');
      if (rout <= rin) throw new Error('环外半径须大于内半径');
      rings_km.push([rin, rout]);
    });
    if (!rings_km.length) throw new Error('至少保留一个环');
    return rings_km;
  }

  function parseRadarLevelMatrixDom(levelIdx, rings_km) {
    const tbody = document.getElementById(`radar-matrix-body-${levelIdx}`);
    const rows = tbody ? tbody.querySelectorAll('tr') : [];
    if (!rows.length) throw new Error(`阈值档 ${levelIdx === 0 ? 'A' : 'B'} 至少保留一个数量档`);
    const count_bins = [];
    const color_matrix = [];
    rows.forEach((tr, idx) => {
      const pair = tr.querySelector('.radar-bin-pair');
      const inputs = pair ? pair.querySelectorAll('input') : [];
      const lo = Number(inputs[0] && inputs[0].value);
      const hiRaw = inputs[1] && inputs[1].value;
      const isLast = idx === rows.length - 1;
      let hi;
      if (isLast) {
        hi = null;
      } else {
        if (!hiRaw || String(hiRaw).toLowerCase() === 'inf') throw new Error('非末档上限不能为 inf');
        hi = Number(hiRaw);
        if (Number.isNaN(hi)) throw new Error('数量档上限须为数字');
      }
      if (Number.isNaN(lo)) throw new Error('数量档下限须为数字');
      if (lo < 0) throw new Error('数量档下限不能小于 0');
      count_bins.push({
        id: `N${idx}`,
        lo,
        hi,
        lo_open: lo === 0,
      });
      const colors = [];
      tr.querySelectorAll('select.radar-color-sel').forEach(sel => colors.push(sel.value));
      while (colors.length < rings_km.length) colors.push('N');
      color_matrix.push(colors.slice(0, rings_km.length));
    });
    return { count_bins, color_matrix };
  }

  function parseRadarForm() {
    const rings_km = parseRadarRingsDom();
    const z7_levels = [0, 1].map(i => {
      const { count_bins, color_matrix } = parseRadarLevelMatrixDom(i, rings_km);
      return {
        label: i === 0 ? '阈值档A' : '阈值档B',
        dbz: Number(document.getElementById(`radar-z7-dbz-${i}`).value),
        min_blob_pixels: Number(document.getElementById(`radar-z7-blob-${i}`).value),
        count_bins,
        color_matrix,
      };
    });
    z7_levels.forEach((lv, i) => {
      if (Number.isNaN(lv.dbz)) throw new Error(`阈值档 ${i === 0 ? 'A' : 'B'} dBZ 无效`);
      if (Number.isNaN(lv.min_blob_pixels) || lv.min_blob_pixels < 1) {
        throw new Error(`阈值档 ${i === 0 ? 'A' : 'B'} 斑块最少像素无效`);
      }
    });
    return {
      ...(_radarCfg || {}),
      enabled: document.getElementById('radar-enabled').checked,
      interval_minutes: Number(document.getElementById('radar-interval').value),
      radius_km: _radarMaxRadius(rings_km),
      rate_limit_per_minute: Number(document.getElementById('radar-rate').value),
      screen_dbz: Number(document.getElementById('radar-screen-dbz').value),
      z3_min_pixels: Number(document.getElementById('radar-z3-min').value),
      z3_skip_dbz: Number(document.getElementById('radar-z3-skip-dbz').value),
      z3_skip_min_pixels: Number(document.getElementById('radar-z3-skip-min').value),
      z5_screen_dbz: Number(document.getElementById('radar-z5-dbz').value),
      z5_min_pixels: Number(document.getElementById('radar-z5-min').value),
      rings_km,
      alarm_colors: _readRadarAlarmColors(),
      z7_levels,
      dbz_thresholds: [z7_levels[0].dbz, z7_levels[1].dbz],
      min_blob_pixels: z7_levels[0].min_blob_pixels,
      count_bins: z7_levels[0].count_bins,
      color_matrix: z7_levels[0].color_matrix,
    };
  }

  function renderRadarLevelMatrix(levelIdx, rings, level) {
    const thead = document.getElementById(`radar-matrix-head-${levelIdx}`);
    const tbody = document.getElementById(`radar-matrix-body-${levelIdx}`);
    if (!thead || !tbody) return;
    const bins = (level.count_bins && level.count_bins.length)
      ? level.count_bins
      : [{ id: 'N0', lo: 1, hi: null, lo_open: false }];
    const matrix = level.color_matrix || [];

    const ratios = _ringAreaRatios(rings);
    thead.innerHTML = `<tr>
      <th>数量档 lo/hi</th>
      ${rings.map((r, i) => `<th><span class="radar-ring-label">${r[0]}-${r[1]}km</span><span class="radar-ring-m">M=${_fmtM(ratios[i])}</span></th>`).join('')}
    </tr>`;

    tbody.innerHTML = bins.map((b, bi) => {
      const isFirst = bi === 0;
      const isLast = bi === bins.length - 1;
      const lo = _radarBinEditLo(b, isFirst);
      const hi = isLast ? 'inf' : (b.hi == null ? '' : b.hi);
      const labelBin = { ...b, lo, lo_open: Number(lo) === 0 };
      const cells = rings.map((_, ri) => {
        const v = (matrix[bi] && matrix[bi][ri]) || 'N';
        const count = _binPixelLabel(labelBin, ratios[ri], isFirst, isLast);
        return `<td><div class="radar-cell"><span class="radar-cell-count">${count}</span>${_colorSelectHtml(v)}</div></td>`;
      }).join('');
      return `<tr data-bin="${bi}">
        <th>
          <div class="radar-bin-pair">
            <input type="number" class="settings-input" value="${lo}" min="0" step="1" title="下限">
            <span>-</span>
            <input type="text" class="settings-input" value="${hi}" ${isLast ? 'disabled' : ''} title="上限">
          </div>
        </th>
        ${cells}
      </tr>`;
    }).join('');
    _bindRadarColorSelectStyle(tbody);
    tbody.querySelectorAll('.radar-bin-pair input').forEach(inp => {
      inp.addEventListener('input', () => _refreshMatrixPixelCounts());
    });
  }

  function _radarBinEditLo(bin, isFirst) {
    const raw = bin && bin.lo != null && bin.lo !== '' ? Number(bin.lo) : (isFirst ? 1 : '');
    if (isFirst && raw === 0) return 1;
    return raw;
  }

  function _ringAreaRatios(rings) {
    const areas = rings.map(r => (Number(r[1]) * Number(r[1])) - (Number(r[0]) * Number(r[0])));
    const s0 = areas[0] > 0 ? areas[0] : 1;
    return areas.map(a => a / s0);
  }

  function _fmtM(m) {
    const rounded = Math.round(m * 10000) / 10000;
    if (Math.abs(rounded - Math.round(rounded)) < 1e-9) return String(Math.round(rounded));
    return String(rounded);
  }

  function _intAtLeast(bound) {
    return Math.ceil(bound - 1e-8);
  }

  function _intAtMost(bound) {
    return Math.floor(bound + 1e-8);
  }

  function _binPixelLabel(bin, m, isFirst, isLast) {
    const lo = Number(bin.lo) * m;
    const openLo = isFirst && (bin.lo_open || Number(bin.lo) === 0);
    let min = openLo ? _intAtMost(lo) + 1 : _intAtLeast(lo);
    if (min < 1) min = 1;
    if (isLast || bin.hi == null) return `≥${min}`;
    const max = _intAtMost(Number(bin.hi) * m);
    if (max < min) return '—';
    if (min === max) return String(min);
    return `${min}–${max}`;
  }

  function _paintMatrixCounts(levelIdx, ratios, bins) {
    const tbody = document.getElementById(`radar-matrix-body-${levelIdx}`);
    if (!tbody) return;
    tbody.querySelectorAll('tr').forEach((tr, bi) => {
      const bin = bins && bins[bi];
      const isFirst = bi === 0;
      const isLast = !!(bins && bi === bins.length - 1);
      tr.querySelectorAll('.radar-cell-count').forEach((el, ri) => {
        const m = ratios[ri];
        el.textContent = (bin && m != null) ? _binPixelLabel(bin, m, isFirst, isLast) : '—';
      });
    });
  }

  function _refreshMatrixPixelCounts() {
    let rings;
    try {
      rings = parseRadarRingsDom();
    } catch (e) {
      return;
    }
    const ratios = _ringAreaRatios(rings);
    [0, 1].forEach(i => {
      let bins = null;
      try {
        bins = parseRadarLevelMatrixDom(i, rings).count_bins;
      } catch (e) {
        bins = null;
      }
      _paintMatrixCounts(i, ratios, bins);
    });
  }

  function renderRadarMatrix(cfg) {
    const rings = (cfg.rings_km && cfg.rings_km.length) ? cfg.rings_km : [[0, 8]];
    const levels = _radarZ7Levels(cfg);
    levels.forEach((lv, i) => renderRadarLevelMatrix(i, rings, lv));
    _updateRadarRadiusDisplay(rings);
  }

  function addRadarBinRow(levelIdx) {
    try {
      const cfg = parseRadarForm();
      const lv = cfg.z7_levels[levelIdx];
      const bins = lv.count_bins || [];
      if (bins.length) {
        const prev = bins[bins.length - 1];
        const prevLo = Number(prev.lo) || 0;
        let newPrevHi = prev.hi;
        if (newPrevHi == null) {
          const before = bins.length >= 2 ? bins[bins.length - 2].hi : null;
          newPrevHi = before != null ? Number(before) + 5 : prevLo + 5;
        }
        bins[bins.length - 1] = { ...prev, hi: newPrevHi, lo_open: false };
        bins.push({ id: `N${bins.length}`, lo: Number(newPrevHi) + 1, hi: null, lo_open: false });
      } else {
        bins.push({ id: 'N0', lo: 1, hi: null, lo_open: false });
      }
      const matrix = lv.color_matrix || [];
      const cols = (cfg.rings_km || []).length || 1;
      matrix.push(Array(cols).fill('N'));
      lv.count_bins = bins;
      lv.color_matrix = matrix;
      cfg.z7_levels[levelIdx] = lv;
      renderRadarMatrix(cfg);
    } catch (e) {
      showMsg('radar-msg', e.message, 'error');
    }
  }

  function addRadarRingCol() {
    try {
      const cfg = parseRadarForm();
      const rings = cfg.rings_km || [];
      const lastOut = rings.length ? Number(rings[rings.length - 1][1]) : 0;
      rings.push([lastOut, lastOut + 50]);
      (cfg.z7_levels || []).forEach(lv => {
        (lv.color_matrix || []).forEach(row => row.push('N'));
      });
      cfg.rings_km = rings;
      cfg.radius_km = _radarMaxRadius(rings);
      renderRadarRings(rings);
      renderRadarMatrix(cfg);
    } catch (e) {
      showMsg('radar-msg', e.message, 'error');
    }
  }

  async function saveRadarAlertSettings() {
    try {
      const config = parseRadarForm();
      const res = await apiFetch(apiUrl('radar/config/'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config }),
      });
      if (!res.success) { showMsg('radar-msg', res.error || '保存失败', 'error'); return; }
      _radarCfg = res.config;
      radarEditing = false;
      fillRadarForm(res.config);
      paintRadarMode();
      showMsg('radar-msg', '已保存', 'success');
    } catch (e) {
      showMsg('radar-msg', e.message, 'error');
    }
  }

  async function rebuildRadarIndex() {
    const res = await apiFetch(apiUrl('radar/rebuild-index/'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    showMsg('radar-msg', res.success
      ? `索引已重建：机场 ${res.airport_count}，瓦片并集 ${JSON.stringify(res.unions)}`
      : (res.error || '失败'), res.success ? 'success' : 'error');
  }

  async function pollRadarStatusOnce() {
    const res = await apiFetch(apiUrl('radar/status/'));
    if (!res.success) return;
    const st = res.status || {};
    const rl = st.rate_limiter || {};
    const el = document.getElementById('radar-status-text');
    if (el) {
      el.textContent = `状态:${st.state || '-'} ${st.phase || ''} | 窗口请求 ${rl.window_count || 0}/${rl.max_per_minute || 80}`
        + (rl.rate_limited ? ` | 限流暂停 ${rl.paused_seconds}s` : '')
        + (rl.queued ? ` | 排队 ${rl.queued}` : '');
    }
  }

  // ========== Tab11: 地图样式 ==========
  let _mapStyleCfg = null;
  let _mapColorSchemes = [];
  let _mapPalettes = {};

  async function loadMapStyleSettings() {
    const res = await apiFetch(apiUrl('map-style/config/'));
    if (!res.success) { showMsg('map-style-msg', res.error || '加载失败', 'error'); return; }
    _mapStyleCfg = res.config;
    _mapColorSchemes = res.color_schemes || [];
    if (res.palette) _mapPalettes[res.config.color_scheme] = res.palette;
    // 补齐预览色：用返回的 palette 列表不够时从 scheme id 简单展示
    fillMapStyleForm(_mapStyleCfg, res.palette);
  }

  function fillMapStyleForm(cfg, palette) {
    document.getElementById('ms-inner-size').value = cfg.marker_inner_size;
    document.getElementById('ms-outer-size').value = cfg.marker_outer_size;
    document.getElementById('ms-airport-labels').checked = !!cfg.show_airport_labels;
    document.getElementById('ms-cn-province-borders').checked = !!(cfg.china && cfg.china.province_borders);
    document.getElementById('ms-cn-province-labels').checked = !!(cfg.china && cfg.china.province_labels);
    document.getElementById('ms-world-admin1-borders').checked = !!(cfg.world && cfg.world.admin1_borders);
    document.getElementById('ms-world-admin1-labels').checked = !!(cfg.world && cfg.world.admin1_labels);
    document.getElementById('ms-country-borders').checked = !!(cfg.global && cfg.global.country_borders);
    document.getElementById('ms-country-labels').checked = !!(cfg.global && cfg.global.country_labels);
    document.getElementById('ms-rivers').checked = !!(cfg.global && cfg.global.rivers);
    document.getElementById('ms-lakes').checked = !!(cfg.global && cfg.global.lakes);
    renderMapSchemeCards(cfg.color_scheme, palette);
  }

  function renderMapSchemeCards(activeId, activePalette) {
    const box = document.getElementById('ms-color-scheme-group');
    if (!box) return;
    const fallbackSwatch = {
      deep_navy: ['#2a3038', '#0c1016', '#9aa4b0'],
      slate_gray: ['#1a1f26', '#2a3340', '#d0dce8'],
      warm_dim: ['#4d7ea6', '#f7f4ec', '#2a261f'],
    };
    box.innerHTML = (_mapColorSchemes.length ? _mapColorSchemes : [
      { id: 'deep_navy', label: '深海军蓝' },
      { id: 'slate_gray', label: '冷灰岩板' },
      { id: 'warm_dim', label: '浅暖纸' },
    ]).map(s => {
      const sw = (s.id === activeId && activePalette)
        ? [activePalette.background, activePalette.land, activePalette.country_border]
        : (fallbackSwatch[s.id] || ['#333', '#555', '#888']);
      return `<button type="button" class="ms-scheme-card ${s.id === activeId ? 'active' : ''}" data-scheme="${s.id}">
        <div>${escHtml(s.label)}</div>
        <div class="ms-scheme-swatches">${sw.map(c => `<span style="background:${c}"></span>`).join('')}</div>
      </button>`;
    }).join('');
    box.querySelectorAll('.ms-scheme-card').forEach(btn => {
      btn.addEventListener('click', () => {
        box.querySelectorAll('.ms-scheme-card').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });
  }

  function parseMapStyleForm() {
    const active = document.querySelector('#ms-color-scheme-group .ms-scheme-card.active');
    return {
      ...(_mapStyleCfg || {}),
      color_scheme: active ? active.dataset.scheme : 'deep_navy',
      marker_inner_size: Number(document.getElementById('ms-inner-size').value),
      marker_outer_size: Number(document.getElementById('ms-outer-size').value),
      show_airport_labels: document.getElementById('ms-airport-labels').checked,
      china: {
        province_borders: document.getElementById('ms-cn-province-borders').checked,
        province_labels: document.getElementById('ms-cn-province-labels').checked,
      },
      world: {
        admin1_borders: document.getElementById('ms-world-admin1-borders').checked,
        admin1_labels: document.getElementById('ms-world-admin1-labels').checked,
      },
      global: {
        country_borders: document.getElementById('ms-country-borders').checked,
        country_labels: document.getElementById('ms-country-labels').checked,
        rivers: document.getElementById('ms-rivers').checked,
        lakes: document.getElementById('ms-lakes').checked,
      },
    };
  }

  async function saveMapStyleSettings() {
    try {
      const config = parseMapStyleForm();
      const res = await apiFetch(apiUrl('map-style/config/'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config }),
      });
      if (!res.success) { showMsg('map-style-msg', res.error || '保存失败', 'error'); return; }
      _mapStyleCfg = res.config;
      fillMapStyleForm(res.config, res.palette);
      showMsg('map-style-msg', '已保存', 'success');
      if (typeof window.applyMapStyleConfig === 'function') {
        window.applyMapStyleConfig(res.config, res.border_widths, res.palette);
      }
    } catch (e) {
      showMsg('map-style-msg', e.message, 'error');
    }
  }

  // ========== 初始化 ==========
  function init() {
    // Tab按钮
    document.querySelectorAll('.settings-tab').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    document.querySelectorAll('.settings-group-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        selectSettingsGroup(btn.dataset.group, true);
      });
    });

    // 关闭按钮
    document.getElementById('settings-modal-close').addEventListener('click', () => {
      if (!confirmLeavePrefixEdit()) return;
      window.hideModal('settings-modal');
    });

    const suBtn = document.getElementById('superuser-btn');
    const unlockBox = document.getElementById('settings-admin-unlock');
    const unlockInput = document.getElementById('settings-admin-password');
    const unlockBtn = document.getElementById('settings-admin-unlock-btn');
    async function unlockSettingsAdmin() {
      const password = unlockInput ? unlockInput.value : '';
      const res = await apiFetch(apiUrl('access/admin/unlock/'), {
        method: 'POST',
        body: JSON.stringify({ password }),
      });
      if (!res.success) {
        alert(res.error || '解锁失败');
        return;
      }
      if (unlockInput) unlockInput.value = '';
      if (unlockBox) unlockBox.style.display = 'none';
      window.__adminUnlocked = true;
      applyScope({ can_edit_default: true });
      await loadTab(currentSettingsTab);
    }
    if (suBtn && unlockBox) {
      suBtn.addEventListener('click', () => {
        const open = unlockBox.style.display === 'none';
        unlockBox.style.display = open ? 'inline-flex' : 'none';
        if (open && unlockInput) unlockInput.focus();
      });
    }
    if (unlockBtn) unlockBtn.addEventListener('click', unlockSettingsAdmin);
    if (unlockInput) {
      unlockInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          unlockSettingsAdmin();
        }
      });
    }
    const groupBtn = document.getElementById('superuser-group-btn');
    if (groupBtn) {
      groupBtn.addEventListener('click', () => {
        if (typeof openSuperuserAdmin === 'function') openSuperuserAdmin();
      });
    }
    const scopeToggle = document.getElementById('settings-default-toggle');
    if (scopeToggle) {
      scopeToggle.addEventListener('click', async () => {
        settingsScope = settingsScope === 'default' ? '' : 'default';
        window.__settingsScope = settingsScope;
        scopeToggle.textContent = settingsScope === 'default' ? '返回我的设置' : '编辑默认模板';
        paintDefaultBanner();
        await loadTab(currentSettingsTab);
      });
    }
    document.querySelectorAll('.settings-restore-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const group = btn.dataset.group;
        const hint = group === 'airport_alert_thresholds'
          ? '只清除你的通用阈值，已单独设置的机场会保留。确定恢复？'
          : '清除你在这一组保存的内容，改回默认。确定恢复？';
        if (!confirm(hint)) return;
        const res = await apiFetch(apiUrl('settings/restore/'), {
          method: 'POST',
          body: JSON.stringify({ group }),
        });
        showMsg(btn.dataset.msg, res.success ? (res.message || '已恢复默认') : (res.error || '恢复失败'), res.success ? 'success' : 'error');
        if (!res.success) return;
        if (group === 'trend_alert_config' && window.TrendAlertSettings) await window.TrendAlertSettings.load();
        else await loadTab(currentSettingsTab);
      });
    });

    const airportResult = document.getElementById('airport-result-area');
    if (airportResult) {
      airportResult.addEventListener('change', (event) => {
        if (event.target.id !== 'af-classification-chk') return;
        const areaSel = document.getElementById('af-area');
        updateAreaSelect(event.target.checked ? '国际' : '国内', areaSel ? areaSel.value : '');
      });
      airportResult.addEventListener('click', (event) => {
        if (event.target.closest('#airport-save-btn')) saveAirport();
        if (event.target.closest('#airport-cancel-btn')) hideAirportForm();
      });
    }

    // 机场信息 — 按四字代码查询
    const airportSearchInput = document.getElementById('airport-search-input');
    if (airportSearchInput) {
      airportSearchInput.addEventListener('keydown', e => { if (e.key === 'Enter') searchAirport(); });
    }
    const airportSearchBtn = document.getElementById('airport-search-btn');
    if (airportSearchBtn) airportSearchBtn.addEventListener('click', () => searchAirport());
    const airportAddBtn = document.getElementById('airport-add-btn');
    if (airportAddBtn) airportAddBtn.addEventListener('click', () => {
      airportEditCode = null; airportViewData = null; airportCurrentCode = null;
      showAirportForm(null, '');
    });
    const prefixExpandAll = document.getElementById('prefix-expand-all');
    if (prefixExpandAll) prefixExpandAll.addEventListener('click', () => setAllPrefixRegions(false));
    const prefixCollapseAll = document.getElementById('prefix-collapse-all');
    if (prefixCollapseAll) prefixCollapseAll.addEventListener('click', () => setAllPrefixRegions(true));
    const prefixBoard = document.getElementById('prefix-board');
    if (prefixBoard) {
      prefixBoard.addEventListener('click', (event) => {
        const fold = event.target.closest('[data-prefix-fold]');
        if (fold) {
          const id = fold.dataset.prefixFold;
          if (prefixCollapsed.has(id)) prefixCollapsed.delete(id);
          else prefixCollapsed.add(id);
          renderPrefixTable();
          return;
        }
        const mode = event.target.closest('[data-prefix-mode]');
        if (mode) {
          const id = mode.dataset.prefixMode;
          if (prefixEditingId === id) savePrefixRegion(id);
          else beginPrefixEdit(id);
          return;
        }
        const cancel = event.target.closest('[data-prefix-cancel]');
        if (cancel) {
          cancelPrefixRegion(cancel.dataset.prefixCancel);
          return;
        }
        const del = event.target.closest('[data-prefix-delete]');
        if (del) {
          deletePrefixLine(del.dataset.region, del.dataset.prefixDelete);
          return;
        }
        const addLine = event.target.closest('[data-prefix-add-line]');
        if (addLine) {
          addPrefixLine(addLine.dataset.prefixAddLine);
          return;
        }
        const addRegion = event.target.closest('[data-prefix-add-region]');
        if (addRegion) addPrefixRegion(addRegion.dataset.prefixAddRegion);
      });
    }
    const tafAdd = document.getElementById('taf-add-btn');
    if (tafAdd) tafAdd.addEventListener('click', () => showTafForm(null));
    const tafSave = document.getElementById('taf-save-btn');
    if (tafSave) tafSave.addEventListener('click', saveTafImport);
    const tafCancel = document.getElementById('taf-cancel-btn');
    if (tafCancel) tafCancel.addEventListener('click', () => {
      document.getElementById('taf-form-panel').style.display = 'none';
      tafEditCode = null;
    });

    const timerMode = document.getElementById('timer-mode-btn');
    if (timerMode) {
      timerMode.addEventListener('click', () => {
        if (!timerEditing) {
          timerEditing = true;
          paintTimerMode();
          return;
        }
        saveAllTimers();
      });
    }
    const timerCancel = document.getElementById('timer-cancel-btn');
    if (timerCancel) timerCancel.addEventListener('click', cancelTimerEdit);
    const popupMode = document.getElementById('popup-mode-btn');
    if (popupMode) {
      popupMode.addEventListener('click', () => {
        if (!popupEditing) {
          popupEditing = true;
          paintPopupMode();
          return;
        }
        savePopupSettings();
      });
    }
    const popupCancel = document.getElementById('popup-cancel-btn');
    if (popupCancel) popupCancel.addEventListener('click', () => loadPopupSettings());

    // 告警阈值
    document.getElementById('threshold-add-btn').addEventListener('click', addThresholdCard);
    document.getElementById('threshold-mode-btn').addEventListener('click', () => {
      if (!thresholdEditing) {
        thresholdEditing = true;
        paintThresholdMode();
        return;
      }
      saveAllThresholds();
    });
    document.getElementById('threshold-cancel-btn').addEventListener('click', () => loadAlertThresholds());
    const thresholdList = document.getElementById('threshold-list');
    if (thresholdList) {
      thresholdList.addEventListener('click', (event) => {
        const del = event.target.closest('[data-threshold-delete]');
        if (del) deleteThresholdCard(del.dataset.thresholdDelete);
      });
    }

    // 天气类型
    document.getElementById('wtype-add-btn').addEventListener('click', addWeatherTypeRow);
    document.getElementById('wtype-mode-btn').addEventListener('click', () => {
      if (!wtypeEditing) {
        wtypeEditing = true;
        paintWTypeMode();
        return;
      }
      saveAllWeatherTypes();
    });
    document.getElementById('wtype-cancel-btn').addEventListener('click', () => loadWeatherType());
    const wtypeBody = document.getElementById('wtype-tbody');
    if (wtypeBody) {
      wtypeBody.addEventListener('click', (event) => {
        const del = event.target.closest('[data-wtype-delete]');
        if (del) deleteWeatherTypeRow(del.dataset.wtypeDelete);
      });
    }

    // 天气告警等级
    document.getElementById('walert-add-btn').addEventListener('click', () => { walertEditId = null; showWAlertForm(null); });
    document.getElementById('walert-save-btn').addEventListener('click', saveWeatherAlert);
    document.getElementById('walert-cancel-btn').addEventListener('click', hideWAlertForm);

    // 雷达告警
    const radarSave = document.getElementById('radar-save-btn');
    if (radarSave) {
      radarSave.addEventListener('click', () => {
        if (!radarEditing) { radarEditing = true; paintRadarMode(); return; }
        saveRadarAlertSettings();
      });
      document.getElementById('radar-rebuild-btn').addEventListener('click', rebuildRadarIndex);
      document.querySelectorAll('#radar-alarm-colors .radar-alarm-switch').forEach((label) => {
        label.addEventListener('click', () => {
          const input = label.querySelector('.radar-alarm-color');
          if (!input) return;
          const value = input.value;
          setTimeout(() => _setRadarAlarmFloor(value), 0);
        });
      });
      document.querySelectorAll('.radar-add-bin-btn').forEach(btn => {
        btn.addEventListener('click', () => addRadarBinRow(Number(btn.dataset.level) || 0));
      });
      const addRing = document.getElementById('radar-add-ring-btn');
      if (addRing) addRing.addEventListener('click', addRadarRingCol);
    }
    const radarCancel = document.getElementById('radar-cancel-btn');
    if (radarCancel) radarCancel.addEventListener('click', cancelRadarEdit);
    const mapStyleSave = document.getElementById('map-style-save-btn');
    if (mapStyleSave) {
      mapStyleSave.addEventListener('click', saveMapStyleSettings);
    }
  }

  function selectSettingsGroup(name, switchToFirst) {
    if (switchToFirst) {
      const groupCls = name === 'global' ? '.settings-tab-group-global' : '.settings-tab-group-personal';
      const first = document.querySelector(groupCls + ' .settings-tab:not([style*="display: none"])');
      if (first) switchTab(first.getAttribute('data-tab'));
    }
  }

  function applySettingsTabVisibility() {
    const TAB_PERM = {
      'airport-info': 'settings_airport_info',
      'prefix-area': 'settings_prefix_area',
      'taf-import': 'settings_taf_import',
      'data-refresh-timer': 'settings_data_refresh',
      'popup': 'settings_popup',
      'alert-thresholds': 'settings_alert_thresholds',
      'weather-type': 'settings_weather_type',
      'weather-alert': 'settings_weather_alert',
      'radar-alert': 'settings_radar_alert',
      'map-style': 'settings_map_style',
      'trend-alert': 'settings_trend_alert',
    };
    Object.keys(TAB_PERM).forEach((tab) => {
      const btn = document.querySelector(`.settings-tab[data-tab="${tab}"]`);
      if (!btn) return;
      const ok = typeof hasAccess !== 'function' || hasAccess(TAB_PERM[tab], 'display');
      btn.style.display = ok ? '' : 'none';
    });
  }

  // ========== 机场区域：单列，按区域编辑 ==========
  let prefixRows = [];
  let prefixEditingId = null;
  let prefixSnapshot = null;
  let prefixDraft = { '国内': [], '国际': [] };
  let prefixCollapsed = new Set();
  let prefixUid = 1;
  let prefixFocus = '';

  function prefixAttr(value) {
    return escHtml(value).replace(/"/g, '&quot;');
  }

  function nextPrefixId() {
    prefixUid += 1;
    return 'pf' + prefixUid;
  }

  function cloneRegion(region) {
    return JSON.parse(JSON.stringify(region));
  }

  function prefixHasPending() {
    if (prefixEditingId) return true;
    return ['国内', '国际'].some((kind) => prefixDraft[kind].some((region) => region.isNew));
  }

  function confirmLeavePrefixEdit() {
    if (!prefixHasPending()) return true;
    if (!confirm('当前区域修改尚未保存，确定离开吗？')) return false;
    prefixEditingId = null;
    prefixSnapshot = null;
    ['国内', '国际'].forEach((kind) => {
      prefixDraft[kind] = prefixDraft[kind].filter((region) => !region.isNew);
    });
    return true;
  }

  function draftFromPrefixRows(rows) {
    const draft = { '国内': [], '国际': [] };
    const index = new Map();
    (rows || []).forEach((row) => {
      const kind = row.classification === '国际' ? '国际' : '国内';
      const key = `${kind}|${row.sequence}|${row.area}`;
      if (!index.has(key)) {
        const region = {
          id: nextPrefixId(),
          area: row.area || '',
          sequence: row.sequence,
          prefixes: [],
          isNew: false,
        };
        index.set(key, region);
        draft[kind].push(region);
      }
      index.get(key).prefixes.push({
        id: nextPrefixId(),
        prefix: row.prefix || '',
        remark: row.remark || '',
      });
    });
    ['国内', '国际'].forEach((kind) => {
      draft[kind].sort((a, b) => Number(a.sequence) - Number(b.sequence));
    });
    return draft;
  }

  function eachPrefixRegion(fn) {
    ['国内', '国际'].forEach((kind) => {
      prefixDraft[kind].forEach((region) => fn(kind, region));
    });
  }

  function findPrefixRegion(regionId) {
    for (const kind of ['国内', '国际']) {
      const region = prefixDraft[kind].find((item) => item.id === regionId);
      if (region) return { kind, region };
    }
    return null;
  }

  function syncPrefixDraft() {
    document.querySelectorAll('[data-prefix-region][data-field]').forEach((el) => {
      const found = findPrefixRegion(el.dataset.prefixRegion);
      if (!found) return;
      if (el.dataset.field === 'area') found.region.area = el.value;
      if (el.dataset.field === 'sequence') found.region.sequence = el.value;
    });
    document.querySelectorAll('[data-prefix-row][data-field]').forEach((el) => {
      eachPrefixRegion((kind, region) => {
        const row = region.prefixes.find((item) => item.id === el.dataset.prefixRow);
        if (!row) return;
        if (el.dataset.field === 'prefix') row.prefix = el.value;
        if (el.dataset.field === 'remark') row.remark = el.value;
      });
    });
  }

  function prefixInput(region, className, attrs, value) {
    const lock = region.id === prefixEditingId ? '' : ' disabled';
    return `<input class="settings-input prefix-inline-input ${className}" ${attrs}${lock} value="${prefixAttr(value)}">`;
  }

  function paintPrefixFoldAll() {
    const ids = [];
    eachPrefixRegion((kind, region) => ids.push(region.id));
    const allClosed = ids.length > 0 && ids.every((id) => prefixCollapsed.has(id));
    const allOpen = ids.length > 0 && ids.every((id) => !prefixCollapsed.has(id));
    const expandBtn = document.getElementById('prefix-expand-all');
    const collapseBtn = document.getElementById('prefix-collapse-all');
    if (expandBtn) {
      expandBtn.disabled = allOpen;
      expandBtn.classList.toggle('is-current', allOpen);
    }
    if (collapseBtn) {
      collapseBtn.disabled = allClosed;
      collapseBtn.classList.toggle('is-current', allClosed);
    }
  }

  function renderPrefixSection(kind, block) {
    const regions = block.map((region) => {
      const editing = region.id === prefixEditingId;
      const collapsed = prefixCollapsed.has(region.id);
      const lines = region.prefixes.map((row) => `<tr>
        <td>${prefixInput(region, 'prefix-code-input', `maxlength="4" data-prefix-row="${row.id}" data-field="prefix" style="text-transform:uppercase;"${prefixFocus === row.id ? ' data-prefix-focus="1"' : ''}`, row.prefix)}</td>
        <td>${prefixInput(region, 'prefix-remark-input', `data-prefix-row="${row.id}" data-field="remark"`, row.remark || '')}</td>
        <td><button class="settings-del-btn prefix-edit-only" type="button" data-prefix-delete="${row.id}" data-region="${region.id}">删除</button></td>
      </tr>`).join('');
      return `<article class="prefix-region${editing ? ' is-editing' : ''}${collapsed ? ' is-collapsed' : ''}" data-region-id="${region.id}">
        <div class="prefix-region-title">
          <div class="prefix-region-fields">
            <span class="prefix-region-label">区域</span>
            ${prefixInput(region, 'prefix-area-input', `data-prefix-region="${region.id}" data-field="area" maxlength="20"${prefixFocus === region.id ? ' data-prefix-focus="1"' : ''}`, region.area)}
            <span class="prefix-region-label">序号</span>
            ${prefixInput(region, 'prefix-seq-input', `type="number" min="1" step="1" data-prefix-region="${region.id}" data-field="sequence"`, region.sequence)}
          </div>
          <div class="prefix-region-actions">
            <button class="settings-edit-btn prefix-edit-only" type="button" data-prefix-add-line="${region.id}">新增前缀</button>
            <button class="settings-save-inline-btn" type="button" data-prefix-mode="${region.id}">${editing ? '保存' : '编辑'}</button>
            <button class="settings-cancel-inline-btn" type="button" data-prefix-cancel="${region.id}"${editing ? '' : ' disabled'}>取消</button>
            <button class="prefix-fold-btn" type="button" data-prefix-fold="${region.id}">${collapsed ? '展开' : '收起'}</button>
          </div>
        </div>
        <table class="settings-table prefix-line-table">
          <thead><tr><th>前缀</th><th>备注</th><th>操作</th></tr></thead>
          <tbody>${lines}</tbody>
        </table>
      </article>`;
    }).join('');
    return `<section class="prefix-kind-block">
      <div class="prefix-kind-head">
        <h4>${kind}</h4>
        <button class="settings-add-btn" type="button" data-prefix-add-region="${kind}">新增区域</button>
      </div>
      <div class="prefix-region-list">${regions || '<p class="prefix-empty">暂无区域</p>'}</div>
    </section>`;
  }

  function renderPrefixTable() {
    const board = document.getElementById('prefix-board');
    if (!board) return;
    board.innerHTML = ['国内', '国际'].map((kind) => renderPrefixSection(kind, prefixDraft[kind] || [])).join('');
    paintPrefixFoldAll();
    const focusEl = board.querySelector('[data-prefix-focus]');
    prefixFocus = '';
    if (focusEl && prefixEditingId) focusEl.focus();
  }

  function setAllPrefixRegions(collapsed) {
    if (collapsed) {
      const ids = [];
      eachPrefixRegion((kind, region) => ids.push(region.id));
      prefixCollapsed = new Set(ids);
    } else {
      prefixCollapsed = new Set();
    }
    renderPrefixTable();
  }

  async function loadPrefixAreas() {
    if (prefixEditingId) return;
    const res = await apiFetch(apiUrl('settings/prefix-area/'));
    if (!res.success) { showMsg('prefix-msg', res.error, 'error'); return; }
    prefixRows = res.data || [];
    prefixDraft = draftFromPrefixRows(prefixRows);
    const alive = new Set();
    eachPrefixRegion((kind, region) => alive.add(region.id));
    prefixCollapsed = new Set([...prefixCollapsed].filter((id) => alive.has(id)));
    renderPrefixTable();
  }

  function beginPrefixEdit(regionId) {
    if (prefixEditingId && prefixEditingId !== regionId) {
      showMsg('prefix-msg', '请先保存或取消正在编辑的区域', 'error');
      return;
    }
    const found = findPrefixRegion(regionId);
    if (!found) return;
    prefixSnapshot = cloneRegion(found.region);
    prefixEditingId = regionId;
    prefixCollapsed.delete(regionId);
    showMsg('prefix-msg', '', '');
    renderPrefixTable();
  }

  function cancelPrefixRegion(regionId) {
    if (prefixEditingId !== regionId || !prefixSnapshot) return;
    const found = findPrefixRegion(regionId);
    if (!found) return;
    const index = prefixDraft[found.kind].findIndex((region) => region.id === regionId);
    if (index >= 0) prefixDraft[found.kind][index] = cloneRegion(prefixSnapshot);
    prefixEditingId = null;
    prefixSnapshot = null;
    showMsg('prefix-msg', '', '');
    renderPrefixTable();
  }

  function addPrefixRegion(kind) {
    if (prefixEditingId) {
      showMsg('prefix-msg', '请先保存或取消正在编辑的区域', 'error');
      return;
    }
    syncPrefixDraft();
    const max = prefixDraft[kind].reduce((highest, region) => Math.max(highest, Number(region.sequence) || 0), 0);
    const region = {
      id: nextPrefixId(),
      area: '',
      sequence: max + 1,
      prefixes: [{ id: nextPrefixId(), prefix: '', remark: '' }],
      isNew: true,
    };
    prefixDraft[kind].push(region);
    prefixSnapshot = cloneRegion(region);
    prefixEditingId = region.id;
    prefixCollapsed.delete(region.id);
    prefixFocus = region.id;
    showMsg('prefix-msg', '', '');
    renderPrefixTable();
  }

  function addPrefixLine(regionId) {
    if (prefixEditingId !== regionId) return;
    syncPrefixDraft();
    const found = findPrefixRegion(regionId);
    if (!found) return;
    const row = { id: nextPrefixId(), prefix: '', remark: '' };
    found.region.prefixes.push(row);
    prefixCollapsed.delete(regionId);
    prefixFocus = row.id;
    renderPrefixTable();
  }

  function deletePrefixLine(regionId, rowId) {
    if (prefixEditingId !== regionId) return;
    syncPrefixDraft();
    const found = findPrefixRegion(regionId);
    if (!found) return;
    const { kind, region } = found;
    const row = region.prefixes.find((item) => item.id === rowId);
    if (!row) return;
    const label = (row.prefix || '').trim() || '这条前缀';
    if (region.prefixes.length === 1 && region.isNew) {
      if (!confirm('删除后该新增区域会去掉。确定删除吗？')) return;
      prefixDraft[kind] = prefixDraft[kind].filter((item) => item.id !== region.id);
      prefixEditingId = null;
      prefixSnapshot = null;
      renderPrefixTable();
      return;
    }
    if (region.prefixes.length === 1 && prefixDraft[kind].length === 1) {
      alert(`${kind}至少要保留一个区域`);
      return;
    }
    const removingRegion = region.prefixes.length === 1;
    const message = removingRegion
      ? `这是区域「${(region.area || '').trim() || '未命名'}」的最后一条前缀，删除后该区域会去掉并保存。确定删除吗？`
      : `确定删除前缀 ${label}？`;
    if (!confirm(message)) return;
    if (removingRegion) {
      const backup = cloneRegion(region);
      prefixDraft[kind] = prefixDraft[kind].filter((item) => item.id !== region.id);
      prefixEditingId = null;
      prefixSnapshot = null;
      persistPrefixDraft(null).then((ok) => {
        if (ok) return;
        prefixDraft[kind].push(backup);
        prefixDraft[kind].sort((a, b) => Number(a.sequence) - Number(b.sequence));
        prefixEditingId = backup.id;
        prefixSnapshot = cloneRegion(backup);
        renderPrefixTable();
      });
      return;
    }
    region.prefixes = region.prefixes.filter((item) => item.id !== rowId);
    renderPrefixTable();
  }

  function draftForSave(savingId) {
    const draft = { '国内': [], '国际': [] };
    ['国内', '国际'].forEach((kind) => {
      prefixDraft[kind].forEach((region) => {
        if (region.isNew && region.id !== savingId) return;
        draft[kind].push(region);
      });
    });
    return draft;
  }

  function validatePrefixDraft(draft) {
    const prefixes = new Set();
    const sequences = new Set();
    const names = new Set();
    for (const kind of ['国内', '国际']) {
      const regions = draft[kind];
      if (!regions.length) return `${kind}至少要有一个区域`;
      for (const region of regions) {
        const area = (region.area || '').trim();
        if (!area) return '请填写区域名称';
        if (area.length > 20) return '区域名称不能超过 20 个字';
        const nameKey = `${kind}|${area}`;
        if (names.has(nameKey)) return `${kind}下区域「${area}」重复`;
        names.add(nameKey);
        const sequence = Number(region.sequence);
        if (!Number.isInteger(sequence) || sequence < 1) return '序号须为正整数';
        const seqKey = `${kind}|${sequence}`;
        if (sequences.has(seqKey)) return `${kind}下序号 ${sequence} 重复`;
        sequences.add(seqKey);
        if (!region.prefixes.length) return `区域「${area}」至少要有一个前缀`;
        for (const row of region.prefixes) {
          const prefix = (row.prefix || '').trim().toUpperCase();
          if (!/^[A-Z]{1,4}$/.test(prefix)) return '前缀须为 1–4 位英文字母';
          if (prefixes.has(prefix)) return `前缀 ${prefix} 重复`;
          prefixes.add(prefix);
        }
      }
    }
    return '';
  }

  async function persistPrefixDraft(savingId) {
    syncPrefixDraft();
    const draft = draftForSave(savingId);
    const error = validatePrefixDraft(draft);
    if (error) { showMsg('prefix-msg', error, 'error'); return false; }
    const extras = [];
    ['国内', '国际'].forEach((kind) => {
      prefixDraft[kind].forEach((region) => {
        if (region.isNew && region.id !== savingId) extras.push({ kind, region: cloneRegion(region) });
      });
    });
    const rows = [];
    ['国内', '国际'].forEach((kind) => {
      draft[kind].forEach((region) => {
        region.prefixes.forEach((row) => {
          rows.push({
            classification: kind,
            area: region.area.trim(),
            sequence: Number(region.sequence),
            prefix: row.prefix.trim().toUpperCase(),
            remark: row.remark || '',
          });
        });
      });
    });
    const saveBtn = savingId ? document.querySelector(`[data-prefix-mode="${savingId}"]`) : null;
    if (saveBtn) saveBtn.disabled = true;
    const res = await apiFetch(apiUrl('settings/prefix-area/'), {
      method: 'PUT',
      body: JSON.stringify({ rows }),
    });
    if (saveBtn) saveBtn.disabled = false;
    showMsg('prefix-msg', res.success ? (res.message || '保存成功') : res.error, res.success ? 'success' : 'error');
    if (!res.success) return false;
    prefixEditingId = null;
    prefixSnapshot = null;
    await loadPrefixAreas();
    if (extras.length) {
      extras.forEach(({ kind, region }) => prefixDraft[kind].push(region));
      renderPrefixTable();
    }
    await refreshAreaOptionsCache();
    return true;
  }

  function savePrefixRegion(regionId) {
    return persistPrefixDraft(regionId);
  }

  // ========== 预报入库告警 ==========
  let tafEditCode = null;

  async function loadTafImport() {
    const res = await apiFetch(apiUrl('settings/taf-import/'));
    if (!res.success) { showMsg('taf-msg', res.error, 'error'); return; }
    const tbody = document.getElementById('taf-tbody');
    tbody.innerHTML = (res.data || []).map(row => `<tr>
      <td>${escHtml(row.airport_4code)}</td>
      <td>${row.taf_init_time == null ? '' : row.taf_init_time}</td>
      <td>${row.import_check_interval == null ? '' : row.import_check_interval + 'h'}</td>
      <td>${row.taf_max_delay == null ? '' : row.taf_max_delay}</td>
      <td>
        <button class="settings-edit-btn" onclick="SettingsModal.editTaf('${escHtml(row.airport_4code)}')">编辑</button>
        <button class="settings-del-btn" onclick="SettingsModal.deleteTaf('${escHtml(row.airport_4code)}')">删除</button>
      </td>
    </tr>`).join('');
    document.getElementById('taf-form-panel').style.display = 'none';
    tafEditCode = null;
  }

  function showTafForm(data, presetCode) {
    const panel = document.getElementById('taf-form-panel');
    panel.style.display = 'flex';
    panel.style.flexDirection = 'column';
    const code = data ? data.airport_4code : (presetCode || '');
    tafEditCode = data ? data.airport_4code : null;
    document.getElementById('taf-form-title').textContent = data ? '编辑预报入库告警' : '新增预报入库告警';
    const codeEl = document.getElementById('tf-4code');
    codeEl.disabled = !!data || !!presetCode;
    codeEl.value = code;
    document.getElementById('tf-init').value = data && data.taf_init_time != null ? data.taf_init_time : '';
    document.getElementById('tf-interval').value = data && String(data.import_check_interval) === '3' ? '3' : '6';
    document.getElementById('tf-delay').value = data && data.taf_max_delay != null ? data.taf_max_delay : '';
  }

  async function saveTafImport() {
    const code = document.getElementById('tf-4code').value.trim().toUpperCase();
    const hour = document.getElementById('tf-init').value;
    const interval = document.getElementById('tf-interval').value;
    const delay = document.getElementById('tf-delay').value;
    if (!/^[A-Z]{4}$/.test(code)) { showMsg('taf-msg', '机场四字代码必须为恰好4位英文大写字母', 'error'); return; }
    if (hour === '' || isNaN(hour) || hour < 0 || hour > 23) { showMsg('taf-msg', '首份发布时间须为 0–23 的整数', 'error'); return; }
    if (delay === '' || isNaN(delay) || delay < 0 || delay > 60) { showMsg('taf-msg', '接收延迟须为 0–60 的整数', 'error'); return; }
    const payload = {
      airport_4code: code,
      taf_init_time: parseInt(hour, 10),
      import_check_interval: parseInt(interval, 10),
      taf_max_delay: parseInt(delay, 10),
    };
    const url = tafEditCode ? apiUrl(`settings/taf-import/${tafEditCode}/`) : apiUrl('settings/taf-import/');
    const res = await apiFetch(url, { method: tafEditCode ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    showMsg('taf-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
    if (res.success) await loadTafImport();
  }

  // ========== 公开接口 ==========
  window.SettingsModal = {
    open() {
      applySettingsTabVisibility();
      window.showModal('settings-modal');
      const first = document.querySelector('.settings-tab:not([style*="display: none"])');
      switchTab(first ? first.getAttribute('data-tab') : 'airport-info');
    },

    // 机场
    editAirport(code) {
      airportEditCode = code;
      apiFetch(apiUrl(`settings/airport-info/${code}/`)).then(res => {
        if (res.success && res.data) showAirportForm(res.data);
      });
    },
    addAirportForCode(code) {
      airportEditCode = null;
      showAirportForm(null, code);
    },

    // 打开设置页，按该四字代码查询并进入配置页
    openAndEdit(code) {
      window.showModal('settings-modal');
      switchTab('airport-info').then(() => searchAirport(code, true));
    },
    newAirportWithCode(code) {
      this.openAndEdit(code);
    },
    openAndEditTaf(code) {
      window.showModal('settings-modal');
      switchTab('taf-import').then(() => {
        apiFetch(apiUrl(`settings/taf-import/${code}/`)).then(res => {
          if (res.success && res.data) showTafForm(res.data);
          else showTafForm(null, code);
        });
      });
    },
    editTaf(code) {
      apiFetch(apiUrl(`settings/taf-import/${code}/`)).then(res => {
        if (res.success && res.data) showTafForm(res.data);
      });
    },
    async deleteTaf(code) {
      if (!confirm(`确定删除 ${code} 的预报入库告警？`)) return;
      const res = await apiFetch(apiUrl(`settings/taf-import/${code}/`), { method: 'DELETE' });
      showMsg('taf-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) await loadTafImport();
    },
    async deleteAirport(code) {
      if (!confirm(`确定删除机场 ${code}？`)) return;
      const res = await apiFetch(apiUrl(`settings/airport-info/${code}/`), { method: 'DELETE' });
      showMsg('airport-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) await searchAirport(code, false);
    },

    // 定时器
    saveTimer,

    // 告警阈值
    editThreshold() {
      switchTab('alert-thresholds').then(() => {
        thresholdEditing = true;
        paintThresholdMode();
      });
    },
    async deleteThreshold(code) {
      if (!confirm(`确定删除 ${code} 的告警阈值？`)) return;
      const res = await apiFetch(apiUrl(`settings/alert-thresholds/${code}/`), { method: 'DELETE' });
      showMsg('threshold-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) await loadAlertThresholds();
    },

    // 天气类型
    editWeatherType() {
      switchTab('weather-type').then(() => {
        wtypeEditing = true;
        paintWTypeMode();
      });
    },
    async deleteWeatherType(id) {
      if (!confirm('确定删除该天气类型？')) return;
      const res = await apiFetch(apiUrl(`settings/weather-type/${id}/`), { method: 'DELETE' });
      showMsg('wtype-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) await loadWeatherType();
    },

    // 天气告警等级
    editWeatherAlert(id) {
      walertEditId = id;
      apiFetch(apiUrl('settings/weather-alert/')).then(res => {
        const r = res.data && res.data.find(x => x.id === id);
        if (r) { weatherTypeCodes = res.type_codes || []; showWAlertForm(r); }
      });
    },
    async deleteWeatherAlert(id) {
      if (!confirm('确定删除该天气告警等级记录？')) return;
      const res = await apiFetch(apiUrl(`settings/weather-alert/${id}/`), { method: 'DELETE' });
      showMsg('walert-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) await loadWeatherAlert();
    },

    // 告警阈值 — 查看(只读)
    viewThreshold() {
      switchTab('alert-thresholds');
    },

  };

  // DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
