import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "streamshield.db"
if not db.exists():
    print("NO_DB")
else:
    c = sqlite3.connect(db)
    tables = [
        r[0]
        for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for t in tables:
        n = c.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"{t}: {n}")
