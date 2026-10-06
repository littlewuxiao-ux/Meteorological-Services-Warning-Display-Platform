(() => {
  const api = () => (location.pathname.startsWith('/omics') ? '/omics/api/' : '/api/') + 'settings_backups';
  async function backup() { const res = await fetch(api(), { method: 'POST' }); const data = await res.json(); if (!data.success) throw new Error(data.error); return data.data; }
  async function download() {
    await window.OMICSSettings.flush();
    await window.OMICSSettings.load();
    const data = window.OMICSSettings?.get?.() || window.OMICS_CONFIG || {};
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `omics-settings-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(link.href);
  }
  async function restore(file) {
    const data = JSON.parse(await file.text());
    await window.OMICSSettings.replace(data);
    reloadNotice('配置已导入');
  }
  function reloadNotice(message) {
    const modal = document.getElementById('global-settings-modal');
    modal.querySelectorAll('input, select, button').forEach(el => { if (el.id !== 'close-global-settings') el.disabled = true; });
    const notice = document.createElement('div'); notice.className = 'settings-reload-notice';
    const text = document.createElement('span'); text.textContent = `${message}，刷新后生效。`;
    const button = document.createElement('button'); button.textContent = '刷新页面'; button.onclick = () => location.reload();
    notice.append(text, button); modal.querySelector('.system-settings-scroll').prepend(notice);
    window.OMICSUI?.notify(`${message}，请刷新页面使全部模块生效。`);
  }
  window.OMICSSettingsTransfer = { backup, download, restore };
  document.addEventListener('DOMContentLoaded', () => {
    const container = document.querySelector('#pane-admin .admin-sub-title')?.parentElement;
    if (!container) return;
    const section = document.createElement('section'); section.className = 'settings-section-card settings-transfer';
    section.innerHTML = '<h4>配置备份与迁移</h4><p>导出配置可用于换机；导入前会自动保存当前配置。</p><div><button type="button" data-export>导出配置</button><button type="button" data-import>导入配置</button><button type="button" data-backup>立即备份</button><input type="file" accept="application/json" hidden></div>';
    container.parentElement.append(section);
    const backups = document.createElement('div'); backups.className = 'settings-backup-list'; section.append(backups);
    const refresh = document.createElement('button'); refresh.type = 'button'; refresh.textContent = '查看备份 / 恢复'; section.querySelector('div').append(refresh);
    refresh.onclick = async () => {
      try {
        const response = await fetch(api(), { cache: 'no-store' }); const result = await response.json();
        if (!result.success) throw new Error(result.error);
        backups.replaceChildren();
        if (!result.data.length) backups.textContent = '暂无备份';
        result.data.forEach(item => {
          const row = document.createElement('div'); const label = document.createElement('span'); label.textContent = item.name;
          const button = document.createElement('button'); button.type = 'button'; button.textContent = '恢复';
          button.onclick = async () => {
            if (!confirm('恢复会覆盖当前已保存配置，并自动备份当前配置。继续吗？')) return;
            button.disabled = true;
            try {
              await window.OMICSSettings.flush();
              const res = await fetch(api(), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ restore: item.name }) });
              const data = await res.json(); if (!data.success) throw new Error(data.error);
              window.OMICSSettings.clearCaches();
              await window.OMICSSettings.load(); reloadNotice('配置已恢复');
            } catch (e) { window.OMICSUI.notify(e.message, 'error'); } finally { button.disabled = false; }
          };
          row.append(label, button); backups.append(row);
        });
      } catch (e) { window.OMICSUI.notify(e.message, 'error'); }
    };
    section.querySelector('[data-export]').onclick = download;
    section.querySelector('[data-backup]').onclick = async () => { try { await backup(); window.OMICSUI?.notify('配置备份已创建'); } catch (e) { window.OMICSUI?.notify(e.message, 'error'); } };
    const input = section.querySelector('input'); section.querySelector('[data-import]').onclick = () => input.click(); input.onchange = async () => {
      if (!input.files[0]) return;
      try {
        if (input.files[0].size > 2 * 1024 * 1024) throw new Error('配置文件不能超过 2 MB');
        if (confirm('导入会替换当前配置，系统会先自动备份。继续吗？')) await restore(input.files[0]);
      } catch (e) { window.OMICSUI?.notify('导入失败：' + e.message, 'error'); }
      input.value = '';
    };
  });
})();
