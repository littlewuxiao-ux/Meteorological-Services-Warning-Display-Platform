function mergeManualForecastCell(existingValue, nextValue) {
    const existing = String(existingValue || '').trim();
    const next = String(nextValue || '').trim();
    if (!next || next.toUpperCase() === 'NSW') return existing;
    if (!existing || existing.toUpperCase() === 'NSW') return next;
    if (` ${existing} `.includes(` ${next} `)) return existing;
    return `${existing} ${next}`;
}

// OMICS can be opened directly on port 8002 or through IWMS at /omics/.
// Keep API requests under the current deployment prefix in both modes.
window.OMICS_API_URL = function(path) {
    const clean = String(path || '').replace(/^\/+/, '');
    return `${window.location.pathname.startsWith('/omics') ? '/omics/api' : '/api'}/${clean}`;
};
const _omicsNativeFetch = window.fetch.bind(window);
window.fetch = function(input, init) {
    if (typeof input === 'string' && input.startsWith('/api/')) {
        // OMICS_API_URL 接收的是接口相对路径；这里去掉原始 /api 前缀，避免生成 /api/api/...
        input = window.OMICS_API_URL(input.replace(/^\/api\//, ''));
    }
    return _omicsNativeFetch(input, init);
};

window.OMICS_mergeManualForecastCell = mergeManualForecastCell;

document.addEventListener('DOMContentLoaded', async () => {
    const loginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const exitAppBtn = document.getElementById('exit-app-btn');
    const userInfoDiv = document.getElementById('user-info');
    const userIdDisplay = document.getElementById('user-id-display');

    const loginModal = document.getElementById('login-modal');
    const qrImage = document.getElementById('qr-image');
    const qrStatusText = document.getElementById('qr-status-text');
    const closeLoginModalBtn = document.getElementById('close-login-modal');

    const settingsBtn = document.getElementById('settings-toggle-btn');

    const modeRadios = document.querySelectorAll('input[name="forecast-mode"]');
    const timeRadios = document.querySelectorAll('input[name="time-range"]');
    const customStartInput = document.getElementById('custom-start-time');
    const customEndInput = document.getElementById('custom-end-time');
    const datePickerInput = document.getElementById('base-date-picker');

    const startTimeHidden = document.getElementById('start-time');
    const endTimeHidden = document.getElementById('end-time');

    const downloadAirports = document.getElementById('download-airports');
    const manualAirportDefault = document.getElementById('manual-airport-default');
    const manualAirportAll = document.getElementById('manual-airport-all');
    const manualAirportAllLabel = document.getElementById('manual-airport-all-label');
    const fetchManualBtn = document.getElementById('fetch-manual-btn');
    const fetchTafListBtn = document.getElementById('fetch-taf-list-btn');
    const importTafMetarBtn = document.getElementById('import-taf-metar-btn');

    const metarInput = document.getElementById('metar-input');
    const addMetarBtn = document.getElementById('add-metar-btn');
    const airportBtnsContainer = document.getElementById('dynamic-airport-buttons-container');

    const scoreButton = document.getElementById('score-button');
    const loader = document.getElementById('loader');
    let resultsContainer;
    const manualGridContainer = document.getElementById('manual-forecast-grid-container');
    const generateGridBtn = document.getElementById('generate-grid-btn');
    const pasteExcelBtn = document.getElementById('paste-excel-btn');

    const metarModal = document.getElementById('metar-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalDisplay = document.getElementById('modal-metar-display');
    const closeMetarModalBtn = document.getElementById('close-metar-modal');

    const phenomenaContainer = document.getElementById('phenomena-settings-container');
    const resetPhenomenaBtn = document.getElementById('reset-phenomena-btn');

    let apiToken = null;

    const UNIFIED_AUTH_STATUS_URL = '/auth/status';
    const UNIFIED_AUTH_UPDATE_URL = '/auth/update';
    const UNIFIED_AUTH_CLEAR_URL = '/auth/clear';
    const SETTINGS_CONFIG_URL = window.OMICS_API_URL('settings_config');

    function isRealUserCode(userCode) {
        const code = String(userCode || '').trim();
        if (!code) return false;
        return !['--', '-', 'OFFLINE', 'UNKNOWN', 'UNDEFINED', 'NULL', 'NONE'].includes(code.toUpperCase());
    }

    function isUsableAuthToken(token) {
        const value = String(token || '').trim();
        if (!value) return false;
        return !['--', '-', 'UNDEFINED', 'NULL', 'NONE'].includes(value.toUpperCase());
    }

    function isLocalBrowserHost() {
        const h = String(location.hostname || '').toLowerCase();
        return h === '127.0.0.1' || h === 'localhost' || h === '::1';
    }

    // 🌟 配置持久化根治(方案A):优先用 <script> 同步加载的 window.OMICS_CONFIG 作为唯一数据源,
    //   再用它回填 localStorage(仅作兼容缓存)。fetch 仅作极端兜底。
    //   这样浏览器清了 localStorage 也不会把空值 PATCH 回去覆盖磁盘配置。
    function cfgBlock(key) {
        const c = window.OMICS_CONFIG || window.OMICS_SETTINGS_CONFIG || {};
        return c && typeof c === 'object' ? c[key] : undefined;
    }
    async function loadSettingsConfigFromServer() {
        try { return await window.OMICSSettings.load(); }
        catch (error) { window.OMICSUI?.notify(error.message, 'error'); return window.OMICS_CONFIG || null; }
    }

    function buildPathsBlock() {
        const s = cfgBlock('paths') || {};
        return {
            taf_excel_path: localStorage.getItem('taf_excel_path') || s.taf_excel_path || '',
            manual_excel_path: localStorage.getItem('manual_excel_path') || s.manual_excel_path || '',
            manual_forecast_path: localStorage.getItem('manual_forecast_path') || s.manual_forecast_path || '',
            backup_save_path: localStorage.getItem('backup_save_path') || s.backup_save_path || ''
        };
    }
    function buildDefaultAirportsBlock() {
        const s = cfgBlock('default_airports') || {};
        return {
            manual: localStorage.getItem('sf_def_manual_aps') || s.manual || 'ZBAA ZGSZ ZHEC ZSHC',
            taf: localStorage.getItem('sf_def_taf_aps') || s.taf || 'ZHEC'
        };
    }
    function buildThresholdsBlock() {
        const s = cfgBlock('thresholds') || {};
        return {
            global: (globalThresholds && Object.keys(globalThresholds).length) ? globalThresholds : (s.global || {}),
            custom_airports: (customAirportsThresholds && Object.keys(customAirportsThresholds).length) ? customAirportsThresholds : (s.custom_airports || {})
        };
    }
    function buildPublishBlock() {
        const s = cfgBlock('publish') || {};
        let groups = null, ec = null;
        try { groups = localStorage.getItem('pb_airport_groups') ? JSON.parse(localStorage.getItem('pb_airport_groups')) : null; } catch (e) {}
        try { ec = localStorage.getItem('pb_auto_ec_cfg') ? JSON.parse(localStorage.getItem('pb_auto_ec_cfg')) : null; } catch (e) {}
        return {
            airport_groups: (groups && groups.length) ? groups : (s.airport_groups || []),
            auto_ec_cfg: (ec && Object.keys(ec).length) ? ec : (s.auto_ec_cfg || {})
        };
    }

    function buildSettingsConfigSnapshot() {
        return {
            personnel_dict: personnelDict || {},
            paths: buildPathsBlock(),
            default_airports: buildDefaultAirportsBlock(),
            phenomena_config: phenomenaSettings || {},
            thresholds: buildThresholdsBlock(),
            publish: buildPublishBlock()
        };
    }

    function saveSettingsConfigToServer(settings) {
        return window.OMICSSettings.patch(settings);
    }

    function syncSettingsConfigToServer() {
        return saveSettingsConfigToServer(buildSettingsConfigSnapshot());
    }

    // 🌟 分块 PATCH:只提交改动的那一块,后端读盘叠加保留其余字段。
    // 避免改 A 设置时拿整个内存快照覆盖 B/C(阈值/人员/权限被冲的根因)。
    function patchSettingsConfig(partial) {
        return saveSettingsConfigToServer(partial);
    }
    window.OMICS_patchSettingsConfig = patchSettingsConfig;

    window.OMICS_syncSettingsConfig = syncSettingsConfigToServer;

    async function fetchUnifiedAuthStatus() {
        try {
            const res = await fetch(UNIFIED_AUTH_STATUS_URL, { cache: 'no-store' });
            const data = await res.json();
            return data.success ? data : null;
        } catch (e) {
            console.warn('读取 Nginx 统一登录态失败', e);
            return null;
        }
    }

    async function updateUnifiedAuth(token, userCode, displayName = null) {
        if (!isUsableAuthToken(token) || !isRealUserCode(userCode)) return;
        try {
            await fetch(UNIFIED_AUTH_UPDATE_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, userCode, displayName, source: 'OMICS' })
            });
        } catch (e) {
            console.warn('同步 OMICS 登录态到 Nginx 失败', e);
        }
    }

    async function clearUnifiedAuth() {
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                await fetch(UNIFIED_AUTH_CLEAR_URL, {
                    method: 'POST', cache: 'no-store', keepalive: true,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source: 'OMICS', expired: false })
                });
                const status = await fetchUnifiedAuthStatus();
                if (!status || !status.logged_in) return true;
            } catch (e) {
                console.warn('清空 Nginx 统一登录态失败', e);
            }
            await new Promise(resolve => setTimeout(resolve, 200));
        }
        return false;
    }

    // 控制台后台定期校验 token,过期时会清空统一登录态。
    // OMICS 轮询发现统一态被清空(且本页面仍认为已登录)时,自动登出并提示重新登录。
    let unifiedAuthWatchTimer = null;
    function startUnifiedAuthWatch() {
        if (unifiedAuthWatchTimer) return;
        unifiedAuthWatchTimer = setInterval(async () => {
            if (!apiToken) return;
            const unified = await fetchUnifiedAuthStatus();
            if (!unified) return; // 接口异常不误判
            if (!unified.logged_in) {
                if (unified.expired) {
                    console.warn('统一登录态已失效(控制台校验),OMICS 自动登出');
                    performAutoLogout();
                } else {
                    // 控制台重启后状态丢失(非过期)-> 回灌本地 token,无需刷新页面
                    console.info('检测到控制台统一登录态为空(可能刚重启),回灌本地 token');
                    const uid = localStorage.getItem('sf_userId') || null;
                    if (isUsableAuthToken(apiToken) && isRealUserCode(uid)) {
                        await updateUnifiedAuth(apiToken, uid, personnelDict[uid] || null);
                    }
                }
            }
        }, 5000);
    }
    function stopUnifiedAuthWatch() {
        if (unifiedAuthWatchTimer) {
            clearInterval(unifiedAuthWatchTimer);
            unifiedAuthWatchTimer = null;
        }
    }
    function performAutoLogout() {
        stopUnifiedAuthWatch();
        clearLocalAuthState();
        try { userInfoDiv.classList.add('hidden'); } catch (e) {}
        try { loginBtn.classList.remove('hidden'); } catch (e) {}
        const adminSection = document.getElementById('pane-admin');
        if (adminSection) {
            adminSection.classList.add('hidden');
            adminSection.style.display = 'none';
        }
        try { updateDisplayUserName(); } catch (e) {}
        alert('登录已过期或异地登录,已自动登出,请重新扫码登录。');
    }

    function saveTokenForBothApps(token, userCode = null) {
        apiToken = token || null;
        if (token) {
            localStorage.setItem('sf_weather_token', token);
            localStorage.setItem('mtws_token', token);
        }
        if (userCode) {
            localStorage.setItem('sf_userId', userCode);
            localStorage.setItem('mtws_userCode', userCode);
        }
    }

    function clearLocalAuthState() {
        apiToken = null;
        localStorage.removeItem('sf_weather_token');
        localStorage.removeItem('sf_userId');
        localStorage.removeItem('mtws_token');
        localStorage.removeItem('mtws_userCode');
    }
    let pollTimer = null;
    let currentMode = 'manual';
    let baseDate = new Date();
    let storedMetars = {};
    window.getPublishMetar = (icao) => (storedMetars[String(icao || '').toUpperCase()] || []).join('\n');
    window.getPublishMetar = (icao) => (storedMetars[String(icao || '').toUpperCase()] || []).join('\n');
    // 🌟 需求3:从纯文本配置缓存中提取机场字典
    let savedAirportTextDict = localStorage.getItem('sf_custom_airport_text_dict');
    if (savedAirportTextDict) {
        try {
            const customDict = JSON.parse(savedAirportTextDict);
            if (customDict.coords) Object.assign(window.AIRPORT_COORDS, customDict.coords);
            if (customDict.names) Object.assign(window.GLOBAL_AIRPORT_NAME_MAP, customDict.names);
        } catch(e) {}
    }
    // 🌟 全局调取 publish.js 中的核心枢纽中文字典
    const AIRPORT_NAME_MAP = window.GLOBAL_AIRPORT_NAME_MAP || {};

    const DEFAULT_PHEN_CATEGORIES = {
        '雷雨类': ['TSRA'],
        '积冰类': ['FZDZ', 'FZRA', 'SN', 'SG', 'PL'],
        '强降水(无雷)类': ['RA', 'SHRA'],
        '特殊类': ['GR', 'GS', 'FC', 'SQ']
    };
    const serverSettingsConfig = await loadSettingsConfigFromServer();
    window.OMICS_SETTINGS_CONFIG = serverSettingsConfig || {};
    const serverPaths = serverSettingsConfig?.paths || {};
    const serverDefaultAirports = serverSettingsConfig?.default_airports || {};
    const serverThresholds = serverSettingsConfig?.thresholds || {};
    const serverPublish = serverSettingsConfig?.publish || {};
    if (serverPaths.taf_excel_path) localStorage.setItem('taf_excel_path', serverPaths.taf_excel_path);
    if (serverPaths.manual_excel_path) localStorage.setItem('manual_excel_path', serverPaths.manual_excel_path);
    if (serverPaths.backup_save_path) localStorage.setItem('backup_save_path', serverPaths.backup_save_path);
    if (serverDefaultAirports.manual) localStorage.setItem('sf_def_manual_aps', serverDefaultAirports.manual);
    if (serverDefaultAirports.taf) localStorage.setItem('sf_def_taf_aps', serverDefaultAirports.taf);
    if (serverPublish.airport_groups && serverPublish.airport_groups.length) localStorage.setItem('pb_airport_groups', JSON.stringify(serverPublish.airport_groups));
    if (serverPublish.auto_ec_cfg && Object.keys(serverPublish.auto_ec_cfg).length) localStorage.setItem('pb_auto_ec_cfg', JSON.stringify(serverPublish.auto_ec_cfg));
    if (serverSettingsConfig?.phenomena_config) localStorage.setItem('phenomena_config', JSON.stringify(serverSettingsConfig.phenomena_config));

    let phenomenaSettings = serverSettingsConfig?.phenomena_config || JSON.parse(localStorage.getItem('phenomena_config')) || JSON.parse(JSON.stringify(DEFAULT_PHEN_CATEGORIES));

    const ADMIN_ID = '41060711';
    const DEFAULT_PERSONNEL = {
        "40690141": "曹骏", "347657": "崔云云", "41060711": "吴霄",
        "41984815": "杨风良", "41917213": "罗亦杰", "42464638": "张倩", "42623776": "苏永发"
    };
    let personnelDict = { ...DEFAULT_PERSONNEL, ...(serverSettingsConfig?.personnel_dict || {}), ...(JSON.parse(localStorage.getItem('personnel_dict') || '{}')) };
    let settingsPassword = localStorage.getItem('settings_pwd') || '123';

    // Shared by script.js and publish.js, which both listen for this button.
    window.OMICS_authorizeSettings = function () {
        const userId = String(localStorage.getItem('sf_userId') || '').trim();
        const token = String(apiToken || localStorage.getItem('sf_weather_token') || '').trim();
        if (token && userId && userId === ADMIN_ID) return true;
        const inputPwd = prompt("安全验证:仅管理员(吴霄)可免密进入,其他账号需输入管理密码。");
        if (inputPwd === null || inputPwd.trim() === '' || inputPwd !== settingsPassword) {
            alert("密码错误,拒绝访问!");
            return false;
        }
        return true;
    };

    const amdSwitch = document.getElementById('admin-recognize-amd');
    if (amdSwitch) {
        const savedAmdState = localStorage.getItem('sf_recognize_amd');
        amdSwitch.checked = (savedAmdState === 'true');
        amdSwitch.addEventListener('change', (e) => {
            localStorage.setItem('sf_recognize_amd', e.target.checked);
        });
    }

    async function syncPersonnelMappingToServer() {
        try {
            await fetch('/api/personnel_mapping', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mapping: personnelDict })
            });
        } catch (e) { console.warn('人员映射同步到后端失败', e); }
    }

    async function loadPersonnelMappingFromServer() {
        try {
            const res = await fetch('/api/personnel_mapping');
            const data = await res.json();
            if (data.success && data.data) {
                personnelDict = { ...DEFAULT_PERSONNEL, ...data.data, ...personnelDict };
                localStorage.setItem('personnel_dict', JSON.stringify(personnelDict));
            }
        } catch (e) { console.warn('人员映射从后端加载失败', e); }
    }

    function renderPersonnelList() {
        const listEl = document.getElementById('personnel-list');
        if (!listEl) return;
        listEl.innerHTML = '';
        for (const [empId, empName] of Object.entries(personnelDict)) {
            const li = document.createElement('li');
            li.className = 'personnel-item';
            li.innerHTML = `<span><b>${empId}</b> - ${empName}</span><span class="del-btn" onclick="deletePersonnel('${empId}')">✖</span>`;
            listEl.appendChild(li);
        }
    }

    const toggleMetarBtn = document.getElementById('toggle-metar-input-btn');
    const metarContent = document.getElementById('metar-collapsible-content');
    if (toggleMetarBtn && metarContent) {
        toggleMetarBtn.onclick = () => {
            if (metarContent.style.display === 'none' || metarContent.style.display === '') {
                metarContent.style.display = 'block';
                metarContent.classList.remove('hidden');
            } else {
                metarContent.style.display = 'none';
            }
        };
    }

    const toggleForecastBtn = document.getElementById('toggle-forecast-input-btn');
    const forecastContent = document.getElementById('manual-forecast-text-group');
    if (toggleForecastBtn && forecastContent) {
        toggleForecastBtn.onclick = () => {
            if (forecastContent.style.display === 'none' || forecastContent.style.display === '') {
                forecastContent.style.display = 'block';
                forecastContent.classList.remove('hidden');
            } else {
                forecastContent.style.display = 'none';
            }
        };
    }

    document.getElementById('add-emp-btn')?.addEventListener('click', () => {
        const newId = document.getElementById('new-emp-id').value.trim();
        const newName = document.getElementById('new-emp-name').value.trim();
        if (newId && newName) {
            personnelDict[newId] = newName;
            localStorage.setItem('personnel_dict', JSON.stringify(personnelDict));
            syncPersonnelMappingToServer();
            patchSettingsConfig({ personnel_dict: personnelDict });
            renderPersonnelList();
            document.getElementById('new-emp-id').value = '';
            document.getElementById('new-emp-name').value = '';
            updateDisplayUserName();
        } else { alert("工号和姓名不能为空!"); }
    });

    window.deletePersonnel = function(empId) {
        if (empId === ADMIN_ID) return alert("吴霄作为超级管理员,无法被删除。");
        if (confirm(`确定要删除工号 ${empId} 的人员映射吗?`)) {
            delete personnelDict[empId];
            localStorage.setItem('personnel_dict', JSON.stringify(personnelDict));
            syncPersonnelMappingToServer();
            patchSettingsConfig({ personnel_dict: personnelDict });
            renderPersonnelList();
            updateDisplayUserName();
        }
    };

    document.getElementById('save-pwd-btn')?.addEventListener('click', () => {
        const newPwd = document.getElementById('admin-pwd-input').value.trim();
        if (newPwd) {
            settingsPassword = newPwd;
            localStorage.setItem('settings_pwd', settingsPassword);
            // 密码仅存本地 localStorage,不在统一配置 schema 中,无需推送配置文件
            alert("通用设置密码已更新!");
        }
    });

    // 🌟 清理了重复嵌套的函数
    function updateDisplayUserName(userCode = null, isOffline = false, displayName = null) {
        const currentUserId = userCode || localStorage.getItem('sf_userId') || '';
        const pbForecaster = document.getElementById('pb-forecaster');

        if (currentUserId) {
            const mappedName = personnelDict[String(currentUserId)];
            const normalizedDisplayName = String(displayName || '').trim();
            const providedName = normalizedDisplayName && normalizedDisplayName !== String(currentUserId)
                ? normalizedDisplayName
                : '';
            const chineseName = (typeof isLocalBrowserHost === "function" && !isLocalBrowserHost())
                ? "共享用户"
                : (mappedName || providedName || (isOffline ? "离线模式" : String(currentUserId)));
            userIdDisplay.textContent = `当前账号: ${chineseName}`;

            localStorage.setItem('sf_userId', currentUserId);

            if (pbForecaster) pbForecaster.value = chineseName;

            const adminSection = document.getElementById('pane-admin');
            if (adminSection) {
                // 🌟 只认吴霄工号常量,不依赖会被配置同步覆盖的姓名映射
                if (currentUserId === ADMIN_ID) {
                    adminSection.classList.remove('hidden');
                    adminSection.style.display = 'block';
                } else {
                    adminSection.classList.add('hidden');
                    adminSection.style.display = 'none';
                }
            }
        } else {
            if (pbForecaster) pbForecaster.value = '未知';
        }
    }
    window.OMICS_updateDisplayUserName = updateDisplayUserName;

    const evalPersonSelect = document.getElementById('eval-person-select');
    const tafExcelPathInput = document.getElementById('taf-excel-path');
    const manualExcelPathInput = document.getElementById('manual-excel-path');
    const manualForecastPathInput = document.getElementById('manual-forecast-path');
    const backupSavePathInput = document.getElementById('backup-save-path');

    if (tafExcelPathInput) tafExcelPathInput.value = localStorage.getItem('taf_excel_path') || '';
    if (manualExcelPathInput) manualExcelPathInput.value = localStorage.getItem('manual_excel_path') || '';
    if (manualForecastPathInput) manualForecastPathInput.value = localStorage.getItem('manual_forecast_path') || '';
    if (backupSavePathInput) backupSavePathInput.value = localStorage.getItem('backup_save_path') || '';

    document.getElementById('browse-taf-btn')?.addEventListener('click', async (e) => {
        e.target.textContent = "打开中...";
        try {
            const res = await fetch(window.OMICS_API_URL('select_folder')); const data = await res.json();
            if (data.success) { tafExcelPathInput.value = data.path; localStorage.setItem('taf_excel_path', data.path); patchSettingsConfig({ paths: buildPathsBlock() }); }
        } catch (err) {} e.target.textContent = "浏览";
    });
    document.getElementById('browse-manual-btn')?.addEventListener('click', async (e) => {
        e.target.textContent = "打开中...";
        try {
            const res = await fetch(window.OMICS_API_URL('select_folder')); const data = await res.json();
            if (data.success) { manualExcelPathInput.value = data.path; localStorage.setItem('manual_excel_path', data.path); patchSettingsConfig({ paths: buildPathsBlock() }); }
        } catch (err) {} e.target.textContent = "浏览";
    });
    document.getElementById('browse-manual-forecast-btn')?.addEventListener('click', async (e) => {
        e.target.textContent = "打开中...";
        try {
            const res = await fetch(window.OMICS_API_URL('select_folder')); const data = await res.json();
            if (data.success && manualForecastPathInput) {
                manualForecastPathInput.value = data.path;
                localStorage.setItem('manual_forecast_path', data.path);
                patchSettingsConfig({ paths: buildPathsBlock() });
            }
        } catch (err) {} e.target.textContent = "浏览";
    });
    document.getElementById('browse-backup-btn')?.addEventListener('click', async (e) => {
        e.target.textContent = "打开中...";
        try {
            const res = await fetch(window.OMICS_API_URL('select_folder')); const data = await res.json();
            if (data.success && backupSavePathInput) { backupSavePathInput.value = data.path; localStorage.setItem('backup_save_path', data.path); patchSettingsConfig({ paths: buildPathsBlock() }); }
        } catch (err) {} e.target.textContent = "浏览";
    });

    function renderEvalPersonSelect() {
        if (!evalPersonSelect) return;
        const currentVal = evalPersonSelect.value;
        evalPersonSelect.innerHTML = '<option value="">请选择人员</option>';
        const statsSelect = document.getElementById('stats-person-select');
        if (statsSelect) statsSelect.innerHTML = '<option value="ALL">全部人员</option>';

        const names = [...new Set(Object.values(personnelDict))];

        names.forEach(name => {
            const opt = document.createElement('option');
            opt.value = name; opt.textContent = name;
            evalPersonSelect.appendChild(opt);

            if (statsSelect) {
                const sOpt = document.createElement('option');
                sOpt.value = name; sOpt.textContent = name;
                statsSelect.appendChild(sOpt);
            }
        });
        evalPersonSelect.value = currentVal;
    }
    loadPersonnelMappingFromServer().then(() => {
        renderPersonnelList();
        renderEvalPersonSelect();
        updateDisplayUserName();
        syncPersonnelMappingToServer();
        // 🌟 初始加载只回写人员映射,不全量推送(避免初始化时用可能还不完整的快照覆盖阈值等)
        patchSettingsConfig({ personnel_dict: personnelDict });
    });

    const adminDefManual = document.getElementById('admin-default-manual');
    const adminDefTaf = document.getElementById('admin-default-taf');
    if (adminDefManual) adminDefManual.value = localStorage.getItem('sf_def_manual_aps') || "ZBAA ZGSZ ZHEC ZSHC";
    if (adminDefTaf) adminDefTaf.value = localStorage.getItem('sf_def_taf_aps') || "ZHEC";

    document.getElementById('save-default-aps-btn')?.addEventListener('click', () => {
        if (adminDefManual) localStorage.setItem('sf_def_manual_aps', adminDefManual.value.trim());
        if (adminDefTaf) localStorage.setItem('sf_def_taf_aps', adminDefTaf.value.trim());
        patchSettingsConfig({ default_airports: buildDefaultAirportsBlock() });
        alert("✅ 默认机场配置已保存!");
    });

    const customStartInputEl = document.getElementById('custom-start-time');
    const customEndInputEl = document.getElementById('custom-end-time');
    customStartInputEl?.addEventListener('input', updateTimeRangeInputs);
    customEndInputEl?.addEventListener('input', updateTimeRangeInputs);

    let customAirportsThresholds = serverThresholds.custom_airports || JSON.parse(localStorage.getItem('sf_custom_ap_thresholds') || '{}');

    let globalThresholds = serverThresholds.global || JSON.parse(localStorage.getItem('sf_global_thresholds')) || {
        vis_takeoff: 400, vis_landing: 800, vis_warning: 1000,
        cld_takeoff: 60, cld_landing: 60, cld_warning: 90, wind_warning: 17
    };

    ['vis_takeoff', 'vis_landing', 'vis_warning', 'cld_takeoff', 'cld_landing', 'cld_warning', 'wind_warning'].forEach(id => {
        const el = document.getElementById(id);
        if (el && globalThresholds[id] !== undefined) el.value = globalThresholds[id];
    });

    function renderGlobalThresholds() {
        const container = document.getElementById('global-thresholds-display');
        if (!container) return;
        const t = globalThresholds;

        container.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div style="color:#005A9C; font-size:12px; font-weight: bold; line-height: 1.5;">
                    全局生效标准:<br>
                    <span style="color:#333; font-weight: normal; font-size: 10px;">
                        能见度 ${t.vis_takeoff}/${t.vis_landing}/${t.vis_warning} 米 |
                        云底高 ${t.cld_takeoff}/${t.cld_landing}/${t.cld_warning} 米 |
                        大风基准 ${t.wind_warning} m/s
                    </span>
                </div>
                <button id="save-global-thresh-btn" class="mini-btn" style="background:#005A9C; color:white; padding:2px 8px; font-size:10px;">💾 保存</button>
            </div>
        `;

        document.getElementById('save-global-thresh-btn').addEventListener('click', () => {
            globalThresholds = {
                vis_takeoff: document.getElementById('vis_takeoff').value,
                vis_landing: document.getElementById('vis_landing').value,
                vis_warning: document.getElementById('vis_warning').value,
                cld_takeoff: document.getElementById('cld_takeoff').value,
                cld_landing: document.getElementById('cld_landing').value,
                cld_warning: document.getElementById('cld_warning').value,
                wind_warning: document.getElementById('wind_warning').value
            };
            localStorage.setItem('sf_global_thresholds', JSON.stringify(globalThresholds));
            patchSettingsConfig({ thresholds: buildThresholdsBlock() });
            renderGlobalThresholds();
            alert("✅ 全局参数已保存并生效！");
        });
    }

    function renderCustomAirports() {
        const container = document.getElementById('custom-airport-thresholds-list');
        if (!container) return;
        container.innerHTML = '';
        for (let ap in customAirportsThresholds) {
            let t = customAirportsThresholds[ap];
            container.innerHTML += `
                <div style="border:1px solid #cce5ff; background:#f8fbff; padding:4px; margin-bottom:4px; border-radius:4px; font-size:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
                        <strong style="color:#005A9C;">${ap} 专属</strong>
                        <button onclick="deleteCustomApThresh('${ap}')" class="mini-btn" style="background:#dc3545; color:white; padding:1px 5px; font-size:10px;">移除</button>
                    </div>
                    <div style="color:#333;">能见度: ${t.vt}/${t.vl}/${t.vw} 米 | 云底高: ${t.ct}/${t.cl}/${t.cw} 米 | 大风基准: ${t.ww} m/s</div>
                </div>`;
        }
    }

    window.deleteCustomApThresh = function(ap) {
        delete customAirportsThresholds[ap];
        localStorage.setItem('sf_custom_ap_thresholds', JSON.stringify(customAirportsThresholds));
        patchSettingsConfig({ thresholds: buildThresholdsBlock() });
        renderCustomAirports();
    };

    document.getElementById('add-custom-thresh-btn')?.addEventListener('click', () => {
        const ap = document.getElementById('custom-thresh-ap').value.trim().toUpperCase();
        if (!ap) return alert("请输入机场代码!");
        customAirportsThresholds[ap] = {
            vt: document.getElementById('vis_takeoff').value,
            vl: document.getElementById('vis_landing').value,
            vw: document.getElementById('vis_warning').value,
            ct: document.getElementById('cld_takeoff').value,
            cl: document.getElementById('cld_landing').value,
            cw: document.getElementById('cld_warning').value,
            ww: document.getElementById('wind_warning').value
        };
        localStorage.setItem('sf_custom_ap_thresholds', JSON.stringify(customAirportsThresholds));
        patchSettingsConfig({ thresholds: buildThresholdsBlock() });
        document.getElementById('custom-thresh-ap').value = '';
        renderCustomAirports();
    });

    renderGlobalThresholds();
    renderCustomAirports();

    function renderPhenomenaSettings() {
        phenomenaContainer.innerHTML = '';
        const rulesText = {
            '雷雨类': '强度一致完美, 差一级优秀。无中生有或强报弱为空报,有而未报或弱报强为漏报。',
            '强降水(无雷)类': '强/中档位一致完美, 差一档优秀。预报偏强为空报,偏弱为漏报。实况与预报均为弱或无则不评。',
            '积冰类': '强度一致完美, 差一级优秀。无中生有或强报弱为空报,有而未报或弱报强为漏报。',
            '特殊类': '不区分强度,报中即完美。多报(无中生有)为空报,少报(有而未报)为漏报。'
        };

        for (const [category, codes] of Object.entries(phenomenaSettings)) {
            const div = document.createElement('div');
            div.style.marginBottom = '8px'; div.style.borderBottom = '1px dashed #eee'; div.style.paddingBottom = '5px';

            const titleLine = document.createElement('div');
            const title = document.createElement('strong'); title.textContent = category + ": ";
            title.style.fontSize = '12px';
            const codeList = document.createElement('span'); codeList.textContent = codes.join(', ');
            codeList.style.color = '#555'; codeList.style.fontSize = '11px';
            titleLine.appendChild(title); titleLine.appendChild(codeList);
            div.appendChild(titleLine);

            if (rulesText[category]) {
                const ruleP = document.createElement('div');
                ruleP.textContent = "评分规则:" + rulesText[category];
                ruleP.style.fontSize = '10px';
                ruleP.style.color = '#888';
                ruleP.style.marginTop = '2px';
                div.appendChild(ruleP);
            }

            const inputContainer = document.createElement('div');
            inputContainer.style.marginTop = '4px'; inputContainer.style.display = 'flex'; inputContainer.style.gap = '5px';
            const input = document.createElement('input'); input.type = 'text'; input.placeholder = '添加代码'; input.style.width = '80px'; input.style.fontSize = '10px'; input.style.padding = '2px';
            const addBtn = document.createElement('button'); addBtn.textContent = '+'; addBtn.className = 'mini-btn'; addBtn.style.padding = '2px 8px';

            addBtn.onclick = () => {
                const val = input.value.trim().toUpperCase();
                if (val) {
                    // 同一天气代码只能属于一个量级；在新分类中添加即视为移动。
                    Object.values(phenomenaSettings).forEach(items => {
                        const pos = items.indexOf(val);
                        if (pos >= 0) items.splice(pos, 1);
                    });
                    codes.push(val);
                    localStorage.setItem('phenomena_config', JSON.stringify(phenomenaSettings));
                    patchSettingsConfig({ phenomena_config: phenomenaSettings });
                    renderPhenomenaSettings();
                }
            };
            inputContainer.appendChild(input); inputContainer.appendChild(addBtn); div.appendChild(inputContainer); phenomenaContainer.appendChild(div);
        }
    }

    resetPhenomenaBtn.onclick = () => {
        if(confirm("确定要重置天气配置为默认值吗?")) {
            phenomenaSettings = JSON.parse(JSON.stringify(DEFAULT_PHEN_CATEGORIES)); localStorage.removeItem('phenomena_config'); patchSettingsConfig({ phenomena_config: phenomenaSettings }); renderPhenomenaSettings();
        }
    };
    renderPhenomenaSettings();

    initSession();
    async function initSession() {
        try {
            const explicitLogoutAt = Number(localStorage.getItem('omics_explicit_logout_at') || 0);
            if (explicitLogoutAt && Date.now() - explicitLogoutAt < 2 * 60 * 1000) {
                await clearUnifiedAuth();
                clearLocalAuthState();
            }
            const unified = await fetchUnifiedAuthStatus();
            if (unified && unified.logged_in && (!isUsableAuthToken(unified.token) || !isRealUserCode(unified.userCode))) {
                console.warn('统一登录态工号或 token 无效，已清空');
                await clearUnifiedAuth();
            }
            let data = null;
            const freshUnified = await fetchUnifiedAuthStatus();
            if (freshUnified && freshUnified.logged_in && isUsableAuthToken(freshUnified.token) && isRealUserCode(freshUnified.userCode)) {
                data = freshUnified;
            } else {
                const res = await fetch('/api/auth/status');
                data = await res.json();
                // Nginx 统一态为空时,允许 OMICS 前端继续使用自己保存的登录信息。
                const localToken = localStorage.getItem('sf_weather_token') || localStorage.getItem('mtws_token');
                const localUserCode = localStorage.getItem('sf_userId') || localStorage.getItem('mtws_userCode');
                if ((!data || !data.logged_in) && isUsableAuthToken(localToken) && isRealUserCode(localUserCode)) {
                    data = { logged_in: true, token: localToken, userCode: localUserCode, displayName: personnelDict[localUserCode], isOffline: false, source: '浏览器缓存' };
                    // 浏览器缓存里仍有可用 token 时,主动回灌到 Nginx 统一登录态,让启动器信息框和 MTWS 立即识别真实登录状态。
                    await updateUnifiedAuth(localToken, localUserCode, personnelDict[localUserCode]);
                }
            }

            if (data && data.logged_in && isUsableAuthToken(data.token) && isRealUserCode(data.userCode)) {
                localStorage.removeItem('omics_explicit_logout_at');
                if (data.token) {
                    saveTokenForBothApps(data.token, data.userCode);
                    await updateUnifiedAuth(data.token, data.userCode, data.displayName || personnelDict[data.userCode]);
                }
                updateDisplayUserName(data.userCode, data.isOffline, data.displayName);
                loginBtn.classList.add('hidden');
                userInfoDiv.classList.remove('hidden');
                startUnifiedAuthWatch();
            } else {
                clearLocalAuthState();
                loginBtn.classList.remove('hidden');
                userInfoDiv.classList.add('hidden');

                const adminSection = document.getElementById('pane-admin');
                if (adminSection) {
                    adminSection.classList.add('hidden');
                    adminSection.style.display = 'none';
                }
            }
        } catch (e) { console.error("连接后端失败:", e); }
    }

    const fp = flatpickr(datePickerInput, {
        defaultDate: new Date(),
        locale: "zh",
        onChange: (selectedDates) => {
            if (selectedDates.length > 0) {
                baseDate = selectedDates[0];
                baseDate.setHours(0,0,0,0);
                updateTimeRangeInputs();
            }
        }
    });
    if(fp.selectedDates.length > 0) {
        baseDate = fp.selectedDates[0];
        baseDate.setHours(0,0,0,0);
        updateTimeRangeInputs();
    }

    downloadAirports.value = "ZBAA ZGSZ ZHEC ZSHC";

    // 🌟 全局设置弹窗交互逻辑 (清理重复代码)
    const globalSettingsModal = document.getElementById('global-settings-modal');

    settingsBtn.addEventListener('click', () => {
        if (globalSettingsModal.dataset.settingsAuthorizationFailed === 'true') {
            delete globalSettingsModal.dataset.settingsAuthorizationFailed;
            return;
        }
        const preAuthorized = globalSettingsModal.dataset.settingsAuthorized === 'true';
        delete globalSettingsModal.dataset.settingsAuthorized;
        if (!preAuthorized && !window.OMICS_authorizeSettings()) return;

        const currentUserId = localStorage.getItem('sf_userId') || '';
        const currentToken = apiToken || localStorage.getItem('sf_weather_token') || '';
        const isLoggedIn = !!currentToken && !!currentUserId;
        // 🌟 权限规则(只认吴霄工号常量,不依赖会被配置同步覆盖的 personnelDict):
        //   1. 吴霄(工号 ADMIN_ID)扫码登录 → 免密进入,并显示高级管理员配置。
        //   2. 其他任何情况(未登录 / 登录的不是吴霄)→ 必须输入管理密码才能进入系统设置,
        //      且只能进普通设置,看不到高级管理员配置。
        const isAdminUser = isLoggedIn && currentUserId === ADMIN_ID;
        globalSettingsModal.style.display = 'flex';
        renderPersonnelList();

        const adminSection = document.getElementById('pane-admin');
        const adminNavBtn = document.querySelector('.set-nav[data-target="pane-admin"]');
        if (adminSection) {
            // 只有吴霄账号能看到高级管理员配置;输密码进来的只能进普通设置。
            if (isAdminUser) {
                adminSection.classList.remove('hidden');
                adminSection.style.display = 'block';
                if (adminNavBtn) adminNavBtn.style.display = 'block';
                const pwdInput = document.getElementById('admin-pwd-input');
                if(pwdInput) pwdInput.value = settingsPassword;
            } else {
                adminSection.classList.add('hidden');
                adminSection.style.display = 'none';
                if (adminNavBtn) adminNavBtn.style.display = 'none';
                const adminPane = document.getElementById('pane-admin');
                if (adminPane && adminPane.style.display !== 'none') {
                    document.querySelector('.set-nav[data-target="pane-pb"]')?.click();
                }
            }
        }
    });

    document.getElementById('close-global-settings')?.addEventListener('click', () => {
        globalSettingsModal.style.display = 'none';
    });

    function hideModal(modal) { modal.style.display = 'none'; }
    closeLoginModalBtn.onclick = () => { hideModal(loginModal); if(pollTimer) clearInterval(pollTimer); };
    closeMetarModalBtn.onclick = () => { hideModal(metarModal); };
    window.onclick = (event) => {
        if (event.target == metarModal) hideModal(metarModal);
        if (event.target == loginModal) { hideModal(loginModal); if(pollTimer) clearInterval(pollTimer); }
    };

    loginBtn.addEventListener('click', startLogin);
    logoutBtn.addEventListener('click', async () => {
        localStorage.setItem('omics_explicit_logout_at', String(Date.now()));
        try { await fetch('/api/auth/logout', { method: 'POST' }); } catch(e) {}
        stopUnifiedAuthWatch();
        await clearUnifiedAuth();
        clearLocalAuthState();
        userInfoDiv.classList.add('hidden');
        loginBtn.classList.remove('hidden');
        setTimeout(() => startLogin(), 0);

        const adminSection = document.getElementById('pane-admin');
        if (adminSection) {
            adminSection.classList.add('hidden');
            adminSection.style.display = 'none';
        }
        alert("账号已注销");
    });

    exitAppBtn.addEventListener('click', async () => {
        if(confirm("确定要退出整个预报评定系统吗?")) {
            try { navigator.sendBeacon('/api/shutdown'); } catch(e) {}
            setTimeout(() => { window.close(); document.body.innerHTML = "<h2 style='text-align:center;'>系统已安全退出</h2>"; }, 500);
        }
    });

    async function startLogin() {
        loginModal.style.display = 'flex';
        if (pollTimer) clearInterval(pollTimer);

        const offlineContainer = document.getElementById('offline-login-container');
        if (offlineContainer) offlineContainer.remove();

        qrImage.style.display = "none";
        qrStatusText.style.display = "block";
        qrStatusText.innerHTML = `<div style="margin-bottom:10px; color:#555;">正在获取二维码...</div>`;

        const redBtn = document.createElement('button');
        redBtn.innerText = "⏳ 连不上?直接进入离线模式";
        redBtn.style.cssText = "background:#dc3545; color:white; padding:8px 16px; border:none; border-radius:4px; cursor:pointer; font-size:12px; box-shadow: 0 2px 4px rgba(220,53,69,0.3);";

        redBtn.onclick = (e) => {
            e.preventDefault();
            showOfflineLoginForm("已手动切换至离线模式");
        };
        qrStatusText.appendChild(redBtn);

        try {
            let data = null;
            let lastError = null;
            for (let attempt = 0; attempt < 3; attempt++) {
                try {
                    const res = await fetch('/api/auth/qrcode', { cache: 'no-store' });
                    data = await res.json();
                    if (data.success) break;
                    lastError = new Error(data.error || '二维码接口返回失败');
                } catch (err) {
                    lastError = err;
                }
                if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 700));
            }
            if (document.getElementById('offline-login-container')) return;

            if (data?.success) {
                qrImage.src = "data:image/png;base64," + data.qr_img_base64;
                qrImage.style.display = "block";
                qrStatusText.textContent = "请使用 SF App 扫码登录";
                pollTimer = setInterval(checkLoginStatus, 2000);
            } else {
                showOfflineLoginForm("获取失败: " + (data?.error || lastError?.message || '未知错误'));
            }
        } catch (e) {
            if (!document.getElementById('offline-login-container')) {
                showOfflineLoginForm("网络不通,请使用离线模式登录");
            }
        }
    }

    function showOfflineLoginForm(errorMsg) {
        qrImage.style.display = "none";
        qrStatusText.style.display = "none";
        if(pollTimer) clearInterval(pollTimer);
        if (document.getElementById('offline-login-container')) return;

        const container = document.createElement('div');
        container.id = 'offline-login-container';
        container.style.cssText = "padding: 15px; text-align: left; background: #f8f9fa; border-radius: 8px; width: 100%; box-sizing: border-box;";
        container.innerHTML = `
            <p style="color: #dc3545; font-size: 13px; margin: 0 0 15px 0;"><b>${errorMsg}</b></p>
            <div style="margin-bottom: 10px;">
                <label style="display:block; font-size:12px; margin-bottom:4px;">账号 (工号):</label>
                <input type="text" id="offline-username" style="width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box;">
            </div>
            <div style="margin-bottom: 15px;">
                <label style="display:block; font-size:12px; margin-bottom:4px;">密码:</label>
                <input type="password" id="offline-password" style="width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box;">
            </div>
            <button id="offline-submit-btn" class="step-button" style="width:100%; background:#6c757d; color:white; padding:10px; border:none; border-radius:4px; cursor:pointer;">立即登录</button>
        `;

        qrImage.parentNode.insertBefore(container, qrImage.nextSibling);

        document.getElementById('offline-submit-btn').onclick = async (e) => {
            e.preventDefault();
            const username = document.getElementById('offline-username').value.trim();
            const password = document.getElementById('offline-password').value;

            if (!username || !personnelDict[username]) {
                return alert("登录失败:该工号未录入系统,无权登录!");
            }

            const btn = document.getElementById('offline-submit-btn');
            const originalText = btn.innerText;
            btn.innerText = "正在验证...";
            btn.disabled = true;

            try {
                const res = await fetch('/api/auth/offline_login', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });

                if (!res.ok) throw new Error(`服务器异常 ${res.status}`);
                const data = await res.json();

                if (data.success) {
                    localStorage.removeItem('omics_explicit_logout_at');
                    location.reload();
                } else {
                    alert("登录失败:" + data.message);
                    btn.innerText = originalText; btn.disabled = false;
                }
            } catch (err) {
                alert("登录异常: " + err.message);
                btn.innerText = originalText; btn.disabled = false;
            }
        };
    }

    async function checkLoginStatus() {
        try {
            const res = await fetch('/api/auth/check');
            const data = await res.json();
            if (data.success && data.status === 'SCANNED') {
                clearInterval(pollTimer);
                qrStatusText.textContent = "扫码成功,正在验证...";
                const valRes = await fetch('/api/auth/validate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ticket: data.ticket, scan_id: data.scan_id})
                });
                const valData = await valRes.json();
                if (valData.success) {
                    localStorage.removeItem('omics_explicit_logout_at');
                    apiToken = valData.token;
                    saveTokenForBothApps(apiToken);
                    hideModal(loginModal);
                    loginBtn.classList.add('hidden');
                    userInfoDiv.classList.remove('hidden');
                    const currentMode = document.querySelector('input[name="forecast-mode"]:checked')?.value;
                    if (currentMode === 'publish' && typeof window.loadForecastData === 'function') {
                        window.loadForecastData();
                    }

                    const statusRes = await fetch('/api/auth/status');
                    const statusData = await statusRes.json();
                    if(isRealUserCode(statusData.userCode)) {
                        saveTokenForBothApps(apiToken, statusData.userCode);
                        await updateUnifiedAuth(apiToken, statusData.userCode, statusData.displayName);
                        updateDisplayUserName(statusData.userCode, statusData.isOffline, statusData.displayName);
                    }
                    startUnifiedAuthWatch();
                } else {
                    qrStatusText.textContent = "验证失败: " + valData.message;
                }
            }
        } catch (e) {
            console.error(e);
        }
    }

    modeRadios.forEach(radio => { radio.addEventListener('change', (e) => { currentMode = e.target.value; handleModeChange(); }); });

    async function applyDesktopStorage() {
        try {
            const res = await fetch('/api/get_desktop_path');
            const data = await res.json();
            if (data.success) {
                window.tempExcelRoot = data.path;
                return data.path;
            }
        } catch (err) { console.error("获取桌面路径失败"); }
        return null;
    }

    document.querySelectorAll('input[name="storage-mode"]').forEach(radio => {
        radio.addEventListener('change', async (e) => {
            if (e.target.value === 'desktop') {
                const path = await applyDesktopStorage();
                if (path) alert(`已切换至【桌面存储】模式!\nExcel表格将保存在您桌面的【SF预报评定导出】文件夹中。`);
            } else {
                window.tempExcelRoot = null;
            }
        });
    });

    const checkedStorage = document.querySelector('input[name="storage-mode"]:checked');
    if (checkedStorage && checkedStorage.value === 'desktop') {
        applyDesktopStorage();
    }

    document.getElementById('stats-type-select')?.addEventListener('change', (e) => {
        const pSelect = document.getElementById('stats-person-select');
        if (pSelect) {
            if (e.target.value === 'taf') { pSelect.value = 'ALL'; pSelect.disabled = true; }
            else { pSelect.disabled = false; }
        }
    });

    const syncExcelBtn = document.getElementById('sync-excel-btn');
    if (syncExcelBtn) {
        syncExcelBtn.addEventListener('click', async () => {
            const tafRoot = document.getElementById('taf-excel-path')?.value.trim() || '';
            const manualRoot = document.getElementById('manual-excel-path')?.value.trim() || '';
            const backupPath = document.getElementById('backup-save-path')?.value.trim() || '';
            const roots = [
                { label: '机场预报', path: tafRoot },
                { label: '席位预报', path: manualRoot }
            ].filter(item => item.path);

            if (!roots.length) return alert("⚠️ 同步前请先配置【机场预报】或【席位预报】Excel 云盘路径!");

            syncExcelBtn.disabled = true; syncExcelBtn.textContent = "⏳ 正在逆向提取并同步数据,请耐心稍候...";
            let progress = document.getElementById('sync-excel-progress');
            if (!progress) { progress = document.createElement('div'); progress.id = 'sync-excel-progress'; progress.style.cssText = 'margin-top:8px;max-height:180px;overflow:auto;border:1px solid #fed7aa;background:#fff7ed;padding:8px;font-size:12px;white-space:pre-line;'; syncExcelBtn.parentElement?.appendChild(progress); }
            progress.textContent = '开始同步...';
            const syncYear = document.getElementById('sync-excel-year')?.value || '';
            const syncMonth = document.getElementById('sync-excel-month')?.value || '';
            try {
                const messages = [];
                const errors = [];
                for (const item of roots) {
                    progress.textContent += `\n⏳ ${item.label}：正在扫描...`;
                    const res = await fetch('/api/sync_excel', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ excel_root: item.path, backup_path: backupPath, year: syncYear, month: syncMonth })
                    });
                    const data = await res.json();
                    if (data.success) { messages.push(`【${item.label}】${data.message}`); progress.textContent += `\n✅ ${item.label}：${data.message}`; }
                    else { errors.push(`【${item.label}】${data.error}`); progress.textContent += `\n❌ ${item.label}：${data.error}`; }
                }
                if (errors.length) alert(`部分同步失败:\n${errors.join('\n')}\n\n已完成:\n${messages.join('\n') || '无'}`);
                else alert(messages.join('\n'));
            } catch (e) { alert("请求异常: " + e.message); }
            finally { syncExcelBtn.disabled = false; syncExcelBtn.textContent = "🔄 从 Excel 逆向同步数据到 JSON"; }
        });
    }

    if (backupSavePathInput) {
        backupSavePathInput.addEventListener('change', () => {
            localStorage.setItem('backup_save_path', backupSavePathInput.value.trim());
            patchSettingsConfig({ paths: buildPathsBlock() });
        });
    }

    function handleModeChange() {
        const checkedRadio = document.querySelector('input[name="forecast-mode"]:checked');
        if (!checkedRadio) return;
        const currentMode = checkedRadio.value;
        const modeSwitcher = document.querySelector('.mode-switcher');

        const publishWorkspace = document.getElementById('publish-workspace');
        const evalWorkspace = document.getElementById('evaluation-workspace');
        const statsWorkspace = document.getElementById('stats-workspace');

        const resMan = document.getElementById('results-manual');
        const resTaf = document.getElementById('results-taf');
        const resStats = document.getElementById('results-stats');

        if (modeSwitcher) modeSwitcher.style.display = 'flex';

        if (currentMode === 'publish') {
            if (publishWorkspace) publishWorkspace.style.display = 'block';
            if (evalWorkspace) evalWorkspace.style.display = 'none';
            if (statsWorkspace) statsWorkspace.style.display = 'none';

            if (typeof window.initPublishModule === 'function' && !window.publishInitialized) {
                window.initPublishModule();
            }

        } else if (currentMode === 'stats') {
            if (publishWorkspace) publishWorkspace.style.display = 'none';
            if (evalWorkspace) evalWorkspace.style.display = 'none';
            if (statsWorkspace) statsWorkspace.style.display = 'block';

        } else {
            if (publishWorkspace) publishWorkspace.style.display = 'none';
            if (evalWorkspace) evalWorkspace.style.display = 'block';
            if (statsWorkspace) statsWorkspace.style.display = 'none';

            const evalPersonContainer = document.getElementById('eval-person-container');
            const manualArea = document.getElementById('manual-forecast-input-area');
            const tafArea = document.getElementById('taf-forecast-input-area');
            const manualTimeOptions = document.getElementById('manual-time-options');
            const fetchManualBtn = document.getElementById('fetch-manual-btn');
            const fetchTafListBtn = document.getElementById('fetch-taf-list-btn');
            const tafSelectionArea = document.getElementById('taf-selection-area');
            const importTafMetarContainer = document.getElementById('import-taf-metar-container');
            const forecastManualGroup = document.getElementById('forecast-manual-group');

            if (currentMode === 'manual') {
                syncManualFetchButtonText();
                document.getElementById('manual-airport-choice')?.style.setProperty('display', 'inline-flex', '');
                if (manualAirportDefault) manualAirportDefault.style.display = 'inline-block';
                const downloadAirports = document.getElementById('download-airports');
                if (downloadAirports) downloadAirports.value = localStorage.getItem('sf_def_manual_aps') || "ZBAA ZGSZ ZHEC ZSHC";

                if (evalPersonContainer) evalPersonContainer.style.display = 'none';
                if (manualArea) { manualArea.classList.remove('hidden'); manualArea.style.display = 'block'; }
                if (tafArea) { tafArea.classList.add('hidden'); tafArea.style.display = 'none'; }
                if (manualTimeOptions) manualTimeOptions.classList.remove('hidden');
                if (fetchManualBtn) fetchManualBtn.classList.remove('hidden');
                if (fetchTafListBtn) fetchTafListBtn.classList.add('hidden');
                if (tafSelectionArea) tafSelectionArea.classList.add('hidden');
                if (importTafMetarContainer) importTafMetarContainer.classList.add('hidden');
                if (forecastManualGroup) forecastManualGroup.style.display = 'none';
                if (manualAirportDefault) manualAirportDefault.checked = true;
                if (manualAirportAll) manualAirportAll.checked = false;
                if (manualAirportAllLabel) manualAirportAllLabel.style.display = isTwentyFourHourRange() ? 'inline' : 'none';
            } else if (currentMode === 'taf') {
                if (manualAirportDefault) manualAirportDefault.style.display = 'none';
                if (manualAirportAllLabel) manualAirportAllLabel.style.display = 'none';
                const downloadAirports = document.getElementById('download-airports');
                if (downloadAirports) downloadAirports.value = localStorage.getItem('sf_def_taf_aps') || "ZHEC";

                if (evalPersonContainer) evalPersonContainer.style.display = 'none';
                if (manualArea) { manualArea.classList.add('hidden'); manualArea.style.display = 'none'; }
                if (tafArea) { tafArea.classList.remove('hidden'); tafArea.style.display = 'block'; }
                if (manualTimeOptions) manualTimeOptions.classList.add('hidden');
                if (fetchManualBtn) fetchManualBtn.classList.add('hidden');
                if (fetchTafListBtn) fetchTafListBtn.classList.remove('hidden');
                if (forecastManualGroup) forecastManualGroup.style.display = 'block';

                const tafListItems = document.getElementById('taf-list-items');
                const hasData = tafListItems && tafListItems.children.length > 0;
                if (tafSelectionArea) {
                    tafSelectionArea.style.display = hasData ? 'block' : 'none';
                    if (hasData) tafSelectionArea.classList.remove('hidden');
                }
                if (importTafMetarContainer) {
                    importTafMetarContainer.style.display = hasData ? 'block' : 'none';
                    if (hasData) importTafMetarContainer.classList.remove('hidden');
                }
            }
        }

        if (resMan) resMan.style.display = (currentMode === 'manual') ? 'block' : 'none';
        if (resTaf) resTaf.style.display = (currentMode === 'taf') ? 'block' : 'none';
        if (resStats) resStats.style.display = (currentMode === 'stats') ? 'block' : 'none';

        resultsContainer = document.getElementById('results-' + currentMode) || document.getElementById('results-stats');

        if (typeof updateTimeRangeInputs === 'function') updateTimeRangeInputs();
        // 🌟 切换视图后同步底部常驻滚动条可见性(离开发布页时隐藏)
        if (typeof window.OMICS_syncBottomScrollbar === 'function') setTimeout(window.OMICS_syncBottomScrollbar, 0);
    }

    timeRadios.forEach(radio => { radio.addEventListener('change', () => { updateTimeRangeInputs(); syncManualAirportChoice?.(); syncManualFetchButtonText(); }); });
    function formatFullTime(date) {
        const y = date.getUTCFullYear(); const m = String(date.getUTCMonth() + 1).padStart(2, '0');
        const d = String(date.getUTCDate()).padStart(2, '0'); const h = String(date.getUTCHours()).padStart(2, '0');
        return `${y}${m}${d}${h}00`;
    }

    function updateTimeRangeInputs() {
        if (currentMode === 'taf') {
            startTimeHidden.value = ""; endTimeHidden.value = ""; return;
        }

        const checkedRadio = document.querySelector('input[name="time-range"]:checked');
        if (!checkedRadio) return;

        const selectedOption = checkedRadio.value;
        const customTimeInputs = document.getElementById('custom-time-inputs');
        if (customTimeInputs) customTimeInputs.style.display = (selectedOption === 'custom') ? 'flex' : 'none';

        let sDate = new Date(baseDate);
        let eDate = new Date(baseDate);

        if (selectedOption === '24') {
            sDate.setDate(sDate.getDate() - 1); sDate.setHours(15, 0, 0, 0); eDate.setHours(15, 0, 0, 0);
        } else if (selectedOption === '8') {
            sDate.setDate(sDate.getDate() - 1); sDate.setHours(20, 0, 0, 0); eDate.setHours(4, 0, 0, 0);
        } else if (selectedOption === '4') {
            sDate.setHours(4, 0, 0, 0); eDate.setHours(8, 0, 0, 0);
        } else if (selectedOption === '12') { // 🌟 修复缺失的 12 小时分支
            sDate.setHours(8, 0, 0, 0); eDate.setHours(20, 0, 0, 0);
        } else if (selectedOption === 'custom') {
            const customStartInput = document.getElementById('custom-start-time');
            const customEndInput = document.getElementById('custom-end-time');
            let startHour = parseInt(customStartInput.value);
            let endHour = parseInt(customEndInput.value);
            if (isNaN(startHour) || isNaN(endHour)) {
                startTimeHidden.value = ""; endTimeHidden.value = ""; return;
            }
            sDate.setHours(startHour, 0, 0, 0);
            eDate.setHours(endHour, 0, 0, 0);
        } else {
            const parts = selectedOption.split('-');
            if (parts.length === 2) {
                sDate.setHours(parseInt(parts[0]), 0, 0, 0); eDate.setHours(parseInt(parts[1]), 0, 0, 0);
            } else return;
        }

        const fmt = d => {
            if (isNaN(d.getTime())) return "";
            return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}${String(d.getHours()).padStart(2, '0')}00`;
        };

        startTimeHidden.value = fmt(sDate);
        endTimeHidden.value = fmt(eDate);
    }

    async function downloadData(s, e, airports, types, callback) {
        const btn = (currentMode === 'manual') ? fetchManualBtn : ((types.includes('SA') && currentMode === 'taf') ? importTafMetarBtn : fetchTafListBtn);
        const originalText = btn.textContent; btn.textContent = "下载中..."; btn.disabled = true;
        try {
            const res = await fetch(window.OMICS_API_URL('fetch_data'), {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ token: apiToken, start_time: s, end_time: e, airports: airports, wtypes: types })
            });
            const contentType = res.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                const preview = (await res.text()).replace(/\s+/g, ' ').slice(0, 160);
                throw new Error(`服务返回了非 JSON 响应（HTTP ${res.status}）：${preview}`);
            }
            const result = await res.json();
            if (result.success && result.data) { callback(result.data); } else { alert(result.message || "未下载到数据"); }
        } catch(err) { console.error(err); alert("下载出错: " + err.message); }
        finally { btn.textContent = originalText; btn.disabled = false; }
    }

    function isTwentyFourHourRange() {
        return document.querySelector('input[name="time-range"]:checked')?.value === '24';
    }
    function syncManualFetchButtonText() {
        if (fetchManualBtn && currentMode === 'manual') fetchManualBtn.textContent = isTwentyFourHourRange() ? '下载实况/扫描预报' : '下载实况';
    }
    function resolveScannedAirportCode(value) {
        const raw = String(value || '').trim();
        const upper = raw.toUpperCase();
        if (/^[A-Z]{4}$/.test(upper)) return upper;
        const normalized = raw.replace(/机场$/u, '').trim();
        const match = Object.entries(AIRPORT_NAME_MAP).find(([code, name]) => {
            const label = String(name || '').trim();
            const labelShort = label.replace(/机场$/u, '').trim();
            return label === raw || label === normalized || labelShort === normalized || raw.includes(label) || normalized.includes(labelShort);
        });
        return match ? match[0] : upper;
    }
    function syncManualAirportChoice() {
        const allowAll = isTwentyFourHourRange();
        if (manualAirportAllLabel) manualAirportAllLabel.style.display = allowAll ? 'inline' : 'none';
        if (!allowAll && manualAirportAll?.checked) manualAirportDefault.checked = true;
        const isAll = allowAll && !!manualAirportAll?.checked;
        downloadAirports.disabled = isAll;
        if (!isAll && manualAirportDefault?.checked) downloadAirports.value = localStorage.getItem('sf_def_manual_aps') || 'ZBAA ZGSZ ZHEC ZSHC';
    }
    function showManualEvalPersonChoice(publishDateText = '') {
        const personContainer = document.getElementById('eval-person-container');
        const publishDate = document.getElementById('manual-forecast-publish-date');
        if (publishDate) publishDate.textContent = publishDateText;
        if (evalPersonSelect) evalPersonSelect.value = '';
        if (personContainer) {
            personContainer.style.display = 'flex';
            personContainer.classList.remove('hidden');
        }
    }
    async function downloadManualObservationsOnly(requested, reason = '') {
        showManualEvalPersonChoice();
        await new Promise(resolve => downloadData(startTimeHidden.value, endTimeHidden.value, requested.join(' '), ['SA', 'SP'], data => {
            const lines = typeof data === 'string' ? data.split('\n').filter(line => line.trim().length > 10) : Object.values(data || {}).flat().filter(Boolean);
            if (lines.length) { metarInput.value = lines.join('\n'); addMetarBtn?.click(); }
            resolve();
        }));
        alert(reason ? `扫描预报失败：${reason}\n已回退按目标机场下载实况，请选择预报发布人后手动录入预报。` : '已按目标机场下载实况，请选择预报发布人后手动录入预报。');
    }
    manualAirportDefault?.addEventListener('change', syncManualAirportChoice);
    manualAirportAll?.addEventListener('change', syncManualAirportChoice);
    downloadAirports?.addEventListener('input', () => {
        if (manualAirportDefault?.checked) localStorage.setItem('sf_def_manual_aps', downloadAirports.value.trim());
    });

    fetchManualBtn.addEventListener('click', async () => {
        if (!apiToken) return alert("请先登录");
        const evaluationDate = datePickerInput?.value || '';
        const root = document.getElementById('manual-forecast-path')?.value.trim() || (currentMode === 'taf' ? '.' : '');
        if (!evaluationDate) return alert('请先选择评定日期');

        const scope = manualAirportAll?.checked && isTwentyFourHourRange() ? 'all' : 'default';
        const requested = downloadAirports.value.split(/[\s,]+/).map(v => v.trim().toUpperCase()).filter(Boolean);
        if (currentMode === 'manual' && !window.__manualGridTimeLocked) updateTimeRangeInputs();
        fetchManualBtn.disabled = true;
        const originalText = fetchManualBtn.textContent;
        let scanStage = 'scan';
        fetchManualBtn.textContent = '正在扫描预报并下载实况...';
        try {
            if (currentMode === 'manual' && !isTwentyFourHourRange()) {
                const toUtc = value => {
                    const y = Number(value.slice(0, 4)), m = Number(value.slice(4, 6)) - 1, d = Number(value.slice(6, 8)), h = Number(value.slice(8, 10));
                    const utc = new Date(Date.UTC(y, m, d, h - 8));
                    return `${utc.getUTCFullYear()}${String(utc.getUTCMonth() + 1).padStart(2, '0')}${String(utc.getUTCDate()).padStart(2, '0')}${String(utc.getUTCHours()).padStart(2, '0')}00`;
                };
                showManualEvalPersonChoice();
                await new Promise(resolve => downloadData(toUtc(startTimeHidden.value), toUtc(endTimeHidden.value), requested.join(' '), ['SA', 'SP'], data => {
                    const lines = typeof data === 'string' ? data.split('\n').filter(line => line.trim().length > 10) : Object.values(data || {}).flat().filter(Boolean);
                    if (lines.length) { metarInput.value = lines.join('\n'); addMetarBtn?.click(); }
                    resolve();
                }));
                alert('已按目标机场下载实况，请选择预报发布人后手动录入预报。');
                return;
            }
            if (currentMode === 'taf') {
                const airports = downloadAirports.value.trim();
                if (!airports) throw new Error('璇疯緭鍏ョ洰鏍囨満鍦?');
                await new Promise(resolve => {
                    downloadData(startTimeHidden.value, endTimeHidden.value, airports, ['SA', 'SP'], data => {
                        const lines = typeof data === 'string' ? data.split('\n').filter(line => line.trim().length > 10) : Object.values(data || {}).flat().filter(Boolean);
                        const cleaned = lines.map(line => { const text = String(line).trim(); const i = text.search(/(METAR|SPECI|[A-Z]{4}\s+\d{6}Z)/); return i > 0 ? text.substring(i) : text; });
                        if (cleaned.length) { metarInput.value = cleaned.join('\n'); addMetarBtn?.click(); }
                        resolve();
                    });
                });
                alert('鎵弿棰勬姤澶辫触，已回退为按目标机场下载实况。');
                return;
            }
            if (!root) {
                await downloadManualObservationsOnly(requested, '未配置席位预报24小时预报路径');
                return;
            }
            const form = new FormData();
            form.append('manual_forecast_path', root);
            form.append('evaluation_date', evaluationDate);
            const response = await fetch(window.OMICS_API_URL('import_publish_excel'), { method: 'POST', body: form });
            const result = await response.json();
            if (!result.success) {
                const reason = result.error || '扫描预报失败';
                await downloadManualObservationsOnly(requested, reason);
                return;
            }
            const data = result.data || {};
            const allEntries = (Array.isArray(data.airports) ? data.airports : []).map(entry => ({
                ...entry,
                airport_code: resolveScannedAirportCode(entry.airport_code || entry.airport_name)
            }));
            if (!allEntries.length) throw new Error('扫描到的预报表中没有机场');
            const entries = scope === 'all' ? allEntries : allEntries.filter(entry => requested.includes(entry.airport_code));
            if (!entries.length) throw new Error(scope === 'all' ? '扫描到的预报没有可用机场' : '默认机场未出现在扫描到的24小时预报中');

            const startHour = Number(data.start_hour_bjt);
            const validity = Math.max(1, Number(data.validity_hours || 24));
            if (!Number.isFinite(startHour) || !data.forecast_date) throw new Error('预报表缺少有效的发布时间或起报时间');
            const start = new Date(`${data.forecast_date}T${String(startHour).padStart(2, '0')}:00:00`);
            const end = new Date(start.getTime() + validity * 3600000);
            const fmt = d => `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}${String(d.getHours()).padStart(2,'0')}00`;
            startTimeHidden.value = fmt(start); endTimeHidden.value = fmt(end);
            window.__manualGridTimeLocked = true;

            downloadAirports.value = entries.map(entry => entry.airport_code).join(' ');
            generateGridBtn.click();
            const byName = new Map(entries.map(entry => [entry.airport_code, entry]));
            document.querySelectorAll('#manual-grid tbody tr').forEach(tr => {
                const entry = byName.get(String(tr.dataset.airport || '').trim().toUpperCase());
                if (!entry) return;
                const merged = [];
                (entry.rows || []).forEach(row => row.forEach((value, index) => { merged[index] = mergeManualForecastCell(merged[index], value); }));
                tr.querySelectorAll('input[data-col]').forEach((input, index) => { input.value = merged[index] || ''; });
            });

            if (data.eval_person) {
                const person = document.getElementById('eval-person-select');
                if (person && !Array.from(person.options).some(option => option.value === data.eval_person)) person.add(new Option(data.eval_person, data.eval_person));
                if (person) person.value = data.eval_person;
            }
            const personContainer = document.getElementById('eval-person-container');
            const publishDate = document.getElementById('manual-forecast-publish-date');
            if (publishDate) publishDate.textContent = `预报发布时间：${data.publish_date || data.forecast_date || '未知'}`;
            if (personContainer) { personContainer.style.display = 'flex'; personContainer.classList.remove('hidden'); }

            function resolveToUtcForFetch(bjtStr, offsetHour = 0) {
                const y = Number(bjtStr.slice(0,4)), m = Number(bjtStr.slice(4,6)) - 1, d = Number(bjtStr.slice(6,8)), h = Number(bjtStr.slice(8,10));
                const utc = new Date(Date.UTC(y, m, d, h - 8 + offsetHour, 0));
                return `${utc.getUTCFullYear()}${String(utc.getUTCMonth()+1).padStart(2,'0')}${String(utc.getUTCDate()).padStart(2,'0')}${String(utc.getUTCHours()).padStart(2,'0')}00`;
            }
            const fetchStartTime = resolveToUtcForFetch(startTimeHidden.value, -1);
            scanStage = 'metar';
            const fetchEndTime = resolveToUtcForFetch(endTimeHidden.value, 1);
            await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('下载实况超时，请检查网络或服务状态')), 60000);
                downloadData(fetchStartTime, fetchEndTime, entries.map(entry => entry.airport_code).join(' '), ['SA', 'SP'], dataResult => {
                    let arr = [];
                    if (typeof dataResult === 'string') arr = dataResult.split('\n').filter(line => line.trim().length > 10);
                    else if (dataResult && typeof dataResult === 'object') Object.values(dataResult).forEach(list => { if (Array.isArray(list)) arr.push(...list); });
                    if (!arr.length) { clearTimeout(timeout); reject(new Error('未查到对应机场实况报文')); return; }
                    const cleaned = arr.map(line => { let text = String(line).trim(); const i = text.search(/(METAR|SPECI|[A-Z]{4}\s+\d{6}Z)/); return i > 0 ? text.substring(i) : text; });
                    metarInput.value = cleaned.join('\n');
                    if (addMetarBtn) addMetarBtn.click();
                    clearTimeout(timeout); resolve();
                });
            });
            alert(`已扫描 ${data.publish_date || data.forecast_date || '前一天'} 预报，生成 ${entries.length} 个机场表格，并导入对应实况报文。`);
        } catch (error) {
            alert(`扫描预报/下载实况失败：${error.message}`);
            if (currentMode === 'manual' && scanStage === 'scan') {
                await downloadManualObservationsOnly(requested, error.message);
            } else {
                alert(`下载实况失败：${error.message}`);
            }
        } finally {
            fetchManualBtn.disabled = false;
            fetchManualBtn.textContent = originalText;
        }
    });

    fetchTafListBtn.addEventListener('click', async () => {
        if (!apiToken) return alert("请先登录");
        const y = baseDate.getFullYear(), m = baseDate.getMonth(), d = baseDate.getDate();
        const utcBase = new Date(Date.UTC(y, m, d));
        const searchDate = new Date(utcBase); searchDate.setUTCDate(d - 2); const targetDay = searchDate.getUTCDate();
        const searchStart = new Date(searchDate); searchStart.setUTCHours(0);
        const searchEnd = new Date(searchDate); searchEnd.setUTCDate(searchDate.getUTCDate() + 1); searchEnd.setUTCHours(0);
        await downloadData(formatFullTime(searchStart), formatFullTime(searchEnd), downloadAirports.value, ["FT", "FC"], (text) => {
            if(!text) return alert("该时段未查询到 TAF 报文"); renderTafList(text, targetDay);
        });
    });

    function renderTafList(text, targetDay) {
        const forecastInputGroup = document.getElementById('forecast-input-group');
        if (forecastInputGroup) forecastInputGroup.style.display = 'block';

        // 🌟 修复:补充声明这三个关键组件
        const tafSelectionArea = document.getElementById('taf-selection-area');
        const importTafMetarContainer = document.getElementById('import-taf-metar-container');
        const tafListItems = document.getElementById('taf-list-items');

        if (tafSelectionArea) {
            tafSelectionArea.classList.remove('hidden');
            tafSelectionArea.style.display = 'block';
        }
        if (importTafMetarContainer) {
            importTafMetarContainer.classList.remove('hidden');
            importTafMetarContainer.style.display = 'block';
        }

        tafListItems.innerHTML = '';
        const raws = text.split('\n').filter(s => s.trim().length > 5);
        let count = 0;
        raws.forEach((raw) => {
            const match = raw.match(/\s(\d{2})(\d{2})(\d{2})Z\s/);
            if (match && parseInt(match[1]) !== targetDay) return;
            const div = document.createElement('div'); div.className = 'taf-item-row';
            const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = true; checkbox.dataset.raw = raw;
            const content = document.createElement('div'); content.className = 'taf-content'; content.textContent = raw;
            div.appendChild(checkbox); div.appendChild(content); tafListItems.appendChild(div); count++;
        });
        if (count === 0) tafListItems.innerHTML = '<p style="color:red;">未找到指定日期 ('+targetDay+'日) 的 TAF 报文</p>';
    }

    importTafMetarBtn.addEventListener('click', async () => {
        if (!apiToken) return alert("请先登录");

        const selectedTafs = Array.from(document.querySelectorAll('#taf-list-items input:checked'));
        if (selectedTafs.length === 0) return alert('请先选择需要评定的 TAF 报文!');

        const rawTexts = selectedTafs
            .map(cb => cb.dataset.raw || cb.getAttribute('data-raw') || '')
            .filter(Boolean);
        if (rawTexts.length === 0) return alert("报文内容为空,请重新查询");

        function resolveTafUtcDate(day, hour, baseDateObj) {
            let d = parseInt(day, 10), h = parseInt(hour, 10);
            let monthIndex = baseDateObj.getMonth();
            if (d > baseDateObj.getDate() + 5) monthIndex -= 1;
            else if (d < baseDateObj.getDate() - 5) monthIndex += 1;
            return new Date(Date.UTC(baseDateObj.getFullYear(), monthIndex, d, h, 0, 0));
        }

        function formatUtcForApi(dateObj) {
            return `${dateObj.getUTCFullYear()}${String(dateObj.getUTCMonth() + 1).padStart(2, '0')}${String(dateObj.getUTCDate()).padStart(2, '0')}${String(dateObj.getUTCHours()).padStart(2, '0')}00`;
        }

        let minValidTime = null;
        let maxValidTime = null;
        const tafValidityRegex = /(\d{2})(\d{2})\/(\d{2})(\d{2})/g;
        rawTexts.forEach(rawText => {
            let timeMatch;
            tafValidityRegex.lastIndex = 0;
            while ((timeMatch = tafValidityRegex.exec(rawText)) !== null) {
                const startUtc = resolveTafUtcDate(timeMatch[1], timeMatch[2], baseDate);
                let endUtc = resolveTafUtcDate(timeMatch[3], timeMatch[4], baseDate);
                if (endUtc <= startUtc) endUtc = new Date(endUtc.getTime() + 24 * 3600 * 1000);
                if (!minValidTime || startUtc < minValidTime) minValidTime = startUtc;
                if (!maxValidTime || endUtc > maxValidTime) maxValidTime = endUtc;
            }
        });

        if (!minValidTime || !maxValidTime) return alert("无法从选中报文中识别出有效时间段");

        // 下载实况必须覆盖所有选中 TAF 的完整 UTC 有效期;允许前后扩大,不能缩小。
        const fetchStartDate = new Date(minValidTime.getTime() - 1 * 3600 * 1000);
        const fetchEndDate = new Date(maxValidTime.getTime() + 1 * 3600 * 1000);
        startTimeHidden.value = formatUtcForApi(minValidTime);
        endTimeHidden.value = formatUtcForApi(maxValidTime);
        const fetchStartTime = formatUtcForApi(fetchStartDate);
        const fetchEndTime = formatUtcForApi(fetchEndDate);
        const airportsInput = document.getElementById('download-airports').value;
        const aps = airportsInput.split(/[\s,]+/).filter(x => x.length > 0);
        if (aps.length === 0) return alert("请输入机场代码!");

        resultsContainer.innerHTML = '<div class="loader" style="display:block;"></div>';
        const originalText = importTafMetarBtn.textContent;
        importTafMetarBtn.textContent = "批量下载中...";
        importTafMetarBtn.disabled = true;

        try {
            let allArr = [];
            for (let ap of aps) {
                await new Promise(resolve => {
                    downloadData(fetchStartTime, fetchEndTime, ap, ["SA", "SP"], (data) => {
                        if (typeof data === 'string') {
                            allArr.push(...data.split('\n').filter(line => line.trim().length > 10));
                        } else if (typeof data === 'object' && data !== null) {
                            Object.values(data).forEach(list => { if (Array.isArray(list)) allArr.push(...list); });
                        }
                        resolve();
                    });
                });
            }

            if (allArr.length === 0) return alert(`未查到实况数据!\n(已查询 UTC 区间: ${fetchStartTime} - ${fetchEndTime})`);

            const cleanedArr = allArr.map(line => {
                let text = line.trim();
                const matchIndex = text.search(/(METAR|SPECI|[A-Z]{4}\s+\d{6}Z)/);
                if (matchIndex > 0) text = text.substring(matchIndex);
                return text;
            });

            const metarInput = document.getElementById('metar-input');
            const addMetarBtn = document.getElementById('add-metar-btn');

            metarInput.value = cleanedArr.join('\n');
            if (addMetarBtn) addMetarBtn.click();

            alert(`✅ 成功导入并解析 ${cleanedArr.length} 条实况!(包含 ${aps.length} 个机场)`);
        } catch (e) {
            alert("❌ 批量导入过程出错: " + e.message);
        } finally {
            resultsContainer.innerHTML = '';
            importTafMetarBtn.textContent = originalText;
            importTafMetarBtn.disabled = false;
        }
    });

    generateGridBtn.addEventListener('click', () => {
        if (!window.__manualGridTimeLocked) updateTimeRangeInputs();
        window.__manualGridTimeLocked = false;
        const sTime = startTimeHidden.value;
        const eTime = endTimeHidden.value;
        if (!sTime || !eTime) return alert("请先在上方设置并确认时间范围!");

        const headers = generateHourlyHeaders(sTime, eTime);
        const aps = downloadAirports.value.split(/[\s,]+/).filter(x => x).map(x => x.toUpperCase());
        let html = `<table class="manual-grid-table" id="manual-grid"><thead><tr><th class="header-col">机场</th>`;
        headers.forEach(h => html += `<th>${h}</th>`);
        html += `<th>操作</th></tr></thead><tbody>`;
        aps.forEach(ap => {
            const name = AIRPORT_NAME_MAP[ap] || ap;
            html += `<tr data-airport="${ap}"><td class="header-col">${name}</td>`;
            headers.forEach((h, idx) => { html += `<td><input type="text" data-hour="${h}" data-col="${idx}"></td>`; });
            html += `<td class="actions-cell"><button class="add-row-btn" title="复制">+</button></td></tr>`;
        });
        html += `</tbody></table>`;
        manualGridContainer.innerHTML = html;
        pasteExcelBtn.classList.remove('hidden');
    });

    function generateHourlyHeaders(startStr, endStr) {
        if (!startStr || !endStr) return [];

        function parseToUTC(str) {
            if (str.length === 12) {
                return new Date(Date.UTC(parseInt(str.slice(0,4)), parseInt(str.slice(4,6))-1, parseInt(str.slice(6,8)), parseInt(str.slice(8,10))));
            } else if (str.length >= 6) {
                let y = baseDate.getFullYear(), m = baseDate.getMonth(), d = parseInt(str.slice(0,2)), h = parseInt(str.slice(2,4));
                return new Date(Date.UTC(y, m, d, h));
            }
            return new Date();
        }

        let current = parseToUTC(startStr);
        let endObj = parseToUTC(endStr);

        if (endObj <= current && startStr.length < 12) endObj.setUTCMonth(endObj.getUTCMonth() + 1);

        const headers = [];
        let safety = 0;
        while (current < endObj && safety < 200) {
            let d = String(current.getUTCDate()).padStart(2, '0');
            let h = String(current.getUTCHours()).padStart(2, '0');
            headers.push(`${d}${h}`);
            current.setUTCHours(current.getUTCHours() + 1);
            safety++;
        }
        return headers;
    }

    manualGridContainer.addEventListener('click', event => {
        if (event.target.classList.contains('add-row-btn')) {
            const currentRow = event.target.closest('tr');
            const newRow = currentRow.cloneNode(true);
            newRow.querySelectorAll('input').forEach(input => input.value = '');
            newRow.querySelector('.actions-cell').innerHTML = `<button class="delete-row-btn">X</button>`;
            currentRow.insertAdjacentElement('afterend', newRow);
        }
        if (event.target.classList.contains('delete-row-btn')) event.target.closest('tr').remove();
    });

    pasteExcelBtn.addEventListener('click', async () => {
        if (!confirm('是否确认手动操作？这将使用剪贴板内容填入当前预报表格。')) return;
        try {
            const text = await navigator.clipboard.readText();
            const rawRows = text.replace(/\r/g, '').trimEnd().split('\n');
            const rows = [];
            rawRows.forEach(line => {
                if (line.includes('\t') || !rows.length) rows.push(line);
                else rows[rows.length - 1] += ` ${line.trim()}`;
            });
            const trs = document.getElementById('manual-grid').querySelectorAll('tbody tr');
            rows.forEach((rowText, i) => {
                if (trs[i]) {
                    const cells = rowText.split('\t');
                    const inputs = trs[i].querySelectorAll('input');
                    cells.forEach((val, j) => { if (inputs[j]) inputs[j].value = val.trim(); });
                }
            });
        } catch (e) { alert("无法访问剪贴板"); }
    });

    function renderAirportTags() {
        airportBtnsContainer.innerHTML = '';
        airportBtnsContainer.style.display = 'block';

        const metarKeys = Object.keys(storedMetars).sort();

        if (metarKeys.length > 0) {
            document.getElementById('forecast-input-group').style.display = 'block';
        } else {
            if (currentMode === 'manual') document.getElementById('forecast-input-group').style.display = 'none';
        }

        metarKeys.forEach(ap => {
            const wrapper = document.createElement('div');
            wrapper.className = 'airport-tag-wrapper';
            wrapper.style.display = 'inline-flex';
            wrapper.style.alignItems = 'center';
            wrapper.style.margin = '5px 8px 5px 0';
            wrapper.style.background = '#E2E8F0';
            wrapper.style.borderRadius = '6px';
            wrapper.style.overflow = 'hidden';

            const btn = document.createElement('button');
            btn.className = 'mini-btn';
            btn.style.border = 'none';
            btn.style.background = 'transparent';
            btn.style.padding = '6px 12px';
            btn.style.color = '#2C3E50';
            btn.style.fontWeight = 'bold';
            btn.style.cursor = 'pointer';
            btn.innerText = `${AIRPORT_NAME_MAP[ap] || ap} (${storedMetars[ap].length}条)`;

            btn.onclick = (e) => {
                e.preventDefault();
                modalTitle.textContent = `机场 ${ap} 实况`;
                modalDisplay.innerHTML = `<textarea readonly style="width:100%;height:300px;font-family:monospace;white-space:pre-wrap;">${storedMetars[ap].join('\n')}</textarea>`;
                metarModal.style.display = 'flex';
            };

            const delBtn = document.createElement('button');
            delBtn.innerText = '✖';
            delBtn.style.border = 'none';
            delBtn.style.background = '#CBD5E0';
            delBtn.style.color = '#fff';
            delBtn.style.padding = '6px 10px';
            delBtn.style.cursor = 'pointer';
            delBtn.onclick = (e) => {
                e.stopPropagation();
                delete storedMetars[ap];
                renderAirportTags();
            };

            wrapper.appendChild(btn);
            wrapper.appendChild(delBtn);
            airportBtnsContainer.appendChild(wrapper);
        });
    }

    addMetarBtn.addEventListener('click', () => {
        const text = metarInput.value.trim().toUpperCase(); if(!text) return;
        text.split('\n').forEach(line => {
            line = line.trim(); if(!line) return;
            let match = line.match(/(?:METAR|SPECI)\s+([A-Z]{4})/);
            if (!match) match = line.match(/^([A-Z]{4})\s+\d{6}Z/);
            if (match) {
                const ap = match[1]; if (!storedMetars[ap]) storedMetars[ap] = [];
                if (!storedMetars[ap].includes(line)) storedMetars[ap].push(line);
            }
        });
        renderAirportTags(); metarInput.value = '';
    });

    const addTafBtn = document.getElementById('add-taf-btn');
    if (addTafBtn) {
        addTafBtn.addEventListener('click', () => {
            const tafInput = document.getElementById('taf-input');
            const text = tafInput.value.trim().toUpperCase();
            if (!text) return alert("请先在框内粘贴 TAF 报文!");

            const raws = text.split('\n').filter(s => s.trim().length > 5);
            const tafListItems = document.getElementById('taf-list-items');
            let count = 0;

            raws.forEach((raw) => {
                const div = document.createElement('div');
                div.className = 'taf-item-row';
                div.style.display = 'flex';
                div.style.alignItems = 'center';
                div.style.marginBottom = '6px';

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = true;
                checkbox.dataset.raw = raw;

                const content = document.createElement('div');
                content.className = 'taf-content';
                content.textContent = raw;
                content.style.color = '#005A9C';
                content.style.fontWeight = 'bold';
                content.style.flex = '1';

                const delBtn = document.createElement('button');
                delBtn.innerText = '✖ 删除';
                delBtn.style.cssText = 'border:none; background:#ff4d4f; color:white; padding:3px 8px; border-radius:4px; font-size:12px; cursor:pointer; margin-left:15px;';
                delBtn.onclick = (e) => {
                    div.remove();
                    if (tafListItems.children.length === 0) {
                        document.getElementById('taf-selection-area').style.display = 'none';
                        document.getElementById('import-taf-metar-container').style.display = 'none';
                    }
                };

                div.appendChild(checkbox);
                div.appendChild(content);
                div.appendChild(delBtn);
                tafListItems.appendChild(div);
                count++;
            });

            if (count > 0) {
                tafInput.value = '';
                const forecastInputGroup = document.getElementById('forecast-input-group');
                const tafSelectionArea = document.getElementById('taf-selection-area');
                const importTafMetarContainer = document.getElementById('import-taf-metar-container');

                if (forecastInputGroup) forecastInputGroup.style.display = 'block';
                if (tafSelectionArea) { tafSelectionArea.classList.remove('hidden'); tafSelectionArea.style.display = 'block'; }
                if (importTafMetarContainer) { importTafMetarContainer.classList.remove('hidden'); importTafMetarContainer.style.display = 'block'; }

                alert(`✅ 成功添加 ${count} 份手工 TAF 报文到评定列表!\n请勾选后点击下方按钮下载实况。`);
            }
        });
    }

    scoreButton.addEventListener('click', async () => {
        loader.style.display = 'block'; scoreButton.disabled = true; resultsContainer.innerHTML = '';
        try {
            const standards = {
                vis_takeoff: document.getElementById('vis_takeoff').value,
                vis_landing: document.getElementById('vis_landing').value,
                vis_warning: document.getElementById('vis_warning').value,
                cld_takeoff: document.getElementById('cld_takeoff').value,
                cld_landing: document.getElementById('cld_landing').value,
                cld_warning: document.getElementById('cld_warning').value,
                wind_warning: document.getElementById('wind_warning') ? document.getElementById('wind_warning').value : 17
            };
            let payload = {
                standards: standards,
                forecast_mode: currentMode,
                phenomena_config: phenomenaSettings,
                custom_thresholds: customAirportsThresholds,
                recognize_amd: document.getElementById('admin-recognize-amd')?.checked || false
            };
            const checkedTimeRadio = document.querySelector('input[name="time-range"]:checked');
            payload.time_range_text = checkedTimeRadio ? checkedTimeRadio.parentNode.textContent.trim() : '综合预报';
            payload.export_config = {
                backup_path: document.getElementById('backup-save-path') ? document.getElementById('backup-save-path').value.trim() : '',
                excel_root: document.getElementById('excel-export-path') ? document.getElementById('excel-export-path').value.trim() : '',
                eval_person: document.getElementById('eval-person-select') ? document.getElementById('eval-person-select').value : '',
                base_date_str: document.getElementById('base-date-picker') ? document.getElementById('base-date-picker').value : ''
            };

            if (currentMode === 'manual' && !payload.export_config.eval_person) {
                throw new Error("席位预报评定必须选择【评定对象】!");
            }
            if (!payload.export_config.base_date_str) {
                payload.export_config.base_date_str = new Date().toISOString().split('T')[0];
            }

            function bjtToUtcTimestamp(bjtStr) {
                if (!bjtStr || bjtStr.length !== 12) return bjtStr;
                let y = parseInt(bjtStr.slice(0, 4)), m = parseInt(bjtStr.slice(4, 6)) - 1;
                let d = parseInt(bjtStr.slice(6, 8)), h = parseInt(bjtStr.slice(8, 10));
                let utcDate = new Date(Date.UTC(y, m, d, h - 8, 0));
                return `${utcDate.getUTCFullYear()}${String(utcDate.getUTCMonth() + 1).padStart(2, '0')}${String(utcDate.getUTCDate()).padStart(2, '0')}${String(utcDate.getUTCHours()).padStart(2, '0')}00`;
            }

            const manualMetarText = document.getElementById('metar-input') ? document.getElementById('metar-input').value.trim() : '';

            if (currentMode === 'manual') {
                const storedText = Object.values(storedMetars).flat().join('\n');
                payload.obs_text = storedText + (manualMetarText ? '\n' + manualMetarText : '');

                payload.start_time = bjtToUtcTimestamp(startTimeHidden.value);
                payload.end_time = bjtToUtcTimestamp(endTimeHidden.value);

                const manualForecasts = {};
                const gridRows = document.querySelectorAll('#manual-grid tbody tr');

                if (gridRows.length > 0) {
                    gridRows.forEach(tr => {
                        const ap = tr.dataset.airport;
                        if (!manualForecasts[ap]) manualForecasts[ap] = {};
                        tr.querySelectorAll('input').forEach(input => {
                            const val = input.value.trim();

                            let bjtHour = input.dataset.hour;
                            let d = parseInt(bjtHour.slice(0, 2)), h = parseInt(bjtHour.slice(2, 4));
                            let mIndex = baseDate.getMonth();
                            if (d > baseDate.getDate() + 15) mIndex -= 1;
                            else if (d < baseDate.getDate() - 15) mIndex += 1;

                            let utcDate = new Date(Date.UTC(baseDate.getFullYear(), mIndex, d, h - 8, 0));
                            let utcKey = `${String(utcDate.getUTCDate()).padStart(2, '0')}${String(utcDate.getUTCHours()).padStart(2, '0')}`;

                            if (!(utcKey in manualForecasts[ap])) manualForecasts[ap][utcKey] = '';
                            manualForecasts[ap][utcKey] = mergeManualForecastCell(manualForecasts[ap][utcKey], val);
                        });
                    });
                    Object.values(manualForecasts).forEach(hourly => {
                        Object.keys(hourly).forEach(hour => {
                            if (!hourly[hour]) hourly[hour] = 'NSW';
                        });
                    });
                }

                if (Object.keys(manualForecasts).length === 0 || Object.values(manualForecasts).every(f => Object.keys(f).length === 0)) {
                    throw new Error("请先填写预报表格!(可使用Excel粘贴)");
                }

                payload.manual_forecasts = manualForecasts;

            } else {
                const checkedBoxes = document.querySelectorAll('#taf-list-items input:checked');
                let rawTafText = [...checkedBoxes].map(cb => cb.dataset.raw).join('\n');

                rawTafText = rawTafText.replace(/(\d{2})(\d{2})\/(\d{2})24/g, (match, p1, p2, p3) => {
                     let y = baseDate.getFullYear(), m = baseDate.getMonth(), d = parseInt(p3);
                     if (d > baseDate.getDate() + 15) { m -= 1; } else if (d < baseDate.getDate() - 15) { m += 1; }
                     let correctedDate = new Date(y, m, d, 24, 0);
                     return `${p1}${p2}/${String(correctedDate.getDate()).padStart(2, '0')}00`;
                });

                payload.taf_text = rawTafText;
                payload.additional_forecast_text = "";

                let minT = null, maxT = null;
                const timeRegex = /(\d{2})(\d{2})\/(\d{2})(\d{2})/g;
                let match;
                while ((match = timeRegex.exec(rawTafText)) !== null) {
                    let s_d = parseInt(match[1]), s_h = parseInt(match[2]);
                    let e_d = parseInt(match[3]), e_h = parseInt(match[4]);

                    let s_m = baseDate.getMonth(), e_m = baseDate.getMonth();
                    if (s_d > baseDate.getDate() + 5) s_m -= 1; else if (s_d < baseDate.getDate() - 5) s_m += 1;
                    if (e_d > baseDate.getDate() + 5) e_m -= 1; else if (e_d < baseDate.getDate() - 5) e_m += 1;

                    let s_t = Date.UTC(baseDate.getFullYear(), s_m, s_d, s_h, 0);
                    let e_t = Date.UTC(baseDate.getFullYear(), e_m, e_d, e_h, 0);

                    if (minT === null || s_t < minT) minT = s_t;
                    if (maxT === null || e_t > maxT) maxT = e_t;
                }

                if (minT !== null && maxT !== null) {
                    let sd = new Date(minT - 48 * 3600 * 1000); sd.setUTCHours(sd.getUTCHours() + 8);
                    let ed = new Date(maxT + 48 * 3600 * 1000); ed.setUTCHours(ed.getUTCHours() + 8);

                    payload.start_time = `${sd.getUTCFullYear()}${String(sd.getUTCMonth()+1).padStart(2,'0')}${String(sd.getUTCDate()).padStart(2,'0')}000000`;
                    payload.end_time = `${ed.getUTCFullYear()}${String(ed.getUTCMonth()+1).padStart(2,'0')}${String(ed.getUTCDate()).padStart(2,'0')}235959`;
                } else {
                    payload.start_time = startTimeHidden.value;
                    payload.end_time = endTimeHidden.value;
                }

                const storedText = Object.values(storedMetars).flat().join('\n');
                payload.obs_text = storedText ? storedText + (manualMetarText ? '\n' + manualMetarText : '') : manualMetarText;
            }

            if (!payload.obs_text || payload.obs_text.trim() === '') {
                throw new Error("实况数据为空!请先在左上方点击【下载实况】,或在框内手动粘贴实况报文。");
            }

            const response = await fetch(window.OMICS_API_URL('score'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            const result = await response.json();
            if (!result.success) throw new Error(result.error);
            if (Object.keys(result.data).length === 0) {
                resultsContainer.innerHTML = '<div class="stats-box">没有生成评分结果。</div>';
            } else {
                displayResults(result.data);
                window.lastScoreResults = result.data;
                window.lastScoreBaseDateStr = payload.export_config.base_date_str;
                const saveBtn = document.getElementById('manual-save-btn');
                if (saveBtn) saveBtn.style.display = 'block';
                const checkBtn = document.getElementById('check-saved-file-btn');
                if (checkBtn) checkBtn.style.display = 'none';
            }

        } catch (e) { resultsContainer.innerHTML = `<div class="error-box">评分失败: ${e.message}</div>`; }
        finally { loader.style.display = 'none'; scoreButton.disabled = false; }
    });

    function displayResults(data) {
        let finalHTML = '';
        for (const resultKey in data) {
            const airportData = data[resultKey];
            const { scores, observations, statistics } = airportData;
            if (!scores || scores.length === 0) continue;

            const baseAirportCode = resultKey.split('_')[0];
            const airportName = AIRPORT_NAME_MAP[baseAirportCode] || baseAirportCode;
            let title = `评定结果: ${airportName}`;
            if (resultKey.includes('_')) title += ` [TAF时段: ${resultKey.split('_')[1]}]`;

            let html = `<div class="result-card"><h3>${title}</h3>`;

            if (currentMode === 'taf' && airportData.recognized_forecasts) {
                let recHtml = `
                <div class="taf-horizontal-recognition">
                    <h4>📝 逐时报文识别与分解 (核对用)</h4>
                    <div class="taf-horizontal-grid">
                `;
                airportData.recognized_forecasts.forEach(f => {
                    recHtml += `
                        <div class="taf-horizontal-card">
                            <div class="taf-horizontal-card-header">${f.hour} UTC</div>
                            <div class="taf-horizontal-card-body">${f.text}</div>
                        </div>
                    `;
                });
                recHtml += `</div></div>`;
                html += recHtml;
            }

            if (airportData.forecast_summary_bjt) {
                html += `<div class="forecast-summary">${airportData.forecast_summary_bjt}</div>`;
            }

            const timeSlots = scores.map(s => s['时次']);
            const displayTimeSlots = timeSlots.map(utcStr => {
                if (currentMode === 'manual' && utcStr.length === 4) {
                    let d = parseInt(utcStr.slice(0, 2)), h = parseInt(utcStr.slice(2, 4));
                    let mIndex = baseDate.getMonth();
                    if (d > baseDate.getDate() + 15) mIndex -= 1; else if (d < baseDate.getDate() - 15) mIndex += 1;
                    let bjtDate = new Date(Date.UTC(baseDate.getFullYear(), mIndex, d, h + 8, 0));
                    return `${String(bjtDate.getUTCDate()).padStart(2, '0')}${String(bjtDate.getUTCHours()).padStart(2, '0')}`;
                }
                return utcStr;
            });

            const obsByTime = new Map(observations.map(o => [o['时次'], o]));
            const scoresByTime = new Map(scores.map(s => [s['_time'] || s['时次'], s]));
            const items = Object.keys(scores[0]).filter(key => !['时次', '预报内容', '预报全文', '预报时效'].includes(key));

            html += `<div class="table-wrapper"><table class="result-table"><thead><tr><th class="item-header-col">项目 / 时次</th>${displayTimeSlots.map(t => `<th>${t}</th>`).join('')}</tr></thead><tbody>`;
            items.forEach(item => {
                const hasScore = scores.some(row => row[item] && row[item] !== '不评');
                const rowClass = hasScore ? 'scored-row' : 'unscored-row';
                html += `<tr class="${rowClass}"><td class="item-header-col copyable-header" title="点击复制该要素两行数据 (无表头)">${item} (实况)</td>`;
                timeSlots.forEach(time => { html += `<td>${(obsByTime.get(time) || {})[item] || '/'}</td>`; });
                html += `</tr><tr class="${rowClass}"><td class="item-header-col copyable-header" title="点击复制该要素两行数据 (无表头)">${item} (评分)</td>`;
                timeSlots.forEach(time => {
                    const val = (scoresByTime.get(time) || {})[item] || '不评';
                    const cls = val.replace(/\s+/g, '').replace('/NSW','');
                    html += `<td class="score-cell score-${cls}">${val}</td>`;
                });
                html += `</tr>`;
            });
            html += `</tbody></table></div>`;

            let statsHtml = '';
            if (typeof statistics === 'object' && statistics !== null) {
                let perf = statistics["完美"] || 0;
                let exc = statistics["优秀"] || 0;
                let fa = statistics["空报"] || 0;
                let miss = statistics["漏报"] || 0;
                let acc = statistics["准确"] || 0;
                let eval_c = statistics["参评"] || 0;
                let tot = statistics["总评"] || 1;
                if (tot === 0) tot = 1;

                let perfRate = eval_c > 0 ? (perf / eval_c * 100) : 0;
                let excRate = eval_c > 0 ? (exc / eval_c * 100) : 0;
                let faRate = tot > 0 ? (fa / tot * 100) : 0;
                let missRate = tot > 0 ? (miss / tot * 100) : 0;
                let accRate = tot > 0 ? (acc / tot * 100) : 0;

                let totalScore = (accRate * 0.5) + (perfRate * 0.3) + (excRate * 0.2) - (faRate * 0.1) - (missRate * 0.1);

                statsHtml = `
                <div class="table-wrapper" style="margin-top: 15px; border-top: 2px dashed #e2e8f0; padding-top: 15px;">
                    <table class="result-table" style="text-align:center; width: 100%; margin: 0;">
                        <thead>
                            <tr>
                                <th></th>
                                <th>完美</th>
                                <th>优秀</th>
                                <th>空报</th>
                                <th>漏报</th>
                                <th>准确</th>
                                <th>参评</th>
                                <th>总评</th>
                                <th>总分</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td style="font-weight:bold; background-color: #f8f9fa;">次数</td>
                                <td>${perf}</td>
                                <td>${exc}</td>
                                <td style="color:red;">${fa}</td>
                                <td style="color:orange;">${miss}</td>
                                <td style="font-weight:bold;">${acc}</td>
                                <td>${eval_c}</td>
                                <td>${tot}</td>
                                <td rowspan="2" style="vertical-align:middle; font-weight:bold; font-size:16px; color:#DA251D; background-color: #fffafb;">${totalScore.toFixed(2)}</td>
                            </tr>
                            <tr>
                                <td style="font-weight:bold; background-color: #f8f9fa;">概率</td>
                                <td>${perfRate.toFixed(2)}%</td>
                                <td>${excRate.toFixed(2)}%</td>
                                <td>${faRate.toFixed(2)}%</td>
                                <td>${missRate.toFixed(2)}%</td>
                                <td style="color:green; font-weight:bold;">${accRate.toFixed(2)}%</td>
                                <td style="background-color: #f8f9fa;"></td>
                                <td style="background-color: #f8f9fa;"></td>
                            </tr>
                        </tbody>
                    </table>
                </div>`;
            } else {
                statsHtml = `<div class="stats-box">${statistics}</div>`;
            }

            html += statsHtml + `</div>`;
            finalHTML += html;
        }
        document.getElementById('results-' + currentMode).innerHTML = finalHTML;
    }

    const btnStatsDay = document.getElementById('btn-stats-day');
    const btnStatsMonth = document.getElementById('btn-stats-month');
    const btnStatsYear = document.getElementById('btn-stats-year');
    const btnQueryRawDay = document.getElementById('btn-query-raw-day');
    const statsSaveBtn = document.getElementById('stats-save-btn');

    function formatChineseDates(dateString) {
        if (!dateString) return '';
        const dates = dateString.split(',').map(d => new Date(d.trim())).sort((a, b) => a - b);
        if (dates.length === 0) return '';

        const groups = [];
        let currentGroup = [dates[0]];
        for (let i = 1; i < dates.length; i++) {
            const prev = dates[i - 1], curr = dates[i];
            const diffDays = Math.round((curr - prev) / (1000 * 60 * 60 * 24));
            if (diffDays === 1) currentGroup.push(curr);
            else { groups.push(currentGroup); currentGroup = [curr]; }
        }
        groups.push(currentGroup);

        let result = '';
        let lastY = null, lastM = null;

        for (let i = 0; i < groups.length; i++) {
            const group = groups[i];
            const start = group[0], end = group[group.length - 1];
            const sY = start.getFullYear(), sM = start.getMonth() + 1, sD = start.getDate();
            let groupStr = '';

            if (group.length > 1) {
                const eY = end.getFullYear(), eM = end.getMonth() + 1, eD = end.getDate();
                let startStr = '';
                if (sY !== lastY) startStr += `${sY}年`;
                if (sY !== lastY || sM !== lastM) startStr += `${sM}月`;
                startStr += `${sD}`;

                let endStr = '';
                if (eY !== sY) { startStr += '日'; endStr += `${eY}年${eM}月${eD}日`; }
                else if (eM !== sM) { startStr += '日'; endStr += `${eM}月${eD}日`; }
                else { endStr += `${eD}日`; }

                groupStr = startStr + '至' + endStr;
                lastY = eY; lastM = eM;
            } else {
                if (sY !== lastY) groupStr += `${sY}年`;
                if (sY !== lastY || sM !== lastM) groupStr += `${sM}月`;
                groupStr += `${sD}日`;
                lastY = sY; lastM = sM;
            }
            result += (i === 0 ? groupStr : '、' + groupStr);
        }
        return result;
    }

    function getRealBackupPath() {
        const curId = localStorage.getItem('sf_userId') || '';
        if (curId === ADMIN_ID) {
            return localStorage.getItem('backup_save_path') || '';
        }
        return '';
    }

    async function executeStatsQuery(timeType, customBaseDates = null) {
        const statsType = document.getElementById('stats-type-select').value;
        const person = document.getElementById('stats-person-select').value;
        const airport = document.getElementById('stats-airport-input').value.trim();
        const baseDateStr = customBaseDates || document.getElementById('base-date-picker').value;

        if (!baseDateStr) return alert("请先选择要查询的日期!");
        resultsContainer.innerHTML = '<div class="loader" style="display:block;"></div>';

        try {
            const res = await fetch('/api/query_stats', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    stats_type: statsType, person: person, airport: airport,
                    time_type: timeType, base_date: baseDateStr, backup_path: getRealBackupPath()
                })
            });
            const data = await res.json();
            if (data.success) {
                const formattedDates = timeType === 'day' ? formatChineseDates(baseDateStr) : baseDateStr;
                renderStatsResults(data.data, timeType, statsType, formattedDates);
                window.lastStatsResults = data.data;

                let titleSuffix = "";
                const dObj = new Date(baseDateStr.split(',')[0].trim());
                if (timeType === 'day') {
                    titleSuffix = `日度汇总-${formattedDates.replace(/,/g, '_').substring(0,20)}`;
                } else if (timeType === 'month') {
                    titleSuffix = `${dObj.getFullYear()}年${String(dObj.getMonth()+1).padStart(2,'0')}月月度汇总`;
                } else if (timeType === 'year') {
                    titleSuffix = `${dObj.getFullYear()}年年度汇总`;
                }
                window.lastStatsTitle = `${statsType === 'taf' ? '机场预报' : '席位预报'}${titleSuffix}`;

                window.lastStatsTimeType = timeType;
                window.lastStatsBaseDate = baseDateStr;
            } else { resultsContainer.innerHTML = `<div class="error-box">查询失败: ${data.error}</div>`; }
        } catch (e) { resultsContainer.innerHTML = `<div class="error-box">接口异常: ${e.message}</div>`; }
    }

    function showQueryModal(title, inputHTML, onConfirm, modalId, isGreen = false) {
        const oldContainer = document.getElementById(modalId);
        if (oldContainer) oldContainer.remove();

        const container = document.createElement('div');
        container.id = modalId;
        const borderColor = isGreen ? '#28a745' : '#005A9C';

        const styleTag = document.getElementById('modal-fix-style') || document.createElement('style');
        styleTag.id = 'modal-fix-style';
        styleTag.innerHTML = `
            .flatpickr-mobile, .flatpickr-input.alt-input { width: 100% !important; box-sizing: border-box !important; }
            #${modalId} .flatpickr-calendar { z-index: 10002 !important; }
        `;
        if (!styleTag.parentNode) document.head.appendChild(styleTag);

        container.style.cssText = `position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:white; padding:25px; border:2px solid ${borderColor}; border-radius:10px; z-index:10001; box-shadow:0 15px 30px rgba(0,0,0,0.3); width: 380px; box-sizing: border-box;`;

        container.innerHTML = `
            <h4 style="margin:0 0 15px 0; color:${borderColor}; font-size:16px; text-align:center;">${title}</h4>
            <div style="width: 100%; box-sizing: border-box;">
                ${inputHTML}
            </div>
            <div style="display:flex; flex-direction:row; flex-wrap:nowrap; gap:12px; width:100%; margin-top:20px; box-sizing:border-box;">
                <button id="${modalId}-confirm" class="mini-btn primary" style="flex:1; padding:10px 0; margin:0; text-align:center; background:${borderColor}; border:none; color:white; border-radius:6px; cursor:pointer; font-weight:bold;">确认查询</button>
                <button id="${modalId}-cancel" class="mini-btn" style="flex:1; padding:10px 0; margin:0; background:#f1f5f9; color:#333; border:1px solid #cbd5e1; text-align:center; border-radius:6px; cursor:pointer;">取消</button>
            </div>
        `;
        document.body.appendChild(container);

        document.getElementById(`${modalId}-cancel`).onclick = () => container.remove();
        document.getElementById(`${modalId}-confirm`).onclick = () => { onConfirm(container); };
    }

    const commonInputStyle = "width:100%; display:block; padding:10px; border:1px solid #ccc; border-radius:6px; box-sizing:border-box !important; font-size:14px; outline:none;";

    function attachSmartScroll(inputElement, type, fpInst = null) {
        if (!inputElement) return;
        inputElement.addEventListener('wheel', (e) => {
            e.preventDefault();
            const dir = e.deltaY < 0 ? 1 : -1;

            if (type === 'day' && fpInst) {
                let d = fpInst.selectedDates.length > 0 ? fpInst.selectedDates[0] : new Date();
                d.setDate(d.getDate() + dir);
                fpInst.setDate([d], true);
            } else if (type === 'month') {
                let d = new Date(inputElement.value + '-01');
                if(isNaN(d.getTime())) d = new Date();
                d.setMonth(d.getMonth() + dir);
                inputElement.value = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
            } else if (type === 'year') {
                let y = parseInt(inputElement.value) || new Date().getFullYear();
                inputElement.value = y + dir;
            }
        });
    }

    if (btnStatsDay) {
        btnStatsDay.addEventListener('click', () => {
            showQueryModal("请选择要查询的日期 (可多选)", `<input type="text" id="input-stats-day" style="${commonInputStyle}">`, (container) => {
                const selectedDates = document.getElementById('input-stats-day').value;
                if (!selectedDates) return; container.remove(); executeStatsQuery('day', selectedDates);
            }, 'modal-stats-day', false);

            flatpickr("#input-stats-day", {
                defaultDate: document.getElementById('base-date-picker').value || new Date(),
                locale: "zh", mode: "multiple", altInput: true,
                onReady: function(sel, dateStr, inst) {
                    inst.altInput.value = formatChineseDates(dateStr);
                    attachSmartScroll(inst.altInput, 'day', inst);
                },
                onChange: function(sel, dateStr, inst) { inst.altInput.value = formatChineseDates(dateStr); },
                onClose: function(sel, dateStr, inst) { inst.altInput.value = formatChineseDates(dateStr); }
            });
        });
    }

    if (btnQueryRawDay) {
        btnQueryRawDay.addEventListener('click', () => {
            showQueryModal("请选择明细数据的日期 (可多选)", `<input type="text" id="input-raw-day" style="${commonInputStyle}">`, async (container) => {
                const rawDates = document.getElementById('input-raw-day').value;
                if (!rawDates) return; container.remove();
                resultsContainer.innerHTML = '<div class="loader" style="display:block;"></div>';
                try {
                    const res = await fetch('/api/query_raw_data', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            stats_type: document.getElementById('stats-type-select').value,
                            person: document.getElementById('stats-person-select').value,
                            airport: document.getElementById('stats-airport-input').value.trim(),
                            base_date: rawDates, backup_path: getRealBackupPath()
                        })
                    });
                    const data = await res.json();
                    if (data.success) renderRawDataResults(data.data, formatChineseDates(rawDates));
                    else resultsContainer.innerHTML = `<div class="error-box">提取失败: ${data.error}</div>`;
                } catch (e) { resultsContainer.innerHTML = `<div class="error-box">接口异常: ${e.message}</div>`; }
            }, 'modal-raw-day', true);

            flatpickr("#input-raw-day", {
                defaultDate: document.getElementById('base-date-picker').value || new Date(),
                locale: "zh", mode: "multiple", altInput: true,
                onReady: function(sel, dateStr, inst) {
                    inst.altInput.value = formatChineseDates(dateStr);
                    attachSmartScroll(inst.altInput, 'day', inst);
                },
                onChange: function(sel, dateStr, inst) { inst.altInput.value = formatChineseDates(dateStr); },
                onClose: function(sel, dateStr, inst) { inst.altInput.value = formatChineseDates(dateStr); }
            });
        });
    }

    if (btnStatsMonth) {
        btnStatsMonth.addEventListener('click', () => {
            const now = new Date(); now.setMonth(now.getMonth() - 1);
            const defMonth = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
            showQueryModal("请选择要查询的月份", `<input type="month" id="input-stats-month" value="${defMonth}" style="${commonInputStyle}">`, (container) => {
                const val = document.getElementById('input-stats-month').value;
                if (!val) return; container.remove(); executeStatsQuery('month', val + '-01');
            }, 'modal-stats-month', false);

            attachSmartScroll(document.getElementById('input-stats-month'), 'month');
        });
    }

    if (btnStatsYear) {
        btnStatsYear.addEventListener('click', () => {
            const defYear = new Date().getFullYear() - 1;
            showQueryModal("请选择要查询的年份", `<input type="number" id="input-stats-year" value="${defYear}" min="2020" max="2050" style="${commonInputStyle}">`, (container) => {
                const val = document.getElementById('input-stats-year').value;
                if (!val) return; container.remove(); executeStatsQuery('year', val + '-01-01');
            }, 'modal-stats-year', false);

            attachSmartScroll(document.getElementById('input-stats-year'), 'year');
        });
    }

    function renderRawDataResults(rawData, formattedDatesTitle) {
        if (!rawData || rawData.length === 0) { resultsContainer.innerHTML = '<div class="error-box">无匹配明细数据</div>'; return; }
        const statsType = document.getElementById('stats-type-select').value;
        const personSelect = document.getElementById('stats-person-select').value;
        const showPerson = (statsType === 'manual' && personSelect === 'ALL');

        let html = `<div class="result-card"><h3 style="color:#28a745;">📄 ${formattedDatesTitle} 明细查询</h3>`;
        html += '<div class="table-wrapper"><table class="result-table"><thead><tr>';
        if (showPerson) html += '<th rowspan="2" style="vertical-align:middle;">评定对象</th>';

        html += '<th rowspan="2" style="vertical-align:middle;">机场</th><th rowspan="2" style="vertical-align:middle;">预报时效</th><th rowspan="2" style="vertical-align:middle;">时次(UTC)</th><th rowspan="2" style="vertical-align:middle;">预报全文</th>';

        const cols = Object.keys(rawData[0]);
        const orderedItems = ['最大风速(MPS)', '最差能见度(m)', '最低云高(m)', '雷雨类', '强降水(无雷)类', '积冰类', '特殊类'];
        const itemNames = orderedItems.filter(item => cols.includes(item + '(实况)'));

        itemNames.forEach(item => { html += `<th colspan="2" style="text-align:center;">${item}</th>`; });
        html += '</tr><tr>';
        itemNames.forEach(() => { html += '<th>实况</th><th>评价</th>'; });
        html += '</tr></thead><tbody>';

        rawData.forEach(row => {
            html += '<tr>';
            if (showPerson) html += `<td style="font-weight:bold; color:#005A9C;">${row['评定对象']}</td>`;
            html += `<td style="font-weight:bold;">${row['机场']}</td>`;
            html += `<td>${row['预报时效'] || '-'}</td>`;
            html += `<td>${row['时次(UTC)']}</td>`;
            html += `<td class="forecast-content-cell" title="${row['预报全文'] || '-'}">${row['预报全文'] || '-'}</td>`;

            itemNames.forEach(item => {
                const valObs = row[item + '(实况)'] || '/';
                const valEval = row[item + '(评价)'] || '/';
                const cls = valEval.replace(/\s+/g, '').replace('/NSW','');
                html += `<td>${valObs}</td><td class="score-cell score-${cls}">${valEval}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table></div></div>';
        document.getElementById('results-stats').innerHTML = html;
    }

    function renderStatsResults(statsData, timeType, statsType, formattedDate) {
        let firstColName = statsType === 'taf' ? '机场' : '评定对象';

        let displayDate = formattedDate;
        if (formattedDate) {
            if (timeType === 'month') {
                const parts = formattedDate.split(',')[0].trim().split('-');
                if (parts.length >= 2) displayDate = `${parts[0]}-${parts[1]}`;
            } else if (timeType === 'year') {
                const parts = formattedDate.split(',')[0].trim().split('-');
                if (parts.length >= 1) displayDate = `${parts[0]}`;
            }
        }

        let title = `📊 ${displayDate || ''} ${timeType === 'day' ? '日度' : (timeType === 'month' ? '月度' : '年度')}汇总统计`;

        let html = `<div class="result-card"><h3>${title}</h3><div class="table-wrapper"><table class="result-table" style="text-align:center;">
            <thead><tr><th style="vertical-align:middle;">${firstColName}</th><th></th><th>完美</th><th>优秀</th><th>空报</th><th>漏报</th><th>准确</th><th>参评</th><th>总评</th><th>总分</th></tr></thead><tbody>`;
        statsData.forEach(row => {
            let accRate = row.总评项次 > 0 ? (row.准确项次 / row.总评项次 * 100) : 0;
            let perfRate = row.参评项次 > 0 ? (row.完美项次 / row.参评项次 * 100) : 0;
            let excRate = row.参评项次 > 0 ? (row.优秀项次 / row.参评项次 * 100) : 0;
            let faRate = row.总评项次 > 0 ? (row.空报项次 / row.总评项次 * 100) : 0;
            let missRate = row.总评项次 > 0 ? (row.漏报项次 / row.总评项次 * 100) : 0;
            let score = (accRate * 0.5) + (perfRate * 0.3) + (excRate * 0.2) - (faRate * 0.1) - (missRate * 0.1);
            html += `<tr><td rowspan="2" style="font-weight:bold; color:#005A9C; vertical-align:middle; border-bottom:2px solid #ccc;">${row.统计对象}</td><td>次数</td><td>${row.完美项次}</td><td>${row.优秀项次}</td><td style="color:red;">${row.空报项次}</td><td style="color:orange;">${row.漏报项次}</td><td style="font-weight:bold;">${row.准确项次}</td><td>${row.参评项次}</td><td>${row.总评项次}</td><td rowspan="2" style="vertical-align:middle; font-weight:bold; font-size:14px; color:#DA251D; border-bottom:2px solid #ccc;">${score.toFixed(2)}</td></tr>`;
            html += `<tr><td style="border-bottom:2px solid #ccc;">概率</td><td style="border-bottom:2px solid #ccc;">${row.完美率}</td><td style="border-bottom:2px solid #ccc;">${row.优秀率}</td><td style="border-bottom:2px solid #ccc;">${row.空报率}</td><td style="border-bottom:2px solid #ccc;">${row.漏报率}</td><td style="color:green; font-weight:bold; border-bottom:2px solid #ccc;">${row.准确率}</td><td style="border-bottom:2px solid #ccc;"></td><td style="border-bottom:2px solid #ccc;"></td></tr>`;
        });
        html += `<tr><td colspan="10" style="text-align:left; font-size:12px; color:#555; padding:8px; font-weight:bold; background-color:#f8f9fa;">评定逻辑:总分=(准确率*50% + 完美率*30% + 优秀率*20% - 空报率*10% - 漏报率*10%)</td></tr></tbody></table></div></div>`;
        document.getElementById('results-stats').innerHTML = html;
        if (document.getElementById('stats-save-container')) document.getElementById('stats-save-container').style.display = 'block';
    }

    if (statsSaveBtn) {
        statsSaveBtn.addEventListener('click', async () => {
            if (!window.lastStatsResults) return alert("请先执行查询!");
            const targetMode = document.getElementById('stats-type-select').value;
            const excelRoot = getFinalExcelRoot(targetMode);
            if (!excelRoot) return alert("请先在左侧【⚙️设置】中配置对应类型的 Excel 导出目录!");

            statsSaveBtn.disabled = true; statsSaveBtn.textContent = "⏳ 导出中...";
            try {
                const res = await fetch('/api/export_stats', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        excel_root: excelRoot, table_data: window.lastStatsResults,
                        title: window.lastStatsTitle,
                        time_type: window.lastStatsTimeType,
                        base_date: window.lastStatsBaseDate
                    })
                });
                const data = await res.json();
                if (data.success) alert(data.message); else throw new Error(data.error);
            } catch (e) { alert("❌ 导出失败: " + e.message); }
            finally { statsSaveBtn.disabled = false; statsSaveBtn.textContent = "💾 导出统计结果 Excel"; }
        });
    }

    const manualSaveBtn = document.getElementById('manual-save-btn');
    const checkSavedFileBtn = document.getElementById('check-saved-file-btn');
    let lastSavedFolder = '';
    checkSavedFileBtn?.addEventListener('click', async () => {
        if (!lastSavedFolder) return alert('尚未找到本次保存目录，请先保存评定结果。');
        try {
            const res = await fetch(window.OMICS_API_URL('open_folder'), {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: lastSavedFolder })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || '打开文件夹失败');
        } catch (e) {
            alert('打开保存文件夹失败: ' + e.message);
        }
    });
    if (manualSaveBtn) {
        manualSaveBtn.addEventListener('click', async () => {
            if (!window.lastScoreResults) return alert("请先进行评定!");
            const exportConfig = {
                backup_path: getRealBackupPath(),
                excel_root: getFinalExcelRoot(currentMode),
                eval_person: document.getElementById('eval-person-select') ? document.getElementById('eval-person-select').value : '',
                base_date_str: window.lastScoreBaseDateStr || (document.getElementById('base-date-picker') ? document.getElementById('base-date-picker').value : ''),
                rater: personnelDict[localStorage.getItem('sf_userId')] || localStorage.getItem('sf_userId') || '未知'
            };
            if (!exportConfig.excel_root) return alert("⚠️ 请先在左侧【⚙️设置】中配置当前预报类型的「Excel导出目录」!");

            manualSaveBtn.disabled = true; manualSaveBtn.textContent = "⏳ 正在生成 Excel 及备份数据...";
            try {
                const res = await fetch(window.OMICS_API_URL('save_score'), {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ results: window.lastScoreResults, forecast_mode: currentMode, export_config: exportConfig })
                });
                const data = await res.json();
                if (data.success) {
                    lastSavedFolder = data.folder_path || '';
                    alert("✅ 保存成功!\n📊 Excel 表格已导出\n📦 数据已同步至底层数据库");
                    manualSaveBtn.style.display = 'none';
                    if (checkSavedFileBtn) checkSavedFileBtn.style.display = lastSavedFolder ? 'block' : 'none';
                }else throw new Error(data.error);
            } catch (e) { alert("❌ 保存失败: " + e.message); }
            finally { manualSaveBtn.disabled = false; manualSaveBtn.textContent = "💾 保存评定结论到文件"; }
        });
    }

    function getFinalExcelRoot(targetMode) {
        if (window.tempExcelRoot) return window.tempExcelRoot;
        if (targetMode === 'taf') return document.getElementById('taf-excel-path') ? document.getElementById('taf-excel-path').value.trim() : '';
        return document.getElementById('manual-excel-path') ? document.getElementById('manual-excel-path').value.trim() : '';
    }

    document.getElementById('backup-save-path')?.addEventListener('change', (e) => {
        localStorage.setItem('backup_save_path', e.target.value.trim());
        patchSettingsConfig({ paths: buildPathsBlock() });
    });

    handleModeChange();
    renderEvalPersonSelect();

    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('copyable-header')) {
            const row = e.target.closest('tr');
            const table = row.closest('table');
            const rows = Array.from(table.querySelectorAll('tr'));
            const rowIndex = rows.indexOf(row);

            let pairRows = [];
            if (e.target.textContent.includes('(实况)')) {
                pairRows = [row, rows[rowIndex + 1]];
            } else {
                pairRows = [rows[rowIndex - 1], row];
            }

            const textToCopy = pairRows.map(r =>
                Array.from(r.cells).slice(1).map(c => c.textContent).join('\t')
            ).join('\n');

            navigator.clipboard.writeText(textToCopy).then(() => {
                const originalText = e.target.textContent;
                e.target.textContent = "✅ 已复制 (无表头)";
                e.target.style.color = "#28a745";
                setTimeout(() => {
                    e.target.textContent = originalText;
                    e.target.style.color = "";
                }, 1000);
            });
        }
    });
});
