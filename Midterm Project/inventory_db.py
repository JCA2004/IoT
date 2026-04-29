import sqlite3
from pathlib import Path

DB_PATH = "wardrobe.db"

def item_exists(image_path: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM items WHERE image_path = ? LIMIT 1", (image_path,))
    row = c.fetchone()
    conn.close()
    return row is not None

def init_db(db_path: str = DB_PATH):
    Path(db_path).touch(exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            category TEXT NOT NULL,         -- top, outerwear, bottoms, shoes, accessory
            color TEXT,
            warmth INTEGER DEFAULT 3,       -- 1(light) ... 5(very warm)
            waterproof INTEGER DEFAULT 0,
            formality INTEGER DEFAULT 2,    -- 1(casual) ... 5(formal)
            image_path TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS wear_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            temp_c REAL,
            humidity REAL,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(item_id) REFERENCES items(id)
        )
        """)

def add_item(label, category, image_path, color=None, warmth=3, waterproof=0, formality=2, db_path: str = DB_PATH) -> int:
    with sqlite3.connect(db_path) as con:
        cur = con.execute("""
            INSERT INTO items(label, category, color, warmth, waterproof, formality, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (label, category, color, int(warmth), int(waterproof), int(formality), image_path))
        return int(cur.lastrowid)

def list_items(db_path: str = DB_PATH):
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

if __name__ == "__main__":
    init_db()
    print("DB ready. Items:", len(list_items()))