import sqlite3
import os
from pathlib import Path

# Path to DB
data_dir = Path(os.environ.get("NULLGRAVITY_DATA_DIR", Path.home() / ".nullgravity"))
db_path = data_dir / "nullgravity.db"

print(f"Checking database at: {db_path}")

if not db_path.exists():
    print("Database file not found.")
    exit(0)

try:
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(accounts)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns: {columns}")

    # Add new columns if missing
    new_columns = {
        "tier": "VARCHAR(50)",
        "status_reason": "VARCHAR(255)",
        "ineligible_tiers": "JSON",
        "quota_buckets": "JSON"
    }

    for col, dtype in new_columns.items():
        if col not in columns:
            print(f"Adding column '{col}'...")
            try:
                cursor.execute(f"ALTER TABLE accounts ADD COLUMN {col} {dtype}")
                print(f"Successfully added {col}")
            except Exception as e:
                print(f"Error adding {col}: {e}")

    connection.commit()
    connection.close()
    print("Migration complete.")
except Exception as e:
    print(f"Overall migration failed: {e}")
