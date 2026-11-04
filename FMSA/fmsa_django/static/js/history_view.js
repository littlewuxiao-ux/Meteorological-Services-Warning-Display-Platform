/**
 * 历史天气统计视图。进入后只加载规则；未点确定不查询。
 */
(function () {
  'use strict';

  let bound = false;
  let loaded = false;
  let querySeq = 0;
  let lastRows = [];
  let lastRange = null;

  const TYPE_CLASS = {
    '航班落地': 'hs-type-land',
    '航班起飞': 'hs-type-dep',
    '飞行中': 'hs-type-enr',
    '即将起飞': 'hs-type-soon',
    '飞机停场': 'hs-type-park',
  };

  function apiUrl(path) {
    const mode = (typeof currentTimeMode !== 'undefined' ? currentTimeMode : null) || window.currentTimeMode || 'current';
    return `/${mode}/api/${path}`;
  }

  function headers() {
    const h = { 'Content-Type': 'application/json' };
    if (typeof getRequestHeaders === 'function') Object.assign(h, getRequestHeaders());
    return h;
  }

  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function preset() {
    const picked = document.querySelector('input[name="history-preset"]:checked');
    return picked ? picked.value : 'day';
  }

  function setStatus(text, isError) {
    const el = document.getElementById('history-status');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('is-error', !!isError);
  }

  function pad(n) {
    return String(n).padStart(2, '0');
  }

  function msToLocalInput(ms) {
    const date = new Date(Number(ms));
    if (!Number.isFinite(date.getTime())) return '';
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function inputToMs(value) {
    if (!value) return null;
    const date = new Date(value);
    const ms = date.getTime();
    return Number.isFinite(ms) ? ms : null;
  }

  function formatRangeLabel(startMs, endMs) {
    if (!startMs || !endMs) return '';
    const fmt = (ms) => {
      if (typeof formatTimestampPartsByMode === 'function') {
        const parts = formatTimestampPartsByMode(ms);
        return [parts.date, parts.time].filter(Boolean).join(' ');
      }
      const date = new Date(ms);
      return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
    };
    return `${fmt(startMs)} → ${fmt(endMs)}`;
  }

  function syncCustomVisible() {
    const box = document.getElementById('history-custom-range');
    if (box) box.hidden = preset() !== 'custom';
  }

  async function fillCustomDefaults() {
    const start = document.getElementById('history-start');
    const end = document.getElementById('history-end');
    if (!start || !end || (start.value && end.value)) return;
    try {
      const res = await fetch(apiUrl('history-stats/range/?preset=day'), { headers: headers() });
      const data = await res.json();
      if (!data.success) return;
      if (!start.value) start.value = msToLocalInput(data.start_ms);
      if (!end.value) end.value = msToLocalInput(data.end_ms);
    } catch (err) { /* 用户稍后手填 */ }
  }

  function paramFields(values, extra) {
    const v = values || {};
    const extraHtml = extra || '';
    return `
      <label class="hs-field" title="ATA/ATD 前后各看多少小时实况">已完成航班实况抓取范围
        <input type="number" min="0" max="24" step="1" data-field="done_hours" value="${esc(v.done_hours ?? 2)}">小时
      </label>
      <label class="hs-field" title="飞行中、即将起飞看过去多少小时到查询截止">未落地/未起飞航班实况抓取范围
        <input type="number" min="0" max="24" step="1" data-field="open_hours" value="${esc(v.open_hours ?? 4)}">小时
      </label>
      <label class="hs-field">实况告警等级抓取范围
        <select data-field="alert_level">
          <option value="G"${v.alert_level === 'G' ? ' selected' : ''}>绿色及以上</option>
          <option value="Y"${v.alert_level !== 'R' && v.alert_level !== 'G' ? ' selected' : ''}>黄色及以上</option>
          <option value="R"${v.alert_level === 'R' ? ' selected' : ''}>仅红色</option>
        </select>
      </label>
      <label class="hs-field" title="两份命中报观测时间差达到该小时数则拆成两段">气象要素分段间隔
        <input type="number" min="0" max="24" step="1" data-field="gap_hours" value="${esc(v.gap_hours ?? 2)}">小时
      </label>
      ${extraHtml}
    `;
  }

  function renderGroups(config) {
    const wrap = document.getElementById('history-groups');
    if (!wrap) return;
    const general = (config && config.general) || {};
    const special = (config && config.special) || [];
    let html = `<div class="hs-group" data-kind="general">
      <div class="hs-group-title">通用组</div>
      <div class="hs-group-fields">${paramFields(general)}</div>
    </div>`;
    special.forEach((group, index) => {
      html += specialGroupHtml(index, group);
    });
    wrap.innerHTML = html;
    const addBtn = document.getElementById('history-add-group');
    if (addBtn) addBtn.disabled = special.length >= 3;
  }

  function specialGroupHtml(index, group) {
    const g = group || {};
    return `<div class="hs-group" data-kind="special" data-index="${index}">
      <div class="hs-group-title">
        <span>特殊组 ${index + 1}</span>
        <button type="button" class="hs-remove" data-remove="${index}">删除</button>
      </div>
      <div class="hs-group-fields">
        ${paramFields(g, `<label class="hs-field hs-airports">适用机场四字代码<input type="text" data-field="airports_text" value="${esc(g.airports_text || (g.airports || []).join(','))}" placeholder="ZBAA,ZSPD">（逗号分隔）</label>`)}
      </div>
    </div>`;
  }

  function readField(box, field, fallback) {
    const el = box ? box.querySelector(`[data-field="${field}"]`) : null;
    if (!el) return fallback;
    if (el.type === 'number') {
      const n = parseFloat(el.value);
      return Number.isFinite(n) ? n : fallback;
    }
    return el.value || fallback;
  }

  function collectParams(box) {
    return {
      done_hours: readField(box, 'done_hours', 2),
      open_hours: readField(box, 'open_hours', 4),
      alert_level: readField(box, 'alert_level', 'Y'),
      gap_hours: readField(box, 'gap_hours', 2),
    };
  }

  function collectConfig() {
    const generalBox = document.querySelector('#history-groups .hs-group[data-kind="general"]');
    const special = [];
    document.querySelectorAll('#history-groups .hs-group[data-kind="special"]').forEach((box, index) => {
      special.push({
        name: `特殊组${index + 1}`,
        ...collectParams(box),
        airports_text: readField(box, 'airports_text', ''),
      });
    });
    return {
      general: collectParams(generalBox),
      special,
    };
  }

  async function loadConfig() {
    const res = await fetch(apiUrl('history-stats/config/'), { headers: headers() });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || '读取规则失败');
    renderGroups(data.config || {});
  }

  async function saveConfig() {
    const res = await fetch(apiUrl('history-stats/config/'), {
      method: 'PUT',
      headers: headers(),
      body: JSON.stringify({ config: collectConfig() }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || '保存失败');
    renderGroups(data.config || collectConfig());
    return data.config;
  }

  function badgeHtml(badge) {
    if (!badge || !badge.text) return '';
    const level = badge.level === 'R' || badge.level === 'Y' || badge.level === 'G' ? badge.level : 'N';
    return `<span class="warning-badge warning-${level}">${esc(badge.text)}</span>`;
  }

  function popupBadgeHtml(row) {
    const elements = row.element_badges || [];
    const weather = row.weather_badges || [];
    const fallback = (!elements.length && !weather.length) ? (row.badges || []) : [];
    const row1 = (elements.length ? elements : fallback).map(badgeHtml).join('');
    const row2 = weather.map(badgeHtml).join('');
    if (!row1 && !row2) return '';
    return `<div class="popup-warning-badges"><div class="popup-warning-row">${row1}</div><div class="popup-warning-row">${row2}</div></div>`;
  }

  function typeHtml(name) {
    return `<span class="hs-type ${TYPE_CLASS[name] || ''}">${esc(name)}</span>`;
  }

  function timeHtml(startMs, endMs) {
    const label = formatRangeLabel(startMs, endMs);
    return `<div class="hs-time">${esc(label)}</div>`;
  }

  function renderRows(rows) {
    const wrap = document.getElementById('history-table-wrap');
    if (!wrap) return;
    lastRows = rows || [];
    if (!lastRows.length) {
      wrap.innerHTML = '<div class="hs-empty">所选时段内没有满足条件的天气</div>';
      return;
    }
    const groups = [];
    lastRows.forEach((row) => {
      const last = groups[groups.length - 1];
      if (last && last.airport === row.airport) last.rows.push(row);
      else groups.push({ airport: row.airport, rows: [row] });
    });
    let html = '<table class="hs-table"><thead><tr><th>机场</th><th>天气时段</th><th>徽章</th><th>影响运行</th><th>明语</th></tr></thead><tbody>';
    groups.forEach((group) => {
      group.rows.forEach((row, index) => {
        html += '<tr>';
        if (index === 0) {
          html += `<td class="hs-airport" rowspan="${group.rows.length}">${esc(group.airport)}</td>`;
        }
        html += `<td>${timeHtml(row.start_ms, row.end_ms)}</td>`;
        html += `<td class="hs-badges">${popupBadgeHtml(row)}</td>`;
        html += `<td class="hs-types">${(row.types || []).map(typeHtml).join('')}</td>`;
        html += `<td class="hs-plain">${esc(row.plain || '')}</td>`;
        html += '</tr>';
      });
    });
    html += '</tbody></table>';
    wrap.innerHTML = html;
  }

  async function runQuery() {
    const seq = ++querySeq;
    const btn = document.getElementById('history-query');
    if (btn) btn.disabled = true;
    setStatus('正在查询…');
    try {
      const kind = preset();
      const body = { preset: kind, config: collectConfig() };
      if (kind === 'custom') {
        body.start_ms = inputToMs(document.getElementById('history-start').value);
        body.end_ms = inputToMs(document.getElementById('history-end').value);
      }
      const res = await fetch(apiUrl('history-stats/query/'), {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (seq !== querySeq) return;
      if (!data.success) {
        setStatus(data.error || '查询失败', true);
        return;
      }
      lastRange = data;
      renderRows(data.rows || []);
      setStatus(`航班 ${data.flight_count || 0} 条，机场 ${data.airport_count || 0} 个，记录 ${(data.rows || []).length} 段`);
    } catch (err) {
      if (seq !== querySeq) return;
      setStatus(err.message || '查询失败', true);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function bindOnce() {
    if (bound) return;
    const panel = document.getElementById('history-panel');
    if (!panel) return;
    bound = true;
    panel.querySelectorAll('input[name="history-preset"]').forEach((el) => {
      el.addEventListener('change', async () => {
        syncCustomVisible();
        if (preset() === 'custom') await fillCustomDefaults();
      });
    });
    const addBtn = document.getElementById('history-add-group');
    if (addBtn) {
      addBtn.addEventListener('click', () => {
        const wrap = document.getElementById('history-groups');
        const count = wrap ? wrap.querySelectorAll('.hs-group[data-kind="special"]').length : 0;
        if (count >= 3) return;
        wrap.insertAdjacentHTML('beforeend', specialGroupHtml(count, {}));
        addBtn.disabled = count + 1 >= 3;
      });
    }
    const groups = document.getElementById('history-groups');
    if (groups) {
      groups.addEventListener('click', (event) => {
        const btn = event.target.closest('[data-remove]');
        if (!btn) return;
        const cfg = collectConfig();
        cfg.special.splice(Number(btn.getAttribute('data-remove')), 1);
        renderGroups(cfg);
      });
    }
    const saveBtn = document.getElementById('history-save');
    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        try {
          await saveConfig();
          setStatus('规则已保存');
        } catch (err) {
          setStatus(err.message || '保存失败', true);
        }
      });
    }
    const queryBtn = document.getElementById('history-query');
    if (queryBtn) queryBtn.addEventListener('click', runQuery);
    const tz = document.getElementById('timezone-toggle-input');
    if (tz) tz.addEventListener('change', () => {
      if (panel.style.display !== 'none' && lastRows.length) renderRows(lastRows);
    });
  }

  async function startHistoryView() {
    bindOnce();
    syncCustomVisible();
    const wrap = document.getElementById('history-table-wrap');
    if (wrap && !lastRows.length) {
      wrap.innerHTML = '<div class="hs-empty">选择时段后点击确定查询</div>';
    }
    if (!loaded) {
      try {
        await loadConfig();
        loaded = true;
      } catch (err) {
        setStatus(err.message || '读取规则失败', true);
      }
    }
    if (preset() === 'custom') fillCustomDefaults();
  }

  function stopHistoryView() {
    querySeq += 1;
  }

  window.startHistoryView = startHistoryView;
  window.stopHistoryView = stopHistoryView;
  window.refreshHistoryTimezone = function () {
    if (lastRows.length) renderRows(lastRows);
  };
})();
