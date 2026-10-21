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
load_modules = _profile.load_modules
save_modules = _profile.save_modules

BG = '#1c1c1e'
BG2 = '#2c2c2e'
BG3 = '#3a3a3c'
BLUE = '#0a84ff'
GREEN = '#30d158'
RED = '#ff453a'
LABEL = '#ffffff'
LABEL2 = '#ebebf5'
SEP = '#38383a'

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('dark-blue')


class ModuleConfigApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('FMSA 模块配置')
        self.geometry('860x760')
        self.minsize(720, 640)
        self.configure(fg_color=BG)
        self._vars = {}
        self._nwp_switch = None
        self._build()
        self._load()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.pack(fill='x', padx=24, pady=(20, 8))
        ctk.CTkLabel(
            header, text='模块配置', font=ctk.CTkFont(size=22, weight='bold'),
            text_color=LABEL, anchor='w',
        ).pack(fill='x')
        ctk.CTkLabel(
            header,
            text='勾选后主程序下次启动生效。核心数据组固定启用。至少再勾选 1 个模块。',
            font=ctk.CTkFont(size=13), text_color=LABEL2, anchor='w', wraplength=800,
        ).pack(fill='x', pady=(4, 0))
        ctk.CTkLabel(
            header, text=str(PROFILE_PATH), font=ctk.CTkFont(size=12),
            text_color='#8e8e93', anchor='w',
        ).pack(fill='x', pady=(2, 0))

        scroll = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        scroll.pack(fill='both', expand=True, padx=16, pady=8)

        for meta in MODULE_META:
            card = ctk.CTkFrame(scroll, fg_color=BG2, corner_radius=12)
            card.pack(fill='x', padx=8, pady=6)
            top = ctk.CTkFrame(card, fg_color='transparent')
            top.pack(fill='x', padx=16, pady=(12, 4))
            var = ctk.BooleanVar(value=True)
            self._vars[meta['key']] = var
            switch = ctk.CTkSwitch(
                top, text=meta['name'], variable=var,
                font=ctk.CTkFont(size=16, weight='bold'),
                text_color=LABEL, progress_color=BLUE,
                command=self._on_toggle,
            )
            switch.pack(side='left')
            if meta.get('locked'):
                switch.configure(state='disabled')
                var.set(True)
            if meta['key'] == 'nwp':
                self._nwp_switch = switch
            ctk.CTkLabel(
                card, text='数据  ' + meta['data'], font=ctk.CTkFont(size=13),
                text_color=LABEL2, anchor='w', justify='left', wraplength=760,
            ).pack(fill='x', padx=16, pady=(0, 2))
            ctk.CTkLabel(
                card, text='写入  ' + meta['writes'], font=ctk.CTkFont(size=13),
                text_color=LABEL2, anchor='w', justify='left', wraplength=760,
            ).pack(fill='x', padx=16, pady=(0, 12))

        bar = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        bar.pack(fill='x', padx=24, pady=(0, 18))
        self.status = ctk.CTkLabel(
            bar, text='', font=ctk.CTkFont(size=13), text_color=LABEL2, anchor='w',
        )
        self.status.pack(side='left', fill='x', expand=True)
        ctk.CTkButton(
            bar, text='保存', width=120, height=36, corner_radius=8,
            fg_color=GREEN, hover_color='#27a846', text_color='#ffffff',
            font=ctk.CTkFont(size=14, weight='bold'), command=self._save,
        ).pack(side='right')

    def _load(self):
        modules = load_modules()
        for key, var in self._vars.items():
            var.set(bool(modules.get(key, True)))
        self._vars['core'].set(True)
        self._sync_nwp()

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
        message = save_modules(self._selection())
        if message:
            self.status.configure(text=message, text_color=RED)
            return
        self.status.configure(text='已保存。请重新启动主程序后生效。', text_color=GREEN)


def main():
    app = ModuleConfigApp()
    app.mainloop()


if __name__ == '__main__':
    main()
