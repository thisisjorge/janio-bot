import sqlite3
import os

db_path = '/app/data/janio.sqlite3'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
else:
    db = sqlite3.connect(db_path)
    try:
        res = db.execute('SELECT * FROM lastfm_sessions').fetchall()
        print(f"LastFM Sessions: {res}")
    except Exception as e:
        print(f"Error querying DB: {e}")
