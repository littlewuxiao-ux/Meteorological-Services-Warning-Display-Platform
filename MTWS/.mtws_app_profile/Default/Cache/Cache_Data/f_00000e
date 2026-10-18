/**
 * 实况趋势告警结果表。
 * 导航悬浮的红黄绿只统计左侧「趋势」数量。
 * 进入本视图时顶部红/黄/绿选中、无告警取消，国内/国际区域全部选中并锁定；离开后恢复进入前的勾选。
 */
(function () {
  'use strict';

  let payload = null;
  let bound = false;
  let loadSeq = 0;

  const HOME_COLOR = { red: 'R', yellow: 'Y', green: 'G', none: 'N' };
  const BAR_COLOR = { R: '#d64545', Y: '#e6b325', G: '#2e9e5b' };
  const SHOWN_KEYS = new Set(['temperature', 'dewpoint', 'rh', 'pressure', 'wind', 'visibility', 'height']);

  function apiUrl(path) {
    const mode = (typeof currentTimeMode !== 'undefined' ? currentTimeMode : null) || window.currentTimeMode || 'current';
    return `/${mode}/api/${path}`;
  }

  function headers() {
    const h = {};
    const token = (typeof currentToken !== 'undefined' ? currentToken : null) || window.currentToken;
    const userCode = (typeof currentUserCode !== 'undefined' ? currentUserCode : null) || window.currentUserCode;
    if (token) h.Authorization = `Bearer ${token}`;
    if (userCode) h['X-User-Code'] = userCode;
    return h;
  }

  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  const HOURS_KEY = 'mtws_flight_future_hours';

  function scopeValue() {
    const picked = document.querySelector('input[name="trend-scope"]:checked');
    return picked ? picked.value : 'has_flight';
  }

  function readStoredHours() {
    const raw = localStorage.getItem(HOURS_KEY);
    const n = parseInt(raw == null || raw === '' ? '2' : raw, 10);
    if (!Number.isFinite(n)) return 2;
    return Math.max(0, Math.min(9, n));
  }

  function futureHours() {
    const input = document.getElementById('trend-future-hours');
    const n = input ? parseInt(input.value, 10) : readStoredHours();
    if (!Number.isFinite(n)) return 2;
    return Math.max(0, Math.min(9, n));
  }

  function syncHoursVisibility() {
    const label = document.getElementById('trend-hours-label');
    if (label) label.classList.toggle('is-on', scopeValue() === 'recent2h');
  }

  function statColors() {
    return Array.from(document.querySelectorAll('.trend-color:checked')).map((el) => el.value);
  }

  function homeColors() {
    const set = new Set();
    document.querySelectorAll('.filter-btn[data-group="alert"].selected').forEach((btn) => {
      const color = HOME_COLOR[btn.dataset.value];
      if (color) set.add(color);
    });
    return set;
  }

  function showHalf() {
    const box = document.getElementById('trend-half');
    return !!(box && box.checked);
  }

  function pad(n) {
    return String(n).padStart(2, '0');
  }

  function slotLabel(ms) {
    const utc = window.displayTimezone === 'UTC';
    const date = new Date(utc ? ms : ms + 8 * 3600 * 1000);
    return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
  }

  function visibleSlots(slots) {
    const hourly = slots.filter((ms) => ms % 3600000 === 0);
    const list = showHalf() ? slots.slice() : hourly;
    const limit = showHalf() ? 48 : 24;
    return list.length > limit ? list.slice(list.length - limit) : list;
  }

  function cellsFor(row, fullSlots, visible) {
    const at = new Map();
    fullSlots.forEach((ms, index) => at.set(ms, index));
    const cells = visible.map((ms) => {
      const index = at.get(ms);
      const cell = index == null ? null : (row.cells || [])[index];
      return cell || { text: '', speci: false };
    });
    const latest = row.latest;
    if (cells.length && latest && latest.text) {
      cells[cells.length - 1] = { text: latest.text, speci: !!latest.speci };
    }
    return cells;
  }

  function trendHandleButton(airport) {
    const color = airport.color;
    if (color !== 'R' && color !== 'Y' && color !== 'G') return '';
    const handled = !!airport.handled;
    const bg = BAR_COLOR[color] || BAR_COLOR.G;
    const fg = color === 'Y' ? '#1b2838' : '#fff';
    const style = handled ? '' : ` style="background:${bg};color:${fg}"`;
    const levelCls = color === 'Y' ? ' level-y' : '';
    return `<button type="button" class="trend-handle-btn${handled ? ' is-handled' : ''}${levelCls}" data-code="${esc(airport.airport)}"${style}>${handled ? '已处理' : '未处理'}</button>`;
  }

  function scoreBar(airport) {
    const score = Number(airport.score);
    if (!score || score <= 0) return '';
    const key = airport.bar_color || airport.color || 'G';
    const color = BAR_COLOR[key] || BAR_COLOR.G;
    const pct = Math.max(0, Math.min(100, score / 10 * 100));
    const background = score > 10
      ? color
      : `linear-gradient(90deg, ${color} 0%, ${color} 58%, rgba(255,255,255,0) 100%)`;
    return `<div class="trend-score-fill" style="width:${pct}%;background:${background}"></div>`;
  }

  function setStatus(text) {
    const el = document.getElementById('trend-status');
    if (el) el.textContent = text || '';
  }

  let statPop = null;
  let statShowTimer = null;
  let statOutsideBound = false;

  function statRoot() {
    return statPop || document;
  }

  function applyStatHierarchy(changed) {
    const root = statRoot();
    if (!changed) return;
    const red = root.querySelector('.trend-color[value="R"]');
    const yellow = root.querySelector('.trend-color[value="Y"]');
    const green = root.querySelector('.trend-color[value="G"]');
    if (changed.value === 'G' && changed.checked) {
      if (yellow) yellow.checked = true;
      if (red) red.checked = true;
    } else if (changed.value === 'Y' && changed.checked) {
      if (red) red.checked = true;
    } else if (changed.value === 'Y' && !changed.checked) {
      if (green) green.checked = false;
    } else if (changed.value === 'R' && !changed.checked) {
      if (yellow) yellow.checked = false;
      if (green) green.checked = false;
    }
  }

  function ensureStatPop() {
    if (statPop) return statPop;
    statPop = document.createElement('div');
    statPop.className = 'trend-stat-pop';
    statPop.innerHTML =
      '<div class="trend-stat-pop-title">告警数量统计阈值</div>' +
      '<label class="trend-switch trend-switch-r"><input type="checkbox" class="trend-color" value="R" checked><span>红</span></label>' +
      '<label class="trend-switch trend-switch-y"><input type="checkbox" class="trend-color" value="Y" checked><span>黄</span></label>' +
      '<label class="trend-switch trend-switch-g"><input type="checkbox" class="trend-color" value="G" checked><span>绿</span></label>';
    document.body.appendChild(statPop);
    statPop.querySelectorAll('.trend-color').forEach((el) => {
      el.addEventListener('change', () => {
        applyStatHierarchy(el);
        updateNavBadge();
      });
    });
    if (!statOutsideBound) {
      statOutsideBound = true;
      document.addEventListener('pointerdown', (event) => {
        if (!statPop || !statPop.classList.contains('is-open')) return;
        if (statPop.contains(event.target)) return;
        updateNavBadge();
        closeStatPop();
      });
    }
    return statPop;
  }

  function placeStatPop() {
    const btn = document.querySelector('.view-nav-item[data-view="trend"]');
    if (!btn || !statPop) return;
    const rect = btn.getBoundingClientRect();
    statPop.style.left = (rect.right + 8) + 'px';
    statPop.style.top = Math.max(8, rect.top) + 'px';
  }

  function openStatPop() {
    ensureStatPop();
    placeStatPop();
    statPop.classList.add('is-open');
  }

  function closeStatPop() {
    if (statPop) statPop.classList.remove('is-open');
  }

  function bindStatHover() {
    const btn = document.querySelector('.view-nav-item[data-view="trend"]');
    if (!btn || btn.dataset.statHover === '1') return;
    btn.dataset.statHover = '1';
    btn.removeAttribute('title');
    btn.addEventListener('mouseenter', () => {
      clearTimeout(statShowTimer);
      statShowTimer = setTimeout(openStatPop, 1500);
    });
    btn.addEventListener('mouseleave', () => {
      clearTimeout(statShowTimer);
    });
  }

  function trendNavBadgeAllowed() {
    if (typeof hasAccess !== 'function' || !window.__accessIdentity) return true;
    return hasAccess('view_trend_nav', 'display');
  }

  function updateNavBadge() {
    const btn = document.querySelector('.view-nav-item[data-view="trend"]');
    if (!btn) return;
    bindStatHover();
    let badge = btn.querySelector('.trend-nav-badge');
    if (!trendNavBadgeAllowed()) {
      if (badge) badge.remove();
      return;
    }
    const colors = new Set(statColors());
    const count = ((payload && payload.airports) || []).filter((item) => colors.has(item.color) && !item.handled).length;
    if (!count) {
      if (badge) badge.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'trend-nav-badge';
      btn.appendChild(badge);
    }
    badge.textContent = String(count);
  }

  function render() {
    const wrap = document.getElementById('trend-table-wrap');
    if (!wrap) return;
    updateNavBadge();
    if (!payload) {
      wrap.innerHTML = '';
      return;
    }
    const colors = homeColors();
    const airports = (payload.airports || []).filter((item) => colors.has(item.color));
    const fullSlots = payload.slots || [];
    const slots = visibleSlots(fullSlots);
    if (!colors.size) {
      wrap.innerHTML = '<div class="trend-empty">请在页面上方勾选红、黄、绿或无。</div>';
      return;
    }
    if (!airports.length) {
      wrap.innerHTML = '<div class="trend-empty">当前范围内没有符合所选告警等级的机场。</div>';
      return;
    }
    const dense = slots.length > 24 ? ' trend-dense' : '';
    const head = slots.map((ms) => `<th>${esc(slotLabel(ms))}</th>`).join('') + '<th class="trend-handle">处理</th>';
    const body = airports.map((airport) => {
      const source = airport.color === 'N' ? [] : (airport.rows || []);
      const kept = source.filter((row) => SHOWN_KEYS.has(row.key));
      const rows = kept.length ? kept : [{ name: '', cells: [] }];
      const note = (airport.labels || []).filter((label) => label).join('，');
      return rows.map((row, index) => {
        const airportCell = index === 0
          ? `<td class="trend-airport" rowspan="${rows.length}">
              <div class="trend-code-box">
                ${scoreBar(airport)}
                <div class="trend-code">${esc(airport.airport)}</div>
              </div>
              ${note ? `<div class="trend-labels">${esc(note)}</div>` : ''}
            </td>`
          : '';
        const cells = cellsFor(row, fullSlots, slots).map((cell) => {
          const cls = cell.speci ? ' class="trend-speci"' : '';
          const title = cell.speci ? ' title="最新特殊报"' : '';
          return `<td${cls}${title}>${esc(cell.text || '')}</td>`;
        }).join('');
        const handleCell = index === 0
          ? `<td class="trend-handle" rowspan="${rows.length}">${trendHandleButton(airport)}</td>`
          : '';
        return `<tr>${airportCell}<td class="trend-element">${esc(row.name || '')}</td>${cells}${handleCell}</tr>`;
      }).join('');
    }).join('');
    wrap.innerHTML = `<table class="trend-table${dense}"><thead><tr><th class="trend-airport">机场</th><th class="trend-element">要素</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  async function markTrendHandled(btn) {
    if (!btn || btn.classList.contains('is-handled') || btn.disabled) return;
    if (typeof hasAccess === 'function' && window.__accessIdentity && !hasAccess('view_trend', 'write')) {
      alert('当前角色无实况趋势写入权限，处理结果不会保存，告警不会消除');
      return;
    }
    const code = btn.getAttribute('data-code');
    if (!code) return;
    btn.disabled = true;
    try {
      const res = await fetch(apiUrl('trend-alert/handle/'), {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, headers()),
        body: JSON.stringify({ airport: code }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || '处理失败');
      const airport = ((payload && payload.airports) || []).find((item) => item.airport === code);
      if (airport) airport.handled = true;
      render();
    } catch (err) {
      btn.disabled = false;
      alert(err.message || '处理失败');
    }
  }

  async function load() {
    const seq = ++loadSeq;
    setStatus('');
    const scope = scopeValue();
    const hours = futureHours();
    sessionStorage.setItem('mtws_trend_scope', scope);
    localStorage.setItem(HOURS_KEY, String(hours));
    syncHoursVisibility();
    try {
      const res = await fetch(
        apiUrl('trend-alert/results/?scope=' + encodeURIComponent(scope) + '&future_hours=' + hours),
        { headers: headers() }
      );
      const data = await res.json();
      if (seq !== loadSeq) return;
      if (!data.success) {
        payload = null;
        setStatus(data.error || '计算失败');
        const wrap = document.getElementById('trend-table-wrap');
        if (wrap) wrap.innerHTML = '';
        updateNavBadge();
        return;
      }
      payload = data;
      const reached = (data.airports || []).filter((item) => item.color === 'R' || item.color === 'Y' || item.color === 'G').length;
      setStatus(`参与机场 ${data.universe_count || 0}，达到阈值 ${reached}`);
      render();
    } catch (err) {
      if (seq !== loadSeq) return;
      setStatus('计算失败');
    }
  }

  function bindOnce() {
    if (bound) return;
    const panel = document.getElementById('trend-panel');
    if (!panel) return;
    bound = true;
    const stored = sessionStorage.getItem('mtws_trend_scope');
    if (stored) {
      const radio = panel.querySelector(`input[name="trend-scope"][value="${stored}"]`);
      if (radio) radio.checked = true;
    }
    const hoursInput = document.getElementById('trend-future-hours');
    if (hoursInput) {
      hoursInput.value = String(readStoredHours());
      hoursInput.addEventListener('change', () => {
        hoursInput.value = String(futureHours());
        const mapHours = document.getElementById('map-future-hours');
        if (mapHours) mapHours.value = hoursInput.value;
        load();
      });
    }
    syncHoursVisibility();
    panel.querySelectorAll('input[name="trend-scope"]').forEach((el) => {
      el.addEventListener('change', load);
    });
    const half = document.getElementById('trend-half');
    if (half) half.addEventListener('change', render);
    const refresh = document.getElementById('trend-refresh');
    if (refresh) refresh.addEventListener('click', load);
    const wrap = document.getElementById('trend-table-wrap');
    if (wrap) wrap.addEventListener('click', (event) => {
      const btn = event.target.closest('.trend-handle-btn');
      if (btn) markTrendHandled(btn);
    });
    const tz = document.getElementById('timezone-toggle-input');
    if (tz) tz.addEventListener('change', () => {
      if (panel.style.display !== 'none') render();
    });
  }

  function lockHomeAlertForTrend() {
    document.body.classList.add('trend-alert-locked');
    document.querySelectorAll('.filter-btn[data-group="domestic"], .filter-btn[data-group="international"]').forEach((btn) => {
      btn.classList.add('selected');
    });
    document.querySelectorAll('.filter-btn[data-group="alert"]').forEach((btn) => {
      const value = btn.getAttribute('data-value');
      btn.classList.toggle('selected', value === 'red' || value === 'yellow' || value === 'green');
    });
  }

  function unlockHomeAlertForTrend() {
    document.body.classList.remove('trend-alert-locked');
    if (typeof updateAlertButtonState === 'function') updateAlertButtonState();
    if (typeof updateRegionButtonState === 'function') {
      updateRegionButtonState('domestic');
      updateRegionButtonState('international');
    }
  }

  function startTrendView() {
    bindOnce();
    lockHomeAlertForTrend();
    if (payload) render();
    load();
  }

  function stopTrendView() {
    unlockHomeAlertForTrend();
  }

  window.startTrendView = startTrendView;
  window.stopTrendView = stopTrendView;
  window.prefetchTrendBadge = function () {
    bindOnce();
    bindStatHover();
    if (payload) {
      updateNavBadge();
      return;
    }
    load();
  };
  window.addEventListener('mtws-carriers-changed', () => {
    load();
  });

  window.syncTrendHomeFilter = function () {
    const panel = document.getElementById('trend-panel');
    if (!panel || panel.style.display === 'none' || !payload) return;
    render();
  };
})();
