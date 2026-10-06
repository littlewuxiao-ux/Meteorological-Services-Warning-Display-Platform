(() => {
  const toastArea = document.createElement('div'); toastArea.className = 'omics-toasts'; toastArea.setAttribute('aria-live', 'polite'); document.body.append(toastArea);
  function notify(message, type = 'info') {
    const toast = document.createElement('div'); toast.className = `omics-toast ${type}`;
    const text = document.createElement('span'); text.textContent = String(message);
    const close = document.createElement('button'); close.textContent = '×'; close.setAttribute('aria-label', '关闭提示'); close.onclick = () => toast.remove();
    toast.append(text, close); toastArea.append(toast);
    if (type !== 'error') setTimeout(() => toast.remove(), 6000);
  }
  const header = document.querySelector('.top-bar');
  const nav = document.querySelector('.mode-switcher');
  // Keep the mode switcher inside its original card; evaluation workspaces depend on that flex container.
  nav.classList.add('workspace-navigation'); nav.setAttribute('aria-label', '工作区导航');
  const bar = document.createElement('div'); bar.className = 'workbench-status';
  const mode = document.createElement('span'); const task = document.createElement('span'); const saved = document.createElement('span');
  task.textContent = '就绪'; saved.textContent = '配置已加载'; bar.append(mode, task, saved); header.after(bar);
  function updateMode() { const checked = document.querySelector('input[name="forecast-mode"]:checked'); mode.textContent = checked?.nextElementSibling?.textContent || '预报发布'; document.querySelector('.container')?.classList.toggle('stats-mode', checked?.value === 'stats'); }
  document.querySelectorAll('input[name="forecast-mode"]').forEach(radio => radio.addEventListener('change', updateMode)); updateMode();
  window.addEventListener('omics:settings-status', e => { saved.textContent = e.detail.text; saved.classList.toggle('status-error', e.detail.error); });
  window.OMICSUI = { notify, task(text, error = false) { task.textContent = text; task.classList.toggle('status-error', error); } };
})();

