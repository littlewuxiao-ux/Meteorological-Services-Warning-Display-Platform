/**
 * 视图导航：左侧竖向导航栏（主页 / 地图 / 翻译 / 趋势 / 入库）同址切换。
 *
 * 视图在身份就绪之后才确定：非本机先过角色选择弹窗，拿到权限再判断地址里的
 * ?view=。有权限则进入，无权限按 主页 → 地图模式 → 中文模式 的优先级回落，
 * 并把地址改写成实际进入的视图；三者都无权限时提示联系管理员。
 * 每个视图的脚本按需注入，未进入过的视图不加载、不请求数据。
 */
(function () {
  const VIEWS = [
    { key: 'home', module: 'view_home', label: '主页', icon: '☰', script: null },
    {
      key: 'map',
      module: 'view_map',
      label: '地图',
      icon:
        '<svg viewBox="0 0 1024 1024" width="18" height="18" aria-hidden="true">' +
        '<path fill="currentColor" d="M819.348 204.651c-78.654-78.653-187.23-127.384-307.239-127.384-120.014 0-228.591 48.731-307.349 127.385-78.763 79.07-127.28 187.647-127.28 307.338 0 120.129 48.518 228.705 127.28 307.359 78.758 78.862 187.335 127.385 307.349 127.385 120.009 0 228.585-48.522 307.238-127.385 78.545-78.654 127.172-187.23 127.172-307.359 0.001-119.691-48.626-228.268-127.171-307.339z m-47.339 47.438c62.087 62.202 102.165 146.414 107.398 239.82H762.415a34.738 34.738 0 0 0-10.182-9.449c-2.909-73.521-16.636-141.713-37.547-200.201a34.282 34.282 0 0 0 3.799-10.044c15.351-8.524 30.322-17.957 44.546-28.883a235.98 235.98 0 0 1 8.978 8.757z m-93.824 472.038a34.389 34.389 0 0 0-9.187 4.158c-3.31-1.279-6.578-2.561-9.84-3.834-36.949-13.804-75.989-22.486-116.781-25.272a34.686 34.686 0 0 0-10.396-10.692v-147.64a34.743 34.743 0 0 0 9.411-9.194h164.549a34.753 34.753 0 0 0 6.494 7.052c-2.826 68.379-14.988 131.783-34.25 185.422zM483.71 699.043c-41.362 2.645-80.909 11.395-118.117 25.408a1391.563 1391.563 0 0 0-8.398 3.129 34.275 34.275 0 0 0-11.443-4.236c-18.99-53.161-31.007-115.857-33.729-183.451a34.707 34.707 0 0 0 8.037-8.24h164.549a34.747 34.747 0 0 0 7.619 7.935v150.158a34.665 34.665 0 0 0-8.518 9.297zM346.651 298.118a34.33 34.33 0 0 0 6.767-2.99c3.992 1.594 7.926 3.114 11.643 4.629 37.75 14.02 77.378 22.967 118.796 25.444a34.712 34.712 0 0 0 8.369 8.302v150.909a34.737 34.737 0 0 0-7.308 7.497H319.747a34.697 34.697 0 0 0-7.744-7.815c2.731-68.795 15.096-132.176 34.648-185.976z m193.482 27.096c41.605-2.457 81.397-11.41 119.025-25.457a1462.2 1462.2 0 0 0 9.724-3.846 34.293 34.293 0 0 0 9.022 3.155c19.467 53.907 31.741 117.365 34.549 186.216a34.67 34.67 0 0 0-6.2 6.626H541.081a34.723 34.723 0 0 0-9.1-8.756V333.355a34.696 34.696 0 0 0 8.152-8.141zM731.18 216.829c-9.238 6.752-18.851 13.046-28.891 18.671a34.29 34.29 0 0 0-9.752-3.925c-2.169-4.311-4.408-8.572-6.877-12.828-9.195-16.66-18.917-31.414-28.963-45.093 26.607 11.334 51.724 26.076 74.483 43.175z m-158.37-67.54c29.171 17.954 55.999 48.939 77.8 88.913 1.595 2.984 3.188 5.871 4.735 8.754a34.302 34.302 0 0 0-4.866 13.376 344.326 344.326 0 0 0-5.536 2.235c-32.762 11.948-67.932 19.989-104.824 22.593a34.698 34.698 0 0 0-8.137-8.121V144.807c13.788 0.416 27.576 2.345 40.828 4.482z m-121.401 0c13.251-1.71 27.034-4.066 40.817-4.482v132.084a34.697 34.697 0 0 0-8.335 8.254c-36.83-2.619-72.035-10.651-104.834-22.578-2.946-1.254-5.957-2.436-8.901-3.629a34.27 34.27 0 0 0-2.873-8.799c2.058-3.956 4.144-7.858 6.327-11.938 22.009-39.972 48.835-70.958 77.799-88.912z m-83.68 24.366c-10.473 13.679-20.194 28.433-29.281 45.093-2.279 4.044-4.401 8.095-6.51 12.187a34.283 34.283 0 0 0-11.676 3.628c-9.244-5.384-18.357-11.354-27.338-17.733 23.082-17.1 47.979-31.842 74.805-43.175zM252.21 252.089c2.564-2.981 6.192-5.984 8.977-8.757 13.032 10.014 26.702 18.761 40.823 26.716a34.342 34.342 0 0 0 6.426 15.688c-20.721 58.027-33.586 125.395-36.492 197.92a34.703 34.703 0 0 0-8.359 8.253H145.02c4.702-93.407 44.988-177.618 107.19-239.82z m0 520.018c-62.202-61.982-102.488-146.193-107.19-240.455h118.254a34.688 34.688 0 0 0 8.689 8.704c2.985 73.728 16.201 142.457 37.458 200.302a34.305 34.305 0 0 0-3.845 11.147c-15.392 9.128-30.261 18.771-44.391 29.071l-8.975-8.769z m40.714 35.688a311.822 311.822 0 0 1 30.379-20.045 34.4 34.4 0 0 0 7.367 2.928c2.531 5.044 5.042 10.078 7.778 14.773 9.087 16.243 18.809 31.413 29.281 44.883-26.826-11.541-51.723-25.438-74.805-42.539z m158.485 67.332c-28.964-18.601-55.79-49.158-77.799-88.913a726.847 726.847 0 0 1-5.156-9.808 34.332 34.332 0 0 0 5.114-12.496 75.193 75.193 0 0 1 5.489-1.634c33.434-13.165 69.561-20.757 107.006-23.342a34.68 34.68 0 0 0 6.163 5.985v133.836c-13.783-0.208-27.566-1.49-40.817-3.628z m121.401 0c-13.252 2.138-27.04 3.42-40.828 3.629V746.18a34.711 34.711 0 0 0 7.866-7.132c36.991 2.692 72.252 10.259 105.095 23.229a76.898 76.898 0 0 1 9.097 2.909 34.292 34.292 0 0 0 3.204 8.498c-2.125 4.17-4.374 8.303-6.634 12.53-21.801 39.755-48.63 70.312-77.8 88.913z m83.887-24.793c10.473-13.47 19.768-28.64 28.963-44.883 2.674-4.457 5.087-9.222 7.423-14.009a34.281 34.281 0 0 0 9.24-2.837c10.027 5.743 19.629 12.092 28.856 19.189-22.758 17.102-47.875 30.999-74.482 42.54z m115.312-78.227l-8.978 8.77c-13.035-9.499-26.708-18.434-40.996-26.927a34.33 34.33 0 0 0-6.305-16.732c20.459-56.807 33.61-123.85 36.485-195.668a34.724 34.724 0 0 0 10.511-9.897h116.681c-5.233 94.261-45.311 178.472-107.398 240.454z"/>' +
        '</svg>',
      deps: ['vendor/maplibre/maplibre-gl.js'],
      css: ['vendor/maplibre/maplibre-gl.css'],
      script: 'js/map.js',
    },
    { key: 'plain', module: 'view_plain', label: '翻译', icon:
        '<svg viewBox="0 0 1024 1024" width="18" height="18" aria-hidden="true">' +
        '<path fill="currentColor" d="M213.333333 682.666667v42.666666a85.333333 85.333333 0 0 0 78.933334 85.12L298.666667 810.666667h85.333333a42.666667 42.666667 0 0 1 0 85.333333H298.666667a170.666667 170.666667 0 0 1-170.666667-170.666667v-42.666666a42.666667 42.666667 0 0 1 85.333333 0z m560.042667-242.602667l170.666667 426.666667a21.333333 21.333333 0 0 1-19.84 29.269333h-45.994667a21.333333 21.333333 0 0 1-19.797333-13.397333L812.544 768h-174.506667l-45.781333 114.602667a21.333333 21.333333 0 0 1-19.84 13.397333H526.506667a21.333333 21.333333 0 0 1-19.797334-29.269333l170.666667-426.666667a21.333333 21.333333 0 0 1 19.797333-13.397333h56.405334a21.333333 21.333333 0 0 1 19.84 13.397333zM725.333333 549.76L672.128 682.666667h106.325333L725.333333 549.76zM341.333333 106.666667V170.666667h149.333334a21.333333 21.333333 0 0 1 21.333333 21.333333v256a21.333333 21.333333 0 0 1-21.333333 21.333333H341.333333v106.666667a21.333333 21.333333 0 0 1-21.333333 21.333333h-42.666667a21.333333 21.333333 0 0 1-21.333333-21.333333V469.333333H106.666667a21.333333 21.333333 0 0 1-21.333334-21.333333v-256a21.333333 21.333333 0 0 1 21.333334-21.333333H256V106.666667a21.333333 21.333333 0 0 1 21.333333-21.333334h42.666667a21.333333 21.333333 0 0 1 21.333333 21.333334z m384 21.333333a170.666667 170.666667 0 0 1 170.666667 170.666667v42.666666a42.666667 42.666667 0 0 1-85.333333 0V298.666667a85.333333 85.333333 0 0 0-85.333334-85.333334h-85.333333a42.666667 42.666667 0 0 1 0-85.333333h85.333333zM256 256H170.666667v128h85.333333V256z m170.666667 0H341.333333v128h85.333334V256z"/>' +
        '</svg>',
      script: 'js/plain_view.js' },
    {
      key: 'trend',
      module: 'view_trend',
      label: '趋势',
      icon:
        '<svg viewBox="0 0 1126 1024" width="18" height="18" aria-hidden="true">' +
        '<path fill="currentColor" d="M561.9712 0.9216c42.3936 0 81.664 22.2208 103.5264 58.5728l440.5248 734.208a120.7296 120.7296 0 0 1-103.5264 182.8352H121.4464A120.7296 120.7296 0 0 1 17.92 793.7024L458.496 59.2384a121.1392 121.1392 0 0 1 103.4752-58.368z m0 102.4a18.5856 18.5856 0 0 0-15.8208 8.8576L105.728 846.336a18.3296 18.3296 0 0 0 15.7184 27.7504H1002.496a18.3296 18.3296 0 0 0 15.7184-27.7504L577.6896 112.128a18.3296 18.3296 0 0 0-15.7184-8.8576zM429.6192 428.6976l63.744 124.416 112.2304-42.9568a22.784 22.784 0 0 1 16.896 0.3584 22.6816 22.6816 0 0 1 12.4416 11.52l59.6992 127.8464 0.6144 1.4848 36.352 77.9776 28.8256-71.3216c4.3008-10.4448 16.8448-15.36 28.16-10.752 11.3152 4.608 16.9984 16.8448 12.6464 27.3408l-46.2336 114.688-0.512 2.2016-1.8432 3.584-1.536 2.1504-4.096 3.7888-3.584 1.9456-4.608 1.4336-3.072 0.4096h-2.7136l-2.048-0.2048-4.096-0.9216-126.8224-51.3536c-11.3664-4.5056-16.9984-16.64-12.8-27.2384 4.2496-10.5472 16.8448-15.36 28.16-10.8032l76.4416 30.9248-1.024-2.2528-70.8608-151.808 0.256-0.1536-16.1792-34.6624-112.3328 43.008a23.04 23.04 0 0 1-16.896-0.256 22.4768 22.4768 0 0 1-12.3904-11.52L389.8368 444.0064a19.6096 19.6096 0 0 1 10.8544-26.9824 23.1936 23.1936 0 0 1 28.928 11.6736z"/>' +
        '</svg>',
      script: 'js/trend_view.js',
    },
    {
      key: 'import',
      module: 'import_alert',
      label: '入库',
      icon:
        '<svg viewBox="0 0 1024 1024" width="18" height="18" aria-hidden="true">' +
        '<path fill="currentColor" d="M868.48 136.58H743.77a28.8 28.8 0 0 0 0 57.6h124.71a34.15 34.15 0 0 1 34.11 34.11v566.92a34.15 34.15 0 0 1-34.11 34.11H155.72a34.15 34.15 0 0 1-34.11-34.11V228.29a34.15 34.15 0 0 1 34.11-34.11h120.89a28.8 28.8 0 0 0 0-57.6H155.72A91.81 91.81 0 0 0 64 228.29v566.92a91.81 91.81 0 0 0 91.71 91.71h712.77a91.81 91.81 0 0 0 91.71-91.71V228.29a91.81 91.81 0 0 0-91.71-91.71z"/>' +
        '<path fill="currentColor" d="M453.23 264.88h118.1v60.49h-118.1zM453.23 146.63h118.1v60.49h-118.1zM479.21 664.24c18.19 20.4 47.65 20.4 65.78 0l131.55-147.75c18.07-20.28 18.07-53.15 0.18-73.55h-105.4v-60.5H453.23v60.49H347.48c-17.89 20.4-17.89 53.21 0.18 73.55z"/>' +
        '</svg>',
      script: null,
    },
  ];
  const STORAGE_KEY = 'mtws_active_view';

  let _current = null;
  let _switching = false;
  const _scripts = {};

  window.__viewNavReady = false;

  // ── 脚本按需加载 ───────────────────────────────────────

  function staticPath(file) {
    return (window.staticUrl || '/static/') + file;
  }

  function ensureCss(file) {
    if (!file || document.querySelector(`link[data-mtws-css="${file}"]`)) return Promise.resolve();
    return new Promise((resolve) => {
      const el = document.createElement('link');
      el.rel = 'stylesheet';
      el.href = staticPath(file);
      el.setAttribute('data-mtws-css', file);
      el.onload = () => resolve();
      el.onerror = () => resolve();
      document.head.appendChild(el);
    });
  }

  function ensureScript(file) {
    if (!file) return Promise.resolve();
    if (_scripts[file]) return _scripts[file];
    _scripts[file] = new Promise((resolve, reject) => {
      const el = document.createElement('script');
      el.src = staticPath(file);
      el.onload = () => resolve();
      el.onerror = () => reject(new Error('模块加载失败: ' + file));
      document.head.appendChild(el);
    });
    return _scripts[file];
  }

  function ensureViewAssets(view) {
    const cssList = view.css || [];
    const deps = view.deps || [];
    return Promise.all(cssList.map(ensureCss))
      .then(() => deps.reduce((p, f) => p.then(() => ensureScript(f)), Promise.resolve()))
      .then(() => ensureScript(view.script));
  }

  // ── 权限 ───────────────────────────────────────────────

  function canView(view) {
    if (typeof hasAccess !== 'function') return true;
    // 鉴权接口异常时身份为空，此时不拿视图挡人，沿用旧行为
    if (!window.__accessIdentity) return true;
    return hasAccess(view.module, 'display');
  }

  function allowedViews() {
    return VIEWS.filter(canView);
  }

  function viewByKey(key) {
    return VIEWS.find((v) => v.key === key) || null;
  }

  // ── 地址 / 记忆 ────────────────────────────────────────

  function urlView() {
    try {
      const key = new URLSearchParams(window.location.search).get('view');
      return viewByKey(key) ? key : null;
    } catch (e) {
      return null;
    }
  }

  function storedView() {
    const key = localStorage.getItem(STORAGE_KEY);
    return viewByKey(key) ? key : null;
  }

  function syncUrl(key) {
    try {
      const url = new URL(window.location.href);
      if (url.searchParams.get('view') === key) return;
      url.searchParams.set('view', key);
      window.history.replaceState(null, '', url.toString());
    } catch (e) { /* 老浏览器忽略 */ }
  }

  // ── 提示 ───────────────────────────────────────────────

  function toast(text) {
    const el = document.createElement('div');
    el.className = 'view-toast';
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2600);
  }

  function showBlocked() {
    if (document.getElementById('view-nav-blocked')) return;
    const el = document.createElement('div');
    el.id = 'view-nav-blocked';
    el.className = 'view-nav-blocked';
    el.innerHTML = '<div>未分配任何视图权限，请联系管理员</div>';
    document.body.appendChild(el);
  }

  function hideBlocked() {
    const el = document.getElementById('view-nav-blocked');
    if (el) el.remove();
  }

  // ── 导航栏 ─────────────────────────────────────────────

  function buildNav() {
    let nav = document.getElementById('view-nav');
    if (!nav) {
      nav = document.createElement('nav');
      nav.id = 'view-nav';
      nav.className = 'view-nav';
      document.body.insertBefore(nav, document.body.firstChild);
    }
    nav.innerHTML = '';
    const usable = allowedViews();
    usable.forEach((view) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'view-nav-item';
      btn.dataset.view = view.key;
      if (view.key !== 'trend') btn.title = view.title || view.label;
      btn.innerHTML =
        `<span class="view-nav-icon">${view.icon}</span>` +
        `<span class="view-nav-text">${view.label}</span>`;
      btn.addEventListener('click', () => switchView(view.key, { fromUser: true }));
      nav.appendChild(btn);
    });
    nav.style.display = usable.length ? '' : 'none';
    document.body.classList.toggle('has-view-nav', usable.length > 0);
    paintNav();
    syncNavTop();
    const trend = viewByKey('trend');
    if (trend && canView(trend)) {
      ensureViewAssets(trend).then(() => {
        if (typeof window.prefetchTrendBadge === 'function') window.prefetchTrendBadge();
      }).catch(() => {});
    }
    if (typeof window.updateImportAlertNavBadge === 'function') {
      window.updateImportAlertNavBadge();
    }
    updateRadarAlarmNavBadge();
  }

  let _radarAlarmCount = 0;
  let _radarAlarmBadgeTimer = null;

  function radarNavBadgeAllowed() {
    if (typeof hasAccess !== 'function' || !window.__accessIdentity) return true;
    return hasAccess('map_radar_nav', 'display');
  }

  function updateRadarAlarmNavBadge(count) {
    if (typeof count === 'number' && !Number.isNaN(count)) {
      _radarAlarmCount = count;
    }
    const btn = document.querySelector('.view-nav-item[data-view="map"]');
    if (!btn) return;
    let badge = btn.querySelector('.view-nav-badge');
    if (!radarNavBadgeAllowed() || _radarAlarmCount <= 0) {
      if (badge) badge.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'view-nav-badge';
      btn.appendChild(badge);
    }
    badge.textContent = String(_radarAlarmCount);
  }

  function refreshRadarAlarmBadge() {
    if (!radarNavBadgeAllowed()) {
      updateRadarAlarmNavBadge(0);
      return;
    }
    if (!document.querySelector('.view-nav-item[data-view="map"]')) return;
    const mode = (typeof currentTimeMode !== 'undefined') ? currentTimeMode : (window.timeMode || 'current');
    const headers = (typeof getRequestHeaders === 'function') ? getRequestHeaders() : {};
    fetch(`/${mode}/api/radar/alerts/`, { headers })
      .then((r) => r.json())
      .then((data) => {
        if (data && data.success) {
          const count = (data.alerts || []).filter((item) => !item.handled).length;
          updateRadarAlarmNavBadge(count);
        }
      })
      .catch(() => {});
  }

  function startRadarAlarmBadgePoll() {
    refreshRadarAlarmBadge();
    if (_radarAlarmBadgeTimer) return;
    _radarAlarmBadgeTimer = setInterval(refreshRadarAlarmBadge, 60000);
  }

  window.updateRadarAlarmNavBadge = updateRadarAlarmNavBadge;

  function paintNav() {
    const nav = document.getElementById('view-nav');
    if (!nav) return;
    nav.querySelectorAll('.view-nav-item').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.view === _current);
    });
  }

  // 导航顶边对齐功能区白线的下沿：有标题行时对齐标题行，否则对齐顶栏底边。
  function contentBandTop() {
    const titleRow = document.querySelector('.main-title-row');
    if (titleRow && titleRow.offsetParent !== null) {
      const top = titleRow.getBoundingClientRect().top;
      if (top > 0) return Math.round(top);
    }
    const chrome = document.querySelector('.page-chrome');
    if (chrome) return Math.max(0, Math.round(chrome.getBoundingClientRect().bottom));
    return 180;
  }

  function syncNavTop() {
    const nav = document.getElementById('view-nav');
    if (!nav) return;
    nav.style.top = contentBandTop() + 'px';
  }

  let _topQueued = false;
  function queueNavTop() {
    if (_topQueued) return;
    _topQueued = true;
    requestAnimationFrame(() => {
      _topQueued = false;
      syncNavTop();
    });
  }

  function watchNavTop() {
    window.addEventListener('scroll', queueNavTop, { passive: true });
    window.addEventListener('resize', queueNavTop);
    const chrome = document.querySelector('.page-chrome');
    if (chrome && typeof ResizeObserver === 'function') {
      new ResizeObserver(queueNavTop).observe(chrome);
    }
  }

  // ── 视图区域显隐 ───────────────────────────────────────

  function setListAreaVisible(visible) {
    const titleRow = document.querySelector('.main-title-row');
    const content = document.querySelector('.content-section');
    if (titleRow) titleRow.style.display = visible ? '' : 'none';
    if (content) content.style.display = visible ? '' : 'none';
  }

  function setPlainPanelVisible(visible) {
    const panel = document.getElementById('plain-panel');
    if (panel) panel.style.display = visible ? '' : 'none';
  }

  function setTrendPanelVisible(visible) {
    const panel = document.getElementById('trend-panel');
    if (panel) panel.style.display = visible ? '' : 'none';
  }

  function setImportPanelVisible(visible) {
    const panel = document.getElementById('import-alert-panel');
    if (panel) panel.style.display = visible ? 'flex' : 'none';
  }

  // ── 切换 ───────────────────────────────────────────────

  async function switchView(key, options) {
    const opts = options || {};
    const view = viewByKey(key);
    if (!view || _switching) return;
    if (!canView(view)) {
      const fallback = allowedViews()[0];
      if (!fallback) {
        showBlocked();
        return;
      }
      if (opts.notifyDenied) toast(`无权访问${view.label}模式，已切换到${fallback.label}`);
      await switchView(fallback.key, { fromUser: opts.fromUser });
      return;
    }
    if (key === _current) {
      syncUrl(key);
      return;
    }

    _switching = true;
    try {
      // 离开上一个视图
      if (_current === 'map' && typeof switchViewMode === 'function') {
        switchViewMode('list');
      }
      if (_current === 'plain' && typeof stopPlainView === 'function') {
        stopPlainView();
      }
      if (_current === 'trend' && typeof stopTrendView === 'function') {
        stopTrendView();
      }
      if (_current === 'import' && typeof stopImportView === 'function') {
        stopImportView();
      }

      _current = key;
      document.body.classList.toggle('plain-mode', key === 'plain');

      if (key === 'plain') {
        setListAreaVisible(false);
        setTrendPanelVisible(false);
        setImportPanelVisible(false);
        setPlainPanelVisible(true);
        window._viewMode = 'plain';
        if (typeof hideFlightMarksLegend === 'function') hideFlightMarksLegend();
        if (typeof removeMarksPastHandle === 'function') {
          removeMarksPastHandle('home');
        }
        await ensureViewAssets(view);
        if (typeof startPlainView === 'function') startPlainView();
      } else if (key === 'map') {
        setPlainPanelVisible(false);
        setTrendPanelVisible(false);
        setImportPanelVisible(false);
        setListAreaVisible(true);
        if (typeof hideFlightMarksLegend === 'function') hideFlightMarksLegend();
        if (typeof removeMarksPastHandle === 'function') {
          removeMarksPastHandle('home');
        }
        await ensureViewAssets(view);
        if (typeof initMapAlertState === 'function') initMapAlertState();
        if (typeof switchViewMode === 'function') {
          switchViewMode('map');
        } else {
          window._viewMode = 'map';
        }
      } else if (key === 'trend') {
        setPlainPanelVisible(false);
        setListAreaVisible(false);
        setImportPanelVisible(false);
        setTrendPanelVisible(true);
        window._viewMode = 'trend';
        if (typeof hideFlightMarksLegend === 'function') hideFlightMarksLegend();
        if (typeof removeMarksPastHandle === 'function') {
          removeMarksPastHandle('home');
        }
        await ensureViewAssets(view);
        if (typeof startTrendView === 'function') startTrendView();
      } else if (key === 'import') {
        setPlainPanelVisible(false);
        setTrendPanelVisible(false);
        setListAreaVisible(false);
        setImportPanelVisible(true);
        window._viewMode = 'import';
        if (typeof hideFlightMarksLegend === 'function') hideFlightMarksLegend();
        if (typeof removeMarksPastHandle === 'function') {
          removeMarksPastHandle('home');
        }
        await ensureViewAssets(view);
        if (typeof startImportView === 'function') startImportView();
      } else {
        setPlainPanelVisible(false);
        setTrendPanelVisible(false);
        setImportPanelVisible(false);
        setListAreaVisible(true);
        window._viewMode = 'list';
        if (typeof ensureMarksPastHandle === 'function') {
          ensureMarksPastHandle('home');
        }
        if (typeof ensureFlightMarksLegend === 'function') {
          ensureFlightMarksLegend();
        }
        const hasData = typeof airportData !== 'undefined' && airportData && airportData.length;
        if (hasData && typeof applyFilters === 'function') applyFilters();
      }

      localStorage.setItem(STORAGE_KEY, key);
      syncUrl(key);
      paintNav();
      if (typeof syncAirportDetailTimelineLabel === 'function') {
        syncAirportDetailTimelineLabel();
      }
      // 标题行显隐变了，顶边要重算；地图面板异步定位，再补一次
      syncNavTop();
      setTimeout(syncNavTop, 80);
      if (_current === 'import' && typeof syncImportAlertLayout === 'function') {
        syncImportAlertLayout();
        setTimeout(syncImportAlertLayout, 80);
      }
    } catch (err) {
      console.error('切换视图失败:', err);
    } finally {
      _switching = false;
    }
  }

  // ── 初始化（身份就绪后调用） ───────────────────────────

  // 每次身份就绪都会调用（首次进入、重新选角后），需可重入
  function initViewNav() {
    const usable = allowedViews();
    if (!window.__viewNavReady) watchNavTop();
    buildNav();
    startRadarAlarmBadgePoll();
    if (!usable.length) {
      setListAreaVisible(false);
      setPlainPanelVisible(false);
      setTrendPanelVisible(false);
      setImportPanelVisible(false);
      showBlocked();
      window.__viewNavReady = true;
      return;
    }
    hideBlocked();

    if (window.__viewNavReady && _current) {
      // 重新选角后权限可能变了：当前视图仍有权限就留着，否则按优先级回落
      if (!canView(viewByKey(_current))) {
        toast(`无权访问当前模式，已切换到${usable[0].label}`);
        switchView(usable[0].key, {});
      } else {
        paintNav();
      }
      return;
    }

    const requested = urlView();
    const target = requested || storedView() || usable[0].key;
    const denied = !canView(viewByKey(target));
    // 地址里点名了无权限的视图才提示；本地记忆静默回落
    switchView(target, { notifyDenied: denied && !!requested });
    window.__viewNavReady = true;
  }

  function currentView() {
    return _current;
  }

  window.contentBandTop = contentBandTop;
  window.syncNavTop = syncNavTop;
  window.initViewNav = initViewNav;
  window.switchView = switchView;
  window.currentView = currentView;
  window.isPlainView = () => _current === 'plain';
})();
