import sqlite3
from pathlib import Path

db_path = Path("data/discovery_history.db")
if not db_path.exists():
    print("DB not found")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT video_id, title, channel, processed FROM processed_videos ORDER BY discovered_at DESC LIMIT 10"
    )
    rows = cursor.fetchall()
    print("VIDEO_ID | TITLE | CHANNEL | PROCESSED")
    for row in rows:
        print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]}")
    conn.close()
