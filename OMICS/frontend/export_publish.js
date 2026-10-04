/* ===================================================================
 * export_publish.js — 预报发布导出（图片/Excel 分离、预览、图片分页切割）
 * 依赖：html2canvas、publish.js 中的 window.pbState / forecast-table DOM
 * 不依赖外部 xlsm 模板，仅复刻其版式观感。
 * =================================================================== */
(function () {
    'use strict';

    const apiBase = () => (window.location.pathname.startsWith('/omics') ? '/omics/api' : '/api');

    // 抓取当前发布表里“已确认/有效”的机场行，作为导出数据源
    function collectPublishRows() {
        const table = document.getElementById('forecast-table');
        const rows = [];
        if (!table) return rows;
        table.querySelectorAll('tbody tr.tr-edit').forEach(tr => {
            if (tr.style.display === 'none') return;
            const nameCell = tr.querySelector('.td-airport');
            const name = nameCell?.childNodes?.[0]?.textContent?.trim() || '';
            const type = nameCell?.nextElementSibling?.textContent?.trim() || '普通';
            const numCells = (window.pbState?.validityHours || 24) + 1;
            const values = [];
            for (let i = 0; i < numCells; i++) {
                const td = tr.querySelector(`td.td-data[data-c="${i}"]`);
                values.push(td ? td.textContent.trim() : '');
            }
            const noteInput = tr.querySelector('.edit-note-input');
            const noteDisplay = tr.querySelector('.edit-note-display');
            const note = (noteInput?.value || noteDisplay?.textContent || '').trim();
            const confirmed = tr.dataset.confirmed === 'true';
            if (name && (values.some(Boolean) || confirmed)) {
                rows.push({ icao: tr.dataset.icao || '', name, type, values, note, confirmed });
            }
        });
        return rows;
    }

    // Excel 使用逐行数据，保留同一机场的全部附加行和每行备注。
    function collectPublishDataRows() {
        const table = document.getElementById('forecast-table');
        const rows = [];
        if (!table) return rows;
        table.querySelectorAll('tbody tr.tr-edit').forEach(mainTr => {
            if (mainTr.style.display === 'none') return;
            const icao = mainTr.dataset.icao || '';
            const nameCell = mainTr.querySelector('.td-airport');
            const name = nameCell?.childNodes?.[0]?.textContent?.trim() || '';
            const type = nameCell?.nextElementSibling?.textContent?.trim() || '普通';
            const airportRows = [mainTr];
            let next = mainTr.nextElementSibling;
            while (next && next.classList.contains('tr-edit-extra') && next.dataset.icao === icao) {
                if (next.style.display !== 'none') airportRows.push(next);
                next = next.nextElementSibling;
            }
            airportRows.forEach((tr, rowIndex) => {
                const values = Array.from(tr.querySelectorAll('td.td-data')).map(td => td.textContent.trim());
                const noteInput = tr.querySelector('.edit-note-input');
                const noteDisplay = tr.querySelector('.edit-note-display');
                const note = (noteInput?.value || noteDisplay?.textContent || '').trim();
                if (!name || (!values.some(Boolean) && !note && tr.dataset.confirmed !== 'true')) return;
                rows.push({
                    icao,
                    name: rowIndex === 0 ? name : '',
                    type: rowIndex === 0 ? type : '',
                    values,
                    note,
                    confirmed: tr.dataset.confirmed === 'true',
                    continuation: rowIndex > 0
                });
            });
        });
        return rows;
    }

    // 把整张表格序列化为二维数组（含表头），供后端 Excel 兜底
    function collectRawRows() {
        const table = document.getElementById('forecast-table');
        const rows = [];
        if (!table) return rows;
        table.querySelectorAll('tr').forEach(tr => {
            if (tr.style.display === 'none') return;
            const rowData = [];
            tr.querySelectorAll('th, td').forEach(td => rowData.push(td.innerText.trim()));
            rows.push(rowData);
        });
        return rows;
    }

    function getIcingText() {
        const inp = document.getElementById('pb-special-airports');
        return inp ? (inp.value.trim() || '无') : '无';
    }

    function exportPath() {
        return document.getElementById('publish-export-path')?.value || '';
    }

    // 计算分页：返回每页机场行数组成的数组。优先按“每页机场数”，否则按“总页数”平均分配。
    function paginate(rows, enableSplit, pageCountValue, perPageValue, pageSizesValue) {
        if (!enableSplit || rows.length === 0) return [rows];
        const customSizes = (pageSizesValue || []).map(v => parseInt(v, 10)).filter(v => v > 0);
        if (customSizes.length) {
            const pages = [];
            let pos = 0;
            customSizes.forEach(size => {
                if (pos < rows.length) { pages.push(rows.slice(pos, pos + size)); pos += size; }
            });
            if (pos < rows.length) pages.push(rows.slice(pos));
            return pages.filter(p => p.length);
        }
        const perPage = parseInt(perPageValue, 10);
        if (perPage && perPage > 0) {
            const pages = [];
            for (let i = 0; i < rows.length; i += perPage) pages.push(rows.slice(i, i + perPage));
            return pages;
        }
        let pageCount = parseInt(pageCountValue, 10);
        if (!pageCount || pageCount < 1) pageCount = Math.min(2, rows.length);
        pageCount = Math.min(pageCount, rows.length);
        const pages = [];
        const base = Math.floor(rows.length / pageCount);
        let extra = rows.length % pageCount;
        let pos = 0;
        for (let p = 0; p < pageCount; p++) {
            const size = base + (extra-- > 0 ? 1 : 0);
            pages.push(rows.slice(pos, pos + size));
            pos += size;
        }
        return pages;
    }

    /* 构建一页用于截图的离屏 DOM：头(标题栏) + 表格(仅选定机场行) + 尾(结冰/颜色/说明)
       通过克隆现有 DOM 节点，最大程度保持与界面一致的观感。 */
    function buildPageNode(pageRows, pageIdx, pageTotal) {
        const wrap = document.createElement('div');
        wrap.style.cssText = 'width:1200px; background:#fff; font-family:微软雅黑,Microsoft YaHei,Arial,sans-serif; color:#1f2937;';

        // 头：克隆标题栏（含已并入的时间轴表头 #pb-timeline-header）
        const headerSrc = document.getElementById('pb-export-header');
        let exportTimelineRows = [];
        if (headerSrc) {
            const h = headerSrc.cloneNode(true);
            // 导出图片保持第五版外观，隔离第六版页面专用的 ID/class 强制样式。
            h.id = '';
            h.style.background = '#4b5563';
            h.style.backgroundColor = '#4b5563';
            h.style.boxShadow = 'none';
            h.style.borderRadius = '0';
            // 🌟 底部 padding 置 0：消除时间轴与正文表之间露出的深色头部背景条（原本 28px padding-bottom + 时间轴 -20px margin 净剩 8px）
            h.style.padding = '14px 18px 0 18px';
            const clonedTimeline = h.querySelector('#pb-timeline-table');
            // 第五版导出结构把时间轴作为正文表格 thead。保留相同结构，
            // 让浏览器用一套 table layout 同时计算时间轴和天气列，避免
            // 两个独立 table 在边框/colspan/margin 上产生累积错位。
            if (clonedTimeline) {
                const timelineBody = clonedTimeline.querySelector('tbody');
                exportTimelineRows = timelineBody
                    ? Array.from(timelineBody.children).map(row => row.cloneNode(true))
                    : [];
            }
            // 🌟 时间轴容器：负 margin 与新 padding(18px) 严格匹配，使时间轴左右边界与正文表齐；
            // 底部 margin 置 0，让时间轴紧贴正文表（不再露背景条）。
            const clonedTlHeader = h.querySelector('#pb-timeline-header');
            if (clonedTlHeader) {
                clonedTlHeader.remove();
            }
            const alertSummary = h.querySelector('.pb-alert-summary');
            if (alertSummary) {
                alertSummary.classList.remove('pb-alert-summary');
                alertSummary.style.width = '75%';
                alertSummary.style.gap = '8px';
                alertSummary.style.margin = '0 auto 20px auto';
                Array.from(alertSummary.children).forEach(item => {
                    item.style.minWidth = '';
                    item.style.borderRadius = '4px';
                    item.style.boxShadow = 'none';
                });
            }
            const headerMeta = h.querySelector('.pb-header-meta');
            if (headerMeta) {
                headerMeta.classList.remove('pb-header-meta');
                headerMeta.style.borderTopColor = '#6b7280';
            }
            h.querySelectorAll('select,input').forEach(el => {
                const display = document.createElement('span');
                display.textContent = el.tagName === 'SELECT' ? (el.options[el.selectedIndex]?.text || el.value || '') : (el.value || '');
                display.style.cssText = el.id === 'pb-main-title-select'
                    ? 'display:block; text-align:center; font-size:42px; line-height:1.15; font-weight:800; letter-spacing:2px; color:#fff; margin-bottom:22px;'
                    : 'display:inline-block; min-width:70px; text-align:center; color:#fff;';
                el.replaceWith(display);
            });
            wrap.appendChild(h);
        }

        // 表格：将第五版的同表 thead 结构用于导出，保证时间轴与天气列共用布局。
        const srcTable = document.getElementById('forecast-table');
        const tbl = document.createElement('table');
        // 🌟 table-layout:fixed + colgroup，与表头共用同一套列宽，保证渲染后逐列对齐（auto 会按内容重分导致错位）
        tbl.style.cssText = 'border-collapse:collapse; table-layout:fixed; text-align:center; border-bottom:2px solid #5D6D7E; font-family:微软雅黑,Microsoft YaHei,Arial,sans-serif;';
        tbl.className = srcTable ? srcTable.className : '';
        tbl.id = '';
        if (srcTable) {
            if (exportTimelineRows.length) {
                const thead = document.createElement('thead');
                exportTimelineRows.forEach(row => thead.appendChild(row));
                tbl.appendChild(thead);
            }
            const tbody = document.createElement('tbody');
            const icaoSet = new Set(pageRows.map(r => r.icao).filter(Boolean));
            srcTable.querySelectorAll('tbody tr').forEach(tr => {
                if (tr.style.display === 'none') return;
                const icao = tr.dataset.icao;
                // 只保留属于本页机场的行（确认主行 + 其附属行）
                if (icao && icaoSet.has(icao)) tbody.appendChild(tr.cloneNode(true));
            });
            tbl.appendChild(tbody);
        }
        // Reuse the live table's rendered column geometry. Estimating widths from
        // text independently makes the cloned timeline drift from the weather
        // cells, especially after responsive/fixed-table layout has fractional
        // hourly widths.
        const liveRow = srcTable?.querySelector('tbody tr.tr-edit:not([style*="display: none"])');
        const liveCells = liveRow ? Array.from(liveRow.children) : [];
        const measured = [];
        liveCells.forEach(cell => {
            const span = Math.max(1, Number(cell.getAttribute('colspan')) || 1);
            const width = cell.getBoundingClientRect().width / span;
            for (let i = 0; i < span; i++) measured.push(width);
        });
        const textWidth = (txt, min, max, unit = 14) => Math.max(min, Math.min(max, String(txt || '').trim().length * unit + 28));
        const airportWidth = measured[0] || Math.max(90, ...pageRows.map(r => textWidth(r.name, 90, 220, 16)));
        const typeWidth = measured[1] || Math.max(60, ...pageRows.map(r => textWidth(r.type, 60, 150, 15)));
        const liveNoteWidth = measured.length >= 4 ? measured[2] + measured[3] : 0;
        const noteWidth = liveNoteWidth || Math.max(92, ...pageRows.map(r => textWidth(r.note, 92, 260, 10)));
        const hourCells = (window.pbState?.validityHours || 24) + 1;
        const measuredHourWidths = measured.slice(4, 4 + hourCells);
        const hourWidth = measuredHourWidths.length === hourCells && measuredHourWidths.every(w => w > 0)
            ? measuredHourWidths[0]
            : (hourCells > 25 ? 38 : 42);
        const noteLeftW = Math.floor(noteWidth / 2);
        const noteRightW = Math.ceil(noteWidth / 2);
        const measuredWidth = airportWidth + typeWidth + noteWidth
            + measuredHourWidths.reduce((sum, width) => sum + width, 0);
        const estimatedWidth = airportWidth + typeWidth + noteWidth + hourCells * hourWidth + 24;
        // Keep the cloned header and body on one exact geometry. The outer page
        // may remain wide, but adding width to the table itself would make the
        // browser redistribute fixed columns and reintroduce drift.
        const tableWidth = measuredHourWidths.length === hourCells ? measuredWidth : Math.max(1200, estimatedWidth);
        wrap.style.width = `${tableWidth}px`;
        tbl.style.width = `${tableWidth}px`;

        // 🌟 为数据表注入 colgroup，列结构与表头完全一致：名称/性质/备注左/备注右 + 逐小时。
        // 已确认态备注是 colspan=2，跨备注左+备注右两列；与表头布局完全同构。
        const dataCg = document.createElement('colgroup');
        let dcgHtml = `<col style="width:${airportWidth}px;"><col style="width:${typeWidth}px;"><col style="width:${noteLeftW}px;"><col style="width:${noteRightW}px;">`;
        for (let i = 0; i < hourCells; i++) dcgHtml += `<col style="width:${measuredHourWidths[i] || hourWidth}px;">`;
        dataCg.innerHTML = dcgHtml;
        tbl.insertBefore(dataCg, tbl.firstChild);

        // 让克隆进导出图的时间轴表头列宽，与数据表 colgroup 逐列一致。
        if (exportTimelineRows.length) {
            // 表头单元格边框/盒模型与数据表一致，保证边框连续、列宽不被 padding 撑偏。
            tbl.querySelectorAll('thead th').forEach(c => {
                c.style.boxSizing = 'border-box';
                c.style.border = '1px solid rgba(148, 163, 184, 0.55)';
                c.style.background = '#4B5563';
                c.style.backgroundColor = '#4B5563';
                c.style.color = '#fff';
                c.style.padding = '4px 2px';
                c.style.overflow = 'hidden';
            });
        }

        // 统一导出图片中表头/名称/性质/备注/时间轴背景色，与“24小时天气预报”黑灰背景一致。
        tbl.querySelectorAll('thead th, th.col-airport, th.col-desc, th.th-lead, th.th-hour').forEach(c => {
            c.style.background = '#4B5563';
            c.style.backgroundColor = '#4B5563';
            c.style.color = '#fff';
            c.style.borderColor = 'rgba(148, 163, 184, 0.55)';
        });

        // sticky 在截图里会错位，统一取消；同时把字体/换行压到适合图片输出，避免内容撑破单元格。
        tbl.querySelectorAll('th, td').forEach(c => {
            c.style.position = 'static';
            c.style.border = '1px solid rgba(148, 163, 184, 0.55)';
            c.style.overflow = 'hidden';
            c.style.textOverflow = 'clip';
            c.style.boxSizing = 'border-box';
            c.style.lineHeight = '1.15';
            c.style.padding = '3px 2px';
            c.style.height = '30px';
            if (c.classList.contains('td-data')) {
                c.style.whiteSpace = 'normal';
                c.style.wordBreak = 'break-word';
                c.style.overflowWrap = 'anywhere';
                c.style.fontFamily = '微软雅黑,Microsoft YaHei,Arial,sans-serif';
                c.style.fontSize = '10px';
                c.style.fontWeight = '700';
                const cellIndex = c.cellIndex - 4;
                const cellWidth = measuredHourWidths[cellIndex] || hourWidth;
                c.style.width = `${cellWidth}px`;
                c.style.minWidth = `${cellWidth}px`;
            }
            if (c.classList.contains('td-airport')) {
                c.style.whiteSpace = 'nowrap';
                c.style.wordBreak = 'keep-all';
                c.style.width = `${airportWidth}px`;
                c.style.minWidth = `${airportWidth}px`;
            } else if (c.classList.contains('col-airport') && !c.classList.contains('td-data')) {
                c.style.whiteSpace = 'nowrap';
                c.style.wordBreak = 'keep-all';
            }
            if (c.classList.contains('col-source') || c.classList.contains('col-op') || c.classList.contains('col-desc')) {
                c.style.whiteSpace = 'nowrap';
                c.style.wordBreak = 'keep-all';
                c.style.width = c.classList.contains('col-desc') ? `${noteWidth}px` : `${Math.ceil(noteWidth / 2)}px`;
                c.style.minWidth = c.style.width;
            }
        });
        tbl.querySelectorAll('input,button').forEach(el => {
            if (el.classList.contains('airport-delete-x')) { el.remove(); return; }
            if (el.tagName === 'INPUT') {
                const span = document.createElement('span');
                span.textContent = el.value || '';
                span.style.cssText = 'font-size:10px; font-weight:700; color:#1e40af; white-space:nowrap; word-break:keep-all;';
                el.replaceWith(span);
            } else {
                el.style.display = 'none';
            }
        });
        wrap.appendChild(tbl);

        // 尾：克隆结冰/颜色/说明区
        const footerSrc = document.getElementById('pb-export-footer');
        if (footerSrc) {
            const f = footerSrc.cloneNode(true);
            f.id = '';
            f.style.borderRadius = '0';
            f.style.overflow = 'visible';
            f.querySelectorAll('input').forEach(el => {
                const span = document.createElement('span');
                span.textContent = el.value || '无';
                span.style.cssText = 'font-weight:700; color:#005A9C;';
                el.replaceWith(span);
            });
            f.style.fontSize = '12px';
            f.style.borderColor = 'rgba(148, 163, 184, 0.55)';
            f.querySelectorAll('div').forEach(el => {
                const st = el.style;
                if (st.border || st.borderBottom || st.borderRight || st.borderTop || st.borderLeft) {
                    st.borderColor = 'rgba(148, 163, 184, 0.55)';
                }
            });
            wrap.appendChild(f);
        }

        if (pageTotal > 1) {
            const tag = document.createElement('div');
            tag.style.cssText = 'text-align:right; padding:6px 12px; font-size:12px; color:#64748b;';
            tag.textContent = `第 ${pageIdx + 1} / ${pageTotal} 页`;
            wrap.appendChild(tag);
        }
        return wrap;
    }

    async function renderPageImage(pageNode) {
        // 离屏渲染：放进一个不可见容器再截图
        const holder = document.createElement('div');
        holder.style.cssText = 'position:fixed; left:-99999px; top:0; z-index:-1;';
        holder.appendChild(pageNode);
        document.body.appendChild(holder);
        try {
            const canvas = await html2canvas(pageNode, {
                scale: 2,
                backgroundColor: '#ffffff',
                useCORS: true,
                logging: false,
                windowWidth: pageNode.scrollWidth,
                windowHeight: pageNode.scrollHeight
            });
            return canvas.toDataURL('image/png');
        } finally {
            document.body.removeChild(holder);
        }
    }

    function updatePublishStickyOffsets() {
        const header = document.getElementById('pb-export-header');
        const workspace = document.getElementById('publish-workspace');
        const table = document.getElementById('forecast-table');
        if (!header || !workspace) return;
        const h = Math.ceil(header.getBoundingClientRect().height || 0);
        workspace.style.setProperty('--pb-sticky-top', `${h}px`);
        // 只有表格滚到标题区下面时，时间轴才让出标题区高度；初始状态不顶出空行。
        const tableTop = table ? table.getBoundingClientRect().top : Infinity;
        workspace.classList.toggle('pb-head-stuck', tableTop <= h);
    }

    // ---- 预览弹窗状态 ----
    const state = { mode: 'image', rows: [], publishRows: [], rawRows: [], images: [], pageSizes: [], rendering: false, renderVersion: 0 };

    function clearPageSizeControls() {
        const box = document.getElementById('export-page-size-controls');
        if (box) { box.innerHTML = ''; box.style.display = 'none'; }
        state.pageSizes = [];
    }

    function refreshPreview() {
        const renderVersion = ++state.renderVersion;
        const body = document.getElementById('export-preview-body');
        const info = document.getElementById('export-page-info');
        if (!body) return;
        const split = document.getElementById('export-split-toggle')?.checked;
        const pageCountInput = document.getElementById('export-pagecount');
        if (split && pageCountInput && !pageCountInput.value) pageCountInput.value = Math.min(2, state.rows.length || 2);
        const pageCount = pageCountInput?.value;
        const perPage = document.getElementById('export-perpage')?.value;
        const pageCountEl = document.getElementById('export-pagecount');
        const perPageEl = document.getElementById('export-perpage');
        if (pageCountEl) pageCountEl.disabled = !split;
        if (perPageEl) perPageEl.disabled = !split;

        if (state.mode === 'excel') {
            // Excel 预览：用 HTML 表格近似展示将写入的机场数据
            // 🌟 隐藏图片分页专属的“单页机场数”控件（先点分割图片再切 Excel 时会残留）
            const sizeBox = document.getElementById('export-page-size-controls');
            if (sizeBox) { sizeBox.style.display = 'none'; sizeBox.innerHTML = ''; }
            renderExcelPreview(body, info, state.publishRows);
            return;
        }

        const sizeInputs = Array.from(document.querySelectorAll('.export-page-size-input')).map(i => i.value);
        const pages = paginate(state.rows, split, pageCount, perPage, sizeInputs);
        state.pageSizes = pages.map(p => p.length);
        renderPageSizeControls(split, pages);
        if (info) info.textContent = `共 ${state.rows.length} 个机场，${pages.length} 页`;
        body.innerHTML = '<div style="color:#64748b; padding:20px;">⏳ 正在生成预览…</div>';

        // 逐页渲染图片
        (async () => {
            state.images = [];
            const frag = document.createElement('div');
            for (let i = 0; i < pages.length; i++) {
                const node = buildPageNode(pages[i], i, pages.length);
                const img = await renderPageImage(node);
                if (renderVersion !== state.renderVersion) return;
                state.images.push(img);
                const card = document.createElement('div');
                card.style.cssText = 'margin:0 auto 18px auto; max-width:100%; box-shadow:0 2px 8px rgba(0,0,0,0.15); background:#fff;';
                const im = document.createElement('img');
                im.src = img;
                im.style.cssText = 'width:100%; display:block;';
                card.appendChild(im);
                frag.appendChild(card);
            }
            if (renderVersion !== state.renderVersion) return;
            body.innerHTML = '';
            body.appendChild(frag);
        })().catch(e => {
            if (renderVersion !== state.renderVersion) return;
            body.innerHTML = `<div style="color:#dc2626; padding:20px;">预览生成失败: ${e.message}</div>`;
        });
    }

    function renderPageSizeControls(split, pages) {
        const box = document.getElementById('export-page-size-controls');
        if (!box) return;
        if (!split || !pages || pages.length <= 1) { box.style.display = 'none'; box.innerHTML = ''; return; }
        box.style.display = 'flex';
        box.innerHTML = '<span style="font-weight:bold;color:#1e40af;">单页机场数:</span>' + pages.map((p, idx) =>
            `<label style="display:flex;align-items:center;gap:4px;">第${idx + 1}页 <input class="export-page-size-input" data-page="${idx}" type="number" min="1" value="${p.length}" style="width:58px;padding:3px;border:1px solid #cbd5e1;border-radius:4px;"></label>`
        ).join('') + '<span style="color:#94a3b8;">修改后会重新分配，剩余机场自动顺延</span>';
        box.querySelectorAll('.export-page-size-input').forEach(inp => inp.addEventListener('change', () => { state.images = []; refreshPreview(); }));
    }

    function renderExcelPreview(body, info, rows) {
        const numCells = (window.pbState?.validityHours || 24) + 1;
        const sH = window.pbState?.startHour || 0;
        let html = '<table style="border-collapse:collapse; margin:0 auto; font-size:12px; background:#fff;">';
        html += '<tr><th style="border:1px solid #d1d5db; background:#5D6D7E; color:#fff; padding:4px 8px;">名称</th>';
        html += '<th style="border:1px solid #d1d5db; background:#5D6D7E; color:#fff; padding:4px 8px;">性质</th>';
        html += '<th style="border:1px solid #d1d5db; background:#5D6D7E; color:#fff; padding:4px 8px;">备注</th>';
        for (let i = 0; i < numCells; i++) {
            const h = (sH + i + 8) % 24;
            html += `<th style="border:1px solid #d1d5db; background:#4A5867; color:#E2E8F0; padding:2px 4px;">${String(h).padStart(2, '0')}时</th>`;
        }
        html += '</tr>';
        rows.forEach(r => {
            html += `<tr><td style="border:1px solid #d1d5db; padding:3px 8px; font-weight:bold;">${r.name}</td>`;
            html += `<td style="border:1px solid #d1d5db; padding:3px 8px;">${r.type}</td>`;
            html += `<td style="border:1px solid #d1d5db; padding:3px 8px;">${r.note || ''}</td>`;
            for (let i = 0; i < numCells; i++) {
                const v = (r.values[i] || '').replace(/[—/]/g, '');
                html += `<td style="border:1px solid #d1d5db; padding:3px 4px;">${v}</td>`;
            }
            html += '</tr>';
        });
        html += '</table>';
        if (info) info.textContent = `共 ${new Set(rows.map(r => r.icao).filter(Boolean)).size} 个机场，${rows.length} 行预报`;
        body.innerHTML = html;
    }

    function openPreview(mode) {
        const table = document.getElementById('forecast-table');
        if (!table || table.innerHTML.trim() === '') { alert('当前没有可导出的数据！'); return; }
        if (mode === 'image' && typeof html2canvas !== 'function') {
            alert('导出组件 html2canvas 未加载，请检查网络或本地依赖。'); return;
        }
        state.mode = mode;
        state.rows = collectPublishRows();
        state.publishRows = collectPublishDataRows();
        state.rawRows = collectRawRows();
        state.images = [];
        state.pageSizes = [];
        if (state.rows.length === 0) { alert('没有已确认编发或有效的机场行可导出。'); return; }

        document.getElementById('export-preview-title').textContent = mode === 'image' ? '🖼️ 导出图片预览' : '📊 导出 Excel 预览';
        // Excel 模式隐藏图片分页控件
        const splitWrap = document.getElementById('export-split-wrap');
        const pageWrap = document.getElementById('export-pagecount-wrap');
        const perWrap = document.getElementById('export-perpage-wrap');
        if (splitWrap) splitWrap.style.display = mode === 'image' ? 'flex' : 'none';
        if (pageWrap) pageWrap.style.display = mode === 'image' ? 'flex' : 'none';
        if (perWrap) perWrap.style.display = mode === 'image' ? 'flex' : 'none';

        document.getElementById('export-preview-modal').style.display = 'flex';
        refreshPreview();
    }

    async function doExport() {
        const btn = document.getElementById('export-preview-confirm');
        const oldTxt = btn.textContent;
        btn.textContent = '⏳ 导出中…';
        btn.disabled = true;
        try {
            const payload = {
                mode: state.mode,
                data: state.rawRows,
                publish_rows: state.publishRows,
                export_path: exportPath(),
                start_date: window.pbState?.startDate,
                start_hour: window.pbState?.startHour,
                forecaster: document.getElementById('pb-forecaster')?.value || '',
                validity_hours: window.pbState?.validityHours || 24,
                icing_text: getIcingText()
            };
            if (state.mode === 'image') {
                // 确保有最新分页图片
                if (!state.images.length) {
                    const split = document.getElementById('export-split-toggle')?.checked;
                    const pageCount = document.getElementById('export-pagecount')?.value;
                    const perPage = document.getElementById('export-perpage')?.value;
                    const sizeInputs = Array.from(document.querySelectorAll('.export-page-size-input')).map(i => i.value);
                    const pages = paginate(state.rows, split, pageCount, perPage, sizeInputs);
                    state.images = [];
                    for (let i = 0; i < pages.length; i++) {
                        const node = buildPageNode(pages[i], i, pages.length);
                        state.images.push(await renderPageImage(node));
                    }
                }
                payload.images = state.images;
                payload.image = state.images[0]; // 兼容旧字段
            }
            const res = await fetch(`${apiBase()}/export_publish`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const contentType = res.headers.get('content-type') || '';
            const responseText = await res.text();
            if (!contentType.includes('application/json')) {
                throw new Error(`导出接口返回了非 JSON 内容 (HTTP ${res.status})：${responseText.slice(0, 120)}`);
            }
            const result = JSON.parse(responseText);
            if (result.success) {
                alert('✅ 导出成功！\n保存目录:\n' + result.path + (result.files ? '\n文件:\n' + result.files.join('\n') : ''));
                document.getElementById('export-preview-modal').style.display = 'none';
            } else {
                alert('❌ 导出失败: ' + result.error);
            }
        } catch (e) {
            alert('导出发生异常: ' + e.message);
        } finally {
            btn.textContent = oldTxt;
            btn.disabled = false;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        updatePublishStickyOffsets();
        window.addEventListener('resize', updatePublishStickyOffsets);
        window.addEventListener('scroll', updatePublishStickyOffsets, { passive: true });
        document.getElementById('table-wrapper')?.addEventListener('scroll', updatePublishStickyOffsets, { passive: true });
        const pbHeader = document.getElementById('pb-export-header');
        if (pbHeader) new MutationObserver(updatePublishStickyOffsets).observe(pbHeader, { childList: true, subtree: true, attributes: true });
        document.getElementById('close-export-preview')?.addEventListener('click', () => {
            document.getElementById('export-preview-modal').style.display = 'none';
        });
        document.getElementById('export-split-toggle')?.addEventListener('change', () => {
            state.images = [];
            clearPageSizeControls();
            refreshPreview();
        });
        document.getElementById('export-pagecount')?.addEventListener('change', () => {
            state.images = [];
            clearPageSizeControls();
            refreshPreview();
        });
        document.getElementById('export-perpage')?.addEventListener('change', () => {
            state.images = [];
            clearPageSizeControls();
            refreshPreview();
        });
        document.getElementById('export-preview-confirm')?.addEventListener('click', doExport);

        const importModal = document.getElementById('airport-import-modal');
        const importText = document.getElementById('import-forecast-text');
        const renderResidentOptions = () => {
            const box = document.getElementById('import-resident-groups');
            if (!box) return;
            const selectAll = document.getElementById('import-resident-groups-all');
            if (selectAll) selectAll.checked = false;
            const groups = typeof window.getPublishAirportGroups === 'function' ? window.getPublishAirportGroups() : [];
            box.innerHTML = groups.map(group =>
                `<label><input type="checkbox" class="import-resident-group" value="${group.index}"> ${escapeHtml(group.name)}${group.alwaysShow ? ' [置顶]' : ''} (${group.airports.length})</label>`
            ).join('') || '<span style="color:#94a3b8;">暂无机场组</span>';
        };
        document.getElementById('global-import-airports-btn')?.addEventListener('click', () => {
            // 每次打开均从“未选择机场分组”开始，避免文字/表格导入继承上一次的置顶分组。
            window.resetPublishResidentGroupSelection?.();
            document.querySelectorAll('#airport-import-modal .airport-import-category-title').forEach(node => node.remove());
            const addCategoryHeading = (id, title) => {
                const input = document.getElementById(id);
                const anchor = input?.closest('label') || input;
                if (!anchor?.parentElement) return;
                const heading = document.createElement('div');
                heading.className = 'airport-import-category-title';
                heading.textContent = title;
                anchor.parentElement.insertBefore(heading, anchor);
            };
            addCategoryHeading('import-source-running', '运行机场与机场分组');
            addCategoryHeading('import-source-text', '文字导入预报');
            addCategoryHeading('import-source-table', '表格导入');
            renderResidentOptions();
            const allGroupsInput = document.getElementById('import-resident-groups-all');
            const groupBox = document.getElementById('import-resident-groups');
            if (allGroupsInput && groupBox && allGroupsInput.parentElement) {
                allGroupsInput.parentElement.classList.add('resident-groups-select-all');
                allGroupsInput.parentElement.childNodes.forEach(node => { if (node.nodeType === Node.TEXT_NODE) node.textContent = ' 机场分组'; });
                const previous = allGroupsInput.parentElement.previousElementSibling;
                if (previous && !previous.querySelector('input')) previous.remove();
                groupBox.parentElement.insertBefore(allGroupsInput.parentElement, groupBox);
            }
            const residentLabels = [...document.querySelectorAll('.import-resident-group')];
            const residentGroups = typeof window.getPublishAirportGroups === 'function' ? window.getPublishAirportGroups() : [];
            residentLabels.forEach(input => {
                const description = residentGroups[Number(input.value)]?.description;
                if (description) {
                    input.parentElement.title = description;
                    const note = document.createElement('small');
                    note.textContent = `（${description}）`;
                    note.style.cssText = 'color:#64748b;margin-left:4px;';
                    input.parentElement.appendChild(note);
                }
            });
            const allGroups = document.getElementById('import-resident-groups-all');
            const groupChecks = [...document.querySelectorAll('.import-resident-group')];
            groupChecks.forEach(input => { input.checked = false; });
            if (allGroups) {
                allGroups.checked = false;
                allGroups.onchange = () => groupChecks.forEach(input => { input.checked = allGroups.checked; });
                groupChecks.forEach(input => input.addEventListener('change', () => { allGroups.checked = groupChecks.length > 0 && groupChecks.every(item => item.checked); }));
            }
            const panel = document.getElementById('import-text-error-panel');
            const textSource = document.getElementById('import-source-text');
            if (textSource && !document.getElementById('import-text-purpose-help')) {
                const help = document.createElement('span');
                help.id = 'import-text-purpose-help';
                help.className = 'import-option-help';
                help.textContent = '主要用于国际备降机场评估。';
                textSource.closest('label')?.after(help);
            }
            if (panel) { panel.style.display = 'none'; panel.innerHTML = ''; }
            importModal.style.display = 'flex';
        });
        document.getElementById('close-airport-import-modal')?.addEventListener('click', () => { importModal.style.display = 'none'; });
        document.getElementById('check-import-text-btn')?.addEventListener('click', () => {
            document.getElementById('import-source-text').checked = true;
            validateImportText(importText.value, true);
        });
        document.getElementById('execute-airport-import-btn')?.addEventListener('click', async (event) => {
            const button = event.currentTarget;
            const useRunning = document.getElementById('import-source-running').checked;
            const useText = document.getElementById('import-source-text').checked;
            const useTable = document.getElementById('import-source-table').checked;
            const residentGroups = Array.from(document.querySelectorAll('.import-resident-group:checked')).map(el => el.value);
            if (!useRunning && !useText && !useTable && residentGroups.length === 0) {
                alert('请至少选择一种机场来源。');
                return;
            }
            if (useText) {
                const checked = validateImportText(importText.value, true);
                if (!checked.ok) return;
            }
            button.disabled = true;
            const oldText = button.textContent;
            button.textContent = '正在导入...';
            try {
                const runningMode = useRunning ? (document.querySelector('input[name="import-running-mode"]:checked')?.value || 'filtered') : null;
                const orderMode = document.querySelector('input[name="import-order-mode"]:checked')?.value || 'default';
                window.configurePublishAirportSources?.({ runningMode, residentGroups, orderMode });
                const operationSources = {
                    text: new Set(), table: new Set(), resident: new Set(), running: new Set()
                };
                let needsNetwork = useRunning || residentGroups.length > 0;
                if (useText) {
                    const result = importTextToForecast(importText.value, true);
                    (result.icaos || []).forEach(icao => operationSources.text.add(icao));
                    needsNetwork = needsNetwork || result.displayOnly > 0;
                }
                if (useTable) {
                    const result = await importPublishWorkbook();
                    (result.icaos || []).forEach(icao => operationSources.table.add(icao));
                }
                // Record the selected resident-group airports explicitly; the
                // source set may also contain airports from an earlier import.
                const groups = typeof window.getPublishAirportGroups === 'function' ? window.getPublishAirportGroups() : [];
                residentGroups.forEach(index => (groups[Number(index)]?.airports || []).forEach(icao => operationSources.resident.add(icao)));
                if (needsNetwork) {
                    await window.loadForecastData?.(true);
                } else {
                    window.renderPublishTable?.();
                }
                if (useRunning) {
                    (window.pbState?.runningAllAirports || []).forEach(icao => operationSources.running.add(icao));
                    (window.pbState?.sourceAirports?.running || []).forEach(icao => operationSources.running.add(icao));
                }
                window.saveConfirmedDataToLocal?.();
                importModal.style.display = 'none';
                // Use the authoritative source registry after loading.  Some
                // sources (notably running airports and workbook imports) are
                // populated asynchronously and are not reliably represented
                // by the direct import return value.
                const sourceCounts = typeof window.getPublishAirportSourceCounts === 'function'
                    ? window.getPublishAirportSourceCounts()
                    : Object.fromEntries(Object.entries(operationSources).map(([key, set]) => [key, set.size]));
                const allImported = new Set();
                const sourceRegistry = window.pbState?.sourceAirports || {};
                Object.values(sourceRegistry).forEach(source => {
                    if (source instanceof Set) source.forEach(icao => allImported.add(icao));
                });
                Object.values(operationSources).forEach(set => set.forEach(icao => allImported.add(icao)));
                const reportLines = [
                    `导入完成，共涉及 ${allImported.size} 个机场。`,
                    `文字预报：${sourceCounts.text || 0} 个`,
                    `预报表格：${sourceCounts.table || 0} 个`,
                    `常驻分组：${sourceCounts.resident || 0} 个`,
                    `运行机场：${sourceCounts.running || 0} 个`,
                    `手动新增：${sourceCounts.custom || 0} 个`
                ];
                alert(reportLines.join('\n'));
            } catch (error) {
                alert('导入失败：' + error.message);
            } finally {
                button.disabled = false;
                button.textContent = oldText;
            }
        });
    });

    /* ===== 需求2：文字 -> 24小时预报（反向解析） =====
       支持行格式：机场名：时段描述。
       北京时：5日08-11时有雷雨；世界时：5日00Z-03Z有雷雨 / 00Z-03Z有雷雨。
       无 Z 默认北京时；任一端带 Z 则按世界时 UTC 解析。 */
    function buildNameToIcao() {
        const map = {};
        const src = window.GLOBAL_AIRPORT_NAME_MAP || {};
        Object.keys(src).forEach(icao => { map[src[icao]] = icao; });
        return map;
    }

    function normalizeText(s) {
        return String(s || '')
            .replace(/[（(].*?[)）]/g, '')
            .replace(/[，,。；;：:\s]+/g, '')
            .replace(/机场$/g, '')
            .trim()
            .toUpperCase();
    }

    // 🌟 返回 { icao } 命中唯一机场；{ candidates:[...] } 模糊多中；{} 无法识别。
    // 支持四字码模糊（如 “ZG”/“ZGS” 前缀）与中文名模糊。
    function resolveAirportResult(namePart, nameToIcao) {
        const raw = String(namePart || '').trim();
        if (!raw) return {};
        const upper = raw.toUpperCase();
        const coords = window.AIRPORT_COORDS || {};

        // 1. 完整四字码：字典已收录则直接命中；未收录也当外部机场接受。
        if (/^[A-Z]{4}$/.test(upper)) return { icao: upper };

        // 2. 中文名完全匹配（原始 / 归一化）。
        if (nameToIcao[raw]) return { icao: nameToIcao[raw] };
        const norm = normalizeText(raw);
        const exactNorm = Object.entries(nameToIcao).find(([name]) => normalizeText(name) === norm);
        if (exactNorm) return { icao: exactNorm[1] };

        // 3. 不足 4 位的英文：当四字码前缀模糊匹配字典已收录机场。
        if (/^[A-Z]{1,3}$/.test(upper)) {
            const codeHits = Object.keys(coords).filter(ic => ic.startsWith(upper));
            if (codeHits.length === 1) return { icao: codeHits[0] };
            if (codeHits.length > 1) return { candidates: codeHits.slice(0, 12) };
        }

        // 4. 中文名模糊（包含）。
        const nameHits = Object.entries(nameToIcao).filter(([name]) => {
            const key = normalizeText(name);
            return key && (key.includes(norm) || norm.includes(key));
        });
        if (nameHits.length === 1) return { icao: nameHits[0][1] };
        if (nameHits.length > 1) return { candidates: nameHits.slice(0, 12).map(x => x[1]) };

        return {};
    }

    function resolveAirportName(namePart, nameToIcao) {
        const r = resolveAirportResult(namePart, nameToIcao);
        return r.icao || null;
    }

    function splitAirportAndBody(line, nameToIcao) {
        const raw = String(line || '').trim();
        if (!raw) return { namePart: '', body: '' };
        const colonMatch = raw.match(/^(.+?)[：:]\s*(.*)$/);
        if (colonMatch) return { namePart: colonMatch[1].trim(), body: colonMatch[2].trim() };

        const candidates = Object.entries(nameToIcao)
            .map(([name, icao]) => ({ name, icao, n: normalizeText(name) }))
            .sort((a, b) => b.n.length - a.n.length);
        for (const cand of candidates) {
            if (!cand.n) continue;
            const rawNorm = normalizeText(raw);
            if (rawNorm.startsWith(cand.n)) {
                const idx = raw.indexOf(cand.name);
                const rest = idx >= 0 ? raw.slice(idx + cand.name.length).trim() : raw.slice(cand.name.length).trim();
                return { namePart: cand.name, body: rest };
            }
        }
        return { namePart: raw, body: '' };
    }

    function splitImportLines(text) {
        return String(text || '')
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '\n')
            .split(/\n+/)
            .map(s => s.trim())
            .filter(Boolean);
    }

    function normalizePhenomenon(text) {
        return String(text || '')
            .replace(/[。．\.、,，;；]+$/g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function getDayShiftForText(dayStr) {
        const startEpoch = startEpochUTC();
        if (startEpoch === null) return 0;
        if (!dayStr) return 0;
        const day = parseInt(dayStr, 10);
        if (isNaN(day)) return 0;
        const startWall = new Date(startEpoch + 8 * 3600000);
        const baseDay = startWall.getUTCDate();
        return day - baseDay;
    }

    function resolveFlexibleOffset(dayStr, hourStr, isUTC = false) {
        const startEpoch = startEpochUTC();
        if (startEpoch === null) return -1;
        const hour = parseInt(hourStr, 10);
        if (isNaN(hour) || hour < 0 || hour > 23) return -1;

        if (!dayStr) {
            return resolveOffset(null, hourStr, isUTC);
        }
        const dayShift = getDayShiftForText(dayStr);
        const base = new Date(startEpoch + (isUTC ? 0 : 8 * 3600000));
        const target = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), base.getUTCDate() + dayShift, hour, 0, 0));
        const targetEpoch = isUTC ? target.getTime() : target.getTime() - 8 * 3600000;
        return Math.round((targetEpoch - startEpoch) / 3600000);
    }

    function startEpochUTC() {
        const sd = window.pbState?.startDate;
        const sh = window.pbState?.startHour || 0;
        if (!sd) return null;
        return new Date(`${sd}T${String(sh).padStart(2, '0')}:00:00Z`).getTime();
    }

    function standardFormatTip() {
        return '标准格式：每行一个机场，例如：\n' +
            '深圳：5日08-11时有雷雨，12-15时有大风。\n' +
            '杭州：5日06Z-09Z有小雨。\n' +
            '说明：无 Z 默认北京时；时间后加 Z 表示世界时/UTC；机场可填中文名或四字码。';
    }

    // 将「N日HH」或「HH」解析为相对起报世界时的小时偏移。
    // isUTC=true 表示输入时间为世界时；false 表示北京时。
    function resolveOffset(dayStr, hourStr, isUTC = false) {
        const startEpoch = startEpochUTC();
        if (startEpoch === null) return -1;
        const hour = parseInt(hourStr, 10);
        if (isNaN(hour) || hour < 0 || hour > 23) return -1;

        const base = new Date(startEpoch + (isUTC ? 0 : 8 * 3600000));
        if (dayStr) {
            const day = parseInt(dayStr, 10);
            if (isNaN(day) || day < 1 || day > 31) return -1;
            const y = base.getUTCFullYear();
            const m = base.getUTCMonth();
            let targetWall = Date.UTC(y, m, day, hour, 0, 0);
            if (day < base.getUTCDate()) targetWall = Date.UTC(y, m + 1, day, hour, 0, 0);
            const targetEpoch = isUTC ? targetWall : targetWall - 8 * 3600000;
            return Math.round((targetEpoch - startEpoch) / 3600000);
        }

        const numCells = (window.pbState?.validityHours || 24) + 1;
        const startWallHour = isUTC ? (window.pbState?.startHour || 0) : ((window.pbState?.startHour || 0) + 8) % 24;
        for (let i = 0; i < numCells; i++) {
            if ((startWallHour + i) % 24 === hour) return i;
        }
        return -1;
    }

    function parseForecastLine(line, lineNo, nameToIcao, numCells) {
        const errors = [];
        const split = splitAirportAndBody(line, nameToIcao);
        const namePart = split.namePart;
        const body = normalizePhenomenon(split.body);
        const resolved = resolveAirportResult(namePart, nameToIcao);
        if (resolved.candidates && resolved.candidates.length) {
            const list = resolved.candidates.map(ic => `${ic}${window.GLOBAL_AIRPORT_NAME_MAP && window.GLOBAL_AIRPORT_NAME_MAP[ic] ? '(' + window.GLOBAL_AIRPORT_NAME_MAP[ic] + ')' : ''}`).join('、');
            errors.push({ lineNo, line, reason: `机场“${namePart}”模糊匹配到多个，请写更完整的四字码或名称。候选：${list}` });
            return { errors };
        }
        const icao = resolved.icao;
        if (!icao) {
            errors.push({ lineNo, line, reason: `无法识别机场“${namePart}”。可写中文名、简称或四字码（支持模糊），如“深圳 / 深圳机场 / ZGSZ / ZGS”。` });
            return { errors };
        }

        const cells = [];
        const phenomenonRows = {};
        for (let i = 0; i < numCells; i++) cells.push({ text: '', bg: 'transparent', fg: '#1e293b', ts: 'none' });

        // 🌟 只写机场名、不写任何天气/时段：仅把该机场加入表格，由系统拉取 TAF/EC 供编发。
        // （用于把外部机场输入软件，做出预报后再导出为文本）
        if (!body) {
            return { icao, cells, displayOnly: true, errors: [] };
        }
        // 显式写“适航”类关键词才按已编发适航处理。
        if (/适航|天气适航|天气较好|无明显天气|无天气|晴好|稳定|正常/.test(body)) {
            return { icao, cells, note: '适航', errors: [] };
        }

        const segs = body.split(/[，,；;]+/).map(s => s.trim()).filter(Boolean);
        if (!segs.length) {
            return { icao, cells, displayOnly: true, errors: [] };
        }

        let lastDay = null;
        let applied = 0;
        segs.forEach(seg => {
            // 例：5日08-11时有雷雨；5日00Z-03Z有雷雨；5日22时-6日02时有雷雨；5日08时雷雨；08-11时小雨
            const r = seg.match(/(?:(\d{1,2})日)?(\d{1,2})(?:时)?(?:\s*(Z))?\s*[-—~至到]\s*(?:(\d{1,2})日)?(\d{1,2})(?:时)?(?:\s*(Z))?\s*(.*)/i);
            let startOff = -1, endOff = -1, phenomenon = '';
            if (r) {
                const d1 = r[1] || lastDay;
                const h1 = r[2];
                const z1 = !!r[3];
                const d2 = r[4] || r[1] || lastDay;
                const h2 = r[5];
                const z2 = !!r[6];
                const isUTC = z1 || z2;
                lastDay = r[4] || r[1] || lastDay;
                startOff = resolveFlexibleOffset(d1, h1, isUTC);
                endOff = resolveFlexibleOffset(d2, h2, isUTC);
                phenomenon = normalizePhenomenon(r[7] || '');
            } else {
                const r2 = seg.match(/(?:(\d{1,2})日)?(\d{1,2})(?:时)?(?:\s*(Z))?(?:\s*(?:有|为|见|出现|伴有|转))?\s*(.*)/i);
                if (r2) {
                    const d1 = r2[1] || lastDay;
                    const h1 = r2[2];
                    const isUTC = !!r2[3];
                    lastDay = r2[1] || lastDay;
                    startOff = endOff = resolveFlexibleOffset(d1, h1, isUTC);
                    phenomenon = normalizePhenomenon(r2[4] || '');
                }
            }
            phenomenon = phenomenon.replace(/[。.、]$/, '').trim();
            if (window.formatPublishWindText) phenomenon = window.formatPublishWindText(phenomenon);
            if (!phenomenon) {
                const m2 = seg.match(/(?:(\d{1,2})日)?(\d{1,2})(?:时)?(?:\s*(Z))?\s*(.+)/i);
                if (m2) {
                    const d1 = m2[1] || lastDay;
                    const h1 = m2[2];
                    const isUTC = !!m2[3];
                    lastDay = m2[1] || lastDay;
                    startOff = endOff = resolveFlexibleOffset(d1, h1, isUTC);
                    phenomenon = normalizePhenomenon(m2[4] || '');
                }
            }
            if (startOff < 0 || endOff < 0) {
                if (phenomenon && /^(适航|无明显天气|无天气|晴好|稳定|正常)$/i.test(phenomenon)) {
                    return;
                }
                errors.push({ lineNo, line, segment: seg, reason: '无法识别时段。可写成“5日08-11时有雷雨”“08-11时小雨”或“5日00Z-03Z有雷雨”。' });
                return;
            }
            if (!phenomenon) {
                // 允许只写时间不写天气：按适航导入，方便先占位后评估。
                if (startOff === endOff) {
                    applied++;
                    return;
                }
                errors.push({ lineNo, line, segment: seg, reason: '已识别到时段，但未识别到天气现象。可直接留空作为占位，或补充“有雷雨/有小雨”等描述。' });
                return;
            }
            if (startOff >= numCells || endOff < 0) {
                errors.push({ lineNo, line, segment: seg, reason: '时段不在当前预报有效期内。' });
                return;
            }
            const lo = Math.max(0, Math.min(startOff, endOff));
            const hi = Math.min(numCells - 1, Math.max(startOff, endOff));
            const style = window.getMultiCellStyle ? window.getMultiCellStyle(phenomenon) : { bg: '#dc2626', fg: '#fff', ts: 'none' };
            if (!phenomenonRows[phenomenon]) phenomenonRows[phenomenon] = cells.map(() => ({ text: '', bg: 'transparent', fg: '#1e293b', ts: 'none' }));
            for (let i = lo; i <= hi; i++) {
                const value = { text: phenomenon, bg: style.bg, fg: style.fg, ts: style.ts || 'none' };
                cells[i] = value;
                phenomenonRows[phenomenon][i] = value;
            }
            applied++;
        });

        if (!applied) return { icao, cells, note: '适航', errors: [] };
        const rows = Object.values(phenomenonRows).filter(row => row.some(cell => cell.text));
        return { icao, cells, rows: rows.length > 1 ? rows : null, note: '/', errors };
    }

    function renderValidationPanel(result) {
        const panel = document.getElementById('import-text-error-panel');
        const ta = document.getElementById('import-forecast-text');
        if (!panel || !ta) return;
        if (result.ok) {
            ta.style.borderColor = '#22c55e';
            panel.style.display = 'block';
            panel.style.borderColor = '#bbf7d0';
            panel.style.background = '#f0fdf4';
            panel.innerHTML = `<div style="color:#15803d; font-weight:bold;">✅ 纠错检查通过：可导入 ${result.validCount} 个机场。</div>`;
            return;
        }
        ta.style.borderColor = '#dc2626';
        panel.style.display = 'block';
        panel.style.borderColor = '#fecaca';
        panel.style.background = '#fff7f7';
        const rows = result.errors.map(e => `<div style="border-left:4px solid #dc2626; background:#fee2e2; padding:6px 8px; margin:5px 0; border-radius:4px; color:#7f1d1d;">
            <b>第 ${e.lineNo} 行无法识别：</b>${escapeHtml(e.line || '')}<br>
            ${e.segment ? `<b>问题片段：</b>${escapeHtml(e.segment)}<br>` : ''}
            <b>原因：</b>${escapeHtml(e.reason)}
        </div>`).join('');
        panel.innerHTML = rows + `<div style="margin-top:8px; color:#92400e; background:#fffbeb; border:1px solid #fde68a; padding:8px; border-radius:4px; white-space:pre-line;">${escapeHtml(standardFormatTip())}</div>`;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
    }

    function validateImportText(text, showPanel = false) {
        if (!window.pbState || startEpochUTC() === null) {
            const result = { ok: false, validCount: 0, errors: [{ lineNo: '-', line: '', reason: '预报状态未就绪，请先选择起报日期/时间并刷新预报。' }] };
            if (showPanel) renderValidationPanel(result);
            return result;
        }
        const nameToIcao = buildNameToIcao();
        const numCells = (window.pbState.validityHours || 24) + 1;
        const lines = (text || '').split(/\n+/).map((raw, idx) => ({ raw: raw.trim(), lineNo: idx + 1 })).filter(x => x.raw);
        if (!lines.length) {
            const result = { ok: false, validCount: 0, errors: [{ lineNo: 1, line: '', reason: '请输入需要导入的预报文本。' }] };
            if (showPanel) renderValidationPanel(result);
            return result;
        }
        const parsed = lines.map(x => parseForecastLine(x.raw, x.lineNo, nameToIcao, numCells));
        const errors = parsed.flatMap(p => p.errors || []);
        const validCount = parsed.filter(p => p.icao && !(p.errors || []).length).length;
        const result = { ok: errors.length === 0, validCount, errors, parsed };
        if (showPanel) renderValidationPanel(result);
        return result;
    }

    async function importPublishWorkbook() {
        window.showPublishLoadingStatus?.('正在读取并解析导入表格，请稍候...');
        const formData = new FormData();
        const file = document.getElementById('import-publish-excel-file')?.files?.[0];
        if (file) formData.append('file', file);
        const response = await fetch((window.OMICS_API_URL || (path => apiBase() + '/' + path))('import_publish_excel'), { method: 'POST', body: formData });
        const result = await response.json();
        if (!result.success) throw new Error(result.error || '无法读取预报表格');
        const data = result.data || {};
        const nameMap = buildNameToIcao();
        const unresolved = [];
        const importedIcaos = [];

        const detectedDate = data.forecast_date || data.publish_date;
        const detectedHour = Number(data.start_hour_bjt);
        if (detectedDate && Number.isFinite(detectedHour)) {
            const parts = String(detectedDate).slice(0, 10).split(/[-/]/).map(Number);
            const utc = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2], detectedHour - 8));
            window.pbState.startDate = utc.toISOString().slice(0, 10);
            window.pbState.startHour = utc.getUTCHours();
            window.pbState.validityHours = Number(data.validity_hours) || 24;
            window.syncPublishTimeControls?.({ custom: true });
        }
        if (data.special_condition_text) {
            const footer = document.getElementById('pb-special-airports');
            if (footer) footer.value = data.special_condition_text;
            localStorage.setItem('pb_special_condition_text', data.special_condition_text);
            window.saveConfirmedDataToLocal?.();
        }

        (data.airports || []).forEach(entry => {
            const resolved = resolveAirportResult(entry.airport_name, nameMap);
            if (!resolved.icao) {
                unresolved.push(entry.airport_name);
                return;
            }
            const icao = resolved.icao;
            const rows = (entry.rows || []).map(row => row.map(value => {
                const rawText = String(value ?? '').trim();
                const text = window.formatPublishWindTableText ? window.formatPublishWindTableText(rawText) : rawText;
                const style = window.getMultiCellStyle ? window.getMultiCellStyle(text) : { bg: 'transparent', fg: '#1e293b', ts: 'none' };
                return { text, bg: style.bg, fg: style.fg, ts: style.ts || 'none' };
            }));
            window.pbState.confirmedData[icao] = { rows, notes: entry.notes || rows.map(() => '/'), origin: 'table' };
            window.pbState.importedAirportTypes[icao] = entry.nature || '普通';
            delete window.pbState.manualAirportTypes[icao];
            window.pbState.forceShowAirports.add(icao);
            importedIcaos.push(icao);
            if (!window.currentApAnalysis.some(item => item.icao === icao)) {
                window.currentApAnalysis.push({ icao, hasAlert: true, hasAlertEC: false, hasAlertTAF: false, nwp: null, tafRaw: '', tafHourly: null, autoAdoptEC: false, autoAdoptReason: '' });
            }
        });
        window.registerPublishSourceAirports?.('table', importedIcaos);
        if (unresolved.length) alert('以下机场未能匹配机场字典，已跳过：\n' + unresolved.join('、'));
        const loader = document.getElementById('publish-loading-indicator');
        if (loader) loader.style.display = 'none';
        return { count: importedIcaos.length, icaos: importedIcaos };
    }

    function importTextToForecast(text, deferRefresh = false) {
        const checked = validateImportText(text, false);
        if (!checked.ok) {
            renderValidationPanel(checked);
            return { count: 0, displayOnly: 0, icaos: [] };
        }
        const importedIcaos = [];
        let imported = 0;
        let displayOnlyCount = 0;
        checked.parsed.forEach(item => {
            if (!item.icao) return;
            if (item.displayOnly) {
                // 🌟 仅把该机场加入表格，由系统拉取 TAF/EC 供编发；不写入已确认数据。
                window.pbState.forceShowAirports.add(item.icao);
                displayOnlyCount++;
            } else {
                const importedRows = item.rows || [item.cells];
                window.pbState.confirmedData[item.icao] = { rows: importedRows, notes: importedRows.map(() => item.note || '/'), origin: 'text' };
                window.pbState.forceShowAirports.add(item.icao);
            }
            importedIcaos.push(item.icao);
            if (!window.currentApAnalysis.some(ap => ap.icao === item.icao)) {
                window.currentApAnalysis.push({ icao: item.icao, hasAlert: true, hasAlertEC: false, hasAlertTAF: false, nwp: null, tafRaw: '', tafHourly: null, autoAdoptEC: false, autoAdoptReason: '' });
            }
            imported++;
        });
        if (imported > 0 && window.setTextImportAirports) window.setTextImportAirports(importedIcaos);
        if (imported > 0 && !deferRefresh) {
            if (window.saveConfirmedDataToLocal) window.saveConfirmedDataToLocal();
            // 🌟 有“仅展示”机场时，必须实际拉取其 TAF/EC 数据（否则表里只有空行）。
            if (displayOnlyCount > 0 && typeof window.loadForecastData === 'function') {
                window.loadForecastData(true);
            } else {
                if (Array.isArray(window.currentApAnalysis)) {
                    Object.keys(window.pbState.confirmedData).forEach(icao => {
                        if (!window.currentApAnalysis.some(a => a.icao === icao)) {
                            window.currentApAnalysis.push({ icao, hasAlert: true, nwp: null, tafRaw: '', tafHourly: null, autoAdoptEC: false, autoAdoptReason: '' });
                        }
                    });
                }
                if (window.renderPublishTable) window.renderPublishTable();
            }
        }
        return { count: imported, displayOnly: displayOnlyCount, icaos: Array.from(new Set(importedIcaos)) };
    }

    window.OMICSExport = { openPreview, importTextToForecast, importPublishWorkbook };
})();
