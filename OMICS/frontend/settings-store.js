// Serialized writes prevent an older response from replacing newer settings.
(() => {
  let state = window.OMICS_CONFIG || {};
  let queue = Promise.resolve();
  const url = () => (location.pathname.startsWith('/omics') ? '/omics/api/' : '/api/') + 'settings_config';
  const clone = x => JSON.parse(JSON.stringify(x));
  function publish(value) {
    state = clone(value);
    window.OMICS_CONFIG = state;
    window.OMICS_SETTINGS_CONFIG = state;
    window.dispatchEvent(new CustomEvent('omics:settings', { detail: clone(state) }));
    return clone(state);
  }
  function status(text, error = false) {
    window.dispatchEvent(new CustomEvent('omics:settings-status', { detail: { text, error } }));
  }
  async function request(method, body) {
    const res = await fetch(url(), { method, cache: 'no-store', headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
    const result = await res.json();
    if (!res.ok || !result.success) throw new Error(result.error || '配置请求失败');
    return result.data;
  }
  function patch(settings) {
    const snapshot = clone(settings);
    const job = queue.then(async () => {
      status('正在保存配置…');
      try { const data = publish(await request('POST', { settings: snapshot })); status('配置已保存'); return data; }
      catch (error) { status(`保存失败：${error.message}`, true); window.OMICSUI?.notify(`配置未保存：${error.message}`, 'error'); return null; }
    });
    queue = job.catch(() => {});
    return job;
  }
  function clearCaches() {
    ['taf_excel_path', 'manual_excel_path', 'manual_forecast_path', 'backup_save_path', 'publish_export_path', 'sf_def_manual_aps', 'sf_def_taf_aps', 'personnel_dict', 'phenomena_config', 'pb_airport_groups', 'pb_auto_ec_cfg', 'sf_global_thresholds', 'sf_custom_ap_thresholds'].forEach(key => localStorage.removeItem(key));
  }
  window.OMICSSettings = {
    get: () => clone(state), patch,
    async load() { return publish(await request('GET')); },
    async flush() { await queue; },
    clearCaches,
    replace(settings) {
      const snapshot = clone(settings);
      const job = queue.then(async () => {
        const data = await request('POST', { settings: snapshot, replace: true });
        clearCaches(); return publish(data);
      });
      queue = job.catch(() => {});
      return job;
    }
  };
})();
