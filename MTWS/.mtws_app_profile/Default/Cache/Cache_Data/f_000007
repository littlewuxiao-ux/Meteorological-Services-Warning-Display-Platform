/**
 * 设置页「实况趋势告警」规则编辑。
 */
(function () {
  'use strict';

  const ELEMENTS = [
    ['temperature', '气温'],
    ['dewpoint', '露点温度'],
    ['rh', '相对湿度'],
    ['pressure', '气压'],
    ['wind', '风速'],
    ['visibility', '能见度'],
  ];
  const COVERS = 'NSC、FEW、SCT、BKN、OVC，多个用逗号分隔。无云组按 NSC';

  let config = { groups: [] };
  let savedConfig = { groups: [] };
  let bound = false;
  let saving = false;
  const groupUi = {};
  let renderLocked = false;

  function dis() {
    return renderLocked ? ' disabled' : '';
  }

  function uiOf(id) {
    if (!groupUi[id]) groupUi[id] = { editing: false, collapsed: false };
    return groupUi[id];
  }

  function lockSaved(groups) {
    const alive = {};
    (groups || []).forEach((group) => {
      alive[group.id] = true;
      uiOf(group.id).editing = false;
    });
    Object.keys(groupUi).forEach((id) => {
      if (!alive[id]) delete groupUi[id];
    });
  }

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

  function uid() {
    return Math.random().toString(16).slice(2, 14);
  }

  function msg(text, ok) {
    const el = document.getElementById('trend-alert-msg');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'settings-msg ' + (text ? (ok ? 'success' : 'error') : '');
  }

  function elementOptions(selected) {
    return ELEMENTS.map(([value, label]) => (
      `<option value="${value}"${value === selected ? ' selected' : ''}>${label}</option>`
    )).join('');
  }

  function scoreRange(role) {
    if (role === 'extra' || role === 'deduct') return { min: 0.1, max: 3 };
    return { min: 1, max: 5 };
  }

  function scoreHint(role) {
    if (role === 'extra') return '0.1–3.0 分，命中后累加到基础分上。';
    if (role === 'deduct') return '0.1–3.0 分，命中后从本组总分中扣减，最低为 0。';
    if (role === 'veto') return '命中后本组总分清零，无需设置分值。';
    return '1.0–5.0 分。';
  }

  function scoreField(g, c, cond) {
    if (cond.role === 'veto') {
      return `<span class="trend-hint">${scoreHint('veto')}</span>`;
    }
    const range = scoreRange(cond.role);
    return `<span>分值</span>${num(g, c, 'score', cond.score, '0.1', range.max, range.min)}<span class="trend-hint">${scoreHint(cond.role)}</span>`;
  }

  function blankCondition(kind) {
    return {
      id: uid(),
      enabled: true,
      role: 'required',
      kind: kind || 'element',
      score: 1,
      label: '',
      hours: 6,
      use_change: true,
      use_current: false,
      direction: 'down',
      change_element: 'temperature',
      change_amount: '',
      current_element: 'visibility',
      current_value: '',
      past_weather: '',
      current_weather: '',
      current_match: 'any',
      cover_from: '',
      cover_to: '',
      cover_now: '',
      from_height: '',
      from_cmp: 'above',
      from_nsc: false,
      to_height: '',
      to_cmp: 'below',
      to_nsc: false,
      now_height: '',
      now_cmp: 'below',
      now_nsc: false,
    };
  }

  function blankGroup() {
    return {
      id: uid(),
      name: '规则' + (config.groups.length + 1),
      enabled: true,
      airport_mode: 'all',
      airports_text: '',
      required_agg: 'max',
      threshold_g: 1,
      threshold_y: 2,
      threshold_r: 3,
      conditions: [],
    };
  }

  function hydrate(raw) {
    const groups = (raw && raw.groups) || [];
    groups.forEach((group) => {
      group.airports_text = group.airports_text || (Array.isArray(group.airports) ? group.airports.join(',') : (group.airports || ''));
      (group.conditions || []).forEach((cond) => {
        ['cover_from', 'cover_to', 'cover_now'].forEach((key) => {
          cond[key] = codesText(cond[key]);
        });
      });
    });
    config = { groups: groups };
    lockSaved(groups);
  }

  function rememberSaved() {
    savedConfig = JSON.parse(JSON.stringify(config));
  }

  function snapshotUi() {
    const collapsed = {};
    const dirty = {};
    config.groups.forEach((group) => {
      const ui = groupUi[group.id];
      if (!ui) return;
      collapsed[group.id] = !!ui.collapsed;
      if (ui.editing) dirty[group.id] = JSON.parse(JSON.stringify(group));
    });
    return { collapsed: collapsed, dirty: dirty };
  }

  function restoreUi(snap, exceptId) {
    Object.keys(snap.dirty || {}).forEach((id) => {
      if (id === exceptId) return;
      const index = config.groups.findIndex((group) => group.id === id);
      if (index < 0) return;
      config.groups[index] = snap.dirty[id];
      uiOf(id).editing = true;
    });
    config.groups.forEach((group) => {
      if (snap.collapsed && snap.collapsed[group.id]) uiOf(group.id).collapsed = true;
    });
  }

  function cmpSelect(g, c, field, value) {
    return `<select data-g="${g}" data-c="${c}" data-field="${field}" data-rerender="1"${dis()}>
      <option value="below"${value === 'below' ? ' selected' : ''}>低于或等于</option>
      <option value="above"${value === 'above' ? ' selected' : ''}>高于或等于</option>
    </select>`;
  }

  function check(g, c, field, on, label, rerender) {
    const cAttr = c === '' ? '' : ` data-c="${c}"`;
    return `<label class="trend-check"><input type="checkbox" data-g="${g}"${cAttr} data-field="${field}"${rerender ? ' data-rerender="1"' : ''}${on ? ' checked' : ''}${dis()}> ${label}</label>`;
  }

  function num(g, c, field, value, step, max, min) {
    const cAttr = c === '' ? '' : ` data-c="${c}"`;
    const maxAttr = max === undefined || max === null || max === '' ? '' : ` max="${max}"`;
    const minValue = min === undefined || min === null || min === '' ? 0 : min;
    return `<input type="number" class="settings-input trend-num" data-g="${g}"${cAttr} data-field="${field}" value="${esc(value)}" step="${step || 'any'}" min="${minValue}"${maxAttr}${dis()}>`;
  }

  function codesText(value) {
    const raw = Array.isArray(value) ? value.join(',') : String(value == null ? '' : value);
    return raw
      .replace(/[\[\]'"]/g, '')
      .split(/[,，]+/)
      .map((part) => part.trim())
      .filter(Boolean)
      .join(',');
  }

  function text(g, c, field, value, placeholder) {
    const cAttr = c === '' ? '' : ` data-c="${c}"`;
    return `<input type="text" class="settings-input trend-text" data-g="${g}"${cAttr} data-field="${field}" value="${esc(value)}" placeholder="${esc(placeholder || '')}"${dis()}>`;
  }

  function codes(g, c, field, value, placeholder) {
    const cAttr = c === '' ? '' : ` data-c="${c}"`;
    return `<textarea class="settings-input trend-codes" rows="1" data-g="${g}"${cAttr} data-field="${field}" placeholder="${esc(placeholder || '')}"${dis()}>${esc(codesText(value))}</textarea>`;
  }

  function fitCodeBoxes(root) {
    (root || document).querySelectorAll('.trend-codes').forEach((el) => {
      const sample = el.value || el.placeholder || '';
      const longest = sample.split('\n').reduce((max, line) => Math.max(max, line.length), 0);
      el.style.width = Math.min(640, Math.max(180, longest * 8 + 28)) + 'px';
      el.style.height = 'auto';
      el.style.height = Math.max(30, el.scrollHeight) + 'px';
    });
  }

  function conditionBody(cond, g, c) {
    const op = cond.direction === 'up' ? '≥' : '≤';
    if (cond.kind === 'element') {
      return `
        <div class="trend-line">
          <span>方向</span>
          <select data-g="${g}" data-c="${c}" data-field="direction" data-rerender="1"${dis()}>
            <option value="down"${cond.direction !== 'up' ? ' selected' : ''}>下降</option>
            <option value="up"${cond.direction === 'up' ? ' selected' : ''}>上升</option>
          </select>
          <span class="trend-hint">当前值自动按 ${op}</span>
        </div>
        <div class="trend-line">
          ${check(g, c, 'use_change', cond.use_change, '过去变化', true)}
          <span>过去</span>${num(g, c, 'hours', cond.hours)}<span>小时</span>
          <select data-g="${g}" data-c="${c}" data-field="change_element"${dis()}>${elementOptions(cond.change_element)}</select>
          <span>${cond.direction === 'up' ? '上升幅度 ≥' : '下降幅度 ≥'}</span>
          ${num(g, c, 'change_amount', cond.change_amount)}
        </div>
        <div class="trend-line">
          ${check(g, c, 'use_current', cond.use_current, '当前值', true)}
          <span>当前</span>
          <select data-g="${g}" data-c="${c}" data-field="current_element"${dis()}>${elementOptions(cond.current_element)}</select>
          <span>${op}</span>
          ${num(g, c, 'current_value', cond.current_value)}
        </div>`;
    }
    if (cond.kind === 'weather') {
      return `
        <div class="trend-line">
          ${check(g, c, 'use_change', cond.use_change, '过去出现', true)}
          <span>过去</span>${num(g, c, 'hours', cond.hours)}<span>小时内出现过</span>
          ${codes(g, c, 'past_weather', cond.past_weather, '留空表示无天气现象')}
        </div>
        <div class="trend-line">
          ${check(g, c, 'use_current', cond.use_current, '当前现象', true)}
          <select data-g="${g}" data-c="${c}" data-field="current_match" data-rerender="1"${dis()}>
            <option value="any"${cond.current_match !== 'none' ? ' selected' : ''}>其中之一</option>
            <option value="none"${cond.current_match === 'none' ? ' selected' : ''}>无天气现象</option>
          </select>
          ${codes(g, c, 'current_weather', cond.current_weather, '多个用逗号分隔')}
        </div>
        <div class="trend-hint">已填写的现象必须能在天气告警等级中查到。留空表示无天气现象。</div>`;
    }
    if (cond.kind === 'cover') {
      return `
        <div class="trend-line">
          ${check(g, c, 'use_change', cond.use_change, '过去变化', true)}
          <span>过去</span>${num(g, c, 'hours', cond.hours)}<span>小时，由</span>
          ${codes(g, c, 'cover_from', cond.cover_from, 'FEW,SCT')}
          <span>变为</span>
          ${codes(g, c, 'cover_to', cond.cover_to, 'BKN,OVC')}
        </div>
        <div class="trend-line">
          ${check(g, c, 'use_current', cond.use_current, '当前云量', true)}
          ${codes(g, c, 'cover_now', cond.cover_now, 'BKN,OVC')}
        </div>
        <div class="trend-hint">${COVERS}</div>`;
    }
    return `
      <div class="trend-line">
        ${check(g, c, 'use_change', cond.use_change, '过去变化', true)}
        <span>过去</span>${num(g, c, 'hours', cond.hours)}<span>小时，由</span>
        ${num(g, c, 'from_height', cond.from_height)}
        ${cmpSelect(g, c, 'from_cmp', cond.from_cmp)}
        ${check(g, c, 'from_nsc', cond.from_nsc, '可为空或NSC')}
        <span>变为</span>
        ${num(g, c, 'to_height', cond.to_height)}
        ${cmpSelect(g, c, 'to_cmp', cond.to_cmp)}
        ${check(g, c, 'to_nsc', cond.to_nsc, '可为空或NSC')}
      </div>
      <div class="trend-line">
        ${check(g, c, 'use_current', cond.use_current, '当前云高', true)}
        ${num(g, c, 'now_height', cond.now_height)}
        ${cmpSelect(g, c, 'now_cmp', cond.now_cmp || 'below')}
        ${check(g, c, 'now_nsc', cond.now_nsc, '可为空或NSC')}
        <span class="trend-hint">单位：百英尺。只勾选可为空或 NSC、不填数字时，这一侧只接受没有云或 NSC。填了数字再勾选，则数字条件或无云都通过。</span>
      </div>`;
  }

  function render() {
    const root = document.getElementById('trend-alert-editor');
    if (!root) return;
    if (!config.groups.length) {
      root.innerHTML = '<div class="trend-empty">还没有规则。点击「新增规则组」开始。</div>';
      return;
    }
    root.innerHTML = config.groups.map((group, g) => {
      const ui = uiOf(group.id);
      renderLocked = !ui.editing;
      const collapsed = ui.collapsed;
      const fields = collapsed ? '' : `
        <div class="trend-global-fields">
          ${check(g, '', 'enabled', group.enabled, '启用')}
          <label>机场范围
            <select data-g="${g}" data-field="airport_mode" data-rerender="1"${dis()}>
              <option value="all"${group.airport_mode !== 'specific' ? ' selected' : ''}>全部</option>
              <option value="specific"${group.airport_mode === 'specific' ? ' selected' : ''}>特定</option>
            </select>
          </label>
          ${group.airport_mode === 'specific' ? text(g, '', 'airports_text', group.airports_text, 'ZBAA,ZSPD') : ''}
          <label>基础条件计分规则
            <select data-g="${g}" data-field="required_agg"${dis()}>
              <option value="max"${group.required_agg !== 'avg' ? ' selected' : ''}>最高值</option>
              <option value="avg"${group.required_agg === 'avg' ? ' selected' : ''}>平均值</option>
            </select>
          </label>
          <span class="trend-thresholds">
            <span class="trend-threshold-title">告警阈值</span>
            <span class="trend-threshold-box trend-threshold-g">${num(g, '', 'threshold_g', group.threshold_g)}</span>
            <span class="trend-threshold-box trend-threshold-y">${num(g, '', 'threshold_y', group.threshold_y)}</span>
            <span class="trend-threshold-box trend-threshold-r">${num(g, '', 'threshold_r', group.threshold_r)}</span>
          </span>
        </div>`;
      const conditions = collapsed ? '' : `
        <div class="trend-group-body">
          ${(group.conditions || []).map((cond, c) => `
            <article class="trend-cond">
              <header class="trend-cond-global">
                ${check(g, c, 'enabled', cond.enabled, '启用')}
                <label>条件
                  <select data-g="${g}" data-c="${c}" data-field="role" data-rerender="1"${dis()}>
                    <option value="required"${cond.role === 'required' ? ' selected' : ''}>基础条件</option>
                    <option value="extra"${cond.role === 'extra' ? ' selected' : ''}>附加条件</option>
                    <option value="veto"${cond.role === 'veto' ? ' selected' : ''}>否决条件</option>
                    <option value="deduct"${cond.role === 'deduct' ? ' selected' : ''}>减分条件</option>
                  </select>
                </label>
                <label>类型
                  <select data-g="${g}" data-c="${c}" data-field="kind" data-rerender="1"${dis()}>
                    <option value="element"${cond.kind === 'element' ? ' selected' : ''}>常规要素</option>
                    <option value="weather"${cond.kind === 'weather' ? ' selected' : ''}>天气现象</option>
                    <option value="cover"${cond.kind === 'cover' ? ' selected' : ''}>云量</option>
                    <option value="height"${cond.kind === 'height' ? ' selected' : ''}>云高</option>
                  </select>
                </label>
                ${renderLocked ? '' : `<button type="button" class="settings-btn-cancel" data-action="del-cond" data-g="${g}" data-c="${c}">删除</button>`}
              </header>
              <div class="trend-cond-body">
                <div class="trend-line">
                  <span>描述</span>${text(g, c, 'label', cond.label, '如能见度快速下降')}
                  ${scoreField(g, c, cond)}
                </div>
                ${conditionBody(cond, g, c)}
              </div>
            </article>
          `).join('')}
          ${renderLocked ? '' : `
          <div class="trend-line">
            <button type="button" class="settings-btn-cancel" data-action="add-cond" data-g="${g}" data-kind="element">+ 常规要素</button>
            <button type="button" class="settings-btn-cancel" data-action="add-cond" data-g="${g}" data-kind="weather">+ 天气现象</button>
            <button type="button" class="settings-btn-cancel" data-action="add-cond" data-g="${g}" data-kind="cover">+ 云量</button>
            <button type="button" class="settings-btn-cancel" data-action="add-cond" data-g="${g}" data-kind="height">+ 云高</button>
          </div>`}
        </div>`;
      return `
      <section class="trend-group${renderLocked ? ' is-readonly' : ''}${collapsed ? ' is-collapsed' : ''}">
        <header class="trend-group-global">
          <div class="trend-group-name-row">
            <label>名称 ${text(g, '', 'name', group.name, '规则名称')}</label>
            ${renderLocked
              ? `<button type="button" class="trend-btn-edit" data-action="edit-group" data-g="${g}">编辑</button>`
              : `<button type="button" class="trend-btn-save" data-action="save-group" data-g="${g}">保存</button>
                 <button type="button" class="trend-btn-cancel" data-action="cancel-group" data-g="${g}">取消</button>`}
            <button type="button" class="trend-btn-delete" data-action="del-group" data-g="${g}">删除规则组</button>
            <button type="button" class="trend-fold" data-action="toggle-fold" data-g="${g}" title="${collapsed ? '展开' : '折叠'}" aria-label="${collapsed ? '展开' : '折叠'}">
              <svg viewBox="0 0 16 16" width="14" height="14" class="${collapsed ? '' : 'is-open'}" aria-hidden="true"><path d="M6 3.2L11 8 6 12.8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
          ${fields}
        </header>
        ${conditions}
      </section>`;
    }).join('');
    fitCodeBoxes(root);
  }

  function targetOf(el) {
    const group = config.groups[Number(el.dataset.g)];
    if (!group) return null;
    if (el.dataset.c === undefined || el.dataset.c === '') return group;
    return (group.conditions || [])[Number(el.dataset.c)] || null;
  }

  function writeField(el) {
    const target = targetOf(el);
    if (!target || !el.dataset.field) return;
    const field = el.dataset.field;
    if (el.type === 'checkbox') target[field] = el.checked;
    else if (el.type === 'number') target[field] = el.value === '' ? '' : Number(el.value);
    else target[field] = el.value;
  }

  function onEdit(event) {
    const el = event.target.closest('[data-field]');
    if (!el || !el.closest('#trend-alert-editor')) return;
    const group = config.groups[Number(el.dataset.g)];
    if (!group || !uiOf(group.id).editing) return;
    writeField(el);
    if (el.dataset.field === 'role' && el.dataset.c !== undefined && el.dataset.c !== '') {
      const cond = (group.conditions || [])[Number(el.dataset.c)];
      if (cond) {
        if (cond.role === 'veto') {
          cond.score = 0;
        } else {
          const range = scoreRange(cond.role);
          const score = Number(cond.score);
          if (!Number.isFinite(score) || score < range.min) cond.score = range.min;
          else if (score > range.max) cond.score = range.max;
        }
      }
    }
    if (el.classList.contains('trend-codes')) fitCodeBoxes(el.parentElement || document);
    if (el.dataset.rerender === '1') render();
  }

  function onClick(event) {
    const btn = event.target.closest('[data-action]');
    if (!btn || !btn.closest('#settings-pane-trend-alert')) return;
    const g = Number(btn.dataset.g);
    const group = config.groups[g];
    if (!group && btn.dataset.action !== 'add-group') return;
    if (btn.dataset.action === 'edit-group') {
      uiOf(group.id).editing = true;
      uiOf(group.id).collapsed = false;
    } else if (btn.dataset.action === 'toggle-fold') {
      uiOf(group.id).collapsed = !uiOf(group.id).collapsed;
    } else if (btn.dataset.action === 'save-group') {
      saveGroup(g);
      return;
    } else if (btn.dataset.action === 'cancel-group') {
      const saved = (savedConfig.groups || []).find((item) => item.id === group.id);
      if (saved) config.groups[g] = JSON.parse(JSON.stringify(saved));
      else { delete groupUi[group.id]; config.groups.splice(g, 1); render(); return; }
      uiOf(group.id).editing = false;
    } else if (btn.dataset.action === 'del-group') {
      deleteGroup(g);
      return;
    } else if (btn.dataset.action === 'add-cond') {
      if (!uiOf(group.id).editing) return;
      group.conditions.push(blankCondition(btn.dataset.kind));
    } else if (btn.dataset.action === 'del-cond') {
      if (!uiOf(group.id).editing) return;
      group.conditions.splice(Number(btn.dataset.c), 1);
    } else {
      return;
    }
    render();
  }

  function ensureBound() {
    if (bound) return;
    const pane = document.getElementById('settings-pane-trend-alert');
    if (!pane) return;
    bound = true;
    pane.addEventListener('input', onEdit);
    pane.addEventListener('change', onEdit);
    pane.addEventListener('click', onClick);
    const addBtn = document.getElementById('trend-alert-add-group');
    if (addBtn) addBtn.addEventListener('click', () => {
      const group = blankGroup();
      groupUi[group.id] = { editing: true, collapsed: false };
      config.groups.push(group);
      render();
    });
  }

  async function load() {
    ensureBound();
    msg('', true);
    try {
      const res = await fetch(apiUrl('trend-alert/config/'), { headers: headers() });
      const data = await res.json();
      if (!data.success) {
        msg(data.error || '读取失败', false);
        return;
      }
      if (typeof window.applySettingsScope === 'function') window.applySettingsScope(data);
      hydrate(data.config || { groups: [] });
      rememberSaved();
      const list = document.getElementById('trend-weather-list');
      if (list) {
        list.innerHTML = (data.weather_codes || []).map((code) => `<option value="${esc(code)}"></option>`).join('');
      }
      render();
    } catch (err) {
      msg('读取失败', false);
    }
  }

  async function putConfig(payload) {
    const res = await fetch(apiUrl('trend-alert/config/'), {
      method: 'PUT',
      headers: headers(),
      body: JSON.stringify({ config: payload }),
    });
    return res.json();
  }

  async function saveGroup(index) {
    const group = config.groups[index];
    if (!group || saving) return;
    saving = true;
    const snap = snapshotUi();
    const payload = JSON.parse(JSON.stringify(savedConfig));
    const current = JSON.parse(JSON.stringify(group));
    current.airports = current.airports_text || '';
    const found = (payload.groups || []).findIndex((item) => item.id === current.id);
    if (found >= 0) payload.groups[found] = current;
    else payload.groups.push(current);
    try {
      const data = await putConfig(payload);
      if (!data.success) {
        msg(data.error || '保存失败', false);
        return;
      }
      hydrate(data.config || payload);
      rememberSaved();
      restoreUi(snap, group.id);
      render();
      msg('已保存，并已重算该组涉及的机场', true);
    } catch (err) {
      msg('保存失败', false);
    } finally {
      saving = false;
    }
  }

  async function deleteGroup(index) {
    const group = config.groups[index];
    if (!group || saving) return;
    const name = (group.name || '').trim() || '未命名规则组';
    if (!window.confirm('确定删除规则组「' + name + '」？')) return;
    const existed = (savedConfig.groups || []).some((item) => item.id === group.id);
    if (!existed) {
      delete groupUi[group.id];
      config.groups.splice(index, 1);
      render();
      return;
    }
    saving = true;
    const snap = snapshotUi();
    const payload = JSON.parse(JSON.stringify(savedConfig));
    payload.groups = (payload.groups || []).filter((item) => item.id !== group.id);
    try {
      const data = await putConfig(payload);
      if (!data.success) {
        msg(data.error || '删除失败', false);
        return;
      }
      hydrate(data.config || payload);
      rememberSaved();
      restoreUi(snap, group.id);
      render();
      msg('已删除', true);
    } catch (err) {
      msg('删除失败', false);
    } finally {
      saving = false;
    }
  }

  window.TrendAlertSettings = { load: load };
})();
