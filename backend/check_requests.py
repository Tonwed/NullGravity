import sqlite3, json
from pathlib import Path

db = Path.home() / ".nullgravity" / "nullgravity.db"
conn = sqlite3.connect(str(db))
c = conn.cursor()

# Find ALL recent logs to see what paths were accessed
rows = c.execute("""
    SELECT method, path, status_code, error_detail, account_id
    FROM request_logs 
    ORDER BY timestamp DESC
    LIMIT 30
""").fetchall()

print("=== Recent 30 requests ===")
for method, path, status, error, acct in rows:
    path_short = path[:100] if path else "?"
    err_short = error[:60] if error else ""
    print(f"  [{status}] {method} {path_short} {err_short}")

conn.close()
