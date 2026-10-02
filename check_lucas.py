
import sqlite3
conn = sqlite3.connect('/app/reciclagem.db')
cur = conn.cursor()
cur.execute('SELECT DISTINCT gestor FROM motoristas WHERE gestor LIKE "%LUCAS%"')
print("Gestores:", cur.fetchall())
cur.execute('SELECT codigo, nome, etapa_kanban, status_monitoramento FROM motoristas WHERE nome LIKE "%LUCAS%"')
print("Motoristas Lucas:", cur.fetchall())
