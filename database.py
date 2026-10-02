import sqlite3
import os
import pandas as pd
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'reciclagem.db')
EXCEL_PATH = os.path.join(os.path.dirname(__file__), 'Controle_de_Reciclagens_Excesso_de_Velocidade.xlsx')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS motoristas (
        codigo TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        operacao TEXT NOT NULL,
        gestor TEXT NOT NULL,
        faixa_risco TEXT DEFAULT 'VERDE',
        nivel_tratamento INTEGER DEFAULT 0,
        total_reciclagens_12m INTEGER DEFAULT 0,
        total_reincidencias_12m INTEGER DEFAULT 0,
        status_monitoramento TEXT DEFAULT 'Aderente',
        etapa_kanban TEXT DEFAULT 'NAO_INICIADO',
        faixa_risco_override INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    try:
        cursor.execute("ALTER TABLE motoristas ADD COLUMN etapa_kanban TEXT DEFAULT 'NAO_INICIADO'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE motoristas ADD COLUMN faixa_risco_override INTEGER DEFAULT 0")
    except Exception:
        pass

    # ── Fluxo completo de reciclagem: responsável, resultado e motivo de
    #    não realização/recusa (migration leve, preserva dados existentes)
    for _col_def in (
        "ALTER TABLE reciclagens ADD COLUMN responsavel TEXT DEFAULT ''",
        "ALTER TABLE reciclagens ADD COLUMN resultado TEXT DEFAULT ''",
        "ALTER TABLE reciclagens ADD COLUMN motivo_recusa TEXT DEFAULT ''",
    ):
        try:
            cursor.execute(_col_def)
        except Exception:
            pass

    # ── Configurações do sistema (regras de negócio isoladas/configuráveis)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS config_sistema (
        chave TEXT PRIMARY KEY,
        valor TEXT,
        descricao TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reciclagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        motorista_codigo TEXT NOT NULL,
        ano INTEGER NOT NULL,
        mes INTEGER NOT NULL,
        acao_corretiva TEXT DEFAULT 'RECICLAGEM',
        operacao TEXT NOT NULL,
        gestor TEXT NOT NULL,
        data_envio TEXT,
        prazo_realizacao TEXT,
        data_realizacao TEXT,
        status TEXT DEFAULT 'PENDENTE',
        instrutor TEXT DEFAULT '',
        observacao TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (motorista_codigo) REFERENCES motoristas (codigo)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pdis_comites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        motorista_codigo TEXT NOT NULL,
        nivel INTEGER NOT NULL,
        tipo_acao TEXT NOT NULL,
        descricao TEXT,
        data_inicio TEXT,
        prazo TEXT,
        status TEXT DEFAULT 'EM ANDAMENTO',
        responsavel TEXT,
        resultado TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (motorista_codigo) REFERENCES motoristas (codigo)
    )
    ''')

    conn.commit()
    conn.close()
    print_startup_banner()

def print_startup_banner():
    banner = r"""
========================================================================================
  ______  __  __ _____   _____  ______ _____ _____  ____  
 |  ____| \ \/ /|  __ \ |  __ \|  ____/ ____/ ____|/ __ \ 
 | |__     \  / | |__) || |__) | |__ | (___| (___ | |  | |
 |  __|     > < |  ___/ |  _  /|  __| \___ \\___ \| |  | |
 | |____   / . \| |     | | \ \| |________) |___) | |__| |
 |______| /_/\_\|_|     |_|  \_\______|_____/_____/ \____/ 

  _   _  ______ _____   ____  __  __ _   _  ____ _____ _   _  ____  
 | \ | ||  ____|  __ \ / __ \|  \/  | | | / ___|  ___| \ | |/ __ \ 
 |  \| || |__  | |__) | |  | | \  / | | | | |   | |__ |  \| | |  | |
 | . ' ||  __| |  ___/| |  | | |\/| | | | | |   |  __|| . ' | |  | |
 | |\  || |____| |    | |__| | |  | | |_| | |___| |___| |\  | |__| |
 |_| \_||______|_|     \____/|_|  |_|\___/ \____|_____|_| \_|\____/ 

       ______________________                _____________________
      |                      |              |  EXPRESSO           |
      |  [PGCSC] TELEMETRIA  |=============='  NEPOMUCENO         |
      |______________________|______________|_____________________|
      (O)------------------(O)              (O)-----------------(O)

             [===]  BANCO DE DADOS E SERVIDOR WEB INICIADOS  [===]
========================================================================================
"""
    print(banner)

def process_excel_dataframe(df):
    conn = get_db_connection()
    cursor = conn.cursor()

    novos_registros   = 0
    ignorados         = 0   # já existiam — ignorados para não sobrescrever edições manuais
    motoristas_processados = set()

    for _, row in df.iterrows():
        raw_driver = str(row['MOTORISTA']).strip() if pd.notna(row.get('MOTORISTA')) else ''
        if not raw_driver or raw_driver.lower() == 'nan':
            continue

        if ' - ' in raw_driver:
            parts = raw_driver.split(' - ', 1)
            codigo = parts[0].strip()
            nome   = parts[1].strip()
        else:
            codigo = raw_driver
            nome   = raw_driver

        motoristas_processados.add(codigo)

        operacao     = str(row['OPERAÇÃO']).strip()         if pd.notna(row.get('OPERAÇÃO'))         else 'NÃO INFORMADA'
        gestor       = str(row['GESTOR']).strip()           if pd.notna(row.get('GESTOR'))           else 'NÃO INFORMADO'
        ano          = int(row['ANO'])                      if pd.notna(row.get('ANO'))              else 2026
        mes          = int(row['MÊS'])                      if pd.notna(row.get('MÊS'))              else 1
        acao         = str(row['AÇÃO CORRETIVA']).strip()   if pd.notna(row.get('AÇÃO CORRETIVA'))   else 'RECICLAGEM'

        # ── Filtro interno: Desconsiderar linhas onde a ação corretiva for "Mensagem educativa" para evitar duplicatas
        if 'mensagem educativa' in acao.lower():
            ignorados += 1
            continue

        data_envio = ''
        if pd.notna(row.get('DATA DE ENVIO')):
            try:
                data_envio = pd.to_datetime(row['DATA DE ENVIO']).strftime('%Y-%m-%d')
            except Exception:
                data_envio = str(row['DATA DE ENVIO'])

        status_planilha = str(row['STATUS']).strip() if pd.notna(row.get('STATUS')) else ''
        if not status_planilha or status_planilha.lower() == 'nan':
            status_planilha = 'AGENDADO' if mes < 4 else 'PENDENTE'

        # ── Garante motorista na base (sem sobrescrever dados editados manualmente)
        cursor.execute('''
            INSERT OR IGNORE INTO motoristas (codigo, nome, operacao, gestor)
            VALUES (?, ?, ?, ?)
        ''', (codigo, nome, operacao, gestor))

        # ── Verifica se a reciclagem deste mês/ano já existe para este motorista
        cursor.execute('''
            SELECT id FROM reciclagens WHERE motorista_codigo = ? AND ano = ? AND mes = ?
        ''', (codigo, ano, mes))
        existente = cursor.fetchone()

        if existente:
            # Registro já existe → IGNORAR, não sobrescrever edições manuais
            ignorados += 1
        else:
            # Registro novo → inserir normalmente
            cursor.execute('''
                INSERT INTO reciclagens (motorista_codigo, ano, mes, acao_corretiva, operacao, gestor, data_envio, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (codigo, ano, mes, acao, operacao, gestor, data_envio, status_planilha))
            novos_registros += 1

    conn.commit()
    conn.close()

    recalculate_driver_metrics()

    return {
        "total_linhas":         len(df),
        "novos_registros":      novos_registros,
        "ignorados":            ignorados,
        "motoristas_afetados":  len(motoristas_processados)
    }

def seed_db_from_excel():
    if not os.path.exists(EXCEL_PATH):
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM reciclagens")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    conn.close()
    print("Populating database from Excel...")
    df = pd.read_excel(EXCEL_PATH, sheet_name='BASE')
    res = process_excel_dataframe(df)
    print(f"Database seeding completed! Stats: {res}")

def recalculate_driver_metrics():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT codigo, faixa_risco, faixa_risco_override, etapa_kanban FROM motoristas")
    motoristas = cursor.fetchall()

    for m in motoristas:
        cod = m['codigo']
        cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE motorista_codigo = ?", (cod,))
        total_rec = cursor.fetchone()[0]

        total_reinc = max(0, total_rec - 1)

        override = m['faixa_risco_override'] if 'faixa_risco_override' in m.keys() else 0
        faixa = m['faixa_risco'] if override else 'VERDE'

        if not override:
            if total_rec == 0:
                faixa = 'VERDE'
                nivel = 0
                status_mon = 'Aderente'
            elif total_rec == 1:
                faixa = 'AMARELA'
                nivel = 1
                status_mon = 'Observação Preventiva'
            elif total_rec in (2, 3):
                faixa = 'LARANJA'
                nivel = 2 if total_rec == 2 else 3
                status_mon = 'Acompanhamento Intensificado'
            else: # total_rec > 3 (Excel: >3 ocorrências = Crítico/Vermelha)
                faixa = 'VERMELHA'
                nivel = 4
                status_mon = 'Crítico - Intervenção'
        else:
            if faixa == 'VERMELHA':
                nivel = 4
                status_mon = 'Crítico - Intervenção'
            elif faixa == 'LARANJA':
                nivel = 3
                status_mon = 'Acompanhamento Intensificado'
            elif faixa == 'AMARELA':
                nivel = 1
                status_mon = 'Observação Preventiva'
            else:
                nivel = 0
                status_mon = 'Aderente'

        # Determina etapa_kanban e pendências
        cursor.execute("SELECT status FROM reciclagens WHERE motorista_codigo = ? ORDER BY id DESC LIMIT 1", (cod,))
        last_rec = cursor.fetchone()
        last_status = last_rec['status'] if last_rec else 'PENDENTE'

        cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE motorista_codigo = ? AND status IN ('PENDENTE', 'AGENDADO', 'MENSAGEM ENVIADA')", (cod,))
        pendentes_cnt = cursor.fetchone()[0]

        etapa = m['etapa_kanban'] if ('etapa_kanban' in m.keys() and m['etapa_kanban']) else ''

        # Se todas as reciclagens foram concluídas e o último status é CONCLUÍDO
        if total_rec > 0 and pendentes_cnt == 0 and last_status == 'CONCLUÍDO':
            etapa = 'APROVADO'
            status_mon = 'Concluído / Aprovado'
        elif etapa == 'APROVADO' and pendentes_cnt == 0:
            status_mon = 'Concluído / Aprovado'
        elif etapa == 'APROVADO' and pendentes_cnt > 0:
            etapa = 'AGUARDANDO'
        elif not etapa or etapa in ('NAO_INICIADO', 'AGUARDANDO', 'MONITORAMENTO'):
            if last_status == 'CONCLUÍDO' and pendentes_cnt == 0:
                etapa = 'APROVADO'
                status_mon = 'Concluído / Aprovado'
            elif last_status in ('AGENDADO', 'MENSAGEM ENVIADA'):
                etapa = 'AGUARDANDO'
            elif last_status == 'VIAGEM_ASSISTIDA' or nivel in (2, 3):
                etapa = 'VIAGEM_ASSISTIDA'
            elif nivel == 4 or faixa == 'VERMELHA':
                etapa = 'AVALIACAO'
            else:
                etapa = 'NAO_INICIADO'

        cursor.execute('''
            UPDATE motoristas
            SET faixa_risco = ?,
                nivel_tratamento = ?,
                total_reciclagens_12m = ?,
                total_reincidencias_12m = ?,
                status_monitoramento = ?,
                etapa_kanban = ?
            WHERE codigo = ?
        ''', (faixa, nivel, total_rec, total_reinc, status_mon, etapa, cod))

    conn.commit()
    conn.close()

def _parse_ops(operacao):
    if not operacao:
        return []
    if isinstance(operacao, list):
        items = operacao
    else:
        items = str(operacao).split(',')
    return [str(o).strip() for o in items if str(o).strip()]

def _parse_meses(mes):
    if not mes:
        return []
    if isinstance(mes, list):
        items = mes
    else:
        items = str(mes).split(',')
    res = []
    for x in items:
        x_str = str(x).strip()
        if x_str.isdigit():
            res.append(int(x_str))
    return res

def _parse_ano(ano):
    if not ano:
        return None
    try:
        return int(str(ano).strip())
    except (ValueError, TypeError):
        return None

def get_kpis_data(operacao='', ano='', mes=''):
    conn = get_db_connection()
    cursor = conn.cursor()

    ops = _parse_ops(operacao)
    meses = _parse_meses(mes)
    ano_val = _parse_ano(ano)

    where_m = " WHERE 1=1"
    params_m = []
    where_r = " WHERE 1=1"
    params_r = []

    if ops:
        ph = ','.join(['?'] * len(ops))
        where_m += f" AND operacao IN ({ph})"
        params_m.extend(ops)
        where_r += f" AND operacao IN ({ph})"
        params_r.extend(ops)

    if ano_val:
        where_r += " AND ano = ?"
        params_r.append(ano_val)
        where_m += " AND codigo IN (SELECT DISTINCT motorista_codigo FROM reciclagens WHERE ano = ?)"
        params_m.append(ano_val)

    if meses:
        ph = ','.join(['?'] * len(meses))
        where_r += f" AND mes IN ({ph})"
        params_r.extend(meses)
        where_m += f" AND codigo IN (SELECT DISTINCT motorista_codigo FROM reciclagens WHERE mes IN ({ph}))"
        params_m.extend(meses)

    cursor.execute("SELECT COUNT(*) FROM motoristas" + where_m, params_m)
    total_motoristas = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reciclagens" + where_r, params_r)
    total_reciclagens = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM motoristas" + where_m + " AND total_reciclagens_12m > 1", params_m)
    total_reincidentes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM motoristas" + where_m + " AND faixa_risco = 'VERMELHA'", params_m)
    total_criticos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT operacao) FROM motoristas" + where_m, params_m)
    total_operacoes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM motoristas" + where_m + " AND etapa_kanban = 'APROVADO'", params_m)
    total_aprovados = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reciclagens" + where_r + " AND status = 'CONCLUÍDO'", params_r)
    concluidas = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reciclagens" + where_r + " AND status IN ('PENDENTE', 'AGENDADO', 'MENSAGEM ENVIADA')", params_r)
    pendentes = cursor.fetchone()[0]

    # Maior Operação em Reciclagens
    if len(ops) == 1:
        maior_operacao_nome = ops[0]
        maior_operacao_total = total_reciclagens
    else:
        q_top = '''
            SELECT operacao, COUNT(*) as total
            FROM reciclagens
        ''' + where_r + '''
            GROUP BY operacao
            ORDER BY total DESC
            LIMIT 1
        '''
        cursor.execute(q_top, params_r)
        top_op = cursor.fetchone()
        maior_operacao_nome = top_op[0] if top_op else '–'
        maior_operacao_total = top_op[1] if top_op else 0

    taxa_reincidencia = round((total_reincidentes / total_motoristas * 100), 1) if total_motoristas > 0 else 0
    efetividade_global = round(100 - taxa_reincidencia, 1)
    media_reciclagens = round((total_reciclagens / total_motoristas), 1) if total_motoristas > 0 else 0

    conn.close()

    return {
        "total_motoristas": total_motoristas,
        "total_reciclagens": total_reciclagens,
        "total_reincidentes": total_reincidentes,
        "total_criticos": total_criticos,
        "total_operacoes": total_operacoes,
        "total_aprovados": total_aprovados,
        "concluidas": concluidas,
        "pendentes": pendentes,
        "maior_operacao_nome": maior_operacao_nome,
        "maior_operacao_total": maior_operacao_total,
        "media_reciclagens": media_reciclagens,
        "taxa_reincidencia": taxa_reincidencia,
        "meta_reincidencia": 15.0,
        "efetividade_global": efetividade_global,
        "meta_efetividade": 85.0
    }

def get_kanban_data(operacao='', gestor='', search='', mes='', ano=''):
    conn = get_db_connection()
    cursor = conn.cursor()

    ops = _parse_ops(operacao)
    meses = _parse_meses(mes)
    ano_val = _parse_ano(ano)

    # Base query for drivers
    query = "SELECT * FROM motoristas WHERE 1=1 AND (etapa_kanban IS NULL OR etapa_kanban != 'APROVADO')"
    params = []
    if search:
        query += " AND (codigo LIKE ? OR nome LIKE ? OR gestor LIKE ? OR operacao LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    if ops:
        ph = ','.join(['?'] * len(ops))
        query += f" AND operacao IN ({ph})"
        params.extend(ops)
    if gestor:
        query += " AND gestor = ?"
        params.append(gestor)
    if meses and ano_val:
        ph = ','.join(['?'] * len(meses))
        query += f" AND codigo IN (SELECT DISTINCT motorista_codigo FROM reciclagens WHERE mes IN ({ph}) AND ano = ?)"
        params.extend(meses)
        params.append(ano_val)
    elif meses:
        ph = ','.join(['?'] * len(meses))
        query += f" AND codigo IN (SELECT DISTINCT motorista_codigo FROM reciclagens WHERE mes IN ({ph}))"
        params.extend(meses)
    elif ano_val:
        query += " AND codigo IN (SELECT DISTINCT motorista_codigo FROM reciclagens WHERE ano = ?)"
        params.append(ano_val)

    cursor.execute(query, params)
    motoristas = [dict(m) for m in cursor.fetchall()]

    kanban = {
        "enquadramento_1": [],     # 1. 1º Enquadramento: Reciclagem
        "reincidencia_1": [],      # 2. 1ª Reincidência: Reciclagem + Termo de Compromisso
        "reincidencia_2": [],      # 3. 2ª Reincidência: Viagem Assistida + PDI + Advertência
        "reincidencia_3": [],      # 4. 3ª Reincidência: Comitê Corporativo + Suspensão
        "reincidencia_4": []       # 5. 4ª Reincidência: Avaliação de Permanência na Função
    }

    for m in motoristas:
        cod = m['codigo']
        
        # Count reciclagens within the specified year (or all years if ano is not filtered)
        if ano_val:
            cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE motorista_codigo = ? AND ano = ?", (cod, ano_val))
        else:
            cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE motorista_codigo = ?", (cod,))
        total_rec_ano = cursor.fetchone()[0]

        if total_rec_ano == 0:
            continue

        # Verifica pendências no escopo selecionado (ano/mês)
        where_pend = "motorista_codigo = ?"
        params_pend = [cod]
        if ano_val:
            where_pend += " AND ano = ?"
            params_pend.append(ano_val)
        if meses:
            ph_m = ','.join(['?'] * len(meses))
            where_pend += f" AND mes IN ({ph_m})"
            params_pend.extend(meses)

        cursor.execute(f"SELECT COUNT(*) FROM reciclagens WHERE {where_pend} AND status IN ('PENDENTE', 'AGENDADO', 'MENSAGEM ENVIADA')", params_pend)
        pendentes_escopo = cursor.fetchone()[0]

        # Se não há tratativas pendentes no escopo (já foi concluído/aprovado), NÃO deve aparecer na Central de Ações
        if pendentes_escopo == 0:
            continue

        cursor.execute(f"SELECT * FROM reciclagens WHERE {where_pend} ORDER BY id DESC LIMIT 1", params_pend)
        last_rec = cursor.fetchone()
        if not last_rec:
            cursor.execute("SELECT * FROM reciclagens WHERE motorista_codigo = ? ORDER BY id DESC LIMIT 1", (cod,))
            last_rec = cursor.fetchone()

        last_status = last_rec['status'] if last_rec else 'PENDENTE'
        last_rec_id = last_rec['id'] if last_rec else None
        instrutor = last_rec['instrutor'] if (last_rec and last_rec['instrutor']) else 'Não atribuído'
        data_envio = last_rec['data_envio'] if last_rec else ''

        # Escalonamento de Consequências PGSC
        if total_rec_ano <= 1:
            situacao = "1º Enquadramento"
            consequencia = "Reciclagem"
            etapa_key = "enquadramento_1"
        elif total_rec_ano == 2:
            situacao = "1ª Reincidência"
            consequencia = "Reciclagem + Termo de Compromisso"
            etapa_key = "reincidencia_1"
        elif total_rec_ano == 3:
            situacao = "2ª Reincidência"
            consequencia = "Viagem Assistida + PDI + Advertência"
            etapa_key = "reincidencia_2"
        elif total_rec_ano == 4:
            situacao = "3ª Reincidência"
            consequencia = "Comitê Corporativo + Suspensão"
            etapa_key = "reincidencia_3"
        else:
            situacao = "4ª Reincidência (12m/ano)"
            consequencia = "Avaliação de Permanência na Função"
            etapa_key = "reincidencia_4"

        card = {
            "codigo": m['codigo'],
            "nome": m['nome'],
            "operacao": m['operacao'],
            "gestor": m['gestor'],
            "instrutor": instrutor,
            "faixa_risco": m['faixa_risco'],
            "nivel_tratamento": m['nivel_tratamento'],
            "total_reciclagens": total_rec_ano,
            "situacao": situacao,
            "consequencia": consequencia,
            "status": last_status,
            "last_rec_id": last_rec_id,
            "etapa_kanban": etapa_key,
            "data_envio": data_envio
        }

        kanban[etapa_key].append(card)

    conn.close()
    return kanban

def get_automatic_alerts():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Alert 1: Reciclagens pendentes
    cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE status = 'PENDENTE'")
    pendentes_cnt = cursor.fetchone()[0]

    # Alert 2: Novas reincidências críticas (Faixa Vermelha)
    cursor.execute("SELECT codigo, nome, operacao FROM motoristas WHERE faixa_risco = 'VERMELHA' LIMIT 3")
    criticos = [dict(r) for r in cursor.fetchall()]

    # Alert 3: Reincidentes nível 3 ou 4 aguardando PDI
    cursor.execute("SELECT codigo, nome, operacao, nivel_tratamento FROM motoristas WHERE nivel_tratamento >= 3 LIMIT 4")
    comites = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "pendentes_count": pendentes_cnt,
        "criticos_lista": criticos,
        "comites_lista": comites
    }

def get_faixas_risco_data(operacao='', ano='', mes=''):
    conn = get_db_connection()
    cursor = conn.cursor()

    ops = _parse_ops(operacao)
    meses = _parse_meses(mes)
    ano_val = _parse_ano(ano)

    if meses or ano_val:
        query = "SELECT m.faixa_risco, COUNT(DISTINCT m.codigo) as qtd FROM motoristas m INNER JOIN reciclagens r ON r.motorista_codigo = m.codigo WHERE 1=1"
        params = []
        if ops:
            ph = ','.join(['?'] * len(ops))
            query += f" AND m.operacao IN ({ph})"
            params.extend(ops)
        if ano_val:
            query += " AND r.ano = ?"
            params.append(ano_val)
        if meses:
            ph = ','.join(['?'] * len(meses))
            query += f" AND r.mes IN ({ph})"
            params.extend(meses)
        query += " GROUP BY m.faixa_risco"
    else:
        query = "SELECT faixa_risco, COUNT(*) as qtd FROM motoristas WHERE 1=1"
        params = []
        if ops:
            ph = ','.join(['?'] * len(ops))
            query += f" AND operacao IN ({ph})"
            params.extend(ops)
        query += " GROUP BY faixa_risco"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    result = {"VERDE": 0, "AMARELA": 0, "LARANJA": 0, "VERMELHA": 0}
    for r in rows:
        result[r['faixa_risco']] = r['qtd']
    return result

def get_comparativo_mensal_data(operacao='', ano='', mes=''):
    conn = get_db_connection()
    cursor = conn.cursor()

    ops = _parse_ops(operacao)
    meses = _parse_meses(mes)
    ano_val = _parse_ano(ano)

    query = '''
        SELECT ano, mes, 
               COUNT(*) as total_eventos,
               COUNT(DISTINCT motorista_codigo) as motoristas_unicos
        FROM reciclagens
        WHERE 1=1
    '''
    params = []
    if ops:
        ph = ','.join(['?'] * len(ops))
        query += f" AND operacao IN ({ph})"
        params.extend(ops)
    if ano_val:
        query += " AND ano = ?"
        params.append(ano_val)
    if meses:
        ph = ','.join(['?'] * len(meses))
        query += f" AND mes IN ({ph})"
        params.extend(meses)

    query += " GROUP BY ano, mes ORDER BY ano ASC, mes ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    months_map = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    result = []
    for r in rows:
        m_num = r['mes']
        reinc_query = '''
            SELECT COUNT(DISTINCT r1.motorista_codigo)
            FROM reciclagens r1
            WHERE r1.mes = ? AND EXISTS (
                SELECT 1 FROM reciclagens r2
                WHERE r2.motorista_codigo = r1.motorista_codigo AND r2.mes < r1.mes
            )
        '''
        reinc_params = [m_num]
        if ops:
            ph = ','.join(['?'] * len(ops))
            reinc_query += f" AND r1.operacao IN ({ph})"
            reinc_params.extend(ops)

        cursor.execute(reinc_query, reinc_params)
        reincidentes_no_mes = cursor.fetchone()[0]

        novos_no_mes = r['motoristas_unicos'] - reincidentes_no_mes
        taxa_reinc_mes = round((reincidentes_no_mes / r['motoristas_unicos'] * 100), 1) if r['motoristas_unicos'] > 0 else 0

        result.append({
            "ano": r['ano'] if 'ano' in r.keys() else 2026,
            "mes_num": m_num,
            "mes_nome": months_map.get(m_num, f'Mês {m_num}'),
            "total_eventos": r['total_eventos'],
            "motoristas_unicos": r['motoristas_unicos'],
            "reincidentes": reincidentes_no_mes,
            "novos": novos_no_mes,
            "taxa_reincidencia": taxa_reinc_mes
        })

    conn.close()
    return result

def gerar_relatorio_ia_comparativo(operacao='', ano='', mes=''):
    mensal = get_comparativo_mensal_data(operacao=operacao, ano=ano, mes=mes)
    if not mensal:
        return {
            "escopo": "Sem Dados",
            "total_acumulado": 0,
            "reinc_acumulado": 0,
            "variacao_global_pct": 0.0,
            "tendencia": "Sem Dados",
            "diagnostico": "Não há reciclagens registradas para os filtros selecionados.",
            "variacoes": [],
            "recomendacoes": ["Importe planilhas de reciclagens ou selecione outro período para gerar a análise comparativa de IA."]
        }

    variacoes = []
    total_acumulado = sum(m['total_eventos'] for m in mensal)
    reinc_acumulado = sum(m['reincidentes'] for m in mensal)

    for i in range(len(mensal)):
        curr = mensal[i]
        if i == 0:
            var_pct = 0.0
        else:
            prev = mensal[i-1]
            if prev['total_eventos'] > 0:
                var_pct = round(((curr['total_eventos'] - prev['total_eventos']) / prev['total_eventos']) * 100, 1)
            else:
                var_pct = 0.0

        variacoes.append({
            "mes_nome": curr['mes_nome'],
            "total_eventos": curr['total_eventos'],
            "motoristas_unicos": curr['motoristas_unicos'],
            "reincidentes": curr['reincidentes'],
            "taxa_reincidencia": curr['taxa_reincidencia'],
            "variacao_pct": var_pct
        })

    primeiro = mensal[0]['total_eventos']
    ultimo = mensal[-1]['total_eventos']
    if primeiro > 0:
        var_global_pct = round(((ultimo - primeiro) / primeiro) * 100, 1)
    else:
        var_global_pct = 0.0

    if var_global_pct < 0:
        tendencia = f"📉 Queda de {abs(var_global_pct)}% nos Incidentes"
        diagnostico = f"As ações de reciclagem surtiram efeito! Houve redução de {abs(var_global_pct)}% do {mensal[0]['mes_nome']} em relação ao {mensal[-1]['mes_nome']}."
    elif var_global_pct > 0:
        tendencia = f"📈 Aumento de {var_global_pct}% nos Incidentes"
        diagnostico = f"Atenção operacional: Houve um aumento de {var_global_pct}% nos registros de reciclagem do {mensal[0]['mes_nome']} ao {mensal[-1]['mes_nome']}."
    else:
        tendencia = "➡️ Estabilidade nos Registros"
        diagnostico = "O volume de reciclagens permaneceu estável durante o período monitorado."

    op_txt = f" na Filial {operacao}" if operacao else " na Visão Consolidada Corporativa"

    recomendacoes = []
    if reinc_acumulado > 0:
        recomendacoes.append("Agendar viagens assistidas (PDL) prioritárias para os motoristas reincidentes.")
    recomendacoes.append("Encaminhar casos da Faixa Vermelha (>3 reciclagens) diretamente à avaliação do Comitê Executivo.")
    if var_global_pct >= 0:
        recomendacoes.append("Reforçar abordagens educativas de controle de velocidade com instrutores de pátio.")

    return {
        "escopo": f"Análise Comparativa Mensal {op_txt}",
        "total_acumulado": total_acumulado,
        "reinc_acumulado": reinc_acumulado,
        "variacao_global_pct": var_global_pct,
        "tendencia": tendencia,
        "diagnostico": diagnostico,
        "variacoes": variacoes,
        "recomendacoes": recomendacoes
    }

def get_ranking_operacoes_data(ano='', mes=''):
    conn = get_db_connection()
    cursor = conn.cursor()

    meses = _parse_meses(mes)
    ano_val = _parse_ano(ano)

    where_r = " WHERE 1=1"
    params_r = []
    if ano_val:
        where_r += " AND ano = ?"
        params_r.append(ano_val)
    if meses:
        ph = ','.join(['?'] * len(meses))
        where_r += f" AND mes IN ({ph})"
        params_r.extend(meses)

    cursor.execute('''
        SELECT operacao,
               COUNT(*) as total_motoristas,
               SUM(CASE WHEN total_reciclagens_12m > 1 THEN 1 ELSE 0 END) as total_reincidentes,
               SUM(CASE WHEN faixa_risco = 'VERMELHA' THEN 1 ELSE 0 END) as criticos_vermelho
        FROM motoristas
        GROUP BY operacao
        ORDER BY total_motoristas DESC
    ''')
    rows = cursor.fetchall()

    result = []
    for r in rows:
        op = r['operacao']
        q_rec = "SELECT COUNT(*) FROM reciclagens " + where_r + " AND operacao = ?"
        p_rec = list(params_r) + [op]
        cursor.execute(q_rec, p_rec)
        total_reciclagens = cursor.fetchone()[0]

        # Obter gestor(es) da operação
        cursor.execute("SELECT DISTINCT gestor FROM motoristas WHERE operacao = ? AND gestor IS NOT NULL AND gestor != ''", (op,))
        g_rows = cursor.fetchall()
        gestores_list = [g[0] for g in g_rows if g[0]]
        gestor_display = " / ".join(gestores_list) if gestores_list else "NÃO INFORMADO"

        t_mot = r['total_motoristas']
        t_reinc = r['total_reincidentes']
        taxa_reinc = round((t_reinc / t_mot * 100), 1) if t_mot > 0 else 0
        efetividade = round(100 - taxa_reinc, 1)

        result.append({
            "operacao": op,
            "gestor": gestor_display,
            "total_reciclagens": total_reciclagens,
            "total_motoristas": t_mot,
            "total_reincidentes": t_reinc,
            "criticos_vermelho": r['criticos_vermelho'],
            "taxa_reincidencia": taxa_reinc,
            "efetividade": efetividade
        })

    result.sort(key=lambda x: x['total_reciclagens'], reverse=True)
    conn.close()
    return result

def get_ranking_gestores_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT gestor,
               operacao,
               COUNT(*) as total_motoristas,
               SUM(CASE WHEN total_reciclagens_12m > 1 THEN 1 ELSE 0 END) as total_reincidentes,
               SUM(CASE WHEN faixa_risco = 'VERMELHA' THEN 1 ELSE 0 END) as criticos
        FROM motoristas
        GROUP BY gestor
        ORDER BY total_motoristas DESC
    ''')
    rows = cursor.fetchall()

    result = []
    for r in rows:
        gst = r['gestor']
        cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE gestor = ?", (gst,))
        total_reciclagens = cursor.fetchone()[0]

        t_mot = r['total_motoristas']
        t_reinc = r['total_reincidentes']
        taxa = round((t_reinc / t_mot * 100), 1) if t_mot > 0 else 0

        result.append({
            "gestor": gst,
            "operacao": r['operacao'],
            "total_reciclagens": total_reciclagens,
            "total_motoristas": t_mot,
            "total_reincidentes": t_reinc,
            "criticos": r['criticos'],
            "taxa_reincidencia": taxa
        })

    result.sort(key=lambda x: x['total_reciclagens'], reverse=True)
    conn.close()
    return result

def get_motoristas_list(search='', operacao='', faixa='', nivel=None, ano='', mes=''):
    conn = get_db_connection()
    cursor = conn.cursor()

    ops = _parse_ops(operacao)
    ano_val = _parse_ano(ano)
    meses = _parse_meses(mes)

    query = '''
        SELECT m.*,
               (SELECT GROUP_CONCAT(r.mes, ', ') FROM reciclagens r WHERE r.motorista_codigo = m.codigo) as meses_eventos
        FROM motoristas m
        WHERE 1=1
    '''
    params = []

    if search:
        query += " AND (m.codigo LIKE ? OR m.nome LIKE ? OR m.gestor LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if ops:
        ph = ','.join(['?'] * len(ops))
        query += f" AND m.operacao IN ({ph})"
        params.extend(ops)
    if faixa:
        query += " AND m.faixa_risco = ?"
        params.append(faixa)
    if nivel is not None and nivel != '':
        query += " AND m.nivel_tratamento = ?"
        params.append(int(nivel))

    query += " ORDER BY m.total_reciclagens_12m DESC, m.nome ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    result = []
    for r in rows:
        d = dict(r)
        cod = d['codigo']
        if ano_val:
            cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE motorista_codigo = ? AND ano = ?", (cod, ano_val))
        else:
            cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE motorista_codigo = ?", (cod,))
        tot_ano = cursor.fetchone()[0]

        d['total_reciclagens_ano'] = tot_ano
        if tot_ano <= 1:
            d['situacao_pgsc'] = "1º Enquadramento"
            d['consequencia_pgsc'] = "Reciclagem"
        elif tot_ano == 2:
            d['situacao_pgsc'] = "1ª Reincidência"
            d['consequencia_pgsc'] = "Reciclagem + Termo de Compromisso"
        elif tot_ano == 3:
            d['situacao_pgsc'] = "2ª Reincidência"
            d['consequencia_pgsc'] = "Viagem Assistida + PDI + Advertência"
        elif tot_ano == 4:
            d['situacao_pgsc'] = "3ª Reincidência"
            d['consequencia_pgsc'] = "Comitê Corporativo + Suspensão"
        else:
            d['situacao_pgsc'] = "4ª Reincidência"
            d['consequencia_pgsc'] = "Avaliação de Permanência na Função"
        result.append(d)

    conn.close()
    return result

def get_top_motoristas_excessos(operacao='', limit=10, ano='', mes=''):
    conn = get_db_connection()
    cursor = conn.cursor()

    ops = _parse_ops(operacao)
    meses = _parse_meses(mes)
    ano_val = _parse_ano(ano)

    if meses or ano_val:
        query = '''
            SELECT m.codigo, m.nome, m.operacao, m.gestor, m.faixa_risco, m.etapa_kanban,
                   COUNT(r.id) as total_reciclagens_12m
            FROM motoristas m
            INNER JOIN reciclagens r ON r.motorista_codigo = m.codigo
            WHERE 1=1
        '''
        params = []
        if ops:
            ph = ','.join(['?'] * len(ops))
            query += f" AND m.operacao IN ({ph})"
            params.extend(ops)
        if ano_val:
            query += " AND r.ano = ?"
            params.append(ano_val)
        if meses:
            ph = ','.join(['?'] * len(meses))
            query += f" AND r.mes IN ({ph})"
            params.extend(meses)
        query += " GROUP BY m.codigo ORDER BY total_reciclagens_12m DESC, m.nome ASC LIMIT ?"
        params.append(limit)
    else:
        query = '''
            SELECT m.codigo, m.nome, m.operacao, m.gestor, m.total_reciclagens_12m, m.faixa_risco, m.etapa_kanban
            FROM motoristas m
            WHERE 1=1
        '''
        params = []
        if ops:
            ph = ','.join(['?'] * len(ops))
            query += f" AND m.operacao IN ({ph})"
            params.extend(ops)
        query += " ORDER BY m.total_reciclagens_12m DESC, m.nome ASC LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_motorista_detail(codigo):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM motoristas WHERE codigo = ?", (codigo,))
    mot = cursor.fetchone()
    if not mot:
        conn.close()
        return None

    motorista_data = dict(mot)

    cursor.execute("SELECT * FROM reciclagens WHERE motorista_codigo = ? ORDER BY mes ASC", (codigo,))
    reciclagens = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM pdis_comites WHERE motorista_codigo = ? ORDER BY id DESC", (codigo,))
    pdis = [dict(p) for p in cursor.fetchall()]

    conn.close()

    return {
        "motorista": motorista_data,
        "reciclagens": reciclagens,
        "pdis": pdis
    }

def update_reciclagem_status(reciclagem_id, status, data_realizacao=None, instrutor=None, observacao=None,
                             responsavel=None, resultado=None, motivo_recusa=None):
    """Atualiza o registro de realização da reciclagem.
    Compatível com chamadas antigas: os novos campos (responsável, resultado,
    motivo de não realização/recusa) são opcionais."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE reciclagens
        SET status = ?,
            data_realizacao = COALESCE(NULLIF(?, ''), data_realizacao),
            instrutor = COALESCE(NULLIF(?, ''), instrutor),
            observacao = COALESCE(NULLIF(?, ''), observacao),
            responsavel = COALESCE(NULLIF(?, ''), responsavel),
            resultado = COALESCE(NULLIF(?, ''), resultado),
            motivo_recusa = COALESCE(NULLIF(?, ''), motivo_recusa)
        WHERE id = ?
    ''', (status, data_realizacao, instrutor, observacao,
          responsavel, resultado, motivo_recusa, reciclagem_id))

    # Se a reciclagem foi marcada como CONCLUÍDO, checa se não restam pendências
    cursor.execute("SELECT motorista_codigo FROM reciclagens WHERE id = ?", (reciclagem_id,))
    row_m = cursor.fetchone()
    if row_m:
        cod_m = row_m['motorista_codigo']
        if status == 'CONCLUÍDO':
            cursor.execute("SELECT COUNT(*) FROM reciclagens WHERE motorista_codigo = ? AND status IN ('PENDENTE', 'AGENDADO', 'MENSAGEM ENVIADA')", (cod_m,))
            pend_rest = cursor.fetchone()[0]
            if pend_rest == 0:
                cursor.execute("UPDATE motoristas SET etapa_kanban = 'APROVADO', status_monitoramento = 'Concluído / Aprovado' WHERE codigo = ?", (cod_m,))
        elif status in ('PENDENTE', 'AGENDADO', 'MENSAGEM ENVIADA'):
            cursor.execute("SELECT etapa_kanban FROM motoristas WHERE codigo = ?", (cod_m,))
            m_curr = cursor.fetchone()
            if m_curr and m_curr['etapa_kanban'] == 'APROVADO':
                nova_e = 'AGUARDANDO' if status in ('AGENDADO', 'MENSAGEM ENVIADA') else 'NAO_INICIADO'
                cursor.execute("UPDATE motoristas SET etapa_kanban = ? WHERE codigo = ?", (nova_e, cod_m))

    conn.commit()
    conn.close()
    recalculate_driver_metrics()
    return True

def update_motorista_geral(codigo, etapa_kanban=None, faixa_risco=None, gestor=None, operacao=None, reciclagem_id=None, status_reciclagem=None, data_realizacao=None, instrutor=None, observacao=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    updates = []
    params = []
    if etapa_kanban is not None and etapa_kanban != '':
        updates.append("etapa_kanban = ?")
        params.append(etapa_kanban)
    if faixa_risco is not None and faixa_risco != '':
        updates.append("faixa_risco = ?")
        params.append(faixa_risco)
        updates.append("faixa_risco_override = 1")
    if gestor is not None and gestor != '':
        updates.append("gestor = ?")
        params.append(gestor)
    if operacao is not None and operacao != '':
        updates.append("operacao = ?")
        params.append(operacao)

    if updates:
        params.append(codigo)
        cursor.execute(f"UPDATE motoristas SET {', '.join(updates)} WHERE codigo = ?", params)

    if reciclagem_id and status_reciclagem:
        cursor.execute('''
            UPDATE reciclagens
            SET status = ?,
                data_realizacao = COALESCE(NULLIF(?, ''), data_realizacao),
                instrutor = COALESCE(NULLIF(?, ''), instrutor),
                observacao = COALESCE(NULLIF(?, ''), observacao)
            WHERE id = ?
        ''', (status_reciclagem, data_realizacao, instrutor, observacao, reciclagem_id))
    elif status_reciclagem:
        cursor.execute("SELECT id FROM reciclagens WHERE motorista_codigo = ? ORDER BY id DESC LIMIT 1", (codigo,))
        last = cursor.fetchone()
        if last:
            cursor.execute('''
                UPDATE reciclagens
                SET status = ?,
                    data_realizacao = COALESCE(NULLIF(?, ''), data_realizacao),
                    instrutor = COALESCE(NULLIF(?, ''), instrutor),
                    observacao = COALESCE(NULLIF(?, ''), observacao)
                WHERE id = ?
            ''', (status_reciclagem, data_realizacao, instrutor, observacao, last['id']))

    conn.commit()
    conn.close()
    recalculate_driver_metrics()
    return True

def mover_motorista_etapa(codigo, nova_etapa):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE motoristas SET etapa_kanban = ? WHERE codigo = ?", (nova_etapa, codigo))
    conn.commit()
    conn.close()
    recalculate_driver_metrics()
    return True

def aprovar_motorista(codigo):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE motoristas
        SET etapa_kanban = 'APROVADO',
            status_monitoramento = 'Concluído / Aprovado'
        WHERE codigo = ?
    ''', (codigo,))

    cursor.execute('''
        UPDATE reciclagens
        SET status = 'CONCLUÍDO'
        WHERE motorista_codigo = ? AND status IN ('PENDENTE', 'AGENDADO', 'MENSAGEM ENVIADA')
    ''', (codigo,))

    conn.commit()
    conn.close()
    recalculate_driver_metrics()
    return True

def add_pdi_record(motorista_codigo, nivel, tipo_acao, descricao, prazo, responsavel):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO pdis_comites (motorista_codigo, nivel, tipo_acao, descricao, data_inicio, prazo, status, responsavel)
        VALUES (?, ?, ?, ?, ?, ?, 'EM ANDAMENTO', ?)
    ''', (motorista_codigo, nivel, tipo_acao, descricao, datetime.now().strftime('%Y-%m-%d'), prazo, responsavel))

    conn.commit()
    conn.close()
    return True

# ── CONFIGURAÇÕES: Limpeza de Dados ──────────────────────────────────────────

def limpar_banco_dados_total():
    """Apaga todos os registros de reciclagens, motoristas e PDIs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pdis_comites")
    cursor.execute("DELETE FROM reciclagens")
    cursor.execute("DELETE FROM motoristas")
    conn.commit()
    conn.close()
    return True

def excluir_reciclagens_mes_ano(mes, ano):
    """Apaga reciclagens de um mês/ano específico e recalcula métricas."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reciclagens WHERE mes = ? AND ano = ?", (int(mes), int(ano)))
    # Remove motoristas que não têm mais nenhuma reciclagem
    cursor.execute("""
        DELETE FROM motoristas
        WHERE codigo NOT IN (SELECT DISTINCT motorista_codigo FROM reciclagens)
    """)
    conn.commit()
    conn.close()
    recalculate_driver_metrics()
    return True

def get_anos_disponiveis():
    """Retorna lista de anos distintos existentes na base de reciclagens."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ano FROM reciclagens ORDER BY ano DESC")
    anos = [r[0] for r in cursor.fetchall() if r[0]]
    conn.close()
    return anos

def get_meses_anos_existentes():
    """Retorna combinações de mês/ano existentes na base."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT mes, ano FROM reciclagens ORDER BY ano DESC, mes DESC")
    rows = [{"mes": r[0], "ano": r[1]} for r in cursor.fetchall() if r[0]]
    conn.close()
    return rows

if __name__ == '__main__':
    init_db()
    seed_db_from_excel()
    print("Database ready!")
