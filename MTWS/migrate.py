"""选择迁移文件后执行。按文件里的模型判断写入配置库、生产库，或两边都写。"""

import importlib
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

os.environ["MTWS_SKIP_SCHEDULER"] = "1"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mtws_system.settings")

SCRIPT_DIR = Path(__file__).resolve().parent
DJANGO_DIR = SCRIPT_DIR / "mtws_django"
MANAGE_PY = DJANGO_DIR / "manage.py"
MIGRATIONS_ROOT = DJANGO_DIR / "mtws_migrations"
APPS = ("core", "parsers")
FILE_RE = re.compile(r"^(\d{4})_.+\.py$")
DB_CONFIG = "default"
DB_RUNTIME = "runtime"

sys.path.insert(0, str(DJANGO_DIR))


def list_migration_files():
    found = []
    for app in APPS:
        folder = MIGRATIONS_ROOT / app
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if FILE_RE.match(path.name):
                found.append((app, path.stem, path))
    found.sort(key=lambda item: (item[1], item[0]))
    return found


def label_of(app, name):
    return f"{app}:{name}"


def parse_label(text):
    app, _, name = text.partition(":")
    return app, name


def migration_number(name):
    match = FILE_RE.match(f"{name}.py")
    return int(match.group(1)) if match else -1


def database_title(alias):
    return "配置库" if alias == DB_CONFIG else "生产库"


def parse_showmigrations(text):
    applied = {}
    pending = {}
    app = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if not raw.startswith(" "):
            app = raw.strip()
            applied.setdefault(app, set())
            pending.setdefault(app, set())
            continue
        if app is None:
            continue
        stripped = raw.strip()
        if stripped.startswith("[X]"):
            applied[app].add(stripped[3:].strip())
        elif stripped.startswith("[ ]"):
            pending[app].add(stripped[3:].strip())
    return applied, pending


def _model_names(operation):
    names = []
    model_name = getattr(operation, "model_name", None)
    if model_name:
        names.append(str(model_name).lower())
    for nested in getattr(operation, "operations", None) or []:
        names.extend(_model_names(nested))
    return names


def databases_for_migration(app, name):
    """读迁移操作里的模型，对照分库名单。没有模型名时，parsers 归生产库，core 两边都执行。"""
    from mtws_system.db_router import database_for

    module = importlib.import_module(f"mtws_migrations.{app}.{name}")
    names = []
    for operation in module.Migration.operations:
        names.extend(_model_names(operation))
    if not names:
        return [DB_RUNTIME] if app == "parsers" else [DB_CONFIG, DB_RUNTIME]
    targets = []
    for model_name in names:
        target = database_for(app, model_name)
        if target and target not in targets:
            targets.append(target)
    return targets or ([DB_RUNTIME] if app == "parsers" else [DB_CONFIG])


class MigrateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("数据库迁移")
        self.geometry("640x420")
        self.minsize(520, 340)
        self.files = []
        self.status_by_db = {}
        self._target_cache = {}
        self._busy = False
        self.selected = tk.StringVar()
        self.status = tk.StringVar(value="准备就绪")
        self._build()
        self.refresh()

    def _build(self):
        pad = {"padx": 10, "pady": 6}
        tk.Label(
            self,
            text="迁移文件在 mtws_migrations 的 core、parsers 子目录。执行前按模型判断写入哪个库。",
            anchor="w",
            justify="left",
        ).pack(fill="x", **pad)

        row = tk.Frame(self)
        row.pack(fill="x", **pad)
        tk.Label(row, text="目标迁移").pack(side="left")
        self.combo = ttk.Combobox(row, textvariable=self.selected, state="readonly")
        self.combo.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="刷新", command=self.refresh).pack(side="left")

        btn_row = tk.Frame(self)
        btn_row.pack(fill="x", **pad)
        self.ok_btn = ttk.Button(btn_row, text="确认执行", command=self.confirm)
        self.ok_btn.pack(side="left")
        ttk.Button(btn_row, text="关闭", command=self.destroy).pack(side="left", padx=8)
        tk.Label(btn_row, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True)

        self.log = tk.Text(self, height=16, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def append_log(self, text):
        def _write():
            self.log.insert("end", text)
            self.log.see("end")

        if threading.current_thread() is threading.main_thread():
            _write()
        else:
            self.after(0, _write)

    def refresh(self):
        self.files = list_migration_files()
        self._target_cache = {}
        labels = [label_of(app, name) for app, name, _path in self.files]
        self.combo["values"] = labels
        if not labels:
            self.selected.set("")
            self.status.set("未找到迁移文件")
            self.log.delete("1.0", "end")
            self.append_log(f"目录不存在或为空：{MIGRATIONS_ROOT}\n")
            return
        newest = max(self.files, key=lambda item: (migration_number(item[1]), item[2].stat().st_mtime))
        self.selected.set(label_of(newest[0], newest[1]))
        self.status.set(f"已选最新：{self.selected.get()}")
        self._load_django_status()

    def _load_django_status(self, replace=True):
        if not MANAGE_PY.is_file():
            self.append_log(f"未找到 {MANAGE_PY}\n")
            return
        self.status_by_db = {}
        lines = []
        for alias in (DB_CONFIG, DB_RUNTIME):
            code, out = self._run_manage(["showmigrations", "--database", alias])
            if code != 0:
                lines.append(f"{database_title(alias)} 状态读取失败：")
                lines.append(out)
                continue
            applied, pending = parse_showmigrations(out)
            self.status_by_db[alias] = (applied, pending)
            lines.append(f"{database_title(alias)}：")
            for app, name, _path in self.files:
                mark = self._mark(alias, app, name, applied, pending)
                suffix = "  ← 默认" if label_of(app, name) == self.selected.get() else ""
                lines.append(f"  {mark}  {label_of(app, name)}{suffix}")
        if replace:
            self.log.delete("1.0", "end")
        self.append_log("\n".join(lines) + "\n")

    def _mark(self, alias, app, name, applied, pending):
        if alias not in self._targets_cached(app, name):
            return "[其他库]"
        if name in applied.get(app, ()):
            return "[已应用]"
        if name in pending.get(app, ()):
            return "[待应用]"
        return "[未知]"

    def _targets_cached(self, app, name):
        key = (app, name)
        if key not in self._target_cache:
            try:
                self._target_cache[key] = databases_for_migration(app, name)
            except Exception as exc:
                self._target_cache[key] = []
                self.append_log(f"无法判断 {label_of(app, name)} 的目标库：{exc}\n")
        return self._target_cache[key]

    def confirm(self):
        if self._busy:
            return
        app, name = parse_label(self.selected.get().strip())
        if not app or not name:
            messagebox.showwarning("提示", "请选择迁移文件。")
            return
        if (app, name) not in {(item[0], item[1]) for item in self.files}:
            messagebox.showwarning("提示", "所选文件不在迁移目录中。")
            return
        targets = self._targets_cached(app, name)
        if not targets:
            messagebox.showerror("无法执行", "没有判断出这个迁移要写入哪个库。")
            return
        target_num = migration_number(name)
        rollback = False
        for alias in targets:
            applied = self.status_by_db.get(alias, ({}, {}))[0].get(app, set())
            current_max = max((migration_number(item) for item in applied), default=-1)
            if current_max >= 0 and target_num < current_max:
                rollback = True
        where = "、".join(database_title(alias) for alias in targets)
        if rollback:
            prompt = f"{label_of(app, name)} 将作用于{where}。\n编号低于该库已应用的迁移，可能改表或丢数据。确定继续？"
            title = "将回退迁移"
        else:
            prompt = f"{label_of(app, name)}\n写入：{where}"
            title = "确认执行"
        if not messagebox.askyesno(title, prompt):
            return
        self._busy = True
        self.ok_btn.state(["disabled"])
        self.status.set("正在迁移…")
        threading.Thread(target=self._migrate, args=(app, name, targets), daemon=True).start()

    def _migrate(self, app, name, targets):
        code = 0
        for alias in targets:
            self.append_log(f"\n>>> migrate {app} {name} --database {alias}\n")
            code, out = self._run_manage(["migrate", app, name, "--database", alias])
            self.append_log(out if out.endswith("\n") else out + "\n")
            if code != 0:
                break

        def done():
            self._busy = False
            self.ok_btn.state(["!disabled"])
            self.status.set("完成" if code == 0 else f"失败（退出码 {code}）")
            if code == 0:
                messagebox.showinfo("完成", "迁移已执行。")
            else:
                messagebox.showerror("失败", "迁移未成功，请看下方日志。")
            self._target_cache = {}
            self._load_django_status(replace=False)

        self.after(0, done)

    def _run_manage(self, args):
        cmd = [sys.executable, str(MANAGE_PY), *args]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(DJANGO_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            return 1, str(exc)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


if __name__ == "__main__":
    import django

    django.setup()
    MigrateApp().mainloop()
