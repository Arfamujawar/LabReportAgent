import sqlite3
from pathlib import Path

db_path = Path("instance/labreport.db")
if not db_path.exists():
    raise SystemExit(f"Database not found: {db_path.resolve()}")

connection = sqlite3.connect(db_path)
try:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(report)")
    }

    if not columns:
        raise RuntimeError("The report table was not found. No changes made.")

    additions = {
        "review_status": "VARCHAR(24) NOT NULL DEFAULT 'Pending Review'",
        "review_notes": "TEXT NOT NULL DEFAULT ''",
        "reviewed_at": "DATETIME",
    }

    for name, definition in additions.items():
        if name not in columns:
            connection.execute(
                f"ALTER TABLE report ADD COLUMN {name} {definition}"
            )
            print(f"Added: {name}")
        else:
            print(f"Already exists: {name}")

    connection.commit()
    print("Database update completed.")
finally:
    connection.close()
