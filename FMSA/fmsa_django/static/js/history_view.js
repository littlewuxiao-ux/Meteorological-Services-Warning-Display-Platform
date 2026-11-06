/**
 * 回顾视图。规则组在设置模块中维护；未点查询不拉数。
 */
(function () {
  'use strict';

  const RESULT_MS = 10 * 60 * 1000;
  const IDLE_EMPTY = '选择时段后点击查询';
  const STATUS_OPTIONS = ['落地', '起飞', '飞行中', '即将起飞', '停场'];
  const ELEMENT_FALLBACK = ['风速', '能见度', 'RVR', '云底高', '气温', '风切变', '趋势'];
  const TYPE_CLASS = {
    '落地': 'hs-type-land',
    '起飞': 'hs-type-dep',
    '飞行中': 'hs-type-enr',
    '即将起飞': 'hs-type-soon',
    '停场': 'hs-type-park',
  };
  const TIME_LEVELS = [
    { key: 'year', label: '年' },
    { key: 'month', label: '月' },
    { key: 'day', label: '日' },
    { key: 'hour', label: '时' },
    { key: 'minute', label: '分' },
  ];

  let bound = false;
  let querySeq = 0;
  let lastRows = [];
  let lastRange = null;
  let expireTimer = null;
  let openFilter = '';
  let elementOptions = ELEMENT_FALLBACK.slice();
  let statusSelected = new Set(STATUS_OPTIONS);
  let elementSelected = new Set(ELEMENT_FALLBACK.filter((name) => name !== '趋势'));
  let clockMode = 'zone';
  let nameMode = 'icao';
  let timeLevel = { year: false, month: false, day: true, hour: true, minute: true };
  let selected = new Set();

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

  function usesUtc(airport) {
    if (clockMode === 'unified') return window.displayTimezone === 'UTC';
    return !String(airport || '').toUpperCase().startsWith('Z');
  }

  function timestampParts(ms, utc) {
    const date = new Date(Number(ms));
    if (!Number.isFinite(date.getTime())) {
      return { year: '', month: '', day: '', hour: '', minute: '' };
    }
    const timeZone = utc ? 'UTC' : 'Asia/Shanghai';
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(date);
    const pick = (type) => {
      const item = parts.find((part) => part.type === type);
      return item ? item.value : '';
    };
    let hour = pick('hour');
    if (hour === '24') hour = '00';
    return {
      year: pick('year'),
      month: pick('month'),
      day: pick('day'),
      hour,
      minute: pick('minute'),
    };
  }

  function addHour(parts) {
    let year = Number(parts.year);
    let month = Number(parts.month);
    let day = Number(parts.day);
    let hour = Number(parts.hour) + 1;
    if (hour >= 24) {
      hour = 0;
      day += 1;
      const dim = new Date(year, month, 0).getDate();
      if (day > dim) {
        day = 1;
        month += 1;
        if (month > 12) {
          month = 1;
          year += 1;
        }
      }
    }
    return {
      year: String(year),
      month: pad(month),
      day: pad(day),
      hour: pad(hour),
      minute: '00',
    };
  }

  function sameDate(a, b) {
    return a.year === b.year && a.month === b.month && a.day === b.day;
  }

  function formatTimeParts(parts, utc, omitDate) {
    let date = '';
    if (!omitDate) {
      if (timeLevel.month) {
        date = timeLevel.year
          ? `${parts.year}-${parts.month}-${parts.day}`
          : `${parts.month}-${parts.day}`;
      } else if (timeLevel.day) {
        date = `${parts.day}日`;
      }
    }
    let time = '';
    if (timeLevel.hour && timeLevel.minute) {
      time = `${parts.hour}:${parts.minute}`;
      if (utc) time += 'Z';
    } else if (timeLevel.hour) {
      time = utc ? `${parts.hour}Z` : `${parts.hour}时`;
    }
    if (!date) return time;
    if (!time) return date;
    return timeLevel.month ? `${date} ${time}` : `${date}${time}`;
  }

  function formatRangeLabel(startMs, endMs, airport, opts) {
    if (!startMs || !endMs) return '';
    const utc = usesUtc(airport);
    const start = timestampParts(startMs, utc);
    let end = timestampParts(endMs, utc);
    const allowBump = !(opts && opts.noBump);
    if (allowBump && !timeLevel.minute && start.hour === end.hour && sameDate(start, end)) {
      end = addHour(end);
    }
    const left = formatTimeParts(start, utc, false);
    const right = formatTimeParts(end, utc, sameDate(start, end));
    if (!right || left === right) return left;
    return `${left}-${right}`;
  }

  function airportLabel(row) {
    if (nameMode === 'name') {
      return row.airport_name || (lastRange && lastRange.airport_names && lastRange.airport_names[row.airport]) || '机场名称未配置';
    }
    return row.airport;
  }

  function setTimeLevel(key, on) {
    if ((key === 'day' || key === 'hour') && !on) return;
    if (on) {
      if (key === 'year') timeLevel.month = true;
      timeLevel[key] = true;
    } else {
      timeLevel[key] = false;
      if (key === 'month') timeLevel.year = false;
    }
  }

  function syncClockSwitch() {
    document.querySelectorAll('#history-clock-switch [data-clock]').forEach((btn) => {
      btn.classList.toggle('is-on', btn.getAttribute('data-clock') === clockMode);
    });
  }

  function timeLevelHtml() {
    const group = `<span class="hs-level-group">${TIME_LEVELS.map((item) => {
      const on = timeLevel[item.key] ? ' is-on' : '';
      const locked = item.key === 'day' || item.key === 'hour' ? ' data-locked="1"' : '';
      return `<button type="button" class="hs-level${on}" data-time-level="${item.key}"${locked}>${item.label}</button>`;
    }).join('')}</span>`;
    return `<div class="hs-th-stack"><div>时段</div>${group}</div>`;
  }

  function airportHeadHtml() {
    const icaoOn = nameMode === 'icao' ? ' is-on' : '';
    const nameOn = nameMode === 'name' ? ' is-on' : '';
    return `<div class="hs-th-stack"><div>机场</div><span class="hs-name-switch"><button type="button" class="hs-name-btn${icaoOn}" data-name-mode="icao">ICAO</button><button type="button" class="hs-name-btn${nameOn}" data-name-mode="name">名称</button></span></div>`;
  }

  function visibleIds() {
    return visibleRows().map((row) => lastRows.indexOf(row)).filter((id) => id >= 0);
  }

  function allVisiblePicked() {
    const ids = visibleIds();
    return ids.length > 0 && ids.every((id) => selected.has(id));
  }

  function pickHeadHtml() {
    const label = allVisiblePicked() ? '取消全选' : '全选';
    return `<button type="button" class="hs-pick-all" data-pick-all>${label}</button>`;
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

  function applyElementOptions(names) {
    const list = (names || []).map((name) => String(name || '').trim()).filter(Boolean);
    if (!list.length) return;
    const next = [];
    const seen = new Set();
    list.forEach((name) => {
      if (seen.has(name)) return;
      seen.add(name);
      next.push(name);
      if (name !== '趋势' && !elementSelected.has(name) && !elementOptions.includes(name)) {
        elementSelected.add(name);
      }
    });
    elementOptions = next;
  }

  function rowBadges(row) {
    const elements = row.element_badges || [];
    const weather = row.weather_badges || [];
    if (elements.length || weather.length) return elements.concat(weather);
    return row.badges || [];
  }

  function rowMatches(row) {
    const types = row.types || [];
    const statusHit = types.some((name) => statusSelected.has(name));
    const elementHit = rowBadges(row).some((badge) => badge && elementSelected.has(badge.text));
    return statusHit && elementHit;
  }

  function visibleRows() {
    return lastRows.filter(rowMatches);
  }

  function filterMenu(kind, options, selected) {
    const open = openFilter === kind ? '' : ' hidden';
    const items = options.map((name) => {
      const checked = selected.has(name) ? ' checked' : '';
      return `<label class="hs-filter-item"><input type="checkbox" data-filter-item="${esc(kind)}" value="${esc(name)}"${checked}><span>${esc(name)}</span></label>`;
    }).join('');
    return `<button type="button" class="hs-filter-btn" data-filter="${esc(kind)}" aria-label="筛选">▾</button><div class="hs-filter-menu" data-filter-menu="${esc(kind)}"${open}>${items}</div>`;
  }

  function badgeHtml(badge) {
    if (!badge || !badge.text) return '';
    const level = badge.level === 'R' || badge.level === 'Y' || badge.level === 'G' ? badge.level : 'N';
    return `<span class="warning-badge warning-${level}">${esc(badge.text)}</span>`;
  }

  function popupBadgeHtml(row) {
    const html = rowBadges(row).map(badgeHtml).join('');
    if (!html) return '';
    return `<div class="popup-warning-badges"><div class="popup-warning-row">${html}</div></div>`;
  }

  function typeHtml(name) {
    return `<span class="hs-type ${TYPE_CLASS[name] || ''}">${esc(name)}</span>`;
  }

  function timeHtml(row) {
    const label = formatRangeLabel(row.start_ms, row.end_ms, row.airport);
    return `<div class="hs-time">${esc(label)}</div>`;
  }

  function showIdle() {
    const wrap = document.getElementById('history-table-wrap');
    if (wrap) wrap.innerHTML = `<div class="hs-empty">${IDLE_EMPTY}</div>`;
  }

  function paintTable() {
    const wrap = document.getElementById('history-table-wrap');
    if (!wrap) return;
    if (!lastRows.length) {
      showIdle();
      return;
    }
    const rows = visibleRows();
    const statusHead = `时段内的航班状态${filterMenu('status', STATUS_OPTIONS, statusSelected)}`;
    const elementHead = `天气要素类型${filterMenu('element', elementOptions, elementSelected)}`;
    const periodHead = timeLevelHtml();
    const airportHead = airportHeadHtml();
    const pickHead = pickHeadHtml();
    if (!rows.length) {
      wrap.innerHTML = `<table class="hs-table"><thead><tr><th class="hs-th-airport">${airportHead}</th><th class="hs-th-time">${periodHead}</th><th class="hs-th-filter">${statusHead}</th><th class="hs-th-filter">${elementHead}</th><th>天气</th><th>原文</th><th class="hs-th-pick">${pickHead}</th><th>复制</th></tr></thead></table><div class="hs-empty">没有符合筛选条件的天气</div>`;
      return;
    }
    const groups = [];
    rows.forEach((row) => {
      const last = groups[groups.length - 1];
      if (last && last.airport === row.airport) last.rows.push(row);
      else groups.push({ airport: row.airport, rows: [row] });
    });
    const COLS = 6;
    let html = `<table class="hs-table"><thead><tr><th class="hs-th-airport">${airportHead}</th><th class="hs-th-time">${periodHead}</th><th class="hs-th-filter">${statusHead}</th><th class="hs-th-filter">${elementHead}</th><th>天气</th><th>原文</th><th class="hs-th-pick">${pickHead}</th><th>复制</th></tr></thead><tbody>`;
    let rowIndex = 0;
    groups.forEach((group) => {
      group.rows.forEach((row, index) => {
        const id = lastRows.indexOf(row);
        const viewId = rowIndex++;
        html += `<tr class="hs-data" data-row="${id}" data-view="${viewId}" data-airport="${esc(group.airport)}">`;
        if (index === 0) {
          html += `<td class="hs-airport" rowspan="${group.rows.length}">${esc(airportLabel(row))}</td>`;
        }
        html += `<td class="hs-period">${timeHtml(row)}</td>`;
        html += `<td class="hs-types">${(row.types || []).map(typeHtml).join('')}</td>`;
        html += `<td class="hs-badges">${popupBadgeHtml(row)}</td>`;
        html += `<td class="hs-plain">${esc(row.plain || '')}</td>`;
        html += `<td class="hs-action"><button type="button" class="hs-text-btn" data-raw="${id}">查看原文</button></td>`;
        html += `<td class="hs-pick"><input type="checkbox" data-pick="${id}"${selected.has(id) ? ' checked' : ''}></td>`;
        if (index === 0) {
          html += `<td class="hs-action hs-copy" rowspan="${group.rows.length}"><button type="button" class="hs-text-btn" data-copy="${esc(group.airport)}">复制</button></td>`;
        }
        html += '</tr>';
        html += `<tr class="hs-raw" data-raw-for="${id}" hidden><td colspan="${COLS}">${rawReportsHtml(row)}</td></tr>`;
      });
    });
    html += '</tbody></table>';
    wrap.innerHTML = html;
  }

  function rawReportsHtml(row) {
    const reports = row.reports || [];
    if (!reports.length) return '<div class="hs-raw-empty">该时段没有报文</div>';
    return reports.map((item) => {
      const when = formatRangeLabel(item.obs_ms, item.obs_ms, row.airport, { noBump: true });
      return `<div class="hs-raw-item"><div class="hs-raw-time">${esc(when)}</div><pre class="hs-raw-text">${esc(item.content || '')}</pre></div>`;
    }).join('');
  }

  function syncAirportRowspan(airport) {
    const wrap = document.getElementById('history-table-wrap');
    if (!wrap) return;
    const dataRows = [...wrap.querySelectorAll(`tr.hs-data[data-airport="${airport}"]`)];
    if (!dataRows.length) return;
    let extra = 0;
    dataRows.forEach((tr) => {
      const raw = tr.nextElementSibling;
      if (raw && raw.classList.contains('hs-raw') && !raw.hidden) extra += 1;
    });
    const span = dataRows.length + extra;
    const airportTd = dataRows[0].querySelector('td.hs-airport');
    if (airportTd) airportTd.rowSpan = span;
    const copyTd = dataRows[0].querySelector('td.hs-copy');
    if (copyTd) copyTd.rowSpan = span;
  }

  function toggleRaw(id) {
    const raw = document.querySelector(`tr.hs-raw[data-raw-for="${id}"]`);
    const data = document.querySelector(`tr.hs-data[data-row="${id}"]`);
    const btn = data ? data.querySelector('[data-raw]') : null;
    if (!raw || !data) return;
    raw.hidden = !raw.hidden;
    if (btn) btn.textContent = raw.hidden ? '查看原文' : '收起原文';
    syncAirportRowspan(data.getAttribute('data-airport'));
  }

  function periodCopyText(row) {
    const span = formatRangeLabel(row.start_ms, row.end_ms, row.airport);
    const weather = row.plain || '无满足告警条件的天气';
    return `${span}，${weather}`;
  }

  function airportCopyText(rows) {
    if (!rows.length) return '';
    return `${airportLabel(rows[0])}：${rows.map(periodCopyText).join('；')}。`;
  }

  function pickedRows(airport) {
    return visibleRows().filter((row) => {
      if (airport && row.airport !== airport) return false;
      return selected.has(lastRows.indexOf(row));
    });
  }

  function copyText(text, okMsg) {
    const done = () => setStatus(okMsg);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
      fallbackCopy(text, done);
    }
  }

  function copyAirport(airport) {
    const rows = pickedRows(airport);
    if (!rows.length) {
      setStatus('没有可复制的内容', true);
      return;
    }
    copyText(airportCopyText(rows), `已复制${airportLabel(rows[0])}天气`);
  }

  function copyAll() {
    const rows = pickedRows();
    if (!rows.length) {
      setStatus('没有可复制的内容', true);
      return;
    }
    const groups = [];
    rows.forEach((row) => {
      const last = groups[groups.length - 1];
      if (last && last[0].airport === row.airport) last.push(row);
      else groups.push([row]);
    });
    copyText(groups.map(airportCopyText).join('\n'), '已复制全部机场天气');
  }

  function refreshPickHeader() {
    const btn = document.querySelector('[data-pick-all]');
    if (btn) btn.textContent = allVisiblePicked() ? '取消全选' : '全选';
  }

  function onPickAll() {
    const ids = visibleIds();
    const all = allVisiblePicked();
    ids.forEach((id) => {
      if (all) selected.delete(id);
      else selected.add(id);
    });
    document.querySelectorAll('[data-pick]').forEach((el) => {
      el.checked = selected.has(Number(el.getAttribute('data-pick')));
    });
    refreshPickHeader();
  }

  function fallbackCopy(text, done) {
    const box = document.createElement('textarea');
    box.value = text;
    document.body.appendChild(box);
    box.select();
    try { document.execCommand('copy'); done(); } catch (err) { setStatus('复制失败', true); }
    box.remove();
  }

  function clearExpired() {
    lastRows = [];
    lastRange = null;
    openFilter = '';
    showIdle();
    setStatus('');
  }

  function armExpire() {
    if (expireTimer) clearTimeout(expireTimer);
    expireTimer = setTimeout(clearExpired, RESULT_MS);
  }

  async function runQuery() {
    const seq = ++querySeq;
    const btn = document.getElementById('history-query');
    if (btn) btn.disabled = true;
    setStatus('正在查询…');
    try {
      const kind = preset();
      const body = { preset: kind };
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
      applyElementOptions(data.element_options);
      lastRows = data.rows || [];
      selected = new Set(lastRows.map((_, index) => index));
      openFilter = '';
      paintTable();
      armExpire();
      if (!lastRows.length) {
        const wrap = document.getElementById('history-table-wrap');
        if (wrap) wrap.innerHTML = '<div class="hs-empty">所选时段内没有满足条件的天气</div>';
      }
      setStatus(`航班 ${data.flight_count || 0} 条，机场 ${data.airport_count || 0} 个，记录 ${visibleRows().length} 段`);
    } catch (err) {
      if (seq !== querySeq) return;
      setStatus(err.message || '查询失败', true);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function toggleFilter(kind) {
    openFilter = openFilter === kind ? '' : kind;
    paintTable();
  }

  function onFilterCheck(kind, name, checked) {
    const selected = kind === 'status' ? statusSelected : elementSelected;
    if (checked) selected.add(name);
    else selected.delete(name);
    paintTable();
    if (lastRows.length) {
      setStatus(`航班 ${lastRange && lastRange.flight_count || 0} 条，机场 ${lastRange && lastRange.airport_count || 0} 个，记录 ${visibleRows().length} 段`);
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
    const clockSwitch = document.getElementById('history-clock-switch');
    if (clockSwitch) {
      clockSwitch.addEventListener('click', (event) => {
        const btn = event.target.closest('[data-clock]');
        if (!btn) return;
        clockMode = btn.getAttribute('data-clock') === 'unified' ? 'unified' : 'zone';
        syncClockSwitch();
        if (lastRows.length) paintTable();
      });
    }
    const queryBtn = document.getElementById('history-query');
    if (queryBtn) queryBtn.addEventListener('click', runQuery);
    const copyAllBtn = document.getElementById('history-copy-all');
    if (copyAllBtn) copyAllBtn.addEventListener('click', copyAll);
    const tableWrap = document.getElementById('history-table-wrap');
    if (tableWrap) {
      tableWrap.addEventListener('click', (event) => {
        const levelBtn = event.target.closest('[data-time-level]');
        if (levelBtn) {
          event.stopPropagation();
          const key = levelBtn.getAttribute('data-time-level');
          setTimeLevel(key, !timeLevel[key]);
          if (lastRows.length) paintTable();
          return;
        }
        const nameBtn = event.target.closest('[data-name-mode]');
        if (nameBtn) {
          event.stopPropagation();
          nameMode = nameBtn.getAttribute('data-name-mode') === 'name' ? 'name' : 'icao';
          if (lastRows.length) paintTable();
          return;
        }
        const filterBtn = event.target.closest('[data-filter]');
        if (filterBtn) {
          event.stopPropagation();
          toggleFilter(filterBtn.getAttribute('data-filter'));
          return;
        }
        if (event.target.closest('[data-filter-menu]')) return;
        const pickAll = event.target.closest('[data-pick-all]');
        if (pickAll) {
          event.stopPropagation();
          onPickAll();
          return;
        }
        const rawBtn = event.target.closest('[data-raw]');
        if (rawBtn) {
          toggleRaw(rawBtn.getAttribute('data-raw'));
          return;
        }
        const copyBtn = event.target.closest('[data-copy]');
        if (copyBtn) copyAirport(copyBtn.getAttribute('data-copy'));
      });
      tableWrap.addEventListener('change', (event) => {
        const pick = event.target.closest('[data-pick]');
        if (pick) {
          const id = Number(pick.getAttribute('data-pick'));
          if (pick.checked) selected.add(id);
          else selected.delete(id);
          refreshPickHeader();
          return;
        }
        const box = event.target.closest('[data-filter-item]');
        if (!box) return;
        onFilterCheck(box.getAttribute('data-filter-item'), box.value, box.checked);
      });
    }
    document.addEventListener('click', (event) => {
      if (!openFilter) return;
      if (event.target.closest('.hs-th-filter')) return;
      openFilter = '';
      if (lastRows.length) paintTable();
    });
    const tz = document.getElementById('timezone-toggle-input');
    if (tz) tz.addEventListener('change', () => {
      if (clockMode === 'unified' && panel.style.display !== 'none' && lastRows.length) paintTable();
    });
    window.addEventListener('resize', syncPanelHeight);
  }

  function syncPanelHeight() {
    const panel = document.getElementById('history-panel');
    const chrome = document.querySelector('.page-chrome');
    if (!panel) return;
    const offset = chrome ? Math.max(0, Math.round(chrome.getBoundingClientRect().bottom)) : 120;
    panel.style.setProperty('--hs-offset', `${offset}px`);
  }

  async function loadElementOptions() {
    try {
      const res = await fetch(apiUrl('history-stats/config/'), { headers: headers() });
      const data = await res.json();
      if (data.success) applyElementOptions(data.element_options);
    } catch (err) { /* 沿用内置选项 */ }
  }

  async function startHistoryView() {
    bindOnce();
    syncClockSwitch();
    syncCustomVisible();
    syncPanelHeight();
    await loadElementOptions();
    if (lastRows.length) paintTable();
    else showIdle();
    if (preset() === 'custom') fillCustomDefaults();
  }

  function stopHistoryView() {
    querySeq += 1;
  }

  window.startHistoryView = startHistoryView;
  window.stopHistoryView = stopHistoryView;
  window.refreshHistoryTimezone = function () {
    if (lastRows.length) paintTable();
  };
})();
