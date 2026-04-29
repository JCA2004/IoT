import sqlite3

DB_FILE = "wardrobe.db"

conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

# Remove all items
cur.execute("DELETE FROM items")

# Reset the auto-increment counter
cur.execute("DELETE FROM sqlite_sequence WHERE name='items'")

conn.commit()
conn.close()

print("Wardrobe database cleared.")