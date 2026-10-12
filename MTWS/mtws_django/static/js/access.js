/**
 * 访问控制：角色选择、席位会话、权限门控、超级用户管理
 */
(function () {
  const apiBase = () => `/${window.timeMode || currentTimeMode || 'current'}/api`;

  window.__accessIdentity = null;
  window.__accessModules = [];
  window.__nonLocalGroups = [];
  let _seatPollTimer = null;
  let _pendingQrGroup = null;
  let _roleQrTimer = null;
  let _roleQrExpireTimer = null;
  const ROLE_QR_VISIBLE_MS = 30000;

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

    const searchInput = document.getElementById('search-input');
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

    const suBtn = document.getElementById('superuser-btn');
    setDisp(suBtn, !!id.is_local);

    paintAccessUserInfo();
    updateHostLoginBanner();

    // 超管改权限后席位轮询会带回新权限，重新校验当前视图；
    // 首次进入由 main.js 在加载数据前触发，此处只做后续复核
    if (window.__viewNavReady && !id.needs_role_select && typeof initViewNav === 'function') {
      initViewNav();
    }
  }
  window.applyAccessUi = applyAccessUi;

  function paintAdminUnlock(unlocked) {
    const on = !!unlocked;
    const was = !!window.__adminUnlocked;
    window.__adminUnlocked = on;
    const groupBtn = document.getElementById('superuser-group-btn');
    const toggle = document.getElementById('settings-default-toggle');
    if (groupBtn) groupBtn.style.display = on ? '' : 'none';
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
    const section = document.getElementById('user-info-section');
    const codeEl = document.getElementById('user-code');
    const logoutBtn = document.getElementById('logout-btn');
    if (!section || !codeEl) return;

    if (id.is_local) {
      // 本机：沿用 CAS userCode 展示，由 main.js paintSeatUserInfo 配合
      window.__seatIdentity = {
        role: 'local',
        show_logout: !!id.show_logout,
        label: '',
        is_local: true,
        permissions: id.permissions,
      };
      if (!id.show_logout) {
        section.style.display = 'none';
      } else if (typeof currentToken !== 'undefined' && currentToken) {
        section.style.display = 'flex';
        if (typeof paintSeatUserInfo === 'function') paintSeatUserInfo();
      }
      return;
    }

    section.style.display = id.show_logout ? 'flex' : 'none';
    codeEl.textContent = id.label || id.group_name || '';
    if (logoutBtn) {
      logoutBtn.style.display = id.show_logout ? 'inline-block' : 'none';
      logoutBtn.dataset.seatLogout = '1';
    }
    window.__seatIdentity = {
      role: 'non_local',
      show_logout: !!id.show_logout,
      label: id.label || '',
      is_local: false,
      permissions: id.permissions,
    };
  }

  function updateHostLoginBanner() {
    let bar = document.getElementById('host-login-warn-banner');
    const id = window.__accessIdentity;
    const need = id && !id.is_local && id.host_login_ok === false;
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'host-login-warn-banner';
      bar.style.cssText = 'display:none;background:#8b1a1a;color:#fff;padding:8px 16px;text-align:center;font-size:14px;';
      bar.textContent = '⚠ 本机登录状态异常，非本机用户数据可能无法刷新，请联系本机值班人员重新登录。';
      const offline = document.getElementById('server-offline-banner');
      if (offline && offline.parentNode) {
        offline.parentNode.insertBefore(bar, offline.nextSibling);
      } else {
        document.body.insertBefore(bar, document.body.firstChild);
      }
    }
    bar.style.display = need ? 'block' : 'none';
  }

  function ensureRoleModal() {
    let modal = document.getElementById('access-role-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'access-role-modal';
    modal.innerHTML = `
      <div class="access-role-backdrop"></div>
      <div class="access-role-dialog">
        <h2>请选择你的角色</h2>
        <p class="access-role-hint">未选择角色前无法进入系统</p>
        <div id="access-role-list" class="access-role-list"></div>
        <div id="access-role-qr-wrap" style="display:none;margin-top:16px;text-align:center;">
          <p id="access-role-qr-title">请扫码认证</p>
          <div id="access-role-qrcode"></div>
          <p id="access-role-qr-status"></p>
          <button type="button" id="access-role-qr-cancel" class="action-btn">返回重选</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    const style = document.createElement('style');
    style.textContent = `
      #access-role-modal{position:fixed;inset:0;z-index:99999;display:none;}
      #access-role-modal.show{display:block;}
      .access-role-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.72);}
      .access-role-dialog{position:relative;margin:8vh auto;max-width:480px;background:#1e2430;color:#eee;
        border-radius:8px;padding:24px 28px;box-shadow:0 8px 32px rgba(0,0,0,.45);}
      .access-role-dialog h2{margin:0 0 8px;font-size:20px;}
      .access-role-hint{margin:0 0 16px;opacity:.75;font-size:13px;}
      .access-role-list{display:flex;flex-direction:column;gap:10px;}
      .access-role-item{padding:12px 16px;border:1px solid #3a4556;border-radius:6px;background:#2a3342;
        cursor:pointer;text-align:left;font-size:15px;color:#fff;}
      .access-role-item:hover{border-color:#6ea8fe;background:#334055;}
      #access-role-qrcode img,#access-role-qrcode canvas{max-width:220px;}
    `;
    document.head.appendChild(style);
    document.getElementById('access-role-qr-cancel').onclick = () => {
      stopRoleQrPoll();
      _pendingQrGroup = null;
      document.getElementById('access-role-qr-wrap').style.display = 'none';
      document.getElementById('access-role-list').style.display = '';
    };
    return modal;
  }

  function showRoleModal(groups) {
    const existing = document.getElementById('access-role-modal');
    const qrWrap = document.getElementById('access-role-qr-wrap');
    if (existing && existing.classList.contains('show') && qrWrap && qrWrap.style.display !== 'none') {
      return;
    }
    const modal = ensureRoleModal();
    const list = document.getElementById('access-role-list');
    list.innerHTML = '';
    list.style.display = '';
    document.getElementById('access-role-qr-wrap').style.display = 'none';
    (groups || []).forEach((g) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'access-role-item';
      btn.textContent = g.require_qr ? `${g.name}（需扫码）` : g.name;
      btn.onclick = () => selectRole(g);
      list.appendChild(btn);
    });
    if (!(groups || []).length) {
      list.innerHTML = '<p style="opacity:.8">暂无可用角色，请联系管理员在超级用户中配置非本机用户组。</p>';
    }
    modal.classList.add('show');
  }

  function hideRoleModal() {
    const modal = document.getElementById('access-role-modal');
    if (modal) modal.classList.remove('show');
    stopRoleQrPoll();
  }

  async function selectRole(group) {
    const { data } = await accessFetch('/access/select-role/', {
      method: 'POST',
      body: JSON.stringify({ group_id: group.id }),
    });
    if (!data.success) {
      alert(data.error || '选择角色失败');
      return;
    }
    const needQr = !!(group.require_qr || (data.data && data.data.require_qr));
    if (needQr) {
      _pendingQrGroup = group;
      document.getElementById('access-role-list').style.display = 'none';
      document.getElementById('access-role-qr-wrap').style.display = '';
      document.getElementById('access-role-qr-title').textContent = `请扫码认证：${group.name}`;
      startRoleQrAuth(group);
      return;
    }
    window.__accessIdentity = data.data.identity;
    hideRoleModal();
    applyAccessUi();
    if (typeof window.onAccessReady === 'function') window.onAccessReady();
  }

  function stopRoleQrPoll() {
    if (_roleQrTimer) {
      clearInterval(_roleQrTimer);
      _roleQrTimer = null;
    }
    if (_roleQrExpireTimer) {
      clearTimeout(_roleQrExpireTimer);
      _roleQrExpireTimer = null;
    }
  }

  async function startRoleQrAuth(group) {
    stopRoleQrPoll();
    const statusEl = document.getElementById('access-role-qr-status');
    const box = document.getElementById('access-role-qrcode');
    statusEl.textContent = '正在获取二维码...';
    box.innerHTML = '';
    try {
      const res = await fetch(`${apiBase()}/auth/get-qrcode/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: '{}',
      });
      const data = await res.json();
      if (!data.success) {
        statusEl.textContent = data.error || '获取二维码失败';
        return;
      }
      const b64 = data.data.qr_img_base64;
      if (b64) {
        box.innerHTML = `<img src="data:image/png;base64,${b64}" alt="CAS二维码" style="width:200px;height:auto;"/>`;
      } else {
        box.textContent = '未返回二维码图片';
      }
      statusEl.textContent = '等待扫码...';
      if (_roleQrExpireTimer) clearTimeout(_roleQrExpireTimer);
      _roleQrExpireTimer = setTimeout(() => expireRoleQr(group), ROLE_QR_VISIBLE_MS);
      _roleQrTimer = setInterval(async () => {
        try {
          const r2 = await fetch(`${apiBase()}/auth/check-login/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: '{}',
          });
          const d2 = await r2.json();
          if (d2.success && d2.data && (d2.data.userCode || d2.data.token)) {
            stopRoleQrPoll();
            const userId = d2.data.userCode;
            // 不保存 token 到本机调度；仅登记席位
            const { data: d3 } = await accessFetch('/access/complete-qr-login/', {
              method: 'POST',
              body: JSON.stringify({ group_id: group.id, user_id: userId }),
            });
            if (!d3.success) {
              statusEl.textContent = d3.error || '认证失败';
              return;
            }
            window.__accessIdentity = d3.data.identity;
            hideRoleModal();
            applyAccessUi();
            if (typeof window.onAccessReady === 'function') window.onAccessReady();
          } else if (!d2.success && d2.message !== '等待扫码') {
            // 保持等待
          }
        } catch (e) {
          console.warn(e);
        }
      }, 2000);
    } catch (e) {
      statusEl.textContent = '获取二维码异常';
      console.error(e);
    }
  }

  function expireRoleQr(group) {
    if (_roleQrTimer) {
      clearInterval(_roleQrTimer);
      _roleQrTimer = null;
    }
    _roleQrExpireTimer = null;
    const statusEl = document.getElementById('access-role-qr-status');
    const box = document.getElementById('access-role-qrcode');
    if (!box) return;
    box.innerHTML = `<div style="width:200px;height:200px;margin:0 auto;border:2px dashed #889;color:#ddd;display:flex;align-items:center;justify-content:center;text-align:center;cursor:pointer;">二维码已过期<br>点击重新获取</div>`;
    if (statusEl) statusEl.textContent = '二维码已过期，请点击重新获取';
    box.onclick = () => {
      box.onclick = null;
      startRoleQrAuth(group);
    };
  }

  async function seatLogout() {
    if (typeof clearPopupSeatSession === 'function') clearPopupSeatSession();
    await accessFetch('/access/seat-logout/', { method: 'POST', body: '{}' });
    window.__accessIdentity = null;
    await bootstrapAccess();
  }
  window.accessSeatLogout = seatLogout;

  function startSeatPoll() {
    if (_seatPollTimer) clearInterval(_seatPollTimer);
    _seatPollTimer = setInterval(async () => {
      try {
        const { data } = await accessFetch('/access/session/');
        if (!data.success) return;
        paintAdminUnlock(data.data && data.data.admin_unlocked);
        const id = data.data.identity;
        window.__accessIdentity = id;
        if (id.needs_role_select) {
          showRoleModal(window.__nonLocalGroups);
          applyAccessUi();
          return;
        }
        applyAccessUi();
        updateHostLoginBanner();
        paintAccessUserInfo();
      } catch (e) { /* ignore */ }
    }, 15000);
  }

  async function bootstrapAccess() {
    const { data } = await accessFetch('/access/bootstrap/');
    if (!data.success) {
      console.error('access bootstrap failed', data);
      return null;
    }
    window.__accessIdentity = data.data.identity;
    paintAdminUnlock(data.data.admin_unlocked);
    window.__accessModules = data.data.modules || [];
    window.__nonLocalGroups = data.data.non_local_groups || [];
    applyAccessUi();
    if (data.data.identity.needs_role_select) {
      showRoleModal(window.__nonLocalGroups);
    } else {
      hideRoleModal();
    }
    startSeatPoll();
    return data.data;
  }
  window.bootstrapAccess = bootstrapAccess;

  window.addEventListener('message', (event) => {
    if (event.origin !== window.location.origin) return;
    if (!event.data || event.data.type !== 'mtws-admin-lock') return;
    paintAdminUnlock(false);
  });

  // —— 超级用户管理（独立页） ——
  let _adminGroupsCache = [];
  let _adminModulesCache = [];
  let _adminBound = false;

  function adminPagePath() {
    const tm = window.timeMode || window.currentTimeMode || 'current';
    return `/${tm}/access-admin/`;
  }

  function bindAdminPage() {
    if (_adminBound || !document.getElementById('access-admin-page')) return;
    _adminBound = true;

    const unlockBtn = document.getElementById('access-admin-unlock-btn');
    const pwInput = document.getElementById('access-admin-password');
    if (unlockBtn) unlockBtn.onclick = unlockAdmin;
    if (pwInput) {
      pwInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          unlockAdmin();
        }
      });
      setTimeout(() => pwInput.focus(), 0);
    }
    document.getElementById('access-admin-group-select').onchange = renderAdminPermTable;
    document.getElementById('access-admin-add-group').onclick = addAdminGroup;
    document.getElementById('access-admin-del-group').onclick = delAdminGroup;
    document.getElementById('access-admin-save').onclick = saveAdminGroup;
    document.getElementById('access-admin-chg-pw').onclick = changeAdminPassword;
    const exitBtn = document.getElementById('access-admin-exit');
    if (exitBtn) exitBtn.onclick = exitAdminSession;
    document.getElementById('access-admin-export').onclick = exportAdminConfig;
    const importFile = document.getElementById('access-admin-import-file');
    document.getElementById('access-admin-import').onclick = () => { importFile.value = ''; importFile.click(); };
    importFile.onchange = () => openImportModal(importFile.files[0]);
    document.getElementById('access-import-cancel').onclick = closeImportModal;
    document.getElementById('access-import-backdrop').onclick = closeImportModal;
    document.getElementById('access-import-ok').onclick = submitImport;
    document.getElementById('bl-add').onclick = addBlacklist;
    document.getElementById('access-admin-bl-title').onclick = openBlacklistModal;
    document.getElementById('access-bl-close').onclick = closeBlacklistModal;
    document.getElementById('access-bl-backdrop').onclick = closeBlacklistModal;
    document.querySelectorAll('.access-home-link').forEach((a) => {
      a.addEventListener('click', goBackHome);
    });
    window.addEventListener('pagehide', lockAdminSession);

    tryRestoreAdminSession();
  }

  function showAdminMain() {
    document.getElementById('access-admin-unlock-pane').style.display = 'none';
    document.getElementById('access-admin-main').style.display = '';
  }

  function openBlacklistModal() {
    document.getElementById('access-bl-modal').hidden = false;
    loadBlacklist();
  }

  function closeBlacklistModal() {
    document.getElementById('access-bl-modal').hidden = true;
  }

  async function tryRestoreAdminSession() {
    const { data } = await accessFetch('/access/admin/groups/');
    if (data.success) {
      showAdminMain();
      _adminGroupsCache = data.data.groups || [];
      _adminModulesCache = data.data.modules || [];
      fillAdminGroupSelect();
      renderAdminPermTable();
    }
  }

  async function unlockAdmin() {
    const pw = document.getElementById('access-admin-password').value;
    const { data } = await accessFetch('/access/admin/unlock/', {
      method: 'POST',
      body: JSON.stringify({ password: pw }),
    });
    const msg = document.getElementById('access-admin-unlock-msg');
    if (!data.success) {
      msg.textContent = data.error || '解锁失败';
      return;
    }
    msg.textContent = '';
    showAdminMain();
    await loadAdminGroups();
  }

  function fillAdminGroupSelect() {
    const sel = document.getElementById('access-admin-group-select');
    sel.innerHTML = '';
    _adminGroupsCache.forEach((g) => {
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = g.is_local ? `${g.name}（本机）` : g.name;
      sel.appendChild(opt);
    });
  }

  async function loadAdminGroups() {
    const { data } = await accessFetch('/access/admin/groups/');
    if (!data.success) {
      alert(data.error || '加载失败');
      return;
    }
    _adminGroupsCache = data.data.groups || [];
    _adminModulesCache = data.data.modules || [];
    fillAdminGroupSelect();
    renderAdminPermTable();
  }

  function currentAdminGroup() {
    const id = Number(document.getElementById('access-admin-group-select').value);
    return _adminGroupsCache.find((g) => g.id === id);
  }

  function renderAdminPermTable() {
    const g = currentAdminGroup();
    const wrap = document.getElementById('access-admin-perm-table');
    const qrLabel = document.getElementById('access-admin-qr-label');
    if (!g) { wrap.innerHTML = ''; return; }
    qrLabel.style.display = g.is_local ? 'none' : '';
    document.getElementById('access-admin-require-qr').checked = !!g.require_qr;
    document.getElementById('access-admin-del-group').style.display = g.is_local ? 'none' : '';

    const catOrder = ['function', 'views', 'shared', 'settings'];
    const catNames = {
      function: '通用功能区',
      views: '视图设置',
      shared: '其它功能',
      settings: '设置选项',
    };
    const grouped = {};
    _adminModulesCache.forEach((m) => {
      const cat = m.category || 'other';
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(m);
    });

    const permCell = (m, k, enabled, checked) => {
      if (!enabled) return '<td class="access-perm-na">-</td>';
      const hint = m[`hint_${k}`] || '';
      return `<td class="access-perm-check"><label class="access-perm-opt"><input type="checkbox" data-mod="${m.code}" data-k="${k}" ${checked ? 'checked' : ''}/>${hint ? `<span class="access-perm-hint">${hint}</span>` : ''}</label></td>`;
    };
    const canGrantWrite = (m) => !!m.has_write && !(m.local_write_only && !g.is_local);
    let html = `<table class="access-perm-table">
      <colgroup>
        <col class="access-col-cat"><col class="access-col-mod">
        <col class="access-col-perm"><col class="access-col-perm">
      </colgroup>
      <thead><tr>
      <th>分类</th><th>模块</th><th>显示</th><th>写入</th></tr></thead><tbody>`;
    let firstCat = true;
    catOrder.forEach((cat) => {
      const mods = grouped[cat] || [];
      if (!mods.length) return;
      mods.forEach((m, idx) => {
        const p = (g.permissions || {})[m.code] || {};
        const rowBits = [];
        if (idx === 0 && !firstCat) rowBits.push('access-cat-start');
        if (m.parent) rowBits.push('access-mod-child-row');
        const rowClass = rowBits.length ? ` class="${rowBits.join(' ')}"` : '';
        html += `<tr${rowClass}>`;
        if (idx === 0) {
          html += `<td class="access-cat-cell" rowspan="${mods.length}">${catNames[cat] || cat}</td>`;
          firstCat = false;
        }
        const nameCls = m.parent ? 'access-mod-name access-mod-child' : 'access-mod-name';
        html += `<td class="${nameCls}">${m.name}</td>
        ${permCell(m, 'display', true, !!p.display)}
        ${permCell(m, 'write', canGrantWrite(m), !!p.write)}
      </tr>`;
      });
    });
    html += '</tbody></table>';
    wrap.innerHTML = html;

    const box = (mod, k) => wrap.querySelector(`input[data-mod="${mod}"][data-k="${k}"]`);
    const checkDisplay = (mod) => {
      const disp = box(mod, 'display');
      if (disp) disp.checked = true;
      const meta = _adminModulesCache.find((m) => m.code === mod);
      if (meta && meta.parent) checkDisplay(meta.parent);
    };
    const clearModule = (mod) => {
      wrap.querySelectorAll(`input[data-mod="${mod}"]`).forEach((x) => { x.checked = false; });
      _adminModulesCache.filter((m) => m.parent === mod).forEach((m) => clearModule(m.code));
    };

    wrap.querySelectorAll('input[type=checkbox]').forEach((cb) => {
      cb.addEventListener('change', () => {
        const mod = cb.getAttribute('data-mod');
        const k = cb.getAttribute('data-k');
        if (k === 'write' && cb.checked && !g.is_local) {
          const qr = document.getElementById('access-admin-require-qr');
          if (!qr.checked) {
            alert('勾选写入权限时必须同时勾选扫码认证');
            cb.checked = false;
            return;
          }
        }
        if (VIEW_MODULES.includes(mod) && k === 'display' && !cb.checked) {
          if (!countCheckedViews(wrap)) {
            alert('主页、地图、翻译、实况趋势、报文入库告警至少选中一个');
            cb.checked = true;
            return;
          }
        }
        if (cb.checked) {
          checkDisplay(mod);
        } else if (k === 'display') {
          clearModule(mod);
        }
      });
    });
  }

  const VIEW_MODULES = ['view_home', 'view_map', 'view_plain', 'view_trend', 'import_alert'];

  function countCheckedViews(wrap) {
    return VIEW_MODULES.filter((code) => {
      const cb = wrap.querySelector(`input[data-mod="${code}"][data-k="display"]`);
      return cb && cb.checked;
    }).length;
  }

  async function saveAdminGroup() {
    const g = currentAdminGroup();
    if (!g) return;
    const wrap = document.getElementById('access-admin-perm-table');
    const permissions = {};
    _adminModulesCache.forEach((m) => {
      permissions[m.code] = { display: false, write: false };
    });
    wrap.querySelectorAll('input[type=checkbox]').forEach((cb) => {
      const mod = cb.getAttribute('data-mod');
      const k = cb.getAttribute('data-k');
      if (!permissions[mod]) permissions[mod] = {};
      permissions[mod][k] = cb.checked;
    });
    if (!VIEW_MODULES.some((code) => (permissions[code] || {}).display)) {
      alert('主页、地图、翻译、实况趋势、报文入库告警至少选中一个');
      return;
    }
    const require_qr = g.is_local ? false : document.getElementById('access-admin-require-qr').checked;
    const anyWrite = Object.values(permissions).some((p) => p.write);
    if (!g.is_local && anyWrite && !require_qr) {
      alert('勾选写入权限时必须同时勾选扫码认证');
      return;
    }
    const { data } = await accessFetch(`/access/admin/groups/${g.id}/`, {
      method: 'PUT',
      body: JSON.stringify({ require_qr, permissions }),
    });
    if (!data.success) {
      alert(data.error || '保存失败');
      return;
    }
    alert('已保存');
    const keepId = data.data.id;
    await loadAdminGroups();
    document.getElementById('access-admin-group-select').value = String(keepId);
    renderAdminPermTable();
  }

  async function addAdminGroup() {
    const name = prompt('新非本机用户组名称');
    if (!name) return;
    const { data } = await accessFetch('/access/admin/groups/', {
      method: 'POST',
      body: JSON.stringify({ name, require_qr: false }),
    });
    if (!data.success) {
      alert(data.error || '创建失败');
      return;
    }
    await loadAdminGroups();
    document.getElementById('access-admin-group-select').value = String(data.data.id);
    renderAdminPermTable();
  }

  async function delAdminGroup() {
    const g = currentAdminGroup();
    if (!g || g.is_local) return;
    if (!confirm(`确认删除用户组「${g.name}」？`)) return;
    const { data } = await accessFetch(`/access/admin/groups/${g.id}/`, { method: 'DELETE' });
    if (!data.success) {
      alert(data.error || '删除失败');
      return;
    }
    await loadAdminGroups();
  }

  async function exportAdminConfig() {
    const userCode = (typeof currentUserCode !== 'undefined' ? currentUserCode : null) || window.currentUserCode;
    const res = await fetch(`${apiBase()}/access/admin/export/`, {
      credentials: 'same-origin',
      headers: userCode ? { 'X-User-Code': userCode } : {},
    });
    if (!res.ok) {
      let msg = '导出失败';
      try { msg = (await res.json()).error || msg; } catch (e) { /* ignore */ }
      alert(msg);
      return;
    }
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="([^"]+)"/);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = match ? match[1] : 'mtws_access.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  let _importConfig = null;

  async function openImportModal(file) {
    if (!file) return;
    let config;
    try {
      config = JSON.parse(await file.text());
    } catch (e) {
      alert('文件不是有效的 JSON');
      return;
    }
    if (!config || config.format !== 'mtws-access-config') {
      alert('不是用户组配置导出文件');
      return;
    }
    _importConfig = config;
    const groups = config.groups || [];
    const nonLocal = groups.filter((g) => !g.is_local).length;
    const hasLocal = groups.some((g) => g.is_local);
    const when = config.exported_at ? `导出于 ${config.exported_at.replace('T', ' ').slice(0, 19)}，` : '';
    document.getElementById('access-import-summary').textContent =
      `${file.name}：${when}${hasLocal ? '含本机组、' : ''}非本机组 ${nonLocal} 个，黑名单 ${(config.blacklist || []).length} 条。`;
    document.querySelector('input[name="access-import-mode"][value="merge"]').checked = true;
    document.getElementById('access-import-modal').hidden = false;
  }

  function closeImportModal() {
    document.getElementById('access-import-modal').hidden = true;
    _importConfig = null;
  }

  async function submitImport() {
    if (!_importConfig) return;
    const mode = document.querySelector('input[name="access-import-mode"]:checked').value;
    if (mode === 'replace' && !confirm('覆盖导入会删除文件中没有的非本机组，并替换整个黑名单，确定继续？')) return;
    const { data } = await accessFetch('/access/admin/import/', {
      method: 'POST',
      body: JSON.stringify({ mode, config: _importConfig }),
    });
    if (!data.success) {
      alert(data.error || '导入失败');
      return;
    }
    closeImportModal();
    const s = data.data || {};
    alert(`导入完成：新增 ${s.created || 0} 个组，更新 ${s.updated || 0} 个组，删除 ${s.deleted || 0} 个组，新增黑名单 ${s.blacklist_added || 0} 条。`);
    await loadAdminGroups();
  }

  async function changeAdminPassword() {
    const old_password = prompt('当前口令');
    if (old_password == null) return;
    const new_password = prompt('新口令（至少6位）');
    if (!new_password) return;
    const { data } = await accessFetch('/access/admin/change-password/', {
      method: 'POST',
      body: JSON.stringify({ old_password, new_password }),
    });
    alert(data.success ? '口令已修改' : (data.error || '修改失败'));
  }

  async function loadBlacklist() {
    const { data } = await accessFetch('/access/admin/blacklist/');
    const box = document.getElementById('access-admin-blacklist');
    if (!data.success) {
      box.textContent = data.error || '';
      return;
    }
    const rows = data.data || [];
    box.innerHTML = rows.map((r) =>
      `<div style="margin:4px 0;">#${r.id} ${r.user_id} ${r.remark || ''}
        <button type="button" data-bl="${r.id}" class="action-btn">删除</button></div>`
    ).join('') || '<p style="opacity:.7">（空）</p>';
    box.querySelectorAll('button[data-bl]').forEach((btn) => {
      btn.onclick = async () => {
        await accessFetch(`/access/admin/blacklist/${btn.getAttribute('data-bl')}/`, { method: 'DELETE' });
        loadBlacklist();
      };
    });
  }

  async function addBlacklist() {
    const user_id = document.getElementById('bl-user-id').value.trim();
    const remark = document.getElementById('bl-remark').value.trim();
    const { data } = await accessFetch('/access/admin/blacklist/', {
      method: 'POST',
      body: JSON.stringify({ user_id, remark }),
    });
    if (!data.success) {
      alert(data.error || '添加失败');
      return;
    }
    document.getElementById('bl-user-id').value = '';
    document.getElementById('bl-remark').value = '';
    loadBlacklist();
  }

  async function exitAdminSession() {
    await accessFetch('/access/admin/lock/', { method: 'POST', body: '{}' });
    const main = document.getElementById('access-admin-main');
    const pane = document.getElementById('access-admin-unlock-pane');
    if (main) main.style.display = 'none';
    if (pane) pane.style.display = '';
    const msg = document.getElementById('access-admin-unlock-msg');
    if (msg) msg.textContent = '';
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type: 'mtws-admin-lock' }, window.location.origin);
    }
  }

  function lockAdminSession() {
    try {
      const url = `${apiBase()}/access/admin/lock/`;
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob(['{}'], { type: 'application/json' }));
      } else {
        fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          keepalive: true,
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
      }
    } catch (e) { /* ignore */ }
  }

  function goBackHome(e) {
    if (e) e.preventDefault();
    lockAdminSession();
    const home = `/${window.timeMode || 'current'}/`;
    try {
      if (window.opener && !window.opener.closed) {
        window.opener.focus();
        window.close();
        return;
      }
    } catch (err) { /* ignore cross-origin */ }
    window.location.href = home;
  }

  function openSuperuserAdmin() {
    const url = adminPagePath();
    const w = window.open(url, 'mtws_access_admin');
    if (w) {
      try { w.focus(); } catch (e) { /* ignore */ }
    } else {
      window.location.href = url;
    }
  }
  window.openSuperuserAdmin = openSuperuserAdmin;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindAdminPage);
  } else {
    bindAdminPage();
  }
})();
