/**
 * 回顾视图。规则组在设置模块中维护；未点查询不拉数。
 */
(function () {
  'use strict';

  const RESULT_MS = 10 * 60 * 1000;
  const IDLE_EMPTY = '选择时段后点击查询';
  const STATUS_OPTIONS = ['落地', '起飞', '飞行中', '即将起飞', '停场'];
  const ELEMENT_FALLBACK = ['风速', '能见度', 'RVR', '云底高', '高温', '低温', '风切变', '趋势'];
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
  let nameMode = 'icao';
  let timeLevel = { year: false, month: false, day: true, hour: true, minute: true };
  let selected = new Set();
  let customStartMs = null;
  let customEndMs = null;

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

  function displayUtc() {
    return window.displayTimezone === 'UTC';
  }

  function msToInput(ms) {
    const parts = timestampParts(ms, displayUtc());
    if (!parts.year) return '';
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  }

  function inputToMs(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(value || ''));
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const hour = Number(match[4]);
    const minute = Number(match[5]);
    if (displayUtc()) return Date.UTC(year, month - 1, day, hour, minute);
    return Date.UTC(year, month - 1, day, hour, minute) - 8 * 3600000;
  }

  function usesUtc(airport) {
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

  const PRESET_RANGE_CST = {
    day: '08:30–17:30',
    night: '17:30–次日08:30',
    daynight: '08:30–次日08:30',
  };
  const PRESET_RANGE_UTC = {
    day: '00:30–09:30',
    night: '09:30–次日00:30',
    daynight: '00:30–次日00:30',
  };

  function syncPresetLabels() {
    const map = displayUtc() ? PRESET_RANGE_UTC : PRESET_RANGE_CST;
    document.querySelectorAll('[data-hs-range]').forEach((el) => {
      const key = el.getAttribute('data-hs-range');
      if (map[key]) el.textContent = map[key];
    });
  }

  let calWhich = '';
  let calView = { year: 0, month: 0 };
  let calDraft = null;
  let calEl = null;

  function formatField(ms) {
    if (ms == null) return '';
    const value = msToInput(ms);
    if (!value) return '';
    const text = value.replace('T', ' ');
    return displayUtc() ? `${text}Z` : text;
  }

  function writeCustomInputs() {
    const start = document.getElementById('history-start');
    const end = document.getElementById('history-end');
    if (start) start.textContent = formatField(customStartMs) || '开始时间';
    if (end) end.textContent = formatField(customEndMs) || '结束时间';
  }

  function partsToMs(parts) {
    const year = Number(parts && parts.year);
    const month = Number(parts && parts.month);
    const day = Number(parts && parts.day);
    const hour = Number(parts && parts.hour);
    const minute = Number(parts && parts.minute);
    if (![year, month, day, hour, minute].every(Number.isFinite)) return null;
    if (displayUtc()) return Date.UTC(year, month - 1, day, hour, minute);
    return Date.UTC(year, month - 1, day, hour, minute) - 8 * 3600000;
  }

  function cloneParts(parts) {
    return {
      year: String(parts.year),
      month: pad(Number(parts.month)),
      day: pad(Number(parts.day)),
      hour: pad(Number(parts.hour)),
      minute: pad(Number(parts.minute)),
    };
  }

  function shiftMonth(year, month, delta) {
    let nextMonth = Number(month) + delta;
    let nextYear = Number(year);
    while (nextMonth < 1) {
      nextMonth += 12;
      nextYear -= 1;
    }
    while (nextMonth > 12) {
      nextMonth -= 12;
      nextYear += 1;
    }
    return { year: nextYear, month: nextMonth };
  }

  const WHEEL = {
    slotPx: 22,
    angle: 12,
    radius: 96,
    span: 3,
  };
  const WHEEL_HOURS = Array.from({ length: 24 }, (_, i) => i);
  const WHEEL_MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);
  let wheels = [];
  let wheelRaf = 0;
  let wheelAudio = null;
  let lastWheelTick = 0;

  function snapMinute(value) {
    const n = Math.round(Number(value) / 5) * 5;
    if (!Number.isFinite(n) || n < 0) return 0;
    return n >= 60 ? 0 : n;
  }

  function wrapSlot(index, count) {
    return ((Math.round(index) % count) + count) % count;
  }

  function tickWheel(wheel) {
    playWheelTick();
    if (!wheel || !wheel.view) return;
    wheel.view.classList.remove('is-tick');
    void wheel.view.offsetWidth;
    wheel.view.classList.add('is-tick');
  }

  function playWheelTick() {
    const now = performance.now();
    if (now - lastWheelTick < 28) return;
    lastWheelTick = now;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!wheelAudio) wheelAudio = new AudioCtx();
      if (wheelAudio.state === 'suspended') wheelAudio.resume();
      const t = wheelAudio.currentTime;
      const osc = wheelAudio.createOscillator();
      const gain = wheelAudio.createGain();
      osc.type = 'square';
      osc.frequency.value = 1400;
      gain.gain.setValueAtTime(0.035, t);
      gain.gain.exponentialRampToValueAtTime(0.0008, t + 0.03);
      osc.connect(gain);
      gain.connect(wheelAudio.destination);
      osc.start(t);
      osc.stop(t + 0.032);
    } catch (err) { /* 无声也保留吸附 */ }
  }

  function syncDraftFromWheels() {
    if (!calDraft) return;
    wheels.forEach((wheel) => {
      const value = wheel.values[wrapSlot(wheel.index, wheel.values.length)];
      if (wheel.kind === 'hour') calDraft.hour = pad(value);
      if (wheel.kind === 'minute') calDraft.minute = pad(value);
    });
  }

  function paintWheel(wheel) {
    const n = wheel.values.length;
    const scene = wheel.scene;
    if (!scene) return;
    const needed = WHEEL.span * 2 + 1;
    while (scene.children.length < needed) {
      const item = document.createElement('span');
      item.className = 'hs-wheel-item';
      scene.appendChild(item);
    }
    while (scene.children.length > needed) scene.removeChild(scene.lastChild);
    const base = Math.round(wheel.index);
    for (let k = -WHEEL.span; k <= WHEEL.span; k += 1) {
      const item = scene.children[k + WHEEL.span];
      const slot = base + k;
      const offset = slot - wheel.index;
      const value = wheel.values[((slot % n) + n) % n];
      const dist = Math.abs(offset);
      const tilt = offset * WHEEL.angle;
      const scale = dist < 0.5 ? 1 : Math.max(0.72, 1 - dist * 0.1);
      const opacity = dist < 0.5 ? 1 : Math.max(0.18, 0.42 * Math.exp(-0.42 * (dist - 1)));
      item.style.visibility = 'visible';
      item.textContent = pad(value);
      item.style.opacity = String(opacity);
      item.style.zIndex = String(Math.round((3 - dist) * 8));
      item.style.filter = 'none';
      item.style.transform = `translate(-50%, -50%) translateY(${(offset * WHEEL.slotPx).toFixed(2)}px) rotateX(${(-tilt).toFixed(2)}deg) scale(${scale.toFixed(3)})`;
      item.classList.toggle('is-on', dist < 0.5);
    }
  }

  function nearestWheelIndex(wheel) {
    return Math.round(wheel.index);
  }

  function stopWheelLoop() {
    if (wheelRaf) {
      cancelAnimationFrame(wheelRaf);
      wheelRaf = 0;
    }
  }

  function wheelLoop(now) {
    wheelRaf = 0;
    let moving = false;
    wheels.forEach((wheel) => {
      if (wheel.dragging) {
        moving = true;
        paintWheel(wheel);
        return;
      }
      const dt = Math.min(32, now - (wheel.lastT || now)) / 1000;
      wheel.lastT = now;
      if (dt <= 0) {
        moving = true;
        return;
      }
      const prevSlot = Math.round(wheel.index);
      if (Math.abs(wheel.vel) > 2.2) {
        wheel.vel *= Math.exp(-3.1 * dt);
        wheel.index += wheel.vel * dt;
        moving = true;
      } else {
        const target = nearestWheelIndex(wheel);
        const dist = target - wheel.index;
        wheel.vel += dist * 90 * dt;
        wheel.vel *= Math.exp(-14 * dt);
        wheel.index += wheel.vel * dt;
        if (Math.abs(dist) < 0.004 && Math.abs(wheel.vel) < 0.12) {
          wheel.index = target;
          wheel.vel = 0;
        } else {
          moving = true;
        }
      }
      const slot = Math.round(wheel.index);
      if (slot !== prevSlot) tickWheel(wheel);
      paintWheel(wheel);
    });
    syncDraftFromWheels();
    if (moving) wheelRaf = requestAnimationFrame(wheelLoop);
  }

  function kickWheelLoop() {
    if (!wheelRaf) wheelRaf = requestAnimationFrame(wheelLoop);
  }

  function bindWheel(wheel) {
    const view = wheel.view;
    if (!view || view.dataset.bound === '1') return;
    view.dataset.bound = '1';
    const samples = [];

    function sampleVel(y, t) {
      samples.push({ y, t });
      if (samples.length > 5) samples.shift();
    }

    function releaseVel() {
      if (samples.length < 2) return 0;
      const a = samples[0];
      const b = samples[samples.length - 1];
      const dt = b.t - a.t;
      if (dt < 8) return 0;
      return -((b.y - a.y) / dt) * (1000 / WHEEL.slotPx);
    }

    view.addEventListener('pointerdown', (event) => {
      if (event.button && event.button !== 0) return;
      event.preventDefault();
      view.setPointerCapture(event.pointerId);
      wheel.dragging = true;
      wheel.vel = 0;
      wheel.startY = event.clientY;
      wheel.startIndex = wheel.index;
      wheel.moved = 0;
      samples.length = 0;
      sampleVel(event.clientY, event.timeStamp);
      view.classList.add('is-grabbing');
      stopWheelLoop();
      paintWheel(wheel);
    });
    view.addEventListener('pointermove', (event) => {
      if (!wheel.dragging) return;
      const dy = event.clientY - wheel.startY;
      wheel.moved = Math.max(wheel.moved, Math.abs(dy));
      const prevSlot = Math.round(wheel.index);
      wheel.index = wheel.startIndex - dy / WHEEL.slotPx;
      if (Math.round(wheel.index) !== prevSlot) tickWheel(wheel);
      sampleVel(event.clientY, event.timeStamp);
      paintWheel(wheel);
      syncDraftFromWheels();
    });
    function endDrag(event) {
      if (!wheel.dragging) return;
      wheel.dragging = false;
      view.classList.remove('is-grabbing');
      if (wheel.moved < 5) {
        const rect = view.getBoundingClientRect();
        const offset = (event.clientY - (rect.top + rect.height / 2)) / WHEEL.slotPx;
        wheel.index = nearestWheelIndex(wheel) + Math.round(offset);
        wheel.vel = 0;
      } else {
        wheel.vel = releaseVel();
        const max = 28;
        if (wheel.vel > max) wheel.vel = max;
        if (wheel.vel < -max) wheel.vel = -max;
      }
      wheel.lastT = performance.now();
      kickWheelLoop();
    }
    view.addEventListener('pointerup', endDrag);
    view.addEventListener('pointercancel', endDrag);
    view.addEventListener('wheel', (event) => {
      event.preventDefault();
      const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
      wheel.dragging = false;
      wheel.vel += (delta / WHEEL.slotPx) * 18;
      const max = 28;
      if (wheel.vel > max) wheel.vel = max;
      if (wheel.vel < -max) wheel.vel = -max;
      wheel.lastT = performance.now();
      kickWheelLoop();
    }, { passive: false });
  }

  function makeWheel(kind, values, view) {
    return {
      kind,
      values,
      view,
      scene: view.querySelector('.hs-wheel-scene'),
      index: 0,
      vel: 0,
      dragging: false,
      lastT: 0,
      startY: 0,
      startIndex: 0,
      moved: 0,
    };
  }

  function jumpWheelsFromDraft() {
    if (!calDraft || wheels.length !== 2) return;
    const hour = Number(calDraft.hour);
    const minute = snapMinute(calDraft.minute);
    calDraft.minute = pad(minute);
    wheels[0].index = Number.isFinite(hour) ? hour : 0;
    wheels[0].vel = 0;
    wheels[1].index = minute / 5;
    wheels[1].vel = 0;
    wheels.forEach((wheel) => paintWheel(wheel));
    syncDraftFromWheels();
  }

  function ensureCal() {
    if (calEl) return calEl;
    calEl = document.createElement('div');
    calEl.id = 'history-cal';
    calEl.className = 'hs-cal';
    calEl.hidden = true;
    calEl.innerHTML = `
      <div class="hs-cal-body">
        <div class="hs-cal-main">
          <div class="hs-cal-nav">
            <button type="button" class="hs-cal-nav-btn" data-cal-prev aria-label="上一月">‹</button>
            <div class="hs-cal-title" data-cal-title></div>
            <button type="button" class="hs-cal-nav-btn" data-cal-next aria-label="下一月">›</button>
          </div>
          <div class="hs-cal-week">${['日', '一', '二', '三', '四', '五', '六'].map((name) => `<span>${name}</span>`).join('')}</div>
          <div class="hs-cal-days" data-cal-days></div>
        </div>
        <div class="hs-cal-time">
          <div class="hs-wheel">
            <span class="hs-wheel-name">时</span>
            <div class="hs-wheel-view" data-wheel="hour">
              <div class="hs-wheel-center"></div>
              <div class="hs-wheel-scene"></div>
            </div>
          </div>
          <div class="hs-wheel">
            <span class="hs-wheel-name">分</span>
            <div class="hs-wheel-view" data-wheel="minute">
              <div class="hs-wheel-center"></div>
              <div class="hs-wheel-scene"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="hs-cal-actions">
        <button type="button" class="hs-cal-cancel" data-cal-cancel>取消</button>
        <button type="button" class="hs-cal-ok" data-cal-ok>确认</button>
      </div>
    `;
    document.body.appendChild(calEl);
    wheels = [
      makeWheel('hour', WHEEL_HOURS, calEl.querySelector('[data-wheel="hour"]')),
      makeWheel('minute', WHEEL_MINUTES, calEl.querySelector('[data-wheel="minute"]')),
    ];
    wheels.forEach(bindWheel);
    calEl.addEventListener('click', (event) => {
      event.stopPropagation();
      if (event.target.closest('[data-cal-prev]')) {
        calView = shiftMonth(calView.year, calView.month, -1);
        renderCal();
        return;
      }
      if (event.target.closest('[data-cal-next]')) {
        calView = shiftMonth(calView.year, calView.month, 1);
        renderCal();
        return;
      }
      const dayBtn = event.target.closest('[data-cal-day]');
      if (dayBtn) {
        calDraft.year = dayBtn.getAttribute('data-year');
        calDraft.month = pad(Number(dayBtn.getAttribute('data-month')));
        calDraft.day = pad(Number(dayBtn.getAttribute('data-cal-day')));
        markSelectedDay();
        return;
      }
      if (event.target.closest('[data-cal-ok]')) commitCal();
      if (event.target.closest('[data-cal-cancel]')) closeCal();
    });
    return calEl;
  }

  function renderCal() {
    const box = ensureCal();
    if (!calDraft) return;
    const title = box.querySelector('[data-cal-title]');
    if (title) title.textContent = `${calView.year}年${pad(calView.month)}月`;
    const days = box.querySelector('[data-cal-days]');
    if (!days) return;
    const first = new Date(calView.year, calView.month - 1, 1);
    const startPad = first.getDay();
    const lastDate = new Date(calView.year, calView.month, 0).getDate();
    const selected = Number(calDraft.year) === calView.year && Number(calDraft.month) === calView.month
      ? Number(calDraft.day) : 0;
    let html = '';
    for (let i = 0; i < startPad; i += 1) html += '<span class="hs-cal-empty"></span>';
    for (let day = 1; day <= lastDate; day += 1) {
      const on = day === selected ? ' is-on' : '';
      html += `<button type="button" class="hs-cal-day${on}" data-cal-day="${day}" data-year="${calView.year}" data-month="${calView.month}">${day}</button>`;
    }
    days.innerHTML = html;
  }

  function markSelectedDay() {
    if (!calEl || !calDraft) return;
    const year = Number(calDraft.year);
    const month = Number(calDraft.month);
    const day = Number(calDraft.day);
    calEl.querySelectorAll('[data-cal-day]').forEach((btn) => {
      const on = Number(btn.getAttribute('data-year')) === year
        && Number(btn.getAttribute('data-month')) === month
        && Number(btn.getAttribute('data-cal-day')) === day;
      btn.classList.toggle('is-on', on);
    });
  }

  function syncWheelMetrics() {
    const view = wheels[0] && wheels[0].view;
    if (!view) return;
    const h = view.clientHeight;
    if (h < 40) return;
    WHEEL.slotPx = (h / 2 - 8) / 3;
    wheels.forEach(paintWheel);
  }

  function placeCal(anchor) {
    const box = ensureCal();
    box.hidden = false;
    const rect = anchor.getBoundingClientRect();
    const width = box.offsetWidth || 260;
    const height = box.offsetHeight || 320;
    let left = rect.left;
    let top = rect.bottom + 4;
    if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8);
    if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 4);
    box.style.left = `${Math.round(left)}px`;
    box.style.top = `${Math.round(top)}px`;
    syncWheelMetrics();
  }

  function closeCal() {
    wheels.forEach((wheel) => {
      wheel.dragging = false;
      wheel.vel = 0;
    });
    stopWheelLoop();
    calWhich = '';
    calDraft = null;
    if (calEl) calEl.hidden = true;
    document.querySelectorAll('.hs-dt-field.is-open').forEach((el) => el.classList.remove('is-open'));
  }

  function openCal(which) {
    if (preset() !== 'custom') return;
    const field = document.getElementById(which === 'end' ? 'history-end' : 'history-start');
    if (!field || field.disabled) return;
    if (calWhich === which) {
      closeCal();
      return;
    }
    const ms = which === 'end' ? customEndMs : customStartMs;
    const parts = ms != null ? timestampParts(ms, displayUtc()) : timestampParts(Date.now(), displayUtc());
    calWhich = which;
    calDraft = cloneParts(parts);
    calView = { year: Number(calDraft.year), month: Number(calDraft.month) };
    document.querySelectorAll('.hs-dt-field.is-open').forEach((el) => el.classList.remove('is-open'));
    field.classList.add('is-open');
    renderCal();
    jumpWheelsFromDraft();
    placeCal(field);
  }

  function commitCal() {
    if (calDraft) {
      syncDraftFromWheels();
      const ms = partsToMs(calDraft);
      if (ms != null) {
        if (calWhich === 'end') customEndMs = ms;
        else customStartMs = ms;
        writeCustomInputs();
      }
    }
    closeCal();
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

  function syncCustomEnabled() {
    const on = preset() === 'custom';
    const box = document.getElementById('history-custom-range');
    const start = document.getElementById('history-start');
    const end = document.getElementById('history-end');
    if (box) box.classList.toggle('is-disabled', !on);
    if (start) start.disabled = !on;
    if (end) end.disabled = !on;
    if (!on) closeCal();
  }

  async function fillCustomDefaults() {
    if (customStartMs != null && customEndMs != null) {
      writeCustomInputs();
      return;
    }
    try {
      const res = await fetch(apiUrl('history-stats/range/?preset=day'), { headers: headers() });
      const data = await res.json();
      if (!data.success) return;
      if (customStartMs == null) customStartMs = data.start_ms;
      if (customEndMs == null) customEndMs = data.end_ms;
      writeCustomInputs();
    } catch (err) { /* 用户稍后手填 */ }
  }

  function applyElementOptions(names) {
    const list = [];
    (names || []).forEach((name) => {
      const text = String(name || '').trim();
      if (!text) return;
      if (text === '气温') {
        list.push('高温', '低温');
        return;
      }
      list.push(text);
    });
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

  function visibleTypes(row) {
    return (row.types || []).filter((name) => statusSelected.has(name));
  }

  function visibleBadges(row) {
    return rowBadges(row).filter((badge) => badge && elementSelected.has(badge.text));
  }

  function visiblePlain(row) {
    const parts = row.plain_parts || [];
    if (parts.length) {
      return parts
        .filter((part) => (part.labels || []).some((name) => elementSelected.has(name)))
        .map((part) => part.text)
        .filter(Boolean)
        .join('；');
    }
    return row.plain || '';
  }

  function rowMatches(row) {
    return visibleTypes(row).length > 0 && visibleBadges(row).length > 0;
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

  const STATUS_HELP = [
    { name: '落地', text: '查询时段内有实际到达（ATA）的机场；抓取其 ATA 前后各「已完成航班实况抓取范围」（可配置）小时的天气。' },
    { name: '起飞', text: '查询时段内有实际起飞（ATD）的机场；抓取其 ATD 前后各「已完成航班实况抓取范围」（可配置）小时的天气。' },
    { name: '飞行中', text: '查询截止时飞机已起飞、尚未落地的航班，抓取目的地机场过去「未落地/未起飞航班实况抓取范围」（可配置）小时至截止时间的天气。' },
    { name: '即将起飞', text: '查询截止时尚未起飞，且计划时刻在截止时刻后「未落地/未起飞航班实况抓取范围」（可配置）内，或计划时刻已过仍未起飞，起飞机场在该范围至截止时刻前「未落地/未起飞航班实况抓取范围」（可配置）小时后的天气。' },
    { name: '停场', text: '查询时段内该机场停场记录与实况重叠的天气；不按落地/起飞小时范围，由停场时段决定。只统计 O3 地面占用，天气要素以回顾设置中勾选的停场要素为准。' },
  ];

  function statusHelpHtml() {
    const items = STATUS_HELP.map((item) => (
      `<div class="hs-status-tip-item"><div class="hs-status-tip-name">${esc(item.name)}</div><div class="hs-status-tip-body">${esc(item.text)}</div></div>`
    )).join('');
    return `<span class="hs-status-help-wrap"><button type="button" class="help-icon-btn hs-status-help" aria-label="航班或飞机状态说明">?</button><div class="hs-status-tip">${items}</div></span>`;
  }

  function filterHeadHtml(title, kind, options, selected, extra) {
    return `<div class="hs-th-stack"><div class="hs-th-title">${esc(title)}${extra || ''}</div><div class="hs-th-tools">${filterMenu(kind, options, selected)}</div></div>`;
  }

  function bindStatusHelp(wrap) {
    const host = wrap.querySelector('.hs-status-help-wrap');
    if (!host) return;
    const tip = host.querySelector('.hs-status-tip');
    const btn = host.querySelector('.hs-status-help');
    if (!tip || !btn) return;
    const place = () => {
      const box = btn.getBoundingClientRect();
      tip.style.left = `${Math.round(box.left + box.width / 2)}px`;
      tip.style.top = `${Math.round(box.bottom + 6)}px`;
    };
    host.addEventListener('mouseenter', place);
    host.addEventListener('mousemove', place);
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
  }

  function badgeHtml(badge) {
    if (!badge || !badge.text) return '';
    const level = badge.level === 'R' || badge.level === 'Y' || badge.level === 'G' ? badge.level : 'N';
    return `<span class="warning-badge warning-${level}">${esc(badge.text)}</span>`;
  }

  function popupBadgeHtml(row) {
    const html = visibleBadges(row).map(badgeHtml).join('');
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
    const statusHead = filterHeadHtml('航班或飞机状态', 'status', STATUS_OPTIONS, statusSelected, statusHelpHtml());
    const elementHead = filterHeadHtml('天气要素类型', 'element', elementOptions, elementSelected);
    const periodHead = timeLevelHtml();
    const airportHead = airportHeadHtml();
    const pickHead = pickHeadHtml();
    if (!rows.length) {
      wrap.innerHTML = `<table class="hs-table"><thead><tr><th class="hs-th-airport">${airportHead}</th><th class="hs-th-time">${periodHead}</th><th class="hs-th-filter hs-th-status">${statusHead}</th><th class="hs-th-filter">${elementHead}</th><th>天气</th><th>原文</th><th class="hs-th-pick">${pickHead}</th><th>复制</th></tr></thead></table><div class="hs-empty">没有符合筛选条件的天气</div>`;
      bindStatusHelp(wrap);
      return;
    }
    const groups = [];
    rows.forEach((row) => {
      const last = groups[groups.length - 1];
      if (last && last.airport === row.airport) last.rows.push(row);
      else groups.push({ airport: row.airport, rows: [row] });
    });
    const COLS = 6;
    let html = `<table class="hs-table"><thead><tr><th class="hs-th-airport">${airportHead}</th><th class="hs-th-time">${periodHead}</th><th class="hs-th-filter hs-th-status">${statusHead}</th><th class="hs-th-filter">${elementHead}</th><th>天气</th><th>原文</th><th class="hs-th-pick">${pickHead}</th><th>复制</th></tr></thead><tbody>`;
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
        html += `<td class="hs-types hs-status-cell">${visibleTypes(row).map(typeHtml).join('')}</td>`;
        html += `<td class="hs-badges">${popupBadgeHtml(row)}</td>`;
        html += `<td class="hs-plain">${esc(visiblePlain(row) || '')}</td>`;
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
    bindStatusHelp(wrap);
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
    const weather = visiblePlain(row) || '无满足告警条件的天气';
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
    const kind = preset();
    if (kind === 'custom' && (customStartMs == null || customEndMs == null)) {
      setStatus('请先确认自定义时间', true);
      return;
    }
    const seq = ++querySeq;
    const btn = document.getElementById('history-query');
    if (btn) btn.disabled = true;
    setStatus('正在查询…');
    try {
      const body = { preset: kind };
      if (kind === 'custom') {
        body.start_ms = customStartMs;
        body.end_ms = customEndMs;
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
        syncCustomEnabled();
        if (preset() === 'custom') await fillCustomDefaults();
      });
    });
    const customBox = document.getElementById('history-custom-range');
    if (customBox) {
      customBox.addEventListener('click', (event) => {
        const field = event.target.closest('[data-hs-dt]');
        if (!field || field.disabled) return;
        event.stopPropagation();
        openCal(field.getAttribute('data-hs-dt'));
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
      const path = typeof event.composedPath === 'function' ? event.composedPath() : [event.target];
      const inCal = path.some((node) => node && (node.id === 'history-cal' || node === calEl));
      const inField = path.some((node) => node && node.getAttribute && node.hasAttribute('data-hs-dt'));
      if (calWhich && !inCal && !inField) closeCal();
      if (!openFilter) return;
      if (event.target.closest('.hs-th-filter')) return;
      openFilter = '';
      if (lastRows.length) paintTable();
    });
    const tz = document.getElementById('timezone-toggle-input');
    if (tz) tz.addEventListener('change', () => {
      closeCal();
      syncPresetLabels();
      writeCustomInputs();
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
    syncPresetLabels();
    syncCustomEnabled();
    writeCustomInputs();
    syncPanelHeight();
    await loadElementOptions();
    if (lastRows.length) paintTable();
    else showIdle();
    await fillCustomDefaults();
  }

  function stopHistoryView() {
    querySeq += 1;
    closeCal();
  }

  window.startHistoryView = startHistoryView;
  window.stopHistoryView = stopHistoryView;
  window.refreshHistoryTimezone = function () {
    closeCal();
    syncPresetLabels();
    writeCustomInputs();
  };
})();
