/**
 * 模块开关门控，以及超级用户解锁（只用于编辑 default 模板）。
 */
(function () {
  const apiBase = () => `/${window.timeMode || currentTimeMode || 'current'}/api`;

  window.__accessIdentity = null;
  window.__modules = null;

  function hasAccess(moduleCode, action) {
    const id = window.__accessIdentity;
    if (!id) return false;
    const p = (id.permissions || {})[moduleCode] || {};
    const visible = !!(p.display || p.write);
    if (action === 'display') return visible;
    if (action === 'write') return visible && !!p.write;
    return false;
  }
  window.hasAccess = hasAccess;

  async function accessFetch(path, options = {}) {
    const opts = Object.assign({ credentials: 'same-origin' }, options);
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    const userCode = (typeof currentUserCode !== 'undefined' ? currentUserCode : null) || window.currentUserCode;
    if (userCode) opts.headers['X-User-Code'] = userCode;
    const res = await fetch(`${apiBase()}${path}`, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { /* ignore */ }
    return { res, data };
  }

  function applyAccessUi() {
    const id = window.__accessIdentity;
    if (!id) return;

    const setDisp = (el, on) => {
      if (!el) return;
      el.style.display = on ? '' : 'none';
    };

    setDisp(document.getElementById('nwp-btn'), hasAccess('nwp', 'display'));
    if (!hasAccess('nwp', 'display') && typeof nwpEnabled !== 'undefined' && nwpEnabled) {
      nwpEnabled = false;
      if (typeof _nwpCache !== 'undefined') _nwpCache = {};
      if (typeof clearAllNwpOverlays === 'function') clearAllNwpOverlays();
      if (typeof updateNwpButtonState === 'function') updateNwpButtonState();
    }
    setDisp(document.getElementById('refresh-btn'), hasAccess('refresh_btn', 'display'));
    setDisp(document.getElementById('settings-btn'), hasAccess('settings_btn', 'display'));

    const searchBtn = document.getElementById('search-btn');
    const searchClear = document.getElementById('search-clear-btn');
    const showSearch = hasAccess('search', 'display');
    setDisp(searchBtn, showSearch);
    const searchWrap = document.querySelector('.search-input-wrap');
    setDisp(searchWrap, showSearch);
    setDisp(searchClear, showSearch);

    const popupSection = document.querySelector('.popup-control-section');
    const canPopup = hasAccess('metar_popup', 'display');
    setDisp(popupSection, canPopup);
    if (!canPopup && typeof dismissMetarPopupsForAccess === 'function') {
      dismissMetarPopupsForAccess();
    }

    setDisp(document.getElementById('superuser-btn'), true);
    paintAccessUserInfo();

    if (window.__viewNavReady && typeof initViewNav === 'function') {
      initViewNav();
    }
  }
  window.applyAccessUi = applyAccessUi;

  function paintAdminUnlock(unlocked) {
    const on = !!unlocked;
    const was = !!window.__adminUnlocked;
    window.__adminUnlocked = on;
    const toggle = document.getElementById('settings-default-toggle');
    if (toggle) toggle.style.display = on ? '' : 'none';
    document.body.classList.toggle('is-superuser', on);
    if (typeof window.__paintSuperButtons === 'function') window.__paintSuperButtons();
    if (!on) {
      const box = document.getElementById('settings-admin-unlock');
      if (box) box.style.display = 'none';
      if (was && typeof window.exitSettingsTemplate === 'function') window.exitSettingsTemplate();
    }
  }

  function paintAccessUserInfo() {
    const id = window.__accessIdentity;
    if (!id) return;
    window.__seatIdentity = {
      role: 'user',
      show_logout: !!id.show_logout,
      label: id.label || '',
      permissions: id.permissions,
    };
    const section = document.getElementById('user-info-section');
    if (!section) return;
    if (!id.show_logout) {
      section.style.display = 'none';
      return;
    }
    if (typeof currentToken !== 'undefined' && currentToken) {
      section.style.display = 'flex';
      if (typeof paintSeatUserInfo === 'function') paintSeatUserInfo();
    }
  }

  async function bootstrapAccess() {
    const { data } = await accessFetch('/access/bootstrap/');
    if (!data.success) {
      console.error('access bootstrap failed', data);
      return null;
    }
    window.__accessIdentity = data.data.identity;
    window.__modules = data.data.modules || {};
    paintAdminUnlock(data.data.admin_unlocked);
    applyAccessUi();
    return data.data;
  }
  window.bootstrapAccess = bootstrapAccess;
})();
