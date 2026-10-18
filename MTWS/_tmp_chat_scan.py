import json
import sqlite3

c = sqlite3.connect(r"C:\Users\monly\AppData\Roaming\Cursor\User\globalStorage\state.vscdb")
cur = c.cursor()
row = cur.execute(
    "SELECT value FROM composerHeaders WHERE composerId=?",
    ("bfc3a263-4e47-4f9b-b2ca-4e54110d3c91",),
).fetchone()
data = json.loads(row[0])
name = data.get("name") or ""
open(r"D:\Projects\MTWS-OMICS\MTWS\_tmp_name.txt", "w", encoding="utf-8").write(name)
print("name_len", len(name))
print(name[:2000])
print("--- keys ---")
print(list(data.keys()))
