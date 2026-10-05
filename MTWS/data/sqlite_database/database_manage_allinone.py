import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import sqlite3
import os
import csv
from datetime import datetime

DB_DIR = os.path.dirname(os.path.abspath(__file__))
FIELDS_PER_PAGE = 15  # 每页显示的字段数
ROWS_PER_PAGE = 100   # 数据表每页显示的行数


def visible_page_numbers(total_pages, current_page):
    """返回要展示的页码（从 0 起）。页数过多时用 '...' 省略中间页。"""
    if total_pages <= 9:
        return list(range(total_pages))
    pages = {0, total_pages - 1}
    for delta in range(-2, 3):
        pp = current_page + delta
        if 0 <= pp < total_pages:
            pages.add(pp)
    result = []
    prev = -1
    for pg in sorted(pages):
        if prev >= 0 and pg - prev > 1:
            result.append('...')
        result.append(pg)
        prev = pg
    return result

def get_tables(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return tables

def get_table_data(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    cursor.execute(f"SELECT rowid, * FROM {table_name}")
    rows = cursor.fetchall()
    cursor.close()
    return columns, rows

def get_table_pk(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    pk_cols = [row[1] for row in cursor.fetchall() if row[5]]
    cursor.close()
    return pk_cols


class PagedEditDialog:
    """
    通用分页字段编辑对话框。
    当字段数超过 FIELDS_PER_PAGE 时自动分页，支持页码按钮和上一页/下一页翻页。
    """

    def __init__(self, parent, title, columns, init_values, orig_nulls, on_confirm):
        """
        parent      : 父窗口
        title       : 对话框标题
        columns     : 字段名列表
        init_values : 各字段初始值列表（字符串），空字符串表示空
        orig_nulls  : 各字段是否原本为 NULL 的布尔列表
        on_confirm  : 确认回调 on_confirm(win, values, orig_nulls)
        """
        self.parent = parent
        self.columns = columns
        self.orig_nulls = orig_nulls
        self.on_confirm = on_confirm

        total = len(columns)
        self.total_pages = max(1, (total + FIELDS_PER_PAGE - 1) // FIELDS_PER_PAGE)
        self.current_page = 0

        # 所有字段的当前值（跨页持久存储）
        self.values = list(init_values)

        # 当前页展示的 (col_idx, Entry) 列表
        self._page_widgets = []

        # ── 窗口 ──
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.resizable(True, True)
        self.win.geometry("660x520")
        self.win.grab_set()

        # ── 顶部导航栏 ──
        nav_bar = tk.Frame(self.win, bd=1, relief='groove', bg='#f0f0f0')
        nav_bar.pack(fill='x', padx=6, pady=(6, 2))

        self._page_label = tk.Label(nav_bar, text='', font=('', 9), bg='#f0f0f0')
        self._page_label.pack(side='left', padx=8)

        self._btn_container = tk.Frame(nav_bar, bg='#f0f0f0')
        self._btn_container.pack(side='right', padx=4)

        # ── 内容区域（带滚动，应对极端情况）──
        self._content_frame = tk.Frame(self.win)
        self._content_frame.pack(fill='both', expand=True, padx=6, pady=2)
        self._content_frame.columnconfigure(1, weight=1)

        # ── 底部确定/取消 ──
        bottom = tk.Frame(self.win)
        bottom.pack(fill='x', padx=6, pady=(2, 8))
        tk.Button(bottom, text='确定', width=10, command=self._on_ok).pack(side='left', padx=6)
        tk.Button(bottom, text='取消', width=10, command=self.win.destroy).pack(side='left', padx=2)

        self._show_page(0)

    # ── 内部方法 ────────────────────────────────────────────

    def _save_current_page(self):
        """把当前页 Entry 的值同步到 values 列表。"""
        for col_idx, entry in self._page_widgets:
            self.values[col_idx] = entry.get()

    def _show_page(self, page_num):
        self._save_current_page()

        # 清空内容区
        for w in self._content_frame.winfo_children():
            w.destroy()
        self._page_widgets.clear()

        self.current_page = page_num
        start = page_num * FIELDS_PER_PAGE
        end = min(start + FIELDS_PER_PAGE, len(self.columns))

        for row_idx, col_idx in enumerate(range(start, end)):
            col = self.columns[col_idx]
            val = self.values[col_idx]

            lbl = tk.Label(self._content_frame, text=col, anchor='e',
                           width=30, fg='#222', font=('', 9))
            lbl.grid(row=row_idx, column=0, sticky='e', padx=(4, 6), pady=2)

            entry = tk.Entry(self._content_frame, width=42, font=('', 9))
            if val:
                entry.insert(0, val)
            elif self.orig_nulls[col_idx]:
                entry.config(fg='gray')
            entry.grid(row=row_idx, column=1, sticky='ew', padx=(0, 4), pady=2)
            self._page_widgets.append((col_idx, entry))

        if self._page_widgets:
            self._page_widgets[0][1].focus_set()

        self._update_nav()

    def _update_nav(self):
        """刷新顶部导航栏。"""
        for w in self._btn_container.winfo_children():
            w.destroy()

        page = self.current_page
        total = len(self.columns)
        start_field = page * FIELDS_PER_PAGE + 1
        end_field = min(start_field + FIELDS_PER_PAGE - 1, total)
        self._page_label.config(
            text=f'第 {page + 1} / {self.total_pages} 页  '
                 f'（字段 {start_field}–{end_field} / 共 {total} 个）'
        )

        # 上一页
        tk.Button(
            self._btn_container, text='◀ 上一页', width=7,
            state='normal' if page > 0 else 'disabled',
            command=lambda: self._show_page(self.current_page - 1)
        ).pack(side='left', padx=2)

        # 数字页码按钮（页数较多时只显示附近几页）
        visible_pages = self._visible_page_range()
        first_shown = True
        for p in visible_pages:
            if p == '...':
                tk.Label(self._btn_container, text='…').pack(side='left', padx=1)
                continue
            is_cur = (p == page)
            tk.Button(
                self._btn_container,
                text=str(p + 1),
                width=3,
                relief='sunken' if is_cur else 'raised',
                bg='#3a8ee6' if is_cur else 'SystemButtonFace',
                fg='white' if is_cur else 'black',
                command=(lambda pn=p: self._show_page(pn)) if not is_cur else (lambda: None)
            ).pack(side='left', padx=1)

        # 下一页
        tk.Button(
            self._btn_container, text='下一页 ▶', width=7,
            state='normal' if page < self.total_pages - 1 else 'disabled',
            command=lambda: self._show_page(self.current_page + 1)
        ).pack(side='left', padx=2)

    def _visible_page_range(self):
        """返回要展示的页码列表（含省略号 '...'），避免页数太多时按钮挤满。"""
        n = self.total_pages
        p = self.current_page
        if n <= 7:
            return list(range(n))
        pages = set()
        pages.add(0)
        pages.add(n - 1)
        for delta in range(-2, 3):
            pp = p + delta
            if 0 <= pp < n:
                pages.add(pp)
        result = []
        prev = -1
        for pg in sorted(pages):
            if pg - prev > 1:
                result.append('...')
            result.append(pg)
            prev = pg
        return result

    def _on_ok(self):
        self._save_current_page()
        self.on_confirm(self.win, self.values, self.orig_nulls)


# ─────────────────────────────────────────────────────────────

class DatabaseViewer(tk.Tk):
    def _open_databases(self):
        found = []
        for label, filename in (("配置库", "mtws_config.db"), ("生产库", "mtws_runtime.db")):
            path = os.path.join(DB_DIR, filename)
            if os.path.isfile(path):
                found.append((label, sqlite3.connect(path)))
        return found

    def __init__(self):
        super().__init__()
        self.title("数据库浏览器")
        self.geometry("1000x700")
        self.current_conns = self._open_databases()
        if not self.current_conns:
            messagebox.showerror("错误", "未找到 mtws_config.db 或 mtws_runtime.db")
            self.destroy()
            return
        self.title("数据库浏览器 - " + "、".join(label for label, _conn in self.current_conns))

        # 左侧表列表
        self.table_listbox = tk.Listbox(self, width=42)
        self.table_listbox.pack(side='left', fill='y')
        self.table_listbox.bind('<<ListboxSelect>>', self.on_table_select)

        # 右侧表数据展示
        self.data_frame = tk.Frame(self)
        self.data_frame.pack(side='right', fill='both', expand=True)

        # 下方操作按钮
        self.button_frame = tk.Frame(self.data_frame)
        self.button_frame.pack(side='bottom', fill='x', padx=5, pady=5)

        self.add_btn = tk.Button(self.button_frame, text="新增", command=self.add_row)
        self.add_btn.pack(side='left', padx=5)
        self.edit_btn = tk.Button(self.button_frame, text="修改选中行", command=self.edit_row)
        self.edit_btn.pack(side='left', padx=5)
        self.del_btn = tk.Button(self.button_frame, text="删除选中行", command=self.delete_row)
        self.del_btn.pack(side='left', padx=5)
        self.copy_btn = tk.Button(self.button_frame, text="复制选中行", command=self.copy_row)
        self.copy_btn.pack(side='left', padx=5)
        self.clear_btn = tk.Button(self.button_frame, text="清空表数据", command=self.clear_table, fg='red')
        self.clear_btn.pack(side='left', padx=5)
        self.export_btn = tk.Button(self.button_frame, text="导出为CSV", command=self.export_to_csv)
        self.export_btn.pack(side='left', padx=5)

        self.tree = None
        self.current_table = None
        self.current_conn = None
        self._table_entries = []
        self.current_columns = []
        self.rows_map = {}
        self._all_rows = []
        self._table_page = 0
        self._total_pages = 1

        self.load_table_names()

    def load_table_names(self):
        self.table_listbox.delete(0, tk.END)
        self._table_entries = []
        for label, conn in self.current_conns:
            for tbl in sorted(get_tables(conn)):
                if tbl.startswith("sqlite_"):
                    continue
                self._table_entries.append((conn, tbl))
                self.table_listbox.insert(tk.END, f"{label} / {tbl}")

    def on_table_select(self, event):
        sel = self.table_listbox.curselection()
        if not sel:
            return
        conn, table_name = self._table_entries[sel[0]]
        if table_name != self.current_table or conn is not self.current_conn:
            self._table_page = 0
        columns, rows = get_table_data(conn, table_name)
        self.current_conn = conn
        self.current_table = table_name
        self.current_columns = columns
        self.show_table_data(columns, rows)

    def show_table_data(self, columns, rows):
        self._all_rows = rows
        total = len(rows)
        self._total_pages = max(1, (total + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
        if self._table_page >= self._total_pages:
            self._table_page = self._total_pages - 1
        if self._table_page < 0:
            self._table_page = 0
        self._render_current_page()

    def _render_current_page(self):
        columns = self.current_columns
        for widget in self.data_frame.winfo_children():
            if widget is not self.button_frame:
                widget.destroy()
        display_columns = [col for col in columns]

        total = len(self._all_rows)
        start = self._table_page * ROWS_PER_PAGE
        end = min(start + ROWS_PER_PAGE, total)
        page_rows = self._all_rows[start:end]

        # 先放分页条，再让表格占满剩余空间（否则分页条会被挤出可视区域）
        self._build_table_pager(total, start, end)

        # 用 Frame 装载 Treeview 和滚动条
        tree_frame = tk.Frame(self.data_frame)
        tree_frame.pack(fill='both', expand=True)

        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(
            tree_frame, columns=display_columns, show='headings',
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set
        )
        self.tree.pack(side='left', fill='both', expand=True)
        yscroll.config(command=self.tree.yview)
        xscroll.config(command=self.tree.xview)
        yscroll.pack(side='right', fill='y')
        xscroll.pack(side='bottom', fill='x')

        for col in display_columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor='center', width=150, stretch=True)

        self.rows_map = {}
        for row in page_rows:
            rowid = row[0]
            data = row[1:]
            iid = self.tree.insert('', tk.END, values=data)
            self.rows_map[iid] = rowid

    def _build_table_pager(self, total, start, end):
        """表格下方页码条：首页/末页、邻近页码、省略号，以及跳转到指定页。"""
        pager = tk.Frame(self.data_frame, bd=1, relief='groove', bg='#f5f5f5')
        pager.pack(side='bottom', fill='x', padx=4, pady=(2, 0))

        page = self._table_page
        pages = self._total_pages
        if total == 0:
            info = '共 0 条    第 1 / 1 页'
        else:
            info = f'共 {total} 条    第 {page + 1} / {pages} 页    （本页 {start + 1}–{end}）'

        # 第一行：条数信息 + 跳转到指定页（避免和页码按钮挤在同一行被裁切）
        info_row = tk.Frame(pager, bg='#f5f5f5')
        info_row.pack(fill='x', padx=4, pady=(3, 0))
        tk.Label(info_row, text=info, bg='#f5f5f5', font=('', 9)).pack(side='left', padx=4)

        jump_box = tk.Frame(info_row, bg='#f5f5f5')
        jump_box.pack(side='right', padx=4)
        tk.Label(jump_box, text='跳至', bg='#f5f5f5').pack(side='left', padx=(0, 2))
        jump_var = tk.StringVar()
        jump_entry = tk.Entry(jump_box, textvariable=jump_var, width=6, justify='center')
        jump_entry.pack(side='left')
        jump_entry.bind('<Return>', lambda e: self._jump_to_page(jump_var.get()))
        tk.Label(jump_box, text='页', bg='#f5f5f5').pack(side='left', padx=(2, 2))
        tk.Button(
            jump_box, text='前往', width=4,
            command=lambda: self._jump_to_page(jump_var.get()),
        ).pack(side='left', padx=1)

        # 第二行：首页 / 上一页 / 页码 / 下一页 / 末页
        nav_row = tk.Frame(pager, bg='#f5f5f5')
        nav_row.pack(fill='x', pady=(0, 3))
        nav = tk.Frame(nav_row, bg='#f5f5f5')
        nav.pack(anchor='center')

        def nav_btn(text, width, enabled, target):
            tk.Button(
                nav, text=text, width=width,
                state='normal' if enabled else 'disabled',
                command=(lambda t=target: self._goto_page(t)) if enabled else None,
            ).pack(side='left', padx=1)

        nav_btn('首页', 4, page > 0, 0)
        nav_btn('上一页', 6, page > 0, page - 1)

        for item in visible_page_numbers(pages, page):
            if item == '...':
                tk.Label(nav, text='…', bg='#f5f5f5').pack(side='left', padx=2)
                continue
            is_cur = (item == page)
            tk.Button(
                nav,
                text=str(item + 1),
                width=max(3, len(str(item + 1))),
                relief='sunken' if is_cur else 'raised',
                bg='#3a8ee6' if is_cur else 'SystemButtonFace',
                fg='white' if is_cur else 'black',
                command=(lambda: None) if is_cur else (lambda pn=item: self._goto_page(pn)),
            ).pack(side='left', padx=1)

        nav_btn('下一页', 6, page < pages - 1, page + 1)
        nav_btn('末页', 4, page < pages - 1, pages - 1)

    def _goto_page(self, page_num):
        if page_num < 0 or page_num >= self._total_pages or page_num == self._table_page:
            return
        self._table_page = page_num
        self._render_current_page()

    def _jump_to_page(self, raw):
        text = str(raw).strip()
        if not text:
            return
        try:
            page = int(text)
        except ValueError:
            messagebox.showinfo("提示", "请输入有效的页码数字")
            return
        if page < 1 or page > self._total_pages:
            messagebox.showinfo("提示", f"页码范围为 1 到 {self._total_pages}")
            return
        self._goto_page(page - 1)

    # ── 新增行 ──────────────────────────────────────────────

    def add_row(self):
        if not self.current_table:
            return
        columns = self.current_columns
        table = self.current_table

        init_values = [''] * len(columns)
        orig_nulls = [False] * len(columns)

        def on_confirm(win, values, orig_nulls):
            try:
                placeholders = ','.join(['?' for _ in values])
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
                self.current_conn.execute(sql, values)
                self.current_conn.commit()
                self.on_table_select(None)
                win.destroy()
            except Exception as e:
                messagebox.showerror("添加失败", str(e))

        PagedEditDialog(
            self,
            title=f"新增到表 {table}",
            columns=columns,
            init_values=init_values,
            orig_nulls=orig_nulls,
            on_confirm=on_confirm,
        )

    # ── 修改选中行 ───────────────────────────────────────────

    def edit_row(self):
        if not self.current_table or not self.tree:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中要修改的行")
            return
        rowid = self.rows_map.get(sel[0])
        old_vals = self.tree.item(sel[0], "values")
        columns = self.current_columns
        table = self.current_table

        # 检测 metar 表中 data_status=N 行的修改（影响入库告警逻辑）
        if table == 'metar' and 'data_status' in columns:
            ds_idx = columns.index('data_status')
            if str(old_vals[ds_idx]) == 'N':
                messagebox.showwarning(
                    "注意",
                    "您正在修改 data_status=N（当前活跃）的 METAR 行。\n\n"
                    "修改 created_at 或 metar_observation_time 为旧时间后，\n"
                    "下次实况更新时该机场将触发入库告警。\n\n"
                    "如果其他机场的 N 行 created_at 也超过阈值（默认70分钟），\n"
                    "它们同样会被告警——这是正常行为，并非本次修改导致。"
                )

        orig_nulls = []
        init_values = []
        for val in old_vals:
            is_null = (str(val) == "None")
            orig_nulls.append(is_null)
            init_values.append('' if is_null else str(val))

        def on_confirm(win, values, orig_nulls):
            new_vals = [
                None if (values[i] == '' and orig_nulls[i]) else
                (None if values[i] == '' else values[i])
                for i in range(len(values))
            ]
            try:
                set_clause = ','.join([f"{col}=?" for col in columns])
                sql = f"UPDATE {table} SET {set_clause} WHERE rowid=?"
                self.current_conn.execute(sql, new_vals + [rowid])
                self.current_conn.commit()
                self.on_table_select(None)
                win.destroy()
            except Exception as e:
                messagebox.showerror("修改失败", str(e))

        PagedEditDialog(
            self,
            title=f"修改表 {table} 的数据",
            columns=columns,
            init_values=init_values,
            orig_nulls=orig_nulls,
            on_confirm=on_confirm,
        )

    # ── 删除选中行 ───────────────────────────────────────────

    def delete_row(self):
        if not self.current_table or not self.tree:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中要删除的行")
            return
        rowid = self.rows_map.get(sel[0])
        table = self.current_table
        answer = messagebox.askyesno("确认删除", "确定删除选中行吗？")
        if not answer:
            return
        try:
            self.current_conn.execute(f"DELETE FROM {table} WHERE rowid=?", (rowid,))
            self.current_conn.commit()
            self.on_table_select(None)
        except Exception as e:
            messagebox.showerror("删除失败", str(e))

    # ── 复制选中行 ───────────────────────────────────────────

    def copy_row(self):
        if not self.current_table or not self.tree:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中要复制的行")
            return

        old_vals = self.tree.item(sel[0], "values")
        columns = self.current_columns
        table = self.current_table

        orig_nulls = [False] * len(columns)
        init_values = [str(v) for v in old_vals]

        def on_confirm(win, values, orig_nulls):
            try:
                placeholders = ','.join(['?' for _ in values])
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
                self.current_conn.execute(sql, values)
                self.current_conn.commit()
                self.on_table_select(None)
                win.destroy()
                messagebox.showinfo("成功", "行已复制")
            except Exception as e:
                messagebox.showerror("复制失败", str(e))

        PagedEditDialog(
            self,
            title=f"复制行到表 {table}",
            columns=columns,
            init_values=init_values,
            orig_nulls=orig_nulls,
            on_confirm=on_confirm,
        )

    # ── 清空表 ───────────────────────────────────────────────

    def clear_table(self):
        if not self.current_table:
            messagebox.showinfo("提示", "请先选择要清空的表")
            return

        table = self.current_table
        cursor = self.current_conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        row_count = cursor.fetchone()[0]
        cursor.close()

        if row_count == 0:
            messagebox.showinfo("提示", f"表 '{table}' 当前没有数据")
            return

        answer = messagebox.askyesno(
            "危险操作确认",
            f"警告：此操作将清空表 '{table}' 的所有数据！\n\n"
            f"当前表共有 {row_count} 行数据\n"
            f"表结构将保留，但所有数据将被永久删除\n\n"
            f"确定要继续吗？",
            icon='warning'
        )
        if not answer:
            return

        try:
            self.current_conn.execute(f"DELETE FROM {table}")
            self.current_conn.commit()
            self.current_conn.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
            self.current_conn.commit()
            self.on_table_select(None)
            messagebox.showinfo("成功", f"表 '{table}' 的所有数据已清空\n共删除 {row_count} 行数据")
        except Exception as e:
            messagebox.showerror("清空失败", str(e))

    # ── 导出 CSV ─────────────────────────────────────────────

    def export_to_csv(self):
        if not self.current_table:
            messagebox.showinfo("提示", "请先选择要导出的表")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{self.current_table}_{timestamp}.csv"

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
            initialfile=default_filename
        )
        if not file_path:
            return

        try:
            cursor = self.current_conn.cursor()
            cursor.execute(f"SELECT * FROM {self.current_table}")
            rows = cursor.fetchall()
            columns = self.current_columns

            with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(columns)
                writer.writerows(rows)

            cursor.close()
            messagebox.showinfo("成功", f"数据已导出到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))


if __name__ == "__main__":
    _root = tk.Tk()
    _root.withdraw()  # 隐藏临时根窗口
    _pwd = simpledialog.askstring("身份验证", "请输入密码：", show="*", parent=_root)
    _root.destroy()
    if _pwd != "admin":
        if _pwd is not None:  # None = 点了取消，不弹提示
            messagebox.showerror("验证失败", "密码错误，无法打开数据库管理工具。")
        raise SystemExit
    app = DatabaseViewer()
    app.mainloop()
