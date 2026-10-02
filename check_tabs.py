import database
k = database.get_kanban_data()
print("Kanban columns:", list(k.keys()))
for col, items in k.items():
    print(f"Col {col}: {len(items)} items")

import sqlite3
conn = sqlite3.connect('/app/reciclagem.db')
c = conn.cursor()
c.execute("SELECT DISTINCT etapa_kanban, count(*) FROM motoristas GROUP BY etapa_kanban")
print("Distinct etapa_kanban in DB:", c.fetchall())
