"""
FMSA 模块配置。本机 CustomTkinter 程序，写入 data/fmsa_modules.json。
主程序下次启动时读取。不启动 Django。
"""

import importlib.util
from pathlib import Path

import customtkinter as ctk

ROOT = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    'fmsa_module_profile',
    ROOT / 'fmsa_django' / 'utils' / 'module_profile.py',
)
_profile = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_profile)

MODULE_META = _profile.MODULE_META
MODULE_GROUPS = _profile.MODULE_GROUPS
PROFILE_PATH = _profile.PROFILE_PATH
load_profile = _profile.load_profile
save_profile = _profile.save_profile
REPORT_LANG_ORIGINAL = _profile.REPORT_LANG_ORIGINAL
REPORT_LANG_CHINESE = _profile.REPORT_LANG_CHINESE

BG = '#161618'
BG2 = '#242426'
BG3 = '#2e2e32'
HEADER = '#1f1f23'
BLUE = '#0a84ff'
GREEN = '#30d158'
RED = '#ff453a'
LABEL = '#f5f5f7'
LABEL2 = '#c7c7cc'
MUTED = '#8e8e93'
LINE = '#3a3a3c'
ROW_ALT = '#1c1c1e'
BOX = 22

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('dark-blue')

COLS = (
    ('模块', 210),
    ('数据', 280),
    ('程序写入', 160),
    ('人写入', 170),
    ('配置', 210),
)


class SquareCheck(ctk.CTkFrame):
    """方块勾选：选中时框内显示 √。locked 时仍显示勾，点了不变。"""

    def __init__(self, master, text, variable, command=None, locked=False, width=210):
        super().__init__(master, fg_color='transparent', width=width)
        self.variable = variable
        self.command = command
        self.locked = locked
        self.box = ctk.CTkButton(
            self, text='', width=BOX, height=BOX, corner_radius=3,
            fg_color=BG3, hover_color='#3a3a40', border_width=2, border_color=MUTED,
            font=ctk.CTkFont(size=14, weight='bold'), text_color='#ffffff',
            command=self._click,
        )
        self.box.pack(side='left', padx=(0, 8), pady=0)
        self.caption = ctk.CTkLabel(
            self, text=text, font=ctk.CTkFont(size=14, weight='bold'),
            text_color=LABEL, anchor='w', cursor='hand2',
        )
        self.caption.pack(side='left', fill='x', expand=True)
        self.caption.bind('<Button-1>', lambda _e: self._click())
        self._trace = variable.trace_add('write', lambda *_: self._paint())
        self._paint()

    def _click(self):
        if self.locked:
            return
        self.variable.set(not bool(self.variable.get()))
        if self.command:
            self.command()

    def set_locked(self, locked):
        self.locked = bool(locked)
        self._paint()

    def _paint(self):
        on = bool(self.variable.get())
        self.box.configure(
            text='√' if on else '',
            fg_color=BLUE if on else BG3,
            hover_color=BLUE if on else '#3a3a40',
            border_color=BLUE if on else MUTED,
        )
        if self.locked:
            self.box.configure(hover_color=BLUE if on else BG3)
            self.caption.configure(text_color=MUTED if not on else LABEL)


class ExclusiveSquare(ctk.CTkFrame):
    """二选一：同样是方块 √，同一组只能勾一个。"""

    def __init__(self, master, text, variable, value, command=None, width=210):
        super().__init__(master, fg_color='transparent', width=width)
        self.variable = variable
        self.value = value
        self.command = command
        self.box = ctk.CTkButton(
            self, text='', width=BOX, height=BOX, corner_radius=3,
            fg_color=BG3, hover_color='#3a3a40', border_width=2, border_color=MUTED,
            font=ctk.CTkFont(size=14, weight='bold'), text_color='#ffffff',
            command=self._click,
        )
        self.box.pack(side='left', padx=(0, 8), pady=0)
        self.caption = ctk.CTkLabel(
            self, text=text, font=ctk.CTkFont(size=14, weight='bold'),
            text_color=LABEL, anchor='w', cursor='hand2',
        )
        self.caption.pack(side='left', fill='x', expand=True)
        self.caption.bind('<Button-1>', lambda _e: self._click())
        variable.trace_add('write', lambda *_: self._paint())
        self._paint()

    def _click(self):
        self.variable.set(self.value)
        if self.command:
            self.command()

    def _paint(self):
        on = self.variable.get() == self.value
        self.box.configure(
            text='√' if on else '',
            fg_color=BLUE if on else BG3,
            hover_color=BLUE if on else '#3a3a40',
            border_color=BLUE if on else MUTED,
        )


class ModuleConfigApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('FMSA 模块配置')
        self.geometry('1180x860')
        self.minsize(980, 700)
        self.configure(fg_color=BG)
        self._vars = {}
        self._checks = {}
        self._lang = ctk.StringVar(value=REPORT_LANG_ORIGINAL)
        self._build()
        self._load()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.pack(fill='x', padx=22, pady=(16, 4))
        ctk.CTkLabel(
            header, text='模块配置', font=ctk.CTkFont(size=22, weight='bold'),
            text_color=LABEL, anchor='w',
        ).pack(fill='x')
        ctk.CTkLabel(
            header,
            text='勾选后主程序下次启动生效。核心数据组固定启用。至少再勾选 1 个模块。雷达和卫星由地图视图一并控制。',
            font=ctk.CTkFont(size=13), text_color=LABEL2, anchor='w', wraplength=1100,
        ).pack(fill='x', pady=(4, 0))
        ctk.CTkLabel(
            header, text=str(PROFILE_PATH), font=ctk.CTkFont(size=12),
            text_color=MUTED, anchor='w',
        ).pack(fill='x', pady=(2, 0))

        scroll = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        scroll.pack(fill='both', expand=True, padx=14, pady=8)

        by_group = {key: [] for key, _title in MODULE_GROUPS}
        for meta in MODULE_META:
            by_group.setdefault(meta['group'], []).append(meta)

        for group_key, title in MODULE_GROUPS:
            wrap = self._section(scroll, title, by_group.get(group_key) or [])
            if group_key == 'general':
                self._lang_rows(wrap)

        bar = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        bar.pack(fill='x', padx=22, pady=(4, 16))
        self.status = ctk.CTkLabel(
            bar, text='', font=ctk.CTkFont(size=13), text_color=LABEL2, anchor='w',
        )
        self.status.pack(side='left', fill='x', expand=True)
        ctk.CTkButton(
            bar, text='保存', width=120, height=36, corner_radius=8,
            fg_color=GREEN, hover_color='#27a846', text_color='#ffffff',
            font=ctk.CTkFont(size=14, weight='bold'), command=self._save,
        ).pack(side='right')

    def _section(self, parent, title, items):
        wrap = ctk.CTkFrame(parent, fg_color=BG2, corner_radius=10)
        wrap.pack(fill='x', padx=8, pady=(0, 10))
        ctk.CTkLabel(
            wrap, text=title, font=ctk.CTkFont(size=16, weight='bold'),
            text_color=LABEL, anchor='w',
        ).pack(fill='x', padx=16, pady=(12, 6))
        self._col_header(wrap)
        for row_i, meta in enumerate(items):
            self._module_row(wrap, meta, row_i)
        return wrap

    def _col_header(self, parent):
        head = ctk.CTkFrame(parent, fg_color=HEADER, corner_radius=0)
        head.pack(fill='x')
        for i, (title, width) in enumerate(COLS):
            ctk.CTkLabel(
                head, text=title, width=width, anchor='w',
                font=ctk.CTkFont(size=12, weight='bold'), text_color=MUTED,
            ).grid(row=0, column=i, sticky='nsew', padx=(16 if i == 0 else 8, 8), pady=8)
            head.grid_columnconfigure(i, weight=1 if i else 0)

    def _module_row(self, parent, meta, row_i):
        bg = ROW_ALT if row_i % 2 else BG2
        row = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0)
        row.pack(fill='x')
        var = ctk.BooleanVar(value=True)
        self._vars[meta['key']] = var
        pad_left = 36 if meta.get('parent') == 'home' else 16
        check = SquareCheck(
            row, meta['name'], var, command=self._on_toggle,
            locked=bool(meta.get('locked')), width=COLS[0][1] - (pad_left - 16),
        )
        check.grid(row=0, column=0, sticky='nw', padx=(pad_left, 8), pady=10)
        self._checks[meta['key']] = check
        texts = (meta['data'], meta['program'], meta['human'], meta['config'])
        for i, text in enumerate(texts, start=1):
            ctk.CTkLabel(
                row, text=text, width=COLS[i][1],
                font=ctk.CTkFont(size=13), text_color=LABEL2,
                anchor='nw', justify='left', wraplength=COLS[i][1] - 8,
            ).grid(row=0, column=i, sticky='nsew', padx=8, pady=10)
            row.grid_columnconfigure(i, weight=1)
        row.grid_columnconfigure(0, weight=0)

    def _lang_rows(self, wrap):
        ctk.CTkLabel(
            wrap, text='机场详情 / 搜索结果',
            font=ctk.CTkFont(size=14, weight='bold'), text_color=LABEL, anchor='w',
        ).pack(fill='x', padx=16, pady=(10, 4))
        rows = (
            (
                REPORT_LANG_ORIGINAL, '原文优先',
                '只有翻译视图下，机场详情和搜索才显示中文；其余视图显示原文。',
            ),
            (
                REPORT_LANG_CHINESE, '中文优先',
                '只有主页视图下，机场详情和搜索才显示原文；其余视图显示中文。',
            ),
        )
        for i, (value, name, desc) in enumerate(rows):
            bg = ROW_ALT if i % 2 else BG2
            row = ctk.CTkFrame(wrap, fg_color=bg, corner_radius=0)
            row.pack(fill='x')
            ExclusiveSquare(
                row, name, self._lang, value, command=self._on_toggle, width=COLS[0][1],
            ).grid(row=0, column=0, sticky='nw', padx=(16, 8), pady=10)
            ctk.CTkLabel(
                row, text=desc, font=ctk.CTkFont(size=13), text_color=LABEL2,
                anchor='nw', justify='left', wraplength=COLS[1][1] + COLS[2][1] + COLS[3][1] + COLS[4][1] - 24,
            ).grid(row=0, column=1, columnspan=4, sticky='nsew', padx=8, pady=10)
            row.grid_columnconfigure(1, weight=1)

    def _load(self):
        profile = load_profile()
        modules = profile['modules']
        for key, var in self._vars.items():
            var.set(bool(modules.get(key, True)))
        self._vars['core'].set(True)
        self._lang.set(profile['options'].get('report_lang') or REPORT_LANG_ORIGINAL)
        self._sync_nwp()

    def _on_toggle(self):
        self._sync_nwp()
        self.status.configure(text='', text_color=LABEL2)

    def _sync_nwp(self):
        home_on = bool(self._vars['home'].get())
        if not home_on:
            self._vars['nwp'].set(False)
        nwp = self._checks.get('nwp')
        if nwp is not None:
            nwp.set_locked(not home_on)

    def _selection(self):
        data = {key: bool(var.get()) for key, var in self._vars.items()}
        data['core'] = True
        if not data.get('home'):
            data['nwp'] = False
        data['radar'] = bool(data.get('map'))
        data['satellite'] = bool(data.get('map'))
        return data

    def _save(self):
        message = save_profile(self._selection(), {'report_lang': self._lang.get()})
        if message:
            self.status.configure(text=message, text_color=RED)
            return
        self.status.configure(text='已保存。请重新启动主程序后生效。', text_color=GREEN)


def main():
    app = ModuleConfigApp()
    app.mainloop()


if __name__ == '__main__':
    main()
