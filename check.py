import ast
from pathlib import Path

bad = []
for p in Path("app").rglob("*.py"):
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except Exception as e:
        bad.append((str(p), str(e)))

if bad:
    for x in bad:
        print("ERROR:", x)
    raise SystemExit(1)
print("Python syntax check: OK")
