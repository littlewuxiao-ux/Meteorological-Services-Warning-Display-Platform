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

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('dark-blue')

COLS = (
    ('模块', 168),
    ('数据', 280),
    ('程序写入', 170),
    ('人写入', 170),
    ('配置', 220),
)


class ModuleConfigApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('FMSA 模块配置')
        self.geometry('1180x820')
        self.minsize(980, 680)
        self.configure(fg_color=BG)
        self._vars = {}
        self._nwp_switch = None
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
            text='勾选后主程序下次启动生效。核心数据组固定启用。至少再勾选 1 个模块。',
            font=ctk.CTkFont(size=13), text_color=LABEL2, anchor='w', wraplength=1100,
        ).pack(fill='x', pady=(4, 0))
        ctk.CTkLabel(
            header, text=str(PROFILE_PATH), font=ctk.CTkFont(size=12),
            text_color=MUTED, anchor='w',
        ).pack(fill='x', pady=(2, 0))

        lang = ctk.CTkFrame(self, fg_color=BG2, corner_radius=10)
        lang.pack(fill='x', padx=22, pady=(10, 6))
        ctk.CTkLabel(
            lang, text='机场详情 / 搜索结果',
            font=ctk.CTkFont(size=15, weight='bold'), text_color=LABEL, anchor='w',
        ).pack(fill='x', padx=16, pady=(12, 4))

        choices = ctk.CTkFrame(lang, fg_color='transparent')
        choices.pack(fill='x', padx=12, pady=(0, 12))
        self._lang_original = self._lang_card(
            choices, REPORT_LANG_ORIGINAL, '原文优先',
            '只有翻译视图下，详情和搜索才显示中文；其余视图显示原文。',
        )
        self._lang_original.pack(side='left', fill='both', expand=True, padx=4)
        self._lang_chinese = self._lang_card(
            choices, REPORT_LANG_CHINESE, '中文优先',
            '只有主页视图下，详情和搜索才显示原文；其余视图显示中文。',
        )
        self._lang_chinese.pack(side='left', fill='both', expand=True, padx=4)
        self._lang.trace_add('write', lambda *_: self._paint_lang())

        table_wrap = ctk.CTkFrame(self, fg_color=BG2, corner_radius=10)
        table_wrap.pack(fill='both', expand=True, padx=22, pady=6)

        head = ctk.CTkFrame(table_wrap, fg_color=HEADER, corner_radius=0)
        head.pack(fill='x')
        for i, (title, width) in enumerate(COLS):
            ctk.CTkLabel(
                head, text=title, width=width, anchor='w',
                font=ctk.CTkFont(size=13, weight='bold'), text_color=LABEL2,
            ).grid(row=0, column=i, sticky='nsew', padx=(16 if i == 0 else 8, 8), pady=10)
            head.grid_columnconfigure(i, weight=1 if i else 0)

        scroll = ctk.CTkScrollableFrame(table_wrap, fg_color=BG2, corner_radius=0)
        scroll.pack(fill='both', expand=True)

        for row_i, meta in enumerate(MODULE_META):
            bg = ROW_ALT if row_i % 2 else BG2
            row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=0)
            row.pack(fill='x')
            var = ctk.BooleanVar(value=True)
            self._vars[meta['key']] = var
            name = meta['name']
            if meta.get('parent') == 'home':
                name = '└  ' + name
            switch = ctk.CTkSwitch(
                row, text=name, variable=var, width=COLS[0][1],
                font=ctk.CTkFont(size=14, weight='bold'),
                text_color=LABEL, progress_color=BLUE,
                command=self._on_toggle,
            )
            switch.grid(row=0, column=0, sticky='nw', padx=(16, 8), pady=10)
            if meta.get('locked'):
                switch.configure(state='disabled')
                var.set(True)
            if meta['key'] == 'nwp':
                self._nwp_switch = switch
            texts = (meta['data'], meta['program'], meta['human'], meta['config'])
            for i, text in enumerate(texts, start=1):
                ctk.CTkLabel(
                    row, text=text, width=COLS[i][1],
                    font=ctk.CTkFont(size=13), text_color=LABEL2,
                    anchor='nw', justify='left', wraplength=COLS[i][1] - 8,
                ).grid(row=0, column=i, sticky='nsew', padx=8, pady=10)
                row.grid_columnconfigure(i, weight=1)
            row.grid_columnconfigure(0, weight=0)

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

    def _lang_card(self, parent, value, title, desc):
        card = ctk.CTkFrame(
            parent, fg_color=BG3, corner_radius=8, cursor='hand2',
            border_width=2, border_color=LINE,
        )
        radio = ctk.CTkRadioButton(
            card, text=title, variable=self._lang, value=value,
            font=ctk.CTkFont(size=15, weight='bold'), text_color=LABEL,
            fg_color=BLUE, hover_color=BLUE, command=self._paint_lang,
        )
        radio.pack(anchor='w', padx=14, pady=(12, 4))
        ctk.CTkLabel(
            card, text=desc, font=ctk.CTkFont(size=13), text_color=LABEL2,
            anchor='w', justify='left', wraplength=480,
        ).pack(fill='x', padx=14, pady=(0, 12))
        card.bind('<Button-1>', lambda _e, v=value: self._lang.set(v))
        return card

    def _paint_lang(self):
        current = self._lang.get()
        for card, value in (
            (self._lang_original, REPORT_LANG_ORIGINAL),
            (self._lang_chinese, REPORT_LANG_CHINESE),
        ):
            on = current == value
            card.configure(
                fg_color='#1a2740' if on else BG3,
                border_color=BLUE if on else LINE,
            )
        self.status.configure(text='', text_color=LABEL2)

    def _load(self):
        profile = load_profile()
        modules = profile['modules']
        for key, var in self._vars.items():
            var.set(bool(modules.get(key, True)))
        self._vars['core'].set(True)
        self._lang.set(profile['options'].get('report_lang') or REPORT_LANG_ORIGINAL)
        self._sync_nwp()
        self._paint_lang()

    def _on_toggle(self):
        self._sync_nwp()
        self.status.configure(text='', text_color=LABEL2)

    def _sync_nwp(self):
        home_on = bool(self._vars['home'].get())
        if not home_on:
            self._vars['nwp'].set(False)
        if self._nwp_switch is not None:
            self._nwp_switch.configure(state='normal' if home_on else 'disabled')

    def _selection(self):
        data = {key: bool(var.get()) for key, var in self._vars.items()}
        data['core'] = True
        if not data.get('home'):
            data['nwp'] = False
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
