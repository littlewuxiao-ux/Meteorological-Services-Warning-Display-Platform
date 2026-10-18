# Django数据库操作注意事项

## 核心原则
**直接使用Python脚本操作SQLite，避免Django迁移的复杂性。**

## 常见问题快速解决

### 1. 路径问题
**使用PowerShell Core (pwsh)代替传统PowerShell**
```bash
# 设置Cursor默认终端为pwsh
# 设置 → 搜索"terminal integrated shell" → 设置为 pwsh.exe
```

### 2. 编码问题
**脚本中避免使用emoji和特殊字符**
```python
# ❌ 错误：print("✅ 成功")
# ✅ 正确：print("SUCCESS: 操作成功")
```

### 3. 路径处理
**脚本内部使用绝对路径，不依赖工作目录**
```python
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, "data", "sqlite_database", "fmsa_database.db")
```

## 数据库操作模板

```python
import sqlite3
import os

# 获取数据库路径（不依赖工作目录）
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, "data", "sqlite_database", "fmsa_database.db")

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 执行SQL操作
cursor.execute("CREATE TABLE IF NOT EXISTS table_name (...)")
conn.commit()
conn.close()

print("操作完成")
```

## 终端设置
**推荐设置Cursor默认终端为PowerShell Core (pwsh)**
1. Ctrl+, 打开设置
2. 搜索 "terminal integrated shell"  
3. 设置为 `pwsh.exe`
