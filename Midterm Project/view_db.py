import sqlite3

DB_PATH = "wardrobe.db"

def view_items():
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM items").fetchall()

        for r in rows:
            print(dict(r))

if __name__ == "__main__":
    view_items()