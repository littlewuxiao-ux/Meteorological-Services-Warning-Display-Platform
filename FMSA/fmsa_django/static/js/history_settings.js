/**
 * 设置页「历史统计」规则组。
 */
(function () {
  'use strict';

  let bound = false;

  function apiUrl(path) {
    const mode = (typeof currentTimeMode !== 'undefined' ? currentTimeMode : null) || window.currentTimeMode || 'current';
    return `/${mode}/api/${path}`;
  }

  function headers() {
    const h = { 'Content-Type': 'application/json' };
    const token = (typeof currentToken !== 'undefined' ? currentToken : null) || window.currentToken;
    const userCode = (typeof currentUserCode !== 'undefined' ? currentUserCode : null) || window.currentUserCode;
    if (token) h.Authorization = `Bearer ${token}`;
    if (userCode) h['X-User-Code'] = userCode;
    if (window.__settingsScope === 'default') h['X-Settings-Scope'] = 'default';
    return h;
  }

  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function msg(text, ok) {
    const el = document.getElementById('history-stats-msg');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'settings-msg ' + (text ? (ok ? 'success' : 'error') : '');
  }

  function paramFields(values, extra) {
    const v = values || {};
    return `
      <label class="hs-field" title="ATA/ATD 前后各看多少小时实况">已完成航班实况抓取范围
        <input type="number" min="0" max="24" step="1" data-field="done_hours" value="${esc(v.done_hours ?? 2)}">
      </label>
      <label class="hs-field" title="飞行中、即将起飞看过去多少小时到查询截止">未落地/未起飞航班实况抓取范围
        <input type="number" min="0" max="24" step="1" data-field="open_hours" value="${esc(v.open_hours ?? 4)}">
      </label>
      <label class="hs-field">实况告警等级抓取范围
        <select data-field="alert_level">
          <option value="G"${v.alert_level === 'G' ? ' selected' : ''}>绿色及以上</option>
          <option value="Y"${v.alert_level !== 'R' && v.alert_level !== 'G' ? ' selected' : ''}>黄色及以上</option>
          <option value="R"${v.alert_level === 'R' ? ' selected' : ''}>仅红色</option>
        </select>
      </label>
      <label class="hs-field" title="两份命中报观测时间差达到该小时数则拆成两段">气象要素分段间隔
        <input type="number" min="0" max="24" step="1" data-field="gap_hours" value="${esc(v.gap_hours ?? 2)}">
      </label>
      ${extra || ''}
    `;
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

  function renderGroups(config) {
    const wrap = document.getElementById('history-groups');
    if (!wrap) return;
    const general = (config && config.general) || {};
    const special = (config && config.special) || [];
    wrap.innerHTML = `<div class="hs-group" data-kind="general">
      <div class="hs-group-title">通用组</div>
      <div class="hs-group-fields">${paramFields(general)}</div>
    </div>` + special.map((group, index) => specialGroupHtml(index, group)).join('');
    const addBtn = document.getElementById('history-add-group');
    if (addBtn) addBtn.disabled = special.length >= 3;
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

  async function load() {
    ensureBound();
    msg('', true);
    try {
      const res = await fetch(apiUrl('history-stats/config/'), { headers: headers() });
      const data = await res.json();
      if (typeof window.applySettingsScope === 'function') window.applySettingsScope(data);
      if (!data.success) {
        msg(data.error || '读取规则失败', false);
        return;
      }
      renderGroups(data.config || {});
    } catch (err) {
      msg('读取规则失败', false);
    }
  }

  async function save() {
    try {
      const res = await fetch(apiUrl('history-stats/config/'), {
        method: 'PUT',
        headers: headers(),
        body: JSON.stringify({ config: collectConfig() }),
      });
      const data = await res.json();
      if (!data.success) {
        msg(data.error || '保存失败', false);
        return;
      }
      renderGroups(data.config || collectConfig());
      msg('规则已保存', true);
    } catch (err) {
      msg('保存失败', false);
    }
  }

  function ensureBound() {
    if (bound) return;
    const pane = document.getElementById('settings-pane-history-stats');
    if (!pane) return;
    bound = true;
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
    if (saveBtn) saveBtn.addEventListener('click', save);
  }

  window.HistoryStatsSettings = { load: load };
})();
