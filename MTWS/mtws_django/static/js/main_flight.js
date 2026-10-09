// ============================================================
// main_flight.js — 航班渲染相关函数
// 依赖 main.js 中的全局变量和工具函数：
//   currentTimeRange, currentCarriers, airportData, filters,
//   getAlertColor(), getSelectedAlertMargin(), getCurrentTime()
// ============================================================

window.flightMarksPastExpanded = window.flightMarksPastExpanded || false;

function isFlightMarksMode() {
    return true;
}

function setFlightMarksMode(enabled) {
    try {
        const url = new URL(window.location.href);
        if (enabled) url.searchParams.set('flight', 'marks');
        else url.searchParams.delete('flight');
        window.history.replaceState(null, '', url.toString());
    } catch (e) { /* ignore */ }
    document.body.classList.toggle('flight-marks-mode', !!enabled);
    if (!enabled) {
        window.flightMarksPastExpanded = false;
        document.body.classList.remove('flight-marks-past-open');
        hideFlightMarksLegend();
    } else {
        ensureFlightMarksLegend();
    }
}

function syncFlightMarksBodyClass() {
    const on = isFlightMarksMode();
    document.body.classList.toggle('flight-marks-mode', on);
    document.body.classList.toggle('flight-marks-past-open', on && !!window.flightMarksPastExpanded);
    document.body.classList.toggle('flight-marks-layout-center', on && isFlightMarksLayoutCenter());
    if (on) {
        syncFlightMarksCssVars();
        ensureFlightMarksLegend();
    } else {
        removeFlightPastHandleFloat();
        hideFlightMarksLegend();
    }
}

/** 分钟精度的当前时刻 */
function getMarksNowMs() {
    const t = (typeof getCurrentTime === 'function') ? getCurrentTime() : new Date();
    const d = new Date(t.getTime());
    d.setSeconds(0, 0);
    return d.getTime();
}

window.detailMarksPastExpanded = true;
window.searchMarksPastByCode = window.searchMarksPastByCode || Object.create(null);

function marksScopeFromElement(el) {
    if (!el || !el.closest) return 'home';
    const block = el.closest('.airport-search-block');
    if (block && block.dataset.code) {
        return 'search:' + String(block.dataset.code).toUpperCase();
    }
    if (el.closest('#airport-detail-modal')) return 'detail';
    return 'home';
}

function getMarksPastExpanded(scope) {
    const s = scope || window._marksRenderScope || 'home';
    if (s === 'detail') return window.detailMarksPastExpanded !== false;
    if (typeof s === 'string' && s.indexOf('search:') === 0) {
        const v = window.searchMarksPastByCode[s.slice(7)];
        return v !== false;
    }
    return !!window.flightMarksPastExpanded;
}

function syncMarksPastOpenClass(scope) {
    const on = getMarksPastExpanded(scope);
    if (!scope || scope === 'home') {
        document.body.classList.toggle('flight-marks-past-open', isFlightMarksMode() && on);
        return;
    }
    if (scope === 'detail') {
        const modal = document.getElementById('airport-detail-modal');
        if (modal) modal.classList.toggle('flight-marks-past-open', on);
        return;
    }
    if (scope.indexOf('search:') === 0) {
        const code = scope.slice(7);
        const block = document.querySelector(`.airport-search-block[data-code="${code}"]`);
        if (block) block.classList.toggle('flight-marks-past-open', on);
    }
}

function setMarksPastExpanded(scope, value) {
    if (scope === 'detail') {
        window.detailMarksPastExpanded = !!value;
    } else if (scope && scope.indexOf('search:') === 0) {
        window.searchMarksPastByCode[scope.slice(7)] = !!value;
    } else {
        window.flightMarksPastExpanded = !!value;
    }
    syncMarksPastOpenClass(scope);
}

function withMarksRenderScope(scope, fn) {
    const prev = window._marksRenderScope;
    window._marksRenderScope = scope || 'home';
    try {
        return fn();
    } finally {
        window._marksRenderScope = prev;
    }
}

function withMarksIncludePast(enabled, fn) {
    return withMarksRenderScope(enabled ? 'detail' : 'home', fn);
}

function marksWindowIncludesPast() {
    return getMarksPastExpanded(window._marksRenderScope || 'home');
}

/** marks 可见窗口起点（折叠=now，展开=now-2h） */
function getMarksWindowStartMs() {
    const now = getMarksNowMs();
    return marksWindowIncludesPast() ? (now - 2 * 3600000) : now;
}

function getMarksWindowDurationMs() {
    const hours = (typeof currentTimeRange !== 'undefined') ? currentTimeRange : 36;
    return hours * 3600000;
}

function marksMsToLeftPercent(ms) {
    const start = getMarksWindowStartMs();
    const dur = getMarksWindowDurationMs();
    if (!dur) return 0;
    return ((ms - start) / dur) * 100;
}

function marksEventWarning(event) {
    const w = event && event.warning;
    const m = (typeof getSelectedAlertMargin === 'function') ? getSelectedAlertMargin() : 2;
    if (Array.isArray(w)) {
        const lv = w[m];
        return (lv && lv !== '') ? lv : 'N';
    }
    return w || 'N';
}

const MARKS_LAYOUT_KEY = 'mtws_marks_layout';

function marksIsDeparture(event) {
    const kind = event && event.kind;
    return kind === 'dep' || kind === 'off' || kind === 'odp' || kind === 'dst';
}

function getFlightMarksLayout() {
    if (window.flightMarksLayout === 'center' || window.flightMarksLayout === 'split') {
        return window.flightMarksLayout;
    }
    let saved = 'split';
    try {
        if (localStorage.getItem(MARKS_LAYOUT_KEY) === 'center') saved = 'center';
    } catch (e) { /* ignore */ }
    window.flightMarksLayout = saved;
    return saved;
}

function isFlightMarksLayoutCenter() {
    return getFlightMarksLayout() === 'center';
}

/** 三角：起飞朝上、着陆朝下；地面白、空中黑；oar/oen/odp 超时闪 */
function marksTickClass(event) {
    const kind = event && event.kind;
    const dir = marksIsDeparture(event) ? ' flight-mark-tick-up' : ' flight-mark-tick-down';
    if (kind === 'oar' || kind === 'oen' || kind === 'odp') return dir + ' flight-mark-tick-overdue';
    if (kind === 'enr' || kind === 'off') return dir + ' flight-mark-tick-air';
    return dir;
}

function marksWarningColor(level) {
    const lv = level || 'N';
    if (typeof getAlertColor === 'function') return getAlertColor(lv);
    return 'rgba(149, 165, 166, 0.8)';
}

function marksWarningRank(level) {
    return ({ R: 4, Y: 3, G: 2, N: 1 }[level] || 1);
}

function _marksEscHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function formatMarksTooltipTime(v) {
    if (v == null || v === '') return '--';
    const n = Number(v);
    if (!Number.isFinite(n)) return '--';
    try {
        const d = new Date(n);
        const utc = window.displayTimezone === 'UTC';
        const day = utc ? d.getUTCDate() : d.getDate();
        const hh = String(utc ? d.getUTCHours() : d.getHours()).padStart(2, '0');
        const mm = String(utc ? d.getUTCMinutes() : d.getMinutes()).padStart(2, '0');
        return `${day}日 ${hh}:${mm}`;
    } catch (e) {
        return '--';
    }
}

function marksTimeMs(v) {
    if (v == null || v === '') return null;
    const n = Number(v);
    if (!Number.isFinite(n) || n <= 0) return null;
    return n;
}

/** 起飞航班看目的地到达（ata 最优先）；着陆航班看上一站起飞（atd 最优先） */
function marksPickLink(ev, isDep) {
    const o = (ev && ev.other) || {};
    const fields = isDep
        ? [['ata', '已落地', true], ['eta', '预达', false], ['sta', '计达', false], ['pta', '计达', false]]
        : [['atd', '已起飞', true], ['etd', '预起', false], ['std', '计起', false], ['ptd', '计起', false]];
    for (let i = 0; i < fields.length; i++) {
        const ms = marksTimeMs(o[fields[i][0]]);
        if (ms != null) {
            return {
                ms: ms,
                label: fields[i][1],
                done: !!fields[i][2],
                code: isDep ? (o.arrivalAirport || '') : (o.departureAirport || ''),
            };
        }
    }
    const fallback = marksTimeMs(ev && ev.link);
    if (fallback == null) return null;
    return {
        ms: fallback,
        label: '',
        done: false,
        code: isDep ? (o.arrivalAirport || '') : (o.departureAirport || ''),
    };
}

/** 方块所在的 at：起飞看本场起飞，着陆看本场落地 */
function marksPickAt(ev, isDep) {
    const o = (ev && ev.other) || {};
    const at = marksTimeMs(ev && ev.at);
    const fields = isDep
        ? [['atd', '已起飞', true], ['etd', '预起', false], ['std', '计起', false], ['ptd', '计起', false]]
        : [['ata', '已落地', true], ['eta', '预达', false], ['sta', '计达', false], ['pta', '计达', false]];
    if (!isDep && ev && ev.kind === 'lnd') {
        const ms = marksTimeMs(o.ata) || at;
        return ms ? { ms: ms, label: '已落地', done: true } : null;
    }
    if (at != null) {
        for (let i = 0; i < fields.length; i++) {
            if (!isDep && fields[i][0] === 'ata') continue;
            if (marksTimeMs(o[fields[i][0]]) === at) {
                return { ms: at, label: fields[i][1], done: !!fields[i][2] };
            }
        }
        return { ms: at, label: '', done: false };
    }
    for (let i = 0; i < fields.length; i++) {
        if (!isDep && fields[i][0] === 'ata') continue;
        const ms = marksTimeMs(o[fields[i][0]]);
        if (ms != null) return { ms: ms, label: fields[i][1], done: !!fields[i][2] };
    }
    return null;
}

function marksTimeTag(label, done) {
    if (!label) return '';
    const text = `（${_marksEscHtml(label)}）`;
    return done ? `<span class="fmt-tag-done">${text}</span>` : text;
}

function marksTooltipPayload(ev, track) {
    const o = ev.other || {};
    const kind = ev && ev.kind;
    const isDep = track === 'dep'
        || kind === 'dep' || kind === 'off' || kind === 'odp' || kind === 'dst';
    const link = marksPickLink(ev, isDep);
    const atInfo = marksPickAt(ev, isDep);
    return {
        role: isDep ? 'dep' : 'arr',
        flightNo: o.flightNo || '',
        dep: o.departureAirport || '',
        arr: o.arrivalAirport || '',
        warning: marksEventWarning(ev),
        linkMs: link ? link.ms : null,
        linkLabel: link ? link.label : '',
        linkDone: !!(link && link.done),
        linkCode: link ? link.code : '',
        atMs: atInfo ? atInfo.ms : null,
        atLabel: atInfo ? atInfo.label : '',
        atDone: !!(atInfo && atInfo.done),
    };
}

function _marksCssColor(c) {
    const s = String(c || '');
    return /^[#a-zA-Z0-9().,%\s]+$/.test(s) ? s : '#fff';
}

function formatMarksTooltipHtml(payload) {
    const items = Array.isArray(payload) ? payload : [payload];
    return items.map((p) => {
        const isDep = p.role === 'dep';
        const role = isDep ? '起飞航班' : '着陆航班';
        const no = _marksEscHtml(p.flightNo || '--');
        const warned = p.warning && p.warning !== 'N';
        const roleStyle = warned
            ? ` style="color:${_marksCssColor((typeof getAlertColor === 'function') ? getAlertColor(p.warning) : '#fff')}"`
            : '';
        const code = _marksEscHtml(p.linkCode || '--');
        const when = _marksEscHtml(formatMarksTooltipTime(p.linkMs));
        const atWhen = _marksEscHtml(formatMarksTooltipTime(p.atMs));
        const detailName = isDep ? '着陆详情' : '起飞详情';
        return `<div class="fmt-card">
            <div class="fmt-row1">
                <span class="fmt-role"${roleStyle}>${role}</span>
                <span class="fmt-no">${no}</span>
                <span class="fmt-at">${atWhen}${marksTimeTag(p.atLabel, p.atDone)}</span>
            </div>
            <div class="fmt-row-detail">${detailName}：${code}|${when}${marksTimeTag(p.linkLabel, p.linkDone)}</div>
        </div>`;
    }).join('');
}

function ensureFlightMarksTooltipEl() {
    let el = document.getElementById('flight-marks-tooltip');
    if (!el) {
        el = document.createElement('div');
        el.id = 'flight-marks-tooltip';
        el.className = 'flight-marks-tooltip';
        el.setAttribute('aria-hidden', 'true');
        document.body.appendChild(el);
    }
    return el;
}

function hideFlightMarksTooltip() {
    const el = document.getElementById('flight-marks-tooltip');
    if (!el) return;
    el.style.display = 'none';
    el.innerHTML = '';
    el._srcMark = null;
    el._fmtOrder = null;
}

function positionFlightMarksTooltip(el, markEl) {
    const row = (markEl && markEl.closest && (markEl.closest('.flight-row') || markEl.closest('.forecast-timeline'))) || markEl;
    const rowRect = row.getBoundingClientRect();
    const markRect = markEl.getBoundingClientRect();
    const modal = markEl.closest && markEl.closest('#airport-detail-modal, #airport-search-modal');
    let limitTop = 4;
    if (modal) {
        const head = modal.querySelector('.airport-detail-header-main');
        const block = markEl.closest('.airport-search-block');
        const title = block
            ? block.querySelector('.title-row, .title-timeline')
            : modal.querySelector('.airport-detail-title-row');
        const headBottom = head ? head.getBoundingClientRect().bottom : modal.getBoundingClientRect().top;
        const titleBottom = title ? title.getBoundingClientRect().bottom : headBottom;
        limitTop = Math.max(4, headBottom, titleBottom) + 4;
    } else {
        const chrome = document.querySelector('.page-chrome');
        const fn = document.querySelector('.function-section');
        limitTop = Math.max(
            4,
            chrome ? chrome.getBoundingClientRect().bottom : 0,
            fn ? fn.getBoundingClientRect().bottom : 0
        ) + 4;
    }
    const limitBottom = window.innerHeight - 4;
    const gap = 4;
    const above = (rowRect.top + rowRect.height / 2) > ((limitTop + limitBottom) / 2);
    const avail = Math.max(36, above
        ? (rowRect.top - gap - limitTop)
        : (limitBottom - (rowRect.bottom + gap)));

    const cards = (el._fmtOrder && el._fmtOrder.length)
        ? el._fmtOrder
        : [...el.querySelectorAll('.fmt-card')];
    if (!cards.length) return;
    el.style.display = 'block';
    el.style.visibility = 'hidden';
    el.style.left = '0px';
    el.style.top = '0px';
    el.classList.remove('fmt-above');
    cards.forEach((card) => el.appendChild(card));
    el.querySelectorAll('.fmt-cols').forEach((node) => node.remove());
    const cardGap = 8;
    const heights = cards.map((card) => card.offsetHeight);
    const cols = [];
    let group = [];
    let used = 0;
    cards.forEach((card, i) => {
        const h = heights[i] || 36;
        const next = group.length ? used + cardGap + h : h;
        if (group.length && next > avail) {
            cols.push(group);
            group = [card];
            used = h;
        } else {
            group.push(card);
            used = next;
        }
    });
    if (group.length) cols.push(group);

    const colsEl = document.createElement('div');
    colsEl.className = 'fmt-cols';
    cols.forEach((list) => {
        const colEl = document.createElement('div');
        colEl.className = 'fmt-col';
        const ordered = above ? list.slice().reverse() : list;
        ordered.forEach((card) => colEl.appendChild(card));
        colsEl.appendChild(colEl);
    });
    el.innerHTML = '';
    el.appendChild(colsEl);
    el.classList.toggle('fmt-above', above);

    const tipW = el.offsetWidth;
    const tipH = el.offsetHeight;
    let left = markRect.left;
    if (left + tipW > window.innerWidth - 8) left = window.innerWidth - 8 - tipW;
    if (left < 8) left = 8;
    let top = above ? (rowRect.top - gap - tipH) : (rowRect.bottom + gap);
    if (top < limitTop) top = limitTop;
    if (top + tipH > limitBottom) top = Math.max(limitTop, limitBottom - tipH);
    el.style.left = `${Math.round(left)}px`;
    el.style.top = `${Math.round(top)}px`;
    el.style.visibility = 'visible';
}

function showFlightMarksTooltip(markEl, clientX, clientY) {
    let payload;
    try {
        payload = JSON.parse(markEl.getAttribute('data-marks-tip') || '[]');
    } catch (e) {
        return;
    }
    const el = ensureFlightMarksTooltipEl();
    if (el._srcMark !== markEl) {
        el.innerHTML = formatMarksTooltipHtml(payload);
        el._srcMark = markEl;
        el._fmtOrder = [...el.querySelectorAll('.fmt-card')];
    }
    el.style.display = 'block';
    positionFlightMarksTooltip(el, markEl);
}

function bindFlightMarksTooltip() {
    if (window._flightMarksTooltipBound) return;
    window._flightMarksTooltipBound = true;
    document.addEventListener('mouseover', (e) => {
        const mark = e.target && e.target.closest && e.target.closest('.flight-mark');
        if (!mark || !mark.getAttribute('data-marks-tip')) return;
        showFlightMarksTooltip(mark, e.clientX, e.clientY);
    });
    document.addEventListener('mousemove', (e) => {
        const mark = e.target && e.target.closest && e.target.closest('.flight-mark');
        const tip = document.getElementById('flight-marks-tooltip');
        if (!mark || !tip || tip.style.display !== 'block') return;
        showFlightMarksTooltip(mark, e.clientX, e.clientY);
    });
    document.addEventListener('mouseout', (e) => {
        const mark = e.target && e.target.closest && e.target.closest('.flight-mark');
        if (!mark) return;
        const next = e.relatedTarget;
        if (next && mark.contains(next)) return;
        hideFlightMarksTooltip();
    });
}

function hideFlightMarkLinks() {
    document.querySelectorAll('.flight-mark-links').forEach((el) => el.remove());
    document.querySelectorAll('.flight-mark-hold-hidden').forEach((el) => {
        el.classList.remove('flight-mark-hold-hidden');
    });
}

function concealSiblingFlightMarks(mark) {
    const row = mark && mark.closest && mark.closest('.airport-row');
    if (!row) return;
    row.querySelectorAll('.flight-mark').forEach((el) => {
        if (el !== mark) el.classList.add('flight-mark-hold-hidden');
    });
}

function _appendMarkLinkBar(track, color, fromPct, toPct, dotPcts) {
    const left = Math.min(fromPct, toPct);
    const right = Math.max(fromPct, toPct);
    const width = right - left;
    if (!(width > 0.05)) return;
    const wrap = document.createElement('div');
    wrap.className = 'flight-mark-links';
    const bar = document.createElement('div');
    bar.className = 'flight-mark-linkbar';
    bar.style.left = left + '%';
    bar.style.width = width + '%';
    bar.style.background = color;
    (dotPcts || []).forEach((p) => {
        if (p < 0 || p > 100 || p < left - 0.05 || p > right + 0.05) return;
        const dot = document.createElement('span');
        dot.className = 'flight-mark-linkdot';
        dot.style.left = (((p - left) / width) * 100) + '%';
        dot.style.background = color;
        bar.appendChild(dot);
    });
    wrap.appendChild(bar);
    track.appendChild(wrap);
}

function showFlightMarkLinks(mark) {
    hideFlightMarkLinks();
    const track = mark && mark.parentElement;
    if (!track) return;
    concealSiblingFlightMarks(mark);
    let payload;
    try {
        payload = JSON.parse(mark.getAttribute('data-marks-tip') || '[]');
    } catch (e) {
        return;
    }
    const items = Array.isArray(payload) ? payload : [payload];
    const boxLeft = parseFloat(mark.style.left);
    const boxWidth = parseFloat(mark.style.width);
    if (!Number.isFinite(boxLeft) || !Number.isFinite(boxWidth)) return;
    const boxRight = boxLeft + boxWidth;
    const color = (getComputedStyle(mark).backgroundColor) || '#95a5a6';
    const depPcts = [];
    const arrPcts = [];
    items.forEach((p) => {
        const ms = marksTimeMs(p && p.linkMs);
        if (ms == null) return;
        const pct = marksMsToLeftPercent(ms);
        if (!Number.isFinite(pct)) return;
        if (p.role === 'dep') depPcts.push(pct);
        else arrPcts.push(pct);
    });
    if (depPcts.length) {
        const farthest = Math.max.apply(null, depPcts);
        const end = Math.min(100, farthest);
        if (end > boxRight) {
            _appendMarkLinkBar(
                track,
                color,
                boxRight,
                end,
                depPcts.filter((p) => p > boxRight && p >= 0 && p <= 100)
            );
        }
    }
    if (arrPcts.length) {
        const farthest = Math.min.apply(null, arrPcts);
        const end = Math.max(0, farthest);
        if (boxLeft > end) {
            _appendMarkLinkBar(
                track,
                color,
                end,
                boxLeft,
                arrPcts.filter((p) => p < boxLeft && p >= 0 && p <= 100)
            );
        }
    }
}

function bindFlightMarkLinkHold() {
    if (window._flightMarkLinkHoldBound) return;
    window._flightMarkLinkHoldBound = true;
    let timer = 0;
    let holding = null;
    const cancel = () => {
        if (timer) clearTimeout(timer);
        timer = 0;
        holding = null;
        hideFlightMarkLinks();
    };
    document.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        const mark = e.target && e.target.closest && e.target.closest('.flight-mark');
        if (!mark) return;
        if (timer) clearTimeout(timer);
        holding = mark;
        timer = setTimeout(() => {
            timer = 0;
            if (holding === mark && document.body.contains(mark)) showFlightMarkLinks(mark);
        }, 500);
    });
    document.addEventListener('mouseup', cancel);
    window.addEventListener('blur', cancel);
}

function clusterFlightMarks(items, timelineWidthPx) {
    if (!items.length) return [];
    const gapPx = 2;
    const sorted = items.slice().sort((a, b) => a.centerPx - b.centerPx);
    // 首轮用估宽
    sorted.forEach((it) => {
        it.halfPx = (it.estWidth || 22) / 2;
    });
    const clusters = [];
    let cur = [sorted[0]];
    for (let i = 1; i < sorted.length; i++) {
        const prev = cur[cur.length - 1];
        const next = sorted[i];
        const edgeGap = (next.centerPx - next.halfPx) - (prev.centerPx + prev.halfPx);
        if (edgeGap < gapPx) cur.push(next);
        else {
            clusters.push(cur);
            cur = [next];
        }
    }
    clusters.push(cur);
    return clusters.map((members) => {
        const leftPx = Math.min(...members.map((m) => m.centerPx - m.halfPx));
        const rightPx = Math.max(...members.map((m) => m.centerPx + m.halfPx));
        const warn = members.reduce((best, m) => {
            const lvl = marksEventWarning(m.event);
            return marksWarningRank(lvl) > marksWarningRank(best) ? lvl : best;
        }, 'N');
        return { members, leftPx, rightPx, warning: warn };
    });
}

function estimateMarkBoxWidth() {
    return 10;
}

function createMarksFlightTimeline(flightData, airportCode) {
    const events = Array.isArray(flightData.events) ? flightData.events : [];
    const winStart = getMarksWindowStartMs();
    const winEnd = winStart + getMarksWindowDurationMs();
    const selectedCarriers = new Set(sortCarrierCodes(currentCarriers));
    // 前端自裁：只画已选承运人，并丢弃窗口外
    const visible = events.filter((e) => {
        const code = String((e && e.carrier) || '').trim().toUpperCase();
        if (!selectedCarriers.has(code)) return false;
        const at = Number(e.at);
        return Number.isFinite(at) && at >= winStart && at <= winEnd;
    });

    // 折叠时也要求 at >= now（与 winStart 一致）；展开则含过去 2h
    // split：上行着陆、下行起飞。center：全部放进同一行并居中，方向只看三角。
    const centerLayout = isFlightMarksLayoutCenter();
    const upper = [];
    const lower = [];
    const merged = [];
    visible.forEach((e) => {
        const at = Number(e.at);
        const leftPct = marksMsToLeftPercent(at);
        if (leftPct < -1 || leftPct > 101) return;
        const isDep = marksIsDeparture(e);
        const isArr = e.kind === 'arr' || e.kind === 'enr' || e.kind === 'lnd' || e.kind === 'oar' || e.kind === 'oen';
        if (!isDep && !isArr) return;
        const item = { event: e, at, leftPct, centerPx: 0, estWidth: estimateMarkBoxWidth() };
        if (centerLayout) merged.push(item);
        else if (isDep) lower.push(item);
        else upper.push(item);
    });

    // 用假定时间轴宽度算像素（与格子同宽逻辑：渲染后由 CSS % 定位，聚簇用 1000px 基准再转 %）
    const axisPx = 1000;
    const prepare = (list) => list.map((it) => {
        it.centerPx = (it.leftPct / 100) * axisPx;
        it.estWidth = estimateMarkBoxWidth();
        it.halfPx = it.estWidth / 2;
        return it;
    });

    const renderTrack = (list, track) => {
        const prepared = prepare(list);
        const clusters = clusterFlightMarks(prepared, axisPx);
        return clusters.map((cl) => {
            const eventsIn = cl.members.map((m) => m.event);
            const minW = estimateMarkBoxWidth();
            const widthPx = Math.max(cl.rightPx - cl.leftPx, minW);
            let leftPct;
            let widthPct;
            if (cl.members.length === 1) {
                widthPct = (minW / axisPx) * 100;
                leftPct = cl.members[0].leftPct - widthPct / 2;
            } else {
                const boxW = Math.max(widthPx, minW);
                const center = (cl.leftPx + cl.rightPx) / 2;
                leftPct = ((center - boxW / 2) / axisPx) * 100;
                widthPct = (boxW / axisPx) * 100;
            }
            const color = marksWarningColor(cl.warning);
            const tipPayload = eventsIn.map((ev) => marksTooltipPayload(ev, track));
            const tipAttr = _marksEscHtml(JSON.stringify(tipPayload));
            const trackClass = track === 'dep'
                ? 'flight-mark-lower'
                : (track === 'center' ? 'flight-mark-center' : 'flight-mark-upper');
            // 簇内每个航班在对应时刻各画上下短线；单票则居中一根
            const boxLeftPx = (leftPct / 100) * axisPx;
            const boxWidthPx = Math.max((widthPct / 100) * axisPx, 1);
            const ticksHtml = cl.members.map((m) => {
                const rel = ((m.centerPx - boxLeftPx) / boxWidthPx) * 100;
                const left = Math.max(0, Math.min(100, rel));
                const tickClass = marksTickClass(m.event);
                return `<span class="flight-mark-tick${tickClass}" style="left:${left}%;"></span>`;
            }).join('');
            return `
                <div class="flight-mark ${trackClass}${cl.members.length > 1 ? ' flight-mark-cluster' : ''}"
                     style="left:${leftPct}%;width:${widthPct}%;--mark-bg:${color};background-color:${color};"
                     data-airport="${_marksEscHtml(airportCode || '')}"
                     data-marks-tip="${tipAttr}">
                    ${ticksHtml}
                </div>`;
        }).join('');
    };

    if (centerLayout) {
        return `
        <div class="flight-marks-layer">
            <div class="flight-marks-track flight-marks-track-center">${renderTrack(merged, 'center')}</div>
        </div>`;
    }
    return `
        <div class="flight-marks-layer">
            <div class="flight-marks-track flight-marks-track-upper">${renderTrack(upper, 'upper')}</div>
            <div class="flight-marks-track flight-marks-track-lower">${renderTrack(lower, 'dep')}</div>
        </div>`;
}

function sortCarrierCodes(codes) {
    const uniq = [];
    const seen = new Set();
    (codes || []).forEach((raw) => {
        const code = String(raw || '').trim().toUpperCase();
        if (!code || seen.has(code)) return;
        seen.add(code);
        uniq.push(code);
    });
    uniq.sort();
    const o3 = uniq.indexOf('O3');
    if (o3 > 0) {
        uniq.splice(o3, 1);
        uniq.unshift('O3');
    }
    return uniq;
}

function carrierLabel(codes) {
    const list = sortCarrierCodes(codes);
    if (!list.length) return '未选择';
    const shown = list.slice(0, 2);
    const extra = list.length - shown.length;
    return extra > 0 ? `${shown.join(' ')} +${extra}` : shown.join(' ');
}

// 更新承运人显示
function updateCarrierDisplay() {
    const carrierDisplay = document.getElementById('carrier-display');
    if (!carrierDisplay) return;
    const list = sortCarrierCodes(currentCarriers);
    carrierDisplay.textContent = carrierLabel(list);
    carrierDisplay.title = list.length ? list.join(' ') : '未选择承运人';
}

function loadCarrierData() {
    currentCarriers = sortCarrierCodes(window.carriers || []);
    window.carriers = currentCarriers;
    updateCarrierDisplay();
    bindCarrierPicker();
}

function bindCarrierPicker() {
    const picker = document.getElementById('carrier-picker');
    const button = document.getElementById('carrier-display');
    const menu = document.getElementById('carrier-menu');
    if (!picker || !button || !menu || picker.dataset.bound) return;
    picker.dataset.bound = '1';
    button.addEventListener('click', (event) => {
        event.stopPropagation();
        if (menu.hidden) openCarrierMenu();
        else closeCarrierMenu();
    });
    document.addEventListener('click', (event) => {
        if (!picker.contains(event.target)) closeCarrierMenu();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !event.target.classList.contains('carrier-add-input')) closeCarrierMenu();
    });
    const matrix = document.getElementById('carrier-matrix');
    if (matrix) matrix.addEventListener('click', onCarrierMatrixClick);
    const confirmBtn = document.getElementById('carrier-confirm');
    if (confirmBtn) {
      confirmBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        confirmCarrierSelection();
      });
    }
}

function closeCarrierMenu() {
    const menu = document.getElementById('carrier-menu');
    const button = document.getElementById('carrier-display');
    if (menu) menu.hidden = true;
    if (button) button.setAttribute('aria-expanded', 'false');
    window.__carrierMenuOpen = false;
}

let carrierFlightCodes = [];
let carrierSelectedCodes = [];
let carrierSavedCodes = [];
let carrierLoadSeq = 0;

function sameCarrierList(left, right) {
    const a = sortCarrierCodes(left);
    const b = sortCarrierCodes(right);
    return a.length === b.length && a.every((code, index) => code === b[index]);
}

function carrierCanEdit() {
    const id = window.__accessIdentity;
    return !id || !!id.is_local;
}

function refreshCarrierConfirm() {
    const btn = document.getElementById('carrier-confirm');
    if (!btn) return;
    const dirty = !sameCarrierList(carrierSelectedCodes, carrierSavedCodes);
    btn.disabled = !dirty || btn.dataset.busy === '1' || !carrierCanEdit();
    btn.textContent = btn.dataset.busy === '1' ? '正在确认…' : '确认';
}

function openCarrierMenu() {
    const menu = document.getElementById('carrier-menu');
    const button = document.getElementById('carrier-display');
    const matrix = document.getElementById('carrier-matrix');
    if (!menu || !matrix) return;
    menu.hidden = false;
    if (button) button.setAttribute('aria-expanded', 'true');
    window.__carrierMenuOpen = true;
    matrix.textContent = '加载中';
    const seq = ++carrierLoadSeq;
    const headers = typeof getRequestHeaders === 'function' ? getRequestHeaders() : {};
    fetch(`/${currentTimeMode}/api/flight-carriers/`, { headers })
        .then((res) => res.json())
        .then((data) => {
            if (seq !== carrierLoadSeq || !window.__carrierMenuOpen) return;
            if (!data.success) throw new Error(data.error || '读取承运人失败');
            carrierSavedCodes = sortCarrierCodes(data.selected || []);
            renderCarrierMatrix(data.flights || [], carrierSavedCodes);
        })
        .catch((err) => {
            if (seq !== carrierLoadSeq) return;
            matrix.textContent = err.message || '读取承运人失败';
        });
}

function carrierCellHtml(code, on, absent) {
    const safe = String(code).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    const classes = ['carrier-cell'];
    if (on) classes.push('is-on');
    if (on && absent) classes.push('is-absent');
    return `<button type="button" class="${classes.join(' ')}" data-carrier="${safe}" aria-pressed="${on ? 'true' : 'false'}">${safe}</button>`;
}

function renderCarrierMatrix(flights, selected) {
    const matrix = document.getElementById('carrier-matrix');
    if (!matrix) return;
    carrierFlightCodes = sortCarrierCodes(flights);
    carrierSelectedCodes = sortCarrierCodes(selected);
    const flightSet = new Set(carrierFlightCodes);
    const picked = new Set(carrierSelectedCodes);
    const codes = sortCarrierCodes(carrierFlightCodes.concat(carrierSelectedCodes));
    const cells = codes.map((code) => carrierCellHtml(code, picked.has(code), !flightSet.has(code)));
    cells.push('<button type="button" class="carrier-cell carrier-add" data-add="1" aria-label="添加承运人">+</button>');
    matrix.innerHTML = cells.join('');
    refreshCarrierConfirm();
}

function carrierEditBusy() {
    const btn = document.getElementById('carrier-confirm');
    return !!(btn && btn.dataset.busy === '1');
}

function toggleCarrierCell(code) {
    if (carrierEditBusy()) return;
    if (!carrierCanEdit()) {
        alert('非本机使用默认承运人');
        return;
    }
    const selected = new Set(carrierSelectedCodes);
    if (selected.has(code)) selected.delete(code);
    else selected.add(code);
    carrierSelectedCodes = sortCarrierCodes(Array.from(selected));
    renderCarrierMatrix(carrierFlightCodes, carrierSelectedCodes);
}

function beginCarrierAdd() {
    const matrix = document.getElementById('carrier-matrix');
    const addBtn = matrix && matrix.querySelector('.carrier-add');
    if (!addBtn || matrix.querySelector('.carrier-add-input')) return;
    const input = document.createElement('input');
    input.type = 'text';
    input.maxLength = 2;
    input.className = 'carrier-cell carrier-add-input';
    input.setAttribute('aria-label', '输入二字代码');
    addBtn.replaceWith(input);
    input.focus();
    input.addEventListener('click', (event) => event.stopPropagation());
    input.addEventListener('keydown', (event) => {
        event.stopPropagation();
        if (event.key === 'Enter') {
            event.preventDefault();
            commitCarrierAdd(input.value);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            renderCarrierMatrix(carrierFlightCodes, carrierSelectedCodes);
        }
    });
}

function commitCarrierAdd(raw) {
    if (carrierEditBusy()) return;
    const code = String(raw || '').trim().toUpperCase();
    if (!/^[A-Z0-9]{2}$/.test(code)) {
        alert('请输入2位字母或数字');
        const input = document.querySelector('.carrier-add-input');
        if (input) input.focus();
        return;
    }
    const shown = new Set(carrierFlightCodes.concat(carrierSelectedCodes));
    if (shown.has(code)) {
        alert(`矩阵中已有 ${code}，不能重复添加`);
        const input = document.querySelector('.carrier-add-input');
        if (input) input.focus();
        return;
    }
    if (!carrierCanEdit()) {
        alert('非本机使用默认承运人');
        return;
    }
    carrierSelectedCodes = sortCarrierCodes(carrierSelectedCodes.concat([code]));
    renderCarrierMatrix(carrierFlightCodes, carrierSelectedCodes);
}

function onCarrierMatrixClick(event) {
    const add = event.target.closest('.carrier-add');
    if (add) {
        event.stopPropagation();
        beginCarrierAdd();
        return;
    }
    const cell = event.target.closest('.carrier-cell[data-carrier]');
    if (!cell) return;
    event.stopPropagation();
    toggleCarrierCell(cell.dataset.carrier);
}

function confirmCarrierSelection() {
    const btn = document.getElementById('carrier-confirm');
    if (!btn || btn.disabled) return;
    if (!carrierCanEdit()) {
        alert('非本机使用默认承运人');
        return;
    }
    btn.dataset.busy = '1';
    refreshCarrierConfirm();
    const headers = Object.assign(
        { 'Content-Type': 'application/json' },
        typeof getRequestHeaders === 'function' ? getRequestHeaders() : {}
    );
    fetch(`/${currentTimeMode}/api/flight-carriers/`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ action: 'confirm', codes: carrierSelectedCodes }),
    })
        .then((res) => res.json())
        .then((data) => {
            if (!data.success) throw new Error(data.error || '确认承运人失败');
            const selected = sortCarrierCodes(data.selected || []);
            carrierSavedCodes = selected.slice();
            carrierSelectedCodes = selected.slice();
            currentCarriers = selected.slice();
            window.carriers = currentCarriers;
            updateCarrierDisplay();
            closeCarrierMenu();
            return reloadAirportsAfterCarrierChange();
        })
        .catch((err) => {
            console.error('确认承运人失败', err);
            alert(err.message || '确认承运人失败');
        })
        .finally(() => {
            if (btn) delete btn.dataset.busy;
            refreshCarrierConfirm();
        });
}

function reloadAirportsAfterCarrierChange() {
    const headers = typeof getRequestHeaders === 'function' ? getRequestHeaders() : {};
    return fetch(`/${currentTimeMode}/api/airports/overview/`, { headers })
        .then((res) => res.json())
        .then((data) => {
            if (!data.success || !data.data) return;
            airportData = data.data.airports || [];
            if (!window.__carrierMenuOpen && Array.isArray(data.data.carriers)) {
                currentCarriers = sortCarrierCodes(data.data.carriers);
                window.carriers = currentCarriers;
                updateCarrierDisplay();
            }
            if (typeof syncAlertStateFromMetarData === 'function') syncAlertStateFromMetarData(airportData);
            if (typeof syncAlertStateFromTafData === 'function') syncAlertStateFromTafData(airportData);
            if (typeof applyFilters === 'function') applyFilters();
            if (typeof updateAllAirportGrids === 'function') updateAllAirportGrids();
            if (typeof nwpEnabled !== 'undefined' && nwpEnabled && typeof fetchNwpDataAndRender === 'function') {
                fetchNwpDataAndRender();
            }
            window.dispatchEvent(new CustomEvent('mtws-carriers-changed'));
        })
        .catch((err) => console.error('承运人变更后刷新机场失败', err));
}

function createFlightTimeline(flightData, tafData = null, metarData = null, airport = null) {
    return createMarksFlightTimeline(flightData || {}, airport && airport.airport_4code);
}

function updateFlightStatusWarning(flightStatus) {
    if (!flightStatus) return;

    let warningElement = document.getElementById('flight-status-warning');

    if (!flightStatus.is_available) {
        if (!warningElement) {
            warningElement = document.createElement('div');
            warningElement.id = 'flight-status-warning';
            warningElement.innerHTML = '⚠';
            warningElement.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 80px;
                height: 80px;
                background-color: #ffc107;
                color: #212529;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 40px;
                font-weight: bold;
                cursor: pointer;
                z-index: 1000;
                box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                transition: transform 0.2s;
            `;
            warningElement.addEventListener('mouseenter', function () {
                this.style.transform = 'scale(1.1)';
            });
            warningElement.addEventListener('mouseleave', function () {
                this.style.transform = 'scale(1)';
            });
            document.body.appendChild(warningElement);
        }

        if (airportData && airportData.length > 0 && airportData[0].flight_data && airportData[0].flight_data.last_updated) {
            const lastUpdated = new Date(airportData[0].flight_data.last_updated);
            const timeString = lastUpdated.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
            warningElement.title = `未获取到最新航班数据，当前显示的航班数据为${timeString}获取`;
        } else {
            warningElement.title = `未获取到最新航班数据，当前无可用的航班数据`;
        }
    } else if (warningElement) {
        warningElement.remove();
    }
}

function getMarksPastRatio() {
    const hours = (typeof currentTimeRange !== 'undefined') ? currentTimeRange : 36;
    return 2 / hours;
}

function syncFlightMarksCssVars() {
    const hours = (typeof currentTimeRange !== 'undefined') ? currentTimeRange : 36;
    document.documentElement.style.setProperty('--marks-range-hours', String(hours));
    document.documentElement.style.setProperty('--marks-past-ratio', String(getMarksPastRatio()));
}

function buildFlightPastHandleHtml() {
    // 已改为页面级悬浮锚点，行内不再插入
    return '';
}

function removeFlightPastHandleFloat() {
    removeMarksPastHandle('home');
}

function marksPastHandleId(scope) {
    if (!scope || scope === 'home') return 'flight-past-handle-float';
    if (scope === 'detail') return 'flight-past-handle-detail';
    return 'flight-past-handle-' + String(scope).replace(/[^a-zA-Z0-9]/g, '-');
}

function marksPastHandleTimelines(scope) {
    if (!scope || scope === 'home') {
        return document.querySelectorAll('#content-main .airport-row .forecast-timeline');
    }
    if (scope === 'detail') {
        return document.querySelectorAll('#airport-detail-main .forecast-timeline');
    }
    const code = scope.slice(7);
    return document.querySelectorAll(`#search-block-main-${code} .forecast-timeline`);
}

function marksPastHandleRows(scope) {
    if (!scope || scope === 'home') {
        return document.querySelectorAll('#content-main .airport-row');
    }
    if (scope === 'detail') {
        return document.querySelectorAll('#airport-detail-main .airport-row');
    }
    const code = scope.slice(7);
    return document.querySelectorAll(`#search-block-main-${code} .airport-row`);
}

function marksScopeHostVisible(scope) {
    if (!scope || scope === 'home') {
        if (window._viewMode === 'plain' || window._viewMode === 'map') return false;
        if (typeof currentView === 'function' && currentView() && currentView() !== 'home') return false;
        const content = document.getElementById('content-main');
        if (content) {
            const host = content.closest('.content-section') || content;
            if (host.style.display === 'none') return false;
        }
        return true;
    }
    if (scope === 'detail') {
        const modal = document.getElementById('airport-detail-modal');
        return !!(modal && modal.style.display === 'block');
    }
    const modal = document.getElementById('airport-search-modal');
    return !!(modal && modal.style.display === 'block');
}

function removeMarksPastHandle(scope) {
    const el = document.getElementById(marksPastHandleId(scope));
    if (el) el.remove();
}

function positionMarksPastHandle(scope) {
    const sc = scope || 'home';
    const wrap = document.getElementById(marksPastHandleId(sc));
    if (!wrap || !isFlightMarksMode()) return;
    if (!marksScopeHostVisible(sc)) {
        wrap.style.display = 'none';
        return;
    }
    const rows = marksPastHandleRows(sc);
    const timelines = marksPastHandleTimelines(sc);
    if (!rows.length || !timelines.length) {
        wrap.style.display = 'none';
        return;
    }
    wrap.style.display = '';
    const firstTl = timelines[0];
    const tlRect = firstTl.getBoundingClientRect();
    const firstRect = rows[0].getBoundingClientRect();
    const lastRect = rows[rows.length - 1].getBoundingClientRect();
    // 不得超过时间轴及以上：下限卡在内容区顶部（标题行底部），上滚时自动裁短
    const hostTop = (() => {
      const content = sc === 'home'
        ? document.getElementById('content-main')
        : sc === 'detail'
          ? document.getElementById('airport-detail-main')
          : (rows[0] && rows[0].closest('[id^="search-block-main-"]'));
      const r = content ? content.getBoundingClientRect() : firstTl.getBoundingClientRect();
      return r.top;
    })();
    const top = Math.max(firstRect.top, hostTop);
    const bottom = Math.max(top, lastRect.bottom);
    const height = Math.max(36, bottom - top);
    wrap.style.left = `${Math.round(tlRect.left)}px`;
    wrap.style.top = `${Math.round(top)}px`;
    wrap.style.height = `${Math.round(height)}px`;
    const expanded = getMarksPastExpanded(sc);
    wrap.classList.toggle('open', expanded);
    wrap.title = expanded ? '收起过去2小时' : '展开过去2小时';
    const knob = wrap.querySelector('.flight-past-handle-knob');
    if (knob) {
        const visTop = Math.max(top, 0);
        const visBottom = Math.min(top + height, window.innerHeight);
        const mid = (visTop + visBottom) / 2;
        const knobH = 28;
        let y = mid - top - knobH / 2;
        y = Math.max(0, Math.min(Math.max(0, height - knobH), y));
        knob.style.top = `${Math.round(y)}px`;
    }
}

function positionFlightPastHandleFloat() {
    positionAllMarksPastHandles();
}

function positionAllMarksPastHandles() {
    positionMarksPastHandle('home');
    positionMarksPastHandle('detail');
    document.querySelectorAll('.airport-search-block[data-code]').forEach((block) => {
        positionMarksPastHandle('search:' + String(block.dataset.code).toUpperCase());
    });
}

function ensureMarksPastHandle(scope) {
    const sc = scope || 'home';
    if (!isFlightMarksMode() || !marksScopeHostVisible(sc)) {
        removeMarksPastHandle(sc);
        return;
    }
    const id = marksPastHandleId(sc);
    let wrap = document.getElementById(id);
    if (!wrap) {
        wrap = document.createElement('div');
        wrap.id = id;
        wrap.className = 'flight-past-handle-float';
        wrap.dataset.marksScope = sc;
        if (sc !== 'home') wrap.classList.add('in-modal');
        if (sc === 'detail') wrap.classList.add('scope-detail');
        if (sc.indexOf('search:') === 0) wrap.classList.add('scope-search');
        wrap.addEventListener('click', (e) => toggleFlightMarksPast(e, sc));
        document.body.appendChild(wrap);
    }
    if (!wrap.querySelector('.flight-past-handle-rail')) {
        wrap.innerHTML = '<span class="flight-past-handle-rail"></span><span class="flight-past-handle-knob"></span>';
    }
    syncFlightMarksCssVars();
    positionMarksPastHandle(sc);
}

function ensureFlightPastHandleFloat() {
    ensureMarksPastHandle('home');
}

function ensureModalMarksPastHandles() {
    const detailModal = document.getElementById('airport-detail-modal');
    if (detailModal && detailModal.style.display === 'block') {
        ensureMarksPastHandle('detail');
    } else {
        removeMarksPastHandle('detail');
    }
    const searchModal = document.getElementById('airport-search-modal');
    const live = new Set();
    if (searchModal && searchModal.style.display === 'block') {
        document.querySelectorAll('.airport-search-block[data-code]').forEach((block) => {
            const sc = 'search:' + String(block.dataset.code).toUpperCase();
            live.add(marksPastHandleId(sc));
            ensureMarksPastHandle(sc);
        });
    }
    document.querySelectorAll('.flight-past-handle-float.scope-search').forEach((el) => {
        if (!live.has(el.id)) el.remove();
    });
}

function _marksAnimTargets(scope) {
    const list = [];
    const sc = scope || 'home';
    if (!sc || sc === 'home') {
        document.querySelectorAll('#content-main .forecast-timeline > .marks-slide-layer').forEach((el) => list.push(el));
        document.querySelectorAll('.main-title-row .title-timeline > .timeline-row').forEach((el) => list.push(el));
        return list;
    }
    if (sc === 'detail') {
        document.querySelectorAll('#airport-detail-main .forecast-timeline > .marks-slide-layer').forEach((el) => list.push(el));
        document.querySelectorAll('#airport-detail-modal .airport-detail-title-row .title-timeline > .timeline-row').forEach((el) => list.push(el));
        return list;
    }
    const code = sc.slice(7);
    document.querySelectorAll(`#search-block-main-${code} .forecast-timeline > .marks-slide-layer`).forEach((el) => list.push(el));
    const block = document.querySelector(`.airport-search-block[data-code="${code}"]`);
    if (block) {
        block.querySelectorAll('.title-timeline > .timeline-row').forEach((el) => list.push(el));
    }
    return list;
}

function getAirportDataByCode(code) {
    if (!code) return null;
    if (typeof searchAirportCache !== 'undefined' && searchAirportCache && searchAirportCache[code]) {
        return searchAirportCache[code];
    }
    if (typeof airportData !== 'undefined' && Array.isArray(airportData)) {
        for (let i = 0; i < airportData.length; i++) {
            if (airportData[i] && airportData[i].airport_4code === code) return airportData[i];
        }
    }
    return null;
}

function redrawMarksScope(scope) {
    const sc = scope || 'home';
    syncFlightMarksCssVars();
    syncMarksPastOpenClass(sc);
    withMarksRenderScope(sc, () => {
        if (!sc || sc === 'home') {
            if (typeof generateTimeline === 'function') generateTimeline();
            if (typeof applyTimeRangeScaling === 'function') applyTimeRangeScaling();
            if (typeof applyFilters === 'function') applyFilters();
            else if (typeof updateAllAirportGrids === 'function') updateAllAirportGrids();
            ensureMarksPastHandle('home');
            return;
        }
        if (sc === 'detail') {
            if (typeof generateAirportDetailTimeline === 'function') generateAirportDetailTimeline();
            const code = typeof currentDetailAirportCode !== 'undefined' ? currentDetailAirportCode : null;
            const airport = getAirportDataByCode(code);
            const detailMain = document.getElementById('airport-detail-main');
            if (airport && detailMain && typeof createAirportRowForDetail === 'function') {
                detailMain.innerHTML = createAirportRowForDetail(airport, { marksScope: 'detail' });
                const airportRow = detailMain.querySelector('.airport-row');
                if (airportRow && typeof updateAirportGridForModal === 'function') {
                    updateAirportGridForModal(airportRow);
                }
                if (typeof renderNwpOverlayForAirportDetail === 'function') {
                    renderNwpOverlayForAirportDetail();
                }
                if (typeof paintPlainDetailMetar === 'function') paintPlainDetailMetar(airport);
            }
            ensureMarksPastHandle('detail');
            return;
        }
        const code = sc.slice(7);
        if (typeof _generateSearchTimeline === 'function') {
            _generateSearchTimeline(`search-block-bj-${code}`, `search-block-utc-${code}`);
        }
        const airport = getAirportDataByCode(code);
        const mainEl = document.getElementById(`search-block-main-${code}`);
        if (airport && mainEl && typeof createAirportRowForDetail === 'function') {
            mainEl.innerHTML = createAirportRowForDetail(airport, { marksScope: sc });
            const airportRow = mainEl.querySelector('.airport-row');
            if (airportRow && typeof updateAirportGridForModal === 'function') {
                updateAirportGridForModal(airportRow);
            }
            if (typeof renderNwpOverlayForAirportSearch === 'function') {
                renderNwpOverlayForAirportSearch(code);
            }
            if (typeof paintSearchBlockMetar === 'function') paintSearchBlockMetar(code, airport);
        }
        ensureMarksPastHandle(sc);
    });
}

/** 清理历史上误包在顶轴上的 slide 层，恢复 beijing/utc 行结构（时刻数字才能显示） */
function unwrapMarksTitleSlideLayer(titleTimeline) {
    if (!titleTimeline) return;
    const slide = titleTimeline.querySelector(':scope > .marks-slide-layer');
    if (!slide) return;
    while (slide.firstChild) titleTimeline.appendChild(slide.firstChild);
    slide.remove();
}

function removeMarksNowBadge(titleTimeline) {
    if (titleTimeline) {
        titleTimeline.querySelectorAll('.marks-now-badge').forEach((el) => el.remove());
        return;
    }
    document.querySelectorAll('.marks-now-badge').forEach((el) => el.remove());
    const row = document.getElementById('marks-now-row');
    if (row) row.remove();
}

/** NOW：悬浮在时间轴轨道内侧下方，不新开行、不挤整点 */
function updateMarksNowBadge(titleTimeline, winStart, dur, forcePast) {
    if (!titleTimeline) return;
    removeMarksNowBadge(titleTimeline);
    const showPast = forcePast === true || (forcePast !== false && marksWindowIncludesPast());
    if (!showPast || !dur) return;
    const nowMs = getMarksNowMs();
    const pct = ((nowMs - winStart) / dur) * 100;
    if (pct < -0.5 || pct > 100.5) return;

    const badge = document.createElement('span');
    badge.className = 'marks-now-badge';
    badge.style.left = `${pct}%`;
    badge.textContent = 'NOW';
    let host = titleTimeline;
    const rows = titleTimeline.querySelectorAll(':scope > .timeline-row');
    for (let i = rows.length - 1; i >= 0; i--) {
        if (window.getComputedStyle(rows[i]).display !== 'none') {
            host = rows[i];
            break;
        }
    }
    host.appendChild(badge);
}

function _playMarksExpandAnimation(expanding, scope) {
    const sc = scope || 'home';
    const pastPct = getMarksPastRatio() * 100;
    const targets = _marksAnimTargets(sc);
    if (!targets.length) {
        if (!expanding) {
            setMarksPastExpanded(sc, false);
            if (sc === 'home' && typeof syncFlightMarksBodyClass === 'function') syncFlightMarksBodyClass();
            redrawMarksScope(sc);
        }
        return;
    }

    if (expanding) {
        targets.forEach((el) => {
            el.style.transition = 'none';
            el.style.transform = `translateX(-${pastPct}%)`;
        });
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                targets.forEach((el) => {
                    el.style.transition = 'transform 0.35s ease-out';
                    el.style.transform = 'translateX(0)';
                });
            });
        });
        setTimeout(() => {
            targets.forEach((el) => {
                el.style.transition = '';
                el.style.transform = '';
            });
            positionAllMarksPastHandles();
        }, 380);
    } else {
        targets.forEach((el) => {
            el.style.transition = 'none';
            el.style.transform = 'translateX(0)';
        });
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                targets.forEach((el) => {
                    el.style.transition = 'transform 0.3s ease-in';
                    el.style.transform = `translateX(-${pastPct}%)`;
                });
            });
        });
        setTimeout(() => {
            targets.forEach((el) => {
                el.style.transition = '';
                el.style.transform = '';
            });
            setMarksPastExpanded(sc, false);
            if (sc === 'home' && typeof syncFlightMarksBodyClass === 'function') syncFlightMarksBodyClass();
            redrawMarksScope(sc);
        }, 320);
    }
}

function toggleFlightMarksPast(event, scope) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!isFlightMarksMode()) return;
    if (window._flightMarksAnimating) return;

    const sc = scope
        || (event && event.currentTarget && event.currentTarget.dataset.marksScope)
        || 'home';
    const willExpand = !getMarksPastExpanded(sc);
    window._flightMarksAnimating = true;

    if (willExpand) {
        setMarksPastExpanded(sc, true);
        if (sc === 'home' && typeof syncFlightMarksBodyClass === 'function') syncFlightMarksBodyClass();
        redrawMarksScope(sc);
        _playMarksExpandAnimation(true, sc);
        setTimeout(() => { window._flightMarksAnimating = false; }, 400);
    } else {
        _playMarksExpandAnimation(false, sc);
        setTimeout(() => { window._flightMarksAnimating = false; }, 400);
    }
}

const MARKS_LEGEND_POS_KEY = 'mtws_marks_legend_pos';

function marksLegendDirHtml(center) {
    if (center) {
        return `
            <span class="fml-item"><span class="fml-tri fml-tri-down"></span>朝下＝进港/落地</span>
            <span class="fml-item"><span class="fml-tri fml-tri-up"></span>朝上＝起飞/离港</span>`;
    }
    return `
        <span class="fml-item"><span class="fml-tri fml-tri-down"></span>上行＝进港/落地</span>
        <span class="fml-item"><span class="fml-tri fml-tri-up"></span>下行＝起飞/离港</span>`;
}

function syncMarksLegendLayout() {
    const el = document.getElementById('flight-marks-legend');
    if (!el) return;
    const center = isFlightMarksLayoutCenter();
    const input = el.querySelector('.fml-layout-input');
    if (input) input.checked = center;
    const dir = el.querySelector('.fml-dir');
    if (dir) dir.innerHTML = marksLegendDirHtml(center);
    document.body.classList.toggle('flight-marks-layout-center', center);
}

function setFlightMarksLayout(mode) {
    window.flightMarksLayout = mode === 'center' ? 'center' : 'split';
    try { localStorage.setItem(MARKS_LAYOUT_KEY, window.flightMarksLayout); } catch (e) { /* ignore */ }
    syncMarksLegendLayout();
    redrawAllFlightMarks();
}

function redrawAllFlightMarks() {
    if (marksScopeHostVisible('home')) redrawMarksScope('home');
    if (marksScopeHostVisible('detail')) redrawMarksScope('detail');
    const searchOpen = marksScopeHostVisible('search:');
    if (!searchOpen) return;
    document.querySelectorAll('.airport-search-block[data-code]').forEach((block) => {
        const code = block.dataset.code;
        if (code) redrawMarksScope('search:' + String(code).toUpperCase());
    });
}

function hideFlightMarksLegend() {
    const el = document.getElementById('flight-marks-legend');
    if (el) el.style.display = 'none';
}

function _clampMarksLegend(el, left, bottom) {
    const w = el.offsetWidth || 420;
    const h = el.offsetHeight || 88;
    const maxL = Math.max(0, window.innerWidth - w);
    const maxB = Math.max(0, window.innerHeight - h);
    return {
        left: Math.max(0, Math.min(maxL, left)),
        bottom: Math.max(0, Math.min(maxB, bottom)),
    };
}

function _applyMarksLegendPos(el, pos) {
    const p = _clampMarksLegend(el, pos.left, pos.bottom);
    el.style.left = p.left + 'px';
    el.style.bottom = p.bottom + 'px';
    el.style.right = 'auto';
    el.style.top = 'auto';
    el.style.transform = 'none';
}

function ensureFlightMarksLegend() {
    if (!isFlightMarksMode() || window._viewMode === 'map' || window._viewMode === 'plain') {
        hideFlightMarksLegend();
        return;
    }
    let el = document.getElementById('flight-marks-legend');
    if (!el) {
        el = document.createElement('div');
        el.id = 'flight-marks-legend';
        el.className = 'flight-marks-legend';
        document.body.appendChild(el);
        window.addEventListener('resize', () => {
            const box = document.getElementById('flight-marks-legend');
            if (!box || box.style.display === 'none') return;
            const left = parseFloat(box.style.left);
            const bottom = parseFloat(box.style.bottom);
            if (Number.isFinite(left) && Number.isFinite(bottom)) {
                _applyMarksLegendPos(box, { left, bottom });
            }
        });
    }
    if (!el.querySelector('.fml-layout-float')) {
        el.innerHTML = `
            <div class="fml-head">
                <div class="fml-handle" title="按住拖动">航班标记说明</div>
            </div>
            <div class="fml-body">
                <div class="fml-left">
                    <span class="fml-swatch"><span class="fml-mark fml-mark-r"></span>红色告警</span>
                    <span class="fml-swatch"><span class="fml-mark fml-mark-y"></span>黄色告警</span>
                    <span class="fml-swatch"><span class="fml-mark fml-mark-g"></span>绿色告警</span>
                    <span class="fml-swatch"><span class="fml-mark fml-mark-n"></span>无告警</span>
                </div>
                <div class="fml-right">
                    <div class="fml-row fml-dir"></div>
                    <div class="fml-row fml-row-lines">
                        <span class="fml-item"><span class="fml-tick fml-tick-white"></span>白＝飞机在地面</span>
                        <span class="fml-item"><span class="fml-tick fml-tick-black"></span>黑＝飞机在空中</span>
                        <span class="fml-item"><span class="fml-tick fml-tick-blink"></span>闪＝超时未起/未落</span>
                    </div>
                    <label class="fml-layout-toggle fml-layout-float" title="切换航班排列">
                        <input type="checkbox" class="fml-layout-input">
                        <span class="fml-layout-track">
                            <span class="fml-layout-label">上下行</span>
                            <span class="fml-layout-label">居中</span>
                            <span class="fml-layout-thumb"></span>
                        </span>
                    </label>
                </div>
            </div>`;
        const layoutInput = el.querySelector('.fml-layout-input');
        if (layoutInput) {
            layoutInput.addEventListener('change', () => {
                setFlightMarksLayout(layoutInput.checked ? 'center' : 'split');
            });
        }
        el.dataset.dragBound = '';
        _bindMarksLegendDrag(el);
    }
    syncMarksLegendLayout();
    el.style.display = 'flex';
    try {
        const saved = JSON.parse(localStorage.getItem(MARKS_LEGEND_POS_KEY) || 'null');
        if (saved && Number.isFinite(saved.left) && Number.isFinite(saved.bottom)) {
            _applyMarksLegendPos(el, saved);
        } else {
            const w = el.offsetWidth || 420;
            _applyMarksLegendPos(el, {
                left: Math.max(8, (window.innerWidth - w) / 2),
                bottom: 12,
            });
        }
    } catch (e) {
        _applyMarksLegendPos(el, { left: 12, bottom: 12 });
    }
}

function _bindMarksLegendDrag(el) {
    if (el.dataset.dragBound === '1') return;
    el.dataset.dragBound = '1';
    const handle = el.querySelector('.fml-handle') || el;
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let origLeft = 0;
    let origBottom = 0;

    const onMove = (e) => {
        if (!dragging) return;
        const pt = e.touches ? e.touches[0] : e;
        const dx = pt.clientX - startX;
        const dy = pt.clientY - startY;
        _applyMarksLegendPos(el, { left: origLeft + dx, bottom: origBottom - dy });
    };
    const onUp = () => {
        if (!dragging) return;
        dragging = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.removeEventListener('touchmove', onMove);
        document.removeEventListener('touchend', onUp);
        try {
            localStorage.setItem(MARKS_LEGEND_POS_KEY, JSON.stringify({
                left: parseFloat(el.style.left) || 0,
                bottom: parseFloat(el.style.bottom) || 0,
            }));
        } catch (err) { /* ignore */ }
    };

    handle.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        dragging = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = el.getBoundingClientRect();
        origLeft = rect.left;
        origBottom = window.innerHeight - rect.bottom;
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        e.preventDefault();
    });
    handle.addEventListener('touchstart', (e) => {
        const pt = e.touches[0];
        if (!pt) return;
        dragging = true;
        startX = pt.clientX;
        startY = pt.clientY;
        const rect = el.getBoundingClientRect();
        origLeft = rect.left;
        origBottom = window.innerHeight - rect.bottom;
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('touchend', onUp);
    }, { passive: true });
}

function bindMarksPastHandleLayoutWatch() {
    if (window._marksPastHandleRo || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
        if (window._marksPastHandleRoRaf) cancelAnimationFrame(window._marksPastHandleRoRaf);
        window._marksPastHandleRoRaf = requestAnimationFrame(() => {
            window._marksPastHandleRoRaf = 0;
            positionAllMarksPastHandles();
        });
    });
    window._marksPastHandleRo = ro;
    [
        document.querySelector('#airport-detail-modal .airport-detail-content'),
        document.getElementById('airport-detail-content'),
        document.querySelector('#airport-search-modal .airport-search-modal-content'),
        document.getElementById('airport-search-list'),
    ].forEach((el) => {
        if (el) ro.observe(el);
    });
}

function initFlightMarksMode() {
    syncFlightMarksBodyClass();
    syncFlightMarksCssVars();
    ensureFlightPastHandleFloat();
    bindFlightMarksTooltip();
    bindFlightMarkLinkHold();
    ensureFlightMarksLegend();
    bindMarksPastHandleLayoutWatch();
    if (!window._flightMarksHandleBound) {
        window._flightMarksHandleBound = true;
        window.addEventListener('resize', () => positionAllMarksPastHandles());
        document.addEventListener('scroll', () => positionAllMarksPastHandles(), true);
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFlightMarksMode);
} else {
    initFlightMarksMode();
}
