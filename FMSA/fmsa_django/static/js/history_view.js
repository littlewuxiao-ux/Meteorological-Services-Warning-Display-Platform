/**
 * 历史天气统计视图。规则组在设置模块中维护；未点确定不查询。
 */
(function () {
  'use strict';

  let bound = false;
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

  function badgeHtml(badge) {
    if (!badge || !badge.text) return '';
    const level = badge.level === 'R' || badge.level === 'Y' || badge.level === 'G' ? badge.level : 'N';
    return `<span class="warning-badge warning-${level}">${esc(badge.text)}</span>`;
  }

  function popupBadgeHtml(row) {
    const elements = row.element_badges || [];
    const weather = row.weather_badges || [];
    const fallback = (!elements.length && !weather.length) ? (row.badges || []) : [];
    const all = (elements.length || weather.length)
      ? elements.concat(weather)
      : fallback;
    const html = all.map(badgeHtml).join('');
    if (!html) return '';
    return `<div class="popup-warning-badges"><div class="popup-warning-row">${html}</div></div>`;
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
    const COLS = 5;
    let html = '<table class="hs-table"><thead><tr><th>机场</th><th>时段</th><th>影响运行的类型</th><th>告警类型</th><th>天气</th><th>原文</th><th>复制</th></tr></thead><tbody>';
    let rowIndex = 0;
    groups.forEach((group) => {
      group.rows.forEach((row, index) => {
        const id = rowIndex++;
        html += `<tr class="hs-data" data-row="${id}" data-airport="${esc(group.airport)}">`;
        if (index === 0) {
          html += `<td class="hs-airport" rowspan="${group.rows.length}">${esc(group.airport)}</td>`;
        }
        html += `<td class="hs-period">${timeHtml(row.start_ms, row.end_ms)}</td>`;
        html += `<td class="hs-types">${(row.types || []).map(typeHtml).join('')}</td>`;
        html += `<td class="hs-badges">${popupBadgeHtml(row)}</td>`;
        html += `<td class="hs-plain">${esc(row.plain || '')}</td>`;
        html += `<td class="hs-action"><button type="button" class="hs-text-btn" data-raw="${id}">显示原文</button></td>`;
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
      const when = formatRangeLabel(item.obs_ms, item.obs_ms).split(' → ')[0] || '';
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
    if (btn) btn.textContent = raw.hidden ? '显示原文' : '收起原文';
    syncAirportRowspan(data.getAttribute('data-airport'));
  }

  function rowCopyText(row) {
    const span = formatRangeLabel(row.start_ms, row.end_ms).replace(' → ', '至');
    const weather = row.plain || '无满足告警条件的天气';
    return `${row.airport} ${span}，${weather}`;
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
    const rows = lastRows.filter((row) => row.airport === airport);
    if (!rows.length) return;
    copyText(rows.map(rowCopyText).join('\n'), `已复制${airport}机场天气`);
  }

  function copyAll() {
    if (!lastRows.length) {
      setStatus('没有可复制的内容', true);
      return;
    }
    const lines = [];
    let prev = null;
    lastRows.forEach((row) => {
      if (prev && prev !== row.airport) lines.push('');
      prev = row.airport;
      lines.push(rowCopyText(row));
    });
    copyText(lines.join('\n'), '已复制全部机场天气');
  }

  function fallbackCopy(text, done) {
    const box = document.createElement('textarea');
    box.value = text;
    document.body.appendChild(box);
    box.select();
    try { document.execCommand('copy'); done(); } catch (err) { setStatus('复制失败', true); }
    box.remove();
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
    const queryBtn = document.getElementById('history-query');
    if (queryBtn) queryBtn.addEventListener('click', runQuery);
    const copyAllBtn = document.getElementById('history-copy-all');
    if (copyAllBtn) copyAllBtn.addEventListener('click', copyAll);
    const tableWrap = document.getElementById('history-table-wrap');
    if (tableWrap) {
      tableWrap.addEventListener('click', (event) => {
        const rawBtn = event.target.closest('[data-raw]');
        if (rawBtn) {
          toggleRaw(rawBtn.getAttribute('data-raw'));
          return;
        }
        const copyBtn = event.target.closest('[data-copy]');
        if (copyBtn) copyAirport(copyBtn.getAttribute('data-copy'));
      });
    }
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
