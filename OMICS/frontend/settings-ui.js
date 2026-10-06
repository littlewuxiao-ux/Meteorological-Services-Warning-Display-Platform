(() => {
  const modal = document.getElementById('global-settings-modal');
  if (!modal) return;
  const scroll = modal.querySelector('.system-settings-scroll');
  const context = modal.querySelector('.system-settings-context');
  const navs = [...modal.querySelectorAll('.set-nav')];
  const titles = ['预报发布', '质量评定', '机场字典', '管理与文件'];
  const hints = ['过滤参数和机场分组修改后，请点击底部保存；显示要素选项即时保存。', '设置评分阈值、天气现象和特殊机场规则；按原有规则即时保存。', '维护机场四字码、名称和坐标，通过每行操作提交修改。', '带保存按钮的配置需手动保存；目录选择和人员操作按原有规则即时保存。'];
  function select(id) {
    const nav = navs.find(n => n.dataset.target === id && n.style.display !== 'none');
    if (!nav) return;
    navs.forEach(n => { n.classList.toggle('active', n === nav); n.setAttribute('aria-selected', n === nav); });
    modal.querySelectorAll('.set-pane').forEach(p => p.style.display = p.id === id ? 'block' : 'none');
    context.textContent = `系统设置 / ${nav.textContent}`;
    scroll.scrollTop = 0;
  }
  navs.forEach((nav, i) => {
    nav.textContent = titles[i]; nav.setAttribute('role', 'tab'); nav.setAttribute('aria-selected', i === 0);
    nav.tabIndex = 0;
    nav.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); nav.click(); } });
    nav.addEventListener('click', () => select(nav.dataset.target));
  });
  const search = document.createElement('input');
  search.type = 'search'; search.placeholder = '搜索设置，例如：结冰、路径、阈值'; search.className = 'settings-search';
  const results = document.createElement('div'); results.className = 'settings-search-results';
  scroll.before(search, results);
  search.setAttribute('aria-label', '搜索设置');
  const admin = document.querySelector('#pane-admin > div');
  if (admin) {
    let card;
    [...admin.children].forEach(child => {
      if (child.classList.contains('admin-sub-title')) {
        card = document.createElement('section'); card.className = 'settings-section-card'; admin.insertBefore(card, child);
      }
      if (card) card.append(child);
    });
  }
  const pb = document.getElementById('pane-pb');
  const displayCard = pb.querySelector('div[style*="border: 1px solid #ccc"]');
  displayCard?.classList.add('settings-section-card');
  displayCard?.querySelector('b')?.classList.add('settings-section-title');
  pb.querySelectorAll('h3')[1]?.classList.add('settings-section-title');
  document.getElementById('pb-settings-save-btn').parentElement.classList.add('settings-save-bar');
  const sections = [];
  modal.querySelectorAll('.set-pane').forEach((pane, i) => {
    const hint = document.createElement('p'); hint.className = 'settings-page-hint'; hint.textContent = hints[i]; pane.querySelector('h3')?.after(hint);
    const shortcut = document.createElement('div'); shortcut.className = 'settings-shortcuts'; hint.after(shortcut);
    [...pane.querySelectorAll('summary, .publish-settings-group-title, .admin-sub-title, .settings-section-title')].forEach(head => {
      const target = head.closest('details, .publish-filter-settings-group, .settings-section-card') || head;
      const label = head.textContent.trim().replace(/\s+/g, ' ');
      if (!label) return;
      const jump = () => { select(pane.id); if (target.tagName === 'DETAILS') target.open = true; target.scrollIntoView({ behavior: 'smooth', block: 'start' }); target.classList.add('settings-highlight'); setTimeout(() => target.classList.remove('settings-highlight'), 1200); };
      const button = document.createElement('button'); button.type = 'button'; button.textContent = label; button.onclick = jump; shortcut.append(button);
      sections.push({ pane, label, target, jump });
    });
  });
  search.addEventListener('input', () => {
    results.replaceChildren(); const q = search.value.trim().toLowerCase(); if (!q) return;
    const found = sections.filter(x => navs.find(n => n.dataset.target === x.pane.id).style.display !== 'none' && x.target.textContent.toLowerCase().includes(q));
    found.forEach(x => { const b = document.createElement('button'); b.textContent = `${titles[navs.findIndex(n => n.dataset.target === x.pane.id)]} / ${x.label}`; b.onclick = () => { search.value = ''; results.replaceChildren(); x.jump(); }; results.append(b); });
    if (!found.length) results.textContent = '没有找到相关设置。';
  });
  window.OMICSSettingsUI = { open: () => { search.value = ''; results.replaceChildren(); select(document.querySelector('input[name="forecast-mode"]:checked')?.value === 'publish' ? 'pane-pb' : 'pane-qa'); } };
})();
