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
  let areaEditId = null;

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
    return h;
  }

  async function apiFetch(url, options) {
    const res = await fetch(url, { headers: getHeaders(), ...options });
    return res.json();
  }

  function showMsg(elId, text, type) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = text;
    el.className = 'settings-msg ' + (type || '');
    if (text) setTimeout(() => { if (el.textContent === text) el.textContent = ''; }, 4000);
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
    document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.settings-tab-pane').forEach(p => p.classList.remove('active'));
    const btn = document.querySelector(`.settings-tab[data-tab="${tabName}"]`);
    const pane = document.getElementById(`settings-pane-${tabName}`);
    if (btn) btn.classList.add('active');
    if (pane) pane.classList.add('active');
    return loadTab(tabName);
  }

  async function loadTab(tabName) {
    switch (tabName) {
      case 'airport-info': await loadAirportInfo(); break;
      case 'area-options': await loadAreaOptions(); break;
      case 'data-refresh-timer': await loadTimers(); break;
      case 'popup': await loadPopupSettings(); break;
      case 'alert-thresholds': await loadAlertThresholds(); break;
      case 'weather-type': await loadWeatherType(); break;
      case 'weather-alert': await loadWeatherAlert(); break;
      case 'airport-location': await loadAirportLocation(); break;
      case 'radar-alert': await loadRadarAlertSettings(); break;
      case 'map-style': await loadMapStyleSettings(); break;
      case 'trend-alert':
        if (window.TrendAlertSettings) await window.TrendAlertSettings.load();
        break;
    }
  }

  // ========== Tab1: 机场信息 ==========
  async function loadAirportInfo() {
    await refreshAreaOptionsCache();
    const res = await apiFetch(apiUrl('settings/airport-info/'));
    if (!res.success) { showMsg('airport-msg', res.error, 'error'); return; }
    const tbody = document.getElementById('airport-tbody');
    tbody.innerHTML = res.data.map(a => {
      const isDefault = a.airport_4code === 'default';
      const ops = isDefault
        ? '<span class="settings-readonly-badge">系统默认</span>'
        : `<button class="settings-edit-btn" onclick="SettingsModal.editAirport('${escHtml(a.airport_4code)}')">编辑</button>
           <button class="settings-del-btn" onclick="SettingsModal.deleteAirport('${escHtml(a.airport_4code)}')">删除</button>`;
      return `<tr class="${isDefault ? 'settings-row-readonly' : ''}">
        <td>${escHtml(a.airport_4code)}</td>
        <td>${escHtml(a.airport_name)}</td>
        <td>${escHtml(a.classification)}</td>
        <td>${escHtml(a.area)}</td>
        <td>${escHtml(a.taf_init_time)}</td>
        <td>${a.import_check_interval}h</td>
        <td>${escHtml(a.taf_max_delay)}</td>
        <td>${escHtml(a.airport_3code)}</td>
        <td>${ops}</td>
      </tr>`;
    }).join('');
    hideAirportForm();
  }

  async function refreshAreaOptionsCache() {
    const res = await apiFetch(apiUrl('settings/area-options/'));
    if (!res.success) return;
    areaOptions = {};
    res.data.forEach(o => {
      if (!areaOptions[o.classification]) areaOptions[o.classification] = [];
      areaOptions[o.classification].push(o.area);
    });
  }

  function updateAreaSelect(classification) {
    const sel = document.getElementById('af-area');
    const areas = areaOptions[classification] || [];
    sel.innerHTML = areas.map(a => `<option value="${escHtml(a)}">${escHtml(a)}</option>`).join('');
  }

  function showAirportForm(data) {
    const panel = document.getElementById('airport-form-panel');
    panel.style.display = 'flex';
    panel.style.flexDirection = 'column';
    document.getElementById('airport-form-title').textContent = data ? '编辑机场' : '新增机场';

    const isEdit = !!data;
    document.getElementById('af-4code').disabled = isEdit;
    document.getElementById('af-4code').value = data ? data.airport_4code : '';
    document.getElementById('af-3code').value = data ? (data.airport_3code || '') : '';
    document.getElementById('af-name').value = data ? (data.airport_name || '') : '';
    document.getElementById('af-taf-init').value = data ? (data.taf_init_time ?? '') : '';
    document.getElementById('af-max-delay').value = data ? (data.taf_max_delay ?? '') : '';
    document.getElementById('af-area-code').value = data ? (data.area_code || '') : '';
    document.getElementById('af-forecast-phone').value = data ? (data.forecast_phone || '') : '';
    document.getElementById('af-obs-phone').value = data ? (data.observation_phone || '') : '';
    document.getElementById('af-other-phone').value = data ? (data.other_phone || '') : '';

    const classification = data ? (data.classification || '国内') : '国内';
    const chk = document.getElementById('af-classification-chk');
    chk.checked = classification === '国际';
    updateAreaSelect(classification);
    if (data && data.area) document.getElementById('af-area').value = data.area;

    const intervalChk = document.getElementById('af-interval-chk');
    intervalChk.checked = data ? (parseInt(data.import_check_interval) === 6) : false;
  }

  function hideAirportForm() {
    document.getElementById('airport-form-panel').style.display = 'none';
    airportEditCode = null;
  }

  async function saveAirport() {
    const code = document.getElementById('af-4code').value.trim().toUpperCase();
    const a3 = document.getElementById('af-3code').value.trim().toUpperCase();
    const name = document.getElementById('af-name').value.trim();
    const classificationChk = document.getElementById('af-classification-chk').checked;
    const classification = classificationChk ? '国际' : '国内';
    const area = document.getElementById('af-area').value;
    const tafInit = document.getElementById('af-taf-init').value;
    const intervalChk = document.getElementById('af-interval-chk').checked;
    const importInterval = intervalChk ? 6 : 3;
    const maxDelay = document.getElementById('af-max-delay').value;

    if (!code || code.length !== 4 || !/^[A-Z]{4}$/.test(code)) {
      showMsg('airport-msg', '机场四字代码必须为恰好4位英文大写字母', 'error'); return;
    }
    if (a3 && (a3.length !== 3 || !/^[A-Z]{3}$/.test(a3))) {
      showMsg('airport-msg', '机场三字代码必须为恰好3位英文大写字母', 'error'); return;
    }
    if (!name || name.length < 3 || name.length > 15) {
      showMsg('airport-msg', '机场名称为3–15位字符', 'error'); return;
    }
    if (!area) { showMsg('airport-msg', '请选择区域', 'error'); return; }
    if (tafInit === '' || isNaN(tafInit)) { showMsg('airport-msg', '请填写首份预报发布时间', 'error'); return; }
    if (maxDelay === '' || isNaN(maxDelay) || maxDelay < 0 || maxDelay > 99) {
      showMsg('airport-msg', '预报接收延迟时间需为0–99的整数', 'error'); return;
    }

    const payload = {
      airport_4code: code,
      airport_3code: a3 || null,
      airport_name: name,
      classification,
      area,
      taf_init_time: parseInt(tafInit),
      import_check_interval: importInterval,
      taf_max_delay: parseInt(maxDelay),
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
      await loadAirportInfo();
    } else {
      showMsg('airport-msg', res.error, 'error');
    }
  }

  // ========== Tab2: 区域信息 ==========
  async function loadAreaOptions() {
    const res = await apiFetch(apiUrl('settings/area-options/'));
    if (!res.success) { showMsg('area-msg', res.error, 'error'); return; }
    const tbody = document.getElementById('area-tbody');
    let lastClass = null;
    const rows = [];
    res.data.forEach(o => {
      if (lastClass !== null && o.classification !== lastClass) {
        rows.push(`<tr class="settings-area-divider-row"><td colspan="4"><div class="settings-area-divider"></div></td></tr>`);
      }
      rows.push(`<tr>
        <td>${escHtml(o.classification)}</td>
        <td>${escHtml(o.area)}</td>
        <td>${escHtml(o.sequence)}</td>
        <td>
          <button class="settings-edit-btn" onclick="SettingsModal.editArea(${o.id})">编辑</button>
          <button class="settings-del-btn" onclick="SettingsModal.deleteArea(${o.id})">删除</button>
        </td>
      </tr>`);
      lastClass = o.classification;
    });
    tbody.innerHTML = rows.join('');
    hideAreaForm();
  }

  function showAreaForm(data) {
    const panel = document.getElementById('area-form-panel');
    panel.style.display = 'flex';
    panel.style.flexDirection = 'column';
    document.getElementById('area-form-title').textContent = data ? '编辑区域' : '新增区域';
    const chk = document.getElementById('aof-classification-chk');
    const classification = data ? (data.classification || '国内') : '国内';
    chk.checked = classification === '国际';
    document.getElementById('aof-area').value = data ? (data.area || '') : '';
    document.getElementById('aof-sequence').value = data ? (data.sequence ?? '') : '';
  }

  function hideAreaForm() {
    document.getElementById('area-form-panel').style.display = 'none';
    areaEditId = null;
  }

  async function saveArea() {
    const chk = document.getElementById('aof-classification-chk').checked;
    const classification = chk ? '国际' : '国内';
    const area = document.getElementById('aof-area').value.trim();
    const sequence = document.getElementById('aof-sequence').value;

    if (!area || area.length < 2 || area.length > 10) {
      showMsg('area-msg', '区域名称为2–10位字符', 'error'); return;
    }
    if (!sequence || isNaN(sequence) || parseInt(sequence) < 1) {
      showMsg('area-msg', '排序需为正整数', 'error'); return;
    }

    const payload = { classification, area, sequence: parseInt(sequence) };
    const isEdit = areaEditId !== null;
    const url = isEdit
      ? apiUrl(`settings/area-options/${areaEditId}/`)
      : apiUrl('settings/area-options/');
    const method = isEdit ? 'PUT' : 'POST';

    const res = await apiFetch(url, { method, body: JSON.stringify(payload) });
    if (res.success) {
      showMsg('area-msg', res.message, 'success');
      await loadAreaOptions();
      await refreshAreaOptionsCache();
    } else {
      showMsg('area-msg', res.error, 'error');
    }
  }

  // ========== Tab3: 数据自动更新 ==========
  async function loadTimers() {
    const res = await apiFetch(apiUrl('settings/data-refresh-timer/'));
    if (!res.success) { showMsg('timer-msg', res.error, 'error'); return; }
    const tbody = document.getElementById('timer-tbody');
    tbody.innerHTML = res.data.map(t => `
      <tr id="timer-row-${t.id}">
        <td>${escHtml(t.data_name)}</td>
        <td><input type="number" class="settings-timer-input" id="timer-init-${t.id}" value="${t.init_time}" min="0" max="50" step="0.5"></td>
        <td><input type="number" class="settings-timer-input" id="timer-interval-${t.id}" value="${t.interval}" min="0.5" max="30" step="0.5"></td>
        <td><button class="settings-save-inline-btn" onclick="SettingsModal.saveTimer(${t.id})">保存</button></td>
      </tr>`).join('');
  }

  async function saveTimer(id) {
    const initVal = parseFloat(document.getElementById(`timer-init-${id}`).value);
    const intervalVal = parseFloat(document.getElementById(`timer-interval-${id}`).value);

    if (isNaN(initVal) || initVal < 0 || initVal > 50 || (initVal * 2) % 1 !== 0) {
      showMsg('timer-msg', 'init_time 需为0–50之间0.5的倍数', 'error'); return;
    }
    if (isNaN(intervalVal) || intervalVal < 0.5 || intervalVal > 30 || (intervalVal * 2) % 1 !== 0) {
      showMsg('timer-msg', 'interval 需为0.5–30之间0.5的倍数', 'error'); return;
    }

    const res = await apiFetch(apiUrl(`settings/data-refresh-timer/${id}/`), {
      method: 'PUT',
      body: JSON.stringify({ init_time: initVal, interval: intervalVal })
    });
    showMsg('timer-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
  }

  // ========== Tab4: 弹窗设置 ==========
  let opLevelTrack, parkLevelTrack;

  async function loadPopupSettings() {
    opLevelTrack = opLevelTrack || initTrack(document.getElementById('pf-op-level-track'));
    parkLevelTrack = parkLevelTrack || initTrack(document.getElementById('pf-park-level-track'));

    const res = await apiFetch(apiUrl('settings/popup/'));
    if (!res.success) { showMsg('popup-msg', res.error, 'error'); return; }
    const d = res.data;
    document.getElementById('pf-leeway').value = d.operation_metar_popup_leeway ?? 0;
    document.getElementById('pf-trace-time').value = d.trace_time ?? 6;
    opLevelTrack.setVal(d.operation_metar_popup_level || 'Y');
    parkLevelTrack.setVal(d.parking_metar_popup_level || 'Y');
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
      showMsg('popup-msg', '保存成功', 'success');
      window.__popupTraceHours = traceTime;
    } else {
      showMsg('popup-msg', res.error, 'error');
    }
  }

  // ========== Tab6: 机场告警阈值 ==========
  const TF_MAP = [
    ['visibility_m_red','tf-vis-r'],['visibility_m_yellow','tf-vis-y'],['visibility_m_green','tf-vis-g'],
    ['cloud_min_red','tf-cld-r'],['cloud_min_yellow','tf-cld-y'],['cloud_min_green','tf-cld-g'],
    ['average_wind_speed_mps_red','tf-ws-r'],['average_wind_speed_mps_yellow','tf-ws-y'],['average_wind_speed_mps_green','tf-ws-g'],
    ['gust_mps_red','tf-gs-r'],['gust_mps_yellow','tf-gs-y'],['gust_mps_green','tf-gs-g'],
    ['temperature_cold_red','tf-tc-r'],['temperature_cold_yellow','tf-tc-y'],['temperature_cold_green','tf-tc-g'],
    ['temperature_hot_red','tf-th-r'],['temperature_hot_yellow','tf-th-y'],['temperature_hot_green','tf-th-g'],
    ['rvr_m_red','tf-rvr-r'],['rvr_m_yellow','tf-rvr-y'],['rvr_m_green','tf-rvr-g'],
  ];
  let thresholdEditCode = null;
  let thresholdReadonly = false;

  async function loadAlertThresholds() {
    const res = await apiFetch(apiUrl('settings/alert-thresholds/'));
    if (!res.success) { showMsg('threshold-msg', res.error, 'error'); return; }
    const tbody = document.getElementById('threshold-tbody');
    tbody.innerHTML = res.data.map(r => {
      const isDefault = r.airport_4code === 'default';
      const ops = isDefault
        ? `<button class="settings-edit-btn" onclick="SettingsModal.viewThreshold('${r.airport_4code}')">查看</button>`
        : `<button class="settings-edit-btn" onclick="SettingsModal.editThreshold('${r.airport_4code}')">编辑</button>
           <button class="settings-del-btn" onclick="SettingsModal.deleteThreshold('${r.airport_4code}')">删除</button>`;
      const fmt = (a,b,c) => `${a??'–'}/${b??'–'}/${c??'–'}`;
      return `<tr class="${isDefault?'settings-row-readonly':''}">
        <td>${escHtml(r.airport_4code)}</td>
        <td>${fmt(r.visibility_m_red,r.visibility_m_yellow,r.visibility_m_green)}</td>
        <td>${fmt(r.cloud_min_red,r.cloud_min_yellow,r.cloud_min_green)}</td>
        <td>${escHtml(r.min_cloud_amt || 'SCT')}</td>
        <td>${fmt(r.average_wind_speed_mps_red,r.average_wind_speed_mps_yellow,r.average_wind_speed_mps_green)}</td>
        <td>${fmt(r.gust_mps_red,r.gust_mps_yellow,r.gust_mps_green)}</td>
        <td>${fmt(r.temperature_cold_red,r.temperature_cold_yellow,r.temperature_cold_green)}</td>
        <td>${fmt(r.temperature_hot_red,r.temperature_hot_yellow,r.temperature_hot_green)}</td>
        <td>${fmt(r.rvr_m_red,r.rvr_m_yellow,r.rvr_m_green)}</td>
        <td>${ops}</td>
      </tr>`;
    }).join('');
    hideThresholdForm();
  }

  function showThresholdForm(data, readonly) {
    thresholdReadonly = !!readonly;
    const panel = document.getElementById('threshold-form-panel');
    panel.style.display = 'flex'; panel.style.flexDirection = 'column';
    document.getElementById('threshold-form-title').textContent =
      thresholdReadonly ? '查看告警阈值（只读）' : (data ? '编辑告警阈值' : '新增告警阈值');
    const codeEl = document.getElementById('tf-4code');
    codeEl.disabled = thresholdReadonly || !!data;
    codeEl.value = data ? data.airport_4code : '';
    TF_MAP.forEach(([field, id]) => {
      const el = document.getElementById(id);
      if (el) { el.value = data ? (data[field] ?? '') : ''; el.disabled = thresholdReadonly; }
    });
    const amtEl = document.getElementById('tf-min-cloud-amt');
    if (amtEl) {
      amtEl.value = (data && data.min_cloud_amt) ? data.min_cloud_amt : 'SCT';
      amtEl.disabled = thresholdReadonly;
    }
    document.getElementById('threshold-save-btn').style.display = thresholdReadonly ? 'none' : '';
    document.getElementById('threshold-cancel-btn').textContent = thresholdReadonly ? '关闭' : '取消';
  }
  function hideThresholdForm() {
    document.getElementById('threshold-form-panel').style.display = 'none';
    thresholdEditCode = null;
    thresholdReadonly = false;
    TF_MAP.forEach(([, id]) => { const el = document.getElementById(id); if (el) el.disabled = false; });
    const amtEl = document.getElementById('tf-min-cloud-amt');
    if (amtEl) amtEl.disabled = false;
    document.getElementById('threshold-save-btn').style.display = '';
    document.getElementById('threshold-cancel-btn').textContent = '取消';
  }

  async function saveThreshold() {
    const code = document.getElementById('tf-4code').value.trim().toUpperCase();
    if (!thresholdEditCode && (code.length !== 4 || !/^[A-Z]{4}$/.test(code))) {
      showMsg('threshold-msg', '机场四字代码必须为4位英文大写字母', 'error'); return;
    }
    const payload = { airport_4code: code };
    for (const [field, id] of TF_MAP) {
      const val = document.getElementById(id).value;
      if (val === '' || isNaN(val)) { showMsg('threshold-msg', `${field} 为必填数字`, 'error'); return; }
      payload[field] = parseInt(val);
    }
    const minCloudAmt = document.getElementById('tf-min-cloud-amt').value;
    if (!['FEW', 'SCT', 'BKN', 'OVC'].includes(minCloudAmt)) {
      showMsg('threshold-msg', '云量下限只能是 FEW、SCT、BKN、OVC', 'error'); return;
    }
    payload.min_cloud_amt = minCloudAmt;
    const isEdit = !!thresholdEditCode;
    const url = isEdit ? apiUrl(`settings/alert-thresholds/${thresholdEditCode}/`) : apiUrl('settings/alert-thresholds/');
    const res = await apiFetch(url, { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    if (res.success) { showMsg('threshold-msg', res.message, 'success'); await loadAlertThresholds(); }
    else showMsg('threshold-msg', res.error, 'error');
  }

  // ========== Tab7: 天气类型信息 ==========
  let wtypeEditId = null;

  async function loadWeatherType() {
    const res = await apiFetch(apiUrl('settings/weather-type/'));
    if (!res.success) { showMsg('wtype-msg', res.error, 'error'); return; }
    const tbody = document.getElementById('wtype-tbody');
    tbody.innerHTML = res.data.map(r => `
      <tr>
        <td>${escHtml(r.weather_type_code)}</td>
        <td>${escHtml(r.description_cn)}</td>
        <td>${escHtml(r.description_en)}</td>
        <td>
          <button class="settings-edit-btn" onclick="SettingsModal.editWeatherType(${r.id})">编辑</button>
          <button class="settings-del-btn" onclick="SettingsModal.deleteWeatherType(${r.id})">删除</button>
        </td>
      </tr>`).join('');
    hideWTypeForm();
  }

  function showWTypeForm(data) {
    const panel = document.getElementById('wtype-form-panel');
    panel.style.display = 'flex'; panel.style.flexDirection = 'column';
    document.getElementById('wtype-form-title').textContent = data ? '编辑天气类型' : '新增天气类型';
    document.getElementById('wtf-code').value = data ? (data.weather_type_code || '') : '';
    document.getElementById('wtf-cn').value = data ? (data.description_cn || '') : '';
    document.getElementById('wtf-en').value = data ? (data.description_en || '') : '';
  }
  function hideWTypeForm() {
    document.getElementById('wtype-form-panel').style.display = 'none';
    wtypeEditId = null;
  }

  async function saveWeatherType() {
    const code = document.getElementById('wtf-code').value.trim();
    const cn = document.getElementById('wtf-cn').value.trim();
    const en = document.getElementById('wtf-en').value.trim();
    if (!code || code.length !== 1) { showMsg('wtype-msg', '天气类型代码必须为1位字符', 'error'); return; }
    if (!cn) { showMsg('wtype-msg', '中文说明为必填项', 'error'); return; }
    if (!en) { showMsg('wtype-msg', '英文说明为必填项', 'error'); return; }
    const payload = { weather_type_code: code, description_cn: cn, description_en: en };
    const isEdit = wtypeEditId !== null;
    const url = isEdit ? apiUrl(`settings/weather-type/${wtypeEditId}/`) : apiUrl('settings/weather-type/');
    const res = await apiFetch(url, { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    if (res.success) { showMsg('wtype-msg', res.message, 'success'); await loadWeatherType(); }
    else showMsg('wtype-msg', res.error, 'error');
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
          <button class="settings-del-btn" onclick="SettingsModal.deleteWeatherAlert(${r.id})">删除</button>
        </td>
      </tr>`).join('');
    hideWAlertForm();
  }

  function showWAlertForm(data) {
    const panel = document.getElementById('walert-form-panel');
    panel.style.display = 'flex'; panel.style.flexDirection = 'column';
    document.getElementById('walert-form-title').textContent = data ? '编辑天气告警等级' : '新增天气告警等级';
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

  // ========== Tab9: 机场坐标（按需查询） ==========
  let locEditCode = null;
  let locCurrentCode = null;  // 当前查询的四字代码

  function loadAirportLocation() {
    // Tab切换时只重置到搜索状态，不发请求
    document.getElementById('loc-search-input').value = '';
    document.getElementById('loc-result-area').innerHTML = '';
    document.getElementById('loc-form-panel').style.display = 'none';
    locCurrentCode = null;
    locEditCode = null;
  }

  async function searchLocation() {
    const code = document.getElementById('loc-search-input').value.trim().toUpperCase();
    if (code.length !== 4 || !/^[A-Z]{4}$/.test(code)) {
      showMsg('loc-msg', '请输入4位英文大写四字代码', 'error'); return;
    }
    locCurrentCode = code;
    hideLocForm();
    const res = await apiFetch(apiUrl(`settings/airport-location/${code}/`));
    const area = document.getElementById('loc-result-area');
    if (res.success) {
      const r = res.data;
      area.innerHTML = `
        <table class="settings-table settings-table-auto loc-result-table">
          <thead><tr><th>四字代码</th><th>纬度</th><th>经度</th><th>机场名称</th><th>操作</th></tr></thead>
          <tbody><tr>
            <td>${escHtml(r.airport_4code)}</td>
            <td>${r.latitude}</td>
            <td>${r.longitude}</td>
            <td>${escHtml(r.airport_name)}</td>
            <td>
              <button class="settings-edit-btn" onclick="SettingsModal.editLocation('${escHtml(r.airport_4code)}')">编辑</button>
              <button class="settings-del-btn" onclick="SettingsModal.deleteLocation('${escHtml(r.airport_4code)}')">删除</button>
            </td>
          </tr></tbody>
        </table>`;
    } else {
      area.innerHTML = `
        <div class="loc-not-found">
          未找到 <strong>${escHtml(code)}</strong> 的坐标记录
          <button class="settings-add-btn loc-add-inline-btn" onclick="SettingsModal.addLocationForCode('${escHtml(code)}')">+ 新增</button>
        </div>`;
    }
  }

  function showLocForm(data, preset4code) {
    const panel = document.getElementById('loc-form-panel');
    panel.style.display = 'block';
    document.getElementById('loc-form-title').textContent = data ? '编辑机场坐标' : '新增机场坐标';
    const codeEl = document.getElementById('lf-4code');
    codeEl.disabled = !!data || !!preset4code;
    codeEl.value = data ? data.airport_4code : (preset4code || '');
    document.getElementById('lf-lat').value = data ? data.latitude : '';
    document.getElementById('lf-lon').value = data ? data.longitude : '';
    document.getElementById('lf-name').value = data ? (data.airport_name || '') : '';
  }
  function hideLocForm() {
    document.getElementById('loc-form-panel').style.display = 'none';
    locEditCode = null;
  }

  async function saveLocation() {
    const code = document.getElementById('lf-4code').value.trim().toUpperCase();
    if (!locEditCode && (code.length !== 4 || !/^[A-Z]{4}$/.test(code))) {
      showMsg('loc-msg', '机场四字代码必须为4位英文大写字母', 'error'); return;
    }
    const lat = document.getElementById('lf-lat').value;
    const lon = document.getElementById('lf-lon').value;
    if (lat === '' || isNaN(lat)) { showMsg('loc-msg', '纬度为必填数字', 'error'); return; }
    if (lon === '' || isNaN(lon)) { showMsg('loc-msg', '经度为必填数字', 'error'); return; }
    const payload = {
      airport_4code: code,
      latitude: parseFloat(lat),
      longitude: parseFloat(lon),
      airport_name: document.getElementById('lf-name').value.trim() || null,
    };
    const isEdit = !!locEditCode;
    const url = isEdit ? apiUrl(`settings/airport-location/${locEditCode}/`) : apiUrl('settings/airport-location/');
    const res = await apiFetch(url, { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    if (res.success) {
      showMsg('loc-msg', res.message, 'success');
      hideLocForm();
      // 保存后自动刷新搜索结果
      const savedCode = locEditCode || code;
      document.getElementById('loc-search-input').value = savedCode;
      locCurrentCode = savedCode;
      await searchLocation();
    } else {
      showMsg('loc-msg', res.error, 'error');
    }
  }

  // ========== Tab10: 雷达告警 ==========
  let _radarCfg = null;

  async function loadRadarAlertSettings() {
    const res = await apiFetch(apiUrl('radar/config/'));
    if (!res.success) { showMsg('radar-msg', res.error || '加载失败', 'error'); return; }
    _radarCfg = res.config;
    fillRadarForm(_radarCfg);
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
      fillRadarForm(res.config);
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

    // 关闭按钮
    document.getElementById('settings-modal-close').addEventListener('click', () => {
      window.hideModal('settings-modal');
    });

    const suBtn = document.getElementById('superuser-btn');
    if (suBtn) {
      suBtn.addEventListener('click', () => {
        if (typeof openSuperuserAdmin === 'function') openSuperuserAdmin();
        else {
          const tm = window.timeMode || window.currentTimeMode || 'current';
          window.location.href = `/${tm}/access-admin/`;
        }
      });
    }

    // classification联动 area select (机场信息Tab)
    const afClassChk = document.getElementById('af-classification-chk');
    if (afClassChk) {
      afClassChk.addEventListener('change', () => {
        updateAreaSelect(afClassChk.checked ? '国际' : '国内');
      });
    }

    // 机场表单按钮
    document.getElementById('airport-add-btn').addEventListener('click', () => {
      airportEditCode = null;
      showAirportForm(null);
    });
    document.getElementById('airport-save-btn').addEventListener('click', saveAirport);
    document.getElementById('airport-cancel-btn').addEventListener('click', hideAirportForm);

    // 区域表单按钮
    document.getElementById('area-add-btn').addEventListener('click', () => {
      areaEditId = null;
      showAreaForm(null);
    });
    document.getElementById('area-save-btn').addEventListener('click', saveArea);
    document.getElementById('area-cancel-btn').addEventListener('click', hideAreaForm);

    // 弹窗设置保存
    document.getElementById('popup-save-btn').addEventListener('click', savePopupSettings);

    // 告警阈值
    document.getElementById('threshold-add-btn').addEventListener('click', () => { thresholdEditCode = null; showThresholdForm(null); });
    document.getElementById('threshold-save-btn').addEventListener('click', saveThreshold);
    document.getElementById('threshold-cancel-btn').addEventListener('click', hideThresholdForm);

    // 天气类型
    document.getElementById('wtype-add-btn').addEventListener('click', () => { wtypeEditId = null; showWTypeForm(null); });
    document.getElementById('wtype-save-btn').addEventListener('click', saveWeatherType);
    document.getElementById('wtype-cancel-btn').addEventListener('click', hideWTypeForm);

    // 天气告警等级
    document.getElementById('walert-add-btn').addEventListener('click', () => { walertEditId = null; showWAlertForm(null); });
    document.getElementById('walert-save-btn').addEventListener('click', saveWeatherAlert);
    document.getElementById('walert-cancel-btn').addEventListener('click', hideWAlertForm);

    // 机场坐标 — 搜索
    const locSearchInput = document.getElementById('loc-search-input');
    locSearchInput.addEventListener('keydown', e => { if (e.key === 'Enter') searchLocation(); });
    document.getElementById('loc-search-btn').addEventListener('click', searchLocation);
    document.getElementById('loc-save-btn').addEventListener('click', saveLocation);
    document.getElementById('loc-cancel-btn').addEventListener('click', hideLocForm);

    // 雷达告警
    const radarSave = document.getElementById('radar-save-btn');
    if (radarSave) {
      radarSave.addEventListener('click', saveRadarAlertSettings);
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
    const mapStyleSave = document.getElementById('map-style-save-btn');
    if (mapStyleSave) {
      mapStyleSave.addEventListener('click', saveMapStyleSettings);
    }
  }

  function applySettingsTabVisibility() {
    const TAB_PERM = {
      'airport-info': 'settings_airport_info',
      'area-options': 'settings_area_options',
      'data-refresh-timer': 'settings_data_refresh',
      'popup': 'settings_popup',
      'alert-thresholds': 'settings_alert_thresholds',
      'weather-type': 'settings_weather_type',
      'weather-alert': 'settings_weather_alert',
      'airport-location': 'settings_airport_location',
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
      apiFetch(apiUrl('settings/airport-info/')).then(res => {
        const a = res.data && res.data.find(x => x.airport_4code === code);
        if (a) showAirportForm(a);
      });
    },

    // 新增机场（预填四字代码）—— 等待 loadAirportInfo 完成（其末尾会 hideAirportForm）再显示表单
    newAirportWithCode(code) {
      window.showModal('settings-modal');
      switchTab('airport-info').then(() => {
        airportEditCode = null;
        showAirportForm(null);
        const el = document.getElementById('af-4code');
        if (el) el.value = (code || '').toUpperCase();
      });
    },

    // 打开设置页并直接进入指定机场的编辑表单
    openAndEdit(code) {
      window.showModal('settings-modal');
      switchTab('airport-info').then(() => {
        airportEditCode = code;
        apiFetch(apiUrl('settings/airport-info/')).then(res => {
          const a = res.data && res.data.find(x => x.airport_4code === code);
          if (a) showAirportForm(a);
        });
      });
    },
    async deleteAirport(code) {
      if (!confirm(`确定删除机场 ${code}？`)) return;
      const res = await apiFetch(apiUrl(`settings/airport-info/${code}/`), { method: 'DELETE' });
      showMsg('airport-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) await loadAirportInfo();
    },

    // 区域
    editArea(id) {
      areaEditId = id;
      apiFetch(apiUrl('settings/area-options/')).then(res => {
        const o = res.data && res.data.find(x => x.id === id);
        if (o) showAreaForm(o);
      });
    },
    async deleteArea(id) {
      if (!confirm('确定删除该区域选项？')) return;
      const res = await apiFetch(apiUrl(`settings/area-options/${id}/`), { method: 'DELETE' });
      showMsg('area-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) { await loadAreaOptions(); await refreshAreaOptionsCache(); }
    },

    // 定时器
    saveTimer,

    // 告警阈值
    editThreshold(code) {
      thresholdEditCode = code;
      apiFetch(apiUrl('settings/alert-thresholds/')).then(res => {
        const r = res.data && res.data.find(x => x.airport_4code === code);
        if (r) showThresholdForm(r);
      });
    },
    async deleteThreshold(code) {
      if (!confirm(`确定删除 ${code} 的告警阈值？`)) return;
      const res = await apiFetch(apiUrl(`settings/alert-thresholds/${code}/`), { method: 'DELETE' });
      showMsg('threshold-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) await loadAlertThresholds();
    },

    // 天气类型
    editWeatherType(id) {
      wtypeEditId = id;
      apiFetch(apiUrl('settings/weather-type/')).then(res => {
        const r = res.data && res.data.find(x => x.id === id);
        if (r) showWTypeForm(r);
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
    viewThreshold(code) {
      apiFetch(apiUrl('settings/alert-thresholds/')).then(res => {
        const r = res.data && res.data.find(x => x.airport_4code === code);
        if (r) { thresholdEditCode = null; showThresholdForm(r, true); }
      });
    },

    // 机场坐标
    editLocation(code) {
      locEditCode = code;
      apiFetch(apiUrl(`settings/airport-location/${code}/`)).then(res => {
        if (res.success) showLocForm(res.data);
      });
    },
    addLocationForCode(code) {
      locEditCode = null;
      showLocForm(null, code);
    },
    async deleteLocation(code) {
      if (!confirm(`确定删除 ${code} 的坐标记录？`)) return;
      const res = await apiFetch(apiUrl(`settings/airport-location/${code}/`), { method: 'DELETE' });
      showMsg('loc-msg', res.success ? res.message : res.error, res.success ? 'success' : 'error');
      if (res.success) {
        document.getElementById('loc-result-area').innerHTML =
          `<div class="loc-not-found">未找到 <strong>${escHtml(code)}</strong> 的坐标记录
           <button class="settings-add-btn loc-add-inline-btn" onclick="SettingsModal.addLocationForCode('${escHtml(code)}')">+ 新增</button></div>`;
        hideLocForm();
      }
    },

  };

  // DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
