# ============================================================
# PGCSC · Módulo de EFETIVIDADE DAS RECICLAGENS
# ------------------------------------------------------------
# Analisa o fluxo completo:
#   EVENTO → MOTORISTA IDENTIFICADO → INDICAÇÃO → RESPONSÁVEL →
#   REALIZAÇÃO → REGISTRO → ACOMPANHAMENTO → REINCIDÊNCIA
#
# IMPORTANTE (regras de negócio NÃO definitivas — configuráveis):
#   - A regra de "reincidência em 3 meses consecutivos" e o
#     "impacto de 30% na premiação" estão ISOLADOS na tabela
#     config_sistema e NÃO são aplicados automaticamente.
#     Eles apenas sinalizam/alertam até validação definitiva.
#   - Nenhuma regra aqui é fixa: ver get_config()/set_config().
#   - Aderência = realizados / indicados × 100 (fórmula do escopo).
# ============================================================

from database import get_db_connection, _parse_ops, _parse_meses, _parse_ano

# ── Configurações (regras isoladas) ─────────────────────────

# Chaves padrão. Valores discutidos mas AINDA NÃO VALIDADOS.
DEFAULT_CONFIG = {
    # Regra discutida: reincidência durante 3 meses consecutivos
    "reincidencia_meses_consecutivos": "3",
    # Regra discutida: impacto de 30% na premiação (NÃO aplicado automaticamente)
    "premiacao_percentual_impacto": "30",
    # Flags de ativação — ficam DESLIGADAS até validação definitiva
    "regra_reincidencia_ativa": "0",
    "regra_premiacao_ativa": "0",
    # Fórmula de aderência confirmada no escopo
    "aderencia_formula": "realizados/indicados*100",
}

def _ensure_config_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS config_sistema (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            descricao TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

def get_config(chave=None, default=None):
    """Lê configuração(ões) do sistema. Garante defaults na primeira leitura."""
    conn = get_db_connection()
    _ensure_config_table(conn)
    cur = conn.cursor()
    for k, v in DEFAULT_CONFIG.items():
        cur.execute("INSERT OR IGNORE INTO config_sistema (chave, valor, descricao) VALUES (?, ?, ?)",
                    (k, v, "Regra não validada — ver documentação do módulo efetividade"))
    conn.commit()
    if chave:
        cur.execute("SELECT valor FROM config_sistema WHERE chave = ?", (chave,))
        row = cur.fetchone()
        conn.close()
        if row and row[0] is not None:
            return row[0]
        return DEFAULT_CONFIG.get(chave, default)
    cur.execute("SELECT chave, valor, descricao FROM config_sistema ORDER BY chave")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def set_config(chave, valor):
    """Grava uma configuração. Só aceita chaves conhecidas (evita lixo)."""
    if chave not in DEFAULT_CONFIG:
        raise ValueError(f"Chave de configuração desconhecida: {chave}")
    conn = get_db_connection()
    _ensure_config_table(conn)
    conn.execute('''
        INSERT INTO config_sistema (chave, valor, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, updated_at = CURRENT_TIMESTAMP
    ''', (chave, str(valor)))
    conn.commit()
    conn.close()
    return True

def get_regras_config():
    """Pacote de regras usado pelo frontend (Configurações) e pelos alertas."""
    cfg = {c["chave"]: c["valor"] for c in get_config()}
    def _int(k):
        try:
            return int(cfg.get(k, DEFAULT_CONFIG[k]))
        except (TypeError, ValueError):
            return int(DEFAULT_CONFIG[k])
    return {
        "reincidencia_meses_consecutivos": _int("reincidencia_meses_consecutivos"),
        "premiacao_percentual_impacto": _int("premiacao_percentual_impacto"),
        "regra_reincidencia_ativa": cfg.get("regra_reincidencia_ativa") == "1",
        "regra_premiacao_ativa": cfg.get("regra_premiacao_ativa") == "1",
        "validada": False,  # marcador explícito: regras ainda não validadas
    }

# ── Buckets de status do fluxo ──────────────────────────────
# Nomes de status EXISTENTES na base foram preservados. Os buckets
# agrupam sem renomear nada. Status desconhecido → tratado como pendente.

STATUS_CONCLUIDO = ('CONCLUÍDO', 'CONCLUIDO')
STATUS_RECUSADO = ('RECUSADO',)
STATUS_EM_ANDAMENTO = ('AGENDADO', 'MENSAGEM ENVIADA', 'VIAGEM_ASSISTIDA', 'EM ANDAMENTO')

def _bucket_status(status):
    s = (status or '').upper().strip()
    if s in [x.upper() for x in STATUS_CONCLUIDO]:
        return 'realizado'
    if s in [x.upper() for x in STATUS_RECUSADO]:
        return 'recusado'
    if s in [x.upper() for x in STATUS_EM_ANDAMENTO]:
        return 'em_andamento'
    return 'pendente'

# ── Filtros SQL compartilhados ──────────────────────────────

def _filtros(operacao='', ano='', mes='', alias=''):
    """Monta WHERE compartilhado. alias='' quando a query não usa alias
    (ex.: FROM reciclagens WHERE ...); alias='r1' quando a query aliasa."""
    where = " WHERE 1=1"
    params = []
    ops = _parse_ops(operacao)
    meses = _parse_meses(mes)
    ano_val = _parse_ano(ano)
    col_op = f"{alias}.operacao" if alias else "operacao"
    col_ano = f"{alias}.ano" if alias else "ano"
    col_mes = f"{alias}.mes" if alias else "mes"
    if ops:
        ph = ','.join(['?'] * len(ops))
        where += f" AND {col_op} IN ({ph})"
        params.extend(ops)
    if ano_val:
        where += f" AND {col_ano} = ?"
        params.append(ano_val)
    if meses:
        ph = ','.join(['?'] * len(meses))
        where += f" AND {col_mes} IN ({ph})"
        params.extend(meses)
    return where, params

def _prox_mes(ym):
    a, m = divmod(ym, 100)
    m += 1
    if m > 12:
        m = 1
        a += 1
    return a * 100 + m

def _streak_max(mset):
    """Maior sequência de meses consecutivos com evento."""
    melhor = atual = 0
    prev = None
    for ym in sorted(mset):
        if prev is not None and _prox_mes(prev) == ym:
            atual += 1
        else:
            atual = 1
        melhor = max(melhor, atual)
        prev = ym
    return melhor

# ── 1. KPIs gerenciais de efetividade ───────────────────────

def get_efetividade_kpis(operacao='', ano='', mes=''):
    """Responde rapidamente:
       - Quantos motoristas precisam de reciclagem?
       - Quantos foram indicados? Quantos realizaram? Qual a aderência?
       - Quantos recusados / pendentes / em andamento?
       - Quantos estão reincidindo? A reincidência está diminuindo?
       - Qual operação está melhor / pior?
       - Comparativo com o período anterior (mês anterior ou ano anterior).
    """
    conn = get_db_connection()
    cur = conn.cursor()

    where, params = _filtros(operacao, ano, mes)

    # ── Indicações (= eventos registrados no período) e buckets de status
    cur.execute(f"SELECT status, COUNT(*) FROM reciclagens{where} GROUP BY status", params)
    por_status = {r[0] or '': r[1] for r in cur.fetchall()}

    indicados = sum(por_status.values())
    realizados = sum(v for s, v in por_status.items() if _bucket_status(s) == 'realizado')
    recusados = sum(v for s, v in por_status.items() if _bucket_status(s) == 'recusado')
    em_andamento = sum(v for s, v in por_status.items() if _bucket_status(s) == 'em_andamento')
    pendentes = indicados - realizados - recusados - em_andamento

    taxa_aderencia = round(realizados / indicados * 100, 1) if indicados > 0 else 0.0

    # ── Motoristas distintos que necessitam de reciclagem no período (teve evento)
    cur.execute(f"SELECT COUNT(DISTINCT motorista_codigo) FROM reciclagens{where}", params)
    motoristas_necessitam = cur.fetchone()[0]

    # ── Reincidentes no período: motoristas que têm evento no escopo E
    #    também tiveram evento em algum mês ANTERIOR (histórico individual)
    cur.execute(f'''
        SELECT COUNT(DISTINCT motorista_codigo) FROM reciclagens
        WHERE motorista_codigo IN (
            SELECT motorista_codigo FROM reciclagens{where}
        )
        AND motorista_codigo IN (
            SELECT r3.motorista_codigo FROM reciclagens r3
            WHERE EXISTS (
                SELECT 1 FROM reciclagens r2
                WHERE r2.motorista_codigo = r3.motorista_codigo
                  AND (r2.ano < r3.ano OR (r2.ano = r3.ano AND r2.mes < r3.mes))
            )
        )
    ''', params)
    reincidentes_periodo = cur.fetchone()[0]

    # ── Alerta de sequência de meses consecutivos (regra configurável)
    regra = get_regras_config()
    n_consec = regra["reincidencia_meses_consecutivos"]
    cur.execute("SELECT DISTINCT motorista_codigo, ano, mes FROM reciclagens")
    meses_hist = {}
    for cod, a, m in cur.fetchall():
        meses_hist.setdefault(cod, set()).add(a * 100 + m)
    total_em_alerta = sum(
        1 for mset in meses_hist.values()
        if len(mset) >= 2 and _streak_max(mset) >= n_consec
    )

    # ── Por operação: aderência, melhor e pior
    cur.execute(f'''
        SELECT operacao,
               COUNT(*) AS indicados,
               SUM(CASE WHEN UPPER(status) IN ('CONCLUÍDO','CONCLUIDO') THEN 1 ELSE 0 END) AS realizados,
               SUM(CASE WHEN UPPER(status) = 'RECUSADO' THEN 1 ELSE 0 END) AS recusados,
               COUNT(DISTINCT motorista_codigo) AS motoristas
        FROM reciclagens{where}
        GROUP BY operacao
    ''', params)
    por_operacao = []
    for r in cur.fetchall():
        ind = r['indicados'] or 0
        rea = r['realizados'] or 0
        por_operacao.append({
            "operacao": r['operacao'],
            "indicados": ind,
            "realizados": rea,
            "recusados": r['recusados'] or 0,
            "motoristas_necessitam": r['motoristas'],
            "taxa_aderencia": round(rea / ind * 100, 1) if ind else 0.0
        })
    com_dados = [o for o in por_operacao if o['indicados'] > 0]
    melhor = max(com_dados, key=lambda o: (o['taxa_aderencia'], -o['indicados'])) if com_dados else None
    pior = min(com_dados, key=lambda o: o['taxa_aderencia']) if com_dados else None

    # ── Comparativo com o período anterior
    comp = _comparativo_periodo_anterior(conn, operacao, ano, mes)

    conn.close()

    return {
        "motoristas_necessitam_reciclagem": motoristas_necessitam,
        "indicados": indicados,
        "realizados": realizados,
        "pendentes": pendentes,
        "em_andamento": em_andamento,
        "recusados": recusados,
        "taxa_aderencia": taxa_aderencia,
        "reincidentes": reincidentes_periodo,
        "reincidentes_meses_consecutivos": total_em_alerta,
        "limiar_meses_consecutivos": n_consec,
        "regra_reincidencia_ativa": regra["regra_reincidencia_ativa"],
        "regra_premiacao_ativa": regra["regra_premiacao_ativa"],
        "premiacao_percentual_impacto": regra["premiacao_percentual_impacto"],
        "melhor_operacao": melhor,
        "pior_operacao": pior,
        "por_operacao": sorted(por_operacao, key=lambda o: (-o['indicados'], o['operacao'])),
        "comparativo_periodo_anterior": comp,
        "fonte_eventos": "reciclagens (importação mensal da telemetria)"
    }

def _comparativo_periodo_anterior(conn, operacao, ano, mes):
    """Compara o período filtrado com o mês anterior (se houver mês
    selecionado) ou com o ano anterior (se filtro anual/geral)."""
    meses = _parse_meses(mes)
    ano_val = _parse_ano(ano)
    ops = _parse_ops(operacao)

    def _agregar(w, p):
        cur = conn.cursor()
        cur.execute(f'''
            SELECT COUNT(*),
                   SUM(CASE WHEN UPPER(status) IN ('CONCLUÍDO','CONCLUIDO') THEN 1 ELSE 0 END),
                   COUNT(DISTINCT motorista_codigo)
            FROM reciclagens{w}
        ''', p)
        r = cur.fetchone()
        ind = r[0] or 0
        rea = r[1] or 0
        return {
            "indicados": ind,
            "realizados": rea,
            "taxa_aderencia": round(rea / ind * 100, 1) if ind else 0.0,
            "motoristas_necessitam": r[2] or 0,
        }

    if meses:
        prev = []
        for m in meses:
            pm = m - 1
            pa = ano_val
            if pm == 0:
                pm = 12
                pa = (ano_val - 1) if ano_val else None
            prev.append((pa, pm))
        w_parts = []
        p_parts = []
        for pa, pm in prev:
            w_parts.append("((? IS NULL OR ano = ?) AND mes = ?)")
            p_parts.extend([pa, pa, pm])
        where_prev = " WHERE (" + " OR ".join(w_parts) + ")"
        rotulo = "mês anterior"
    else:
        ano_prev = (ano_val - 1) if ano_val else None
        where_prev = " WHERE (? IS NULL OR ano = ?)"
        p_parts = [ano_prev, ano_prev]
        rotulo = "ano anterior"

    if ops:
        ph = ','.join(['?'] * len(ops))
        where_prev += f" AND operacao IN ({ph})"
        p_parts.extend(ops)

    atual_w, atual_p = _filtros(operacao, ano, mes)
    atual = _agregar(atual_w, atual_p)
    anterior = _agregar(where_prev, p_parts)

    def _delta(a, b):
        if b:
            return round((a - b) / abs(b) * 100, 1)
        return None

    return {
        "rotulo_anterior": rotulo,
        "atual": atual,
        "anterior": anterior,
        "variacao_indicados_pct": _delta(atual['indicados'], anterior['indicados']),
        "variacao_aderencia_pp": round(atual['taxa_aderencia'] - anterior['taxa_aderencia'], 1),
        "variacao_motoristas_pct": _delta(atual['motoristas_necessitam'], anterior['motoristas_necessitam']),
    }

# ── 2. Evolução mensal (aderência, reincidência, por operação) ──

MESES_NOME = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
              7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}

def get_evolucao_mensal(operacao='', ano='', mes=''):
    """Por mês do escopo: motoristas que necessitam reciclagem, indicados x
    realizados, aderência %, reincidentes (motoristas com eventos em meses
    anteriores — histórico individual preservado)."""
    conn = get_db_connection()
    cur = conn.cursor()

    where, params = _filtros(operacao, ano, mes)
    cur.execute(f'''
        SELECT ano, mes,
               COUNT(*) AS indicados,
               SUM(CASE WHEN UPPER(status) IN ('CONCLUÍDO','CONCLUIDO') THEN 1 ELSE 0 END) AS realizados,
               SUM(CASE WHEN UPPER(status) = 'RECUSADO' THEN 1 ELSE 0 END) AS recusados,
               COUNT(DISTINCT motorista_codigo) AS motoristas_necessitam
        FROM reciclagens{where}
        GROUP BY ano, mes
        ORDER BY ano ASC, mes ASC
    ''', params)
    rows = [dict(r) for r in cur.fetchall()]

    ops = _parse_ops(operacao)
    op_ph = f" AND r1.operacao IN ({','.join(['?'] * len(ops))})" if ops else ""

    result = []
    for r in rows:
        # Reincidentes no mês: teve evento no mês E em algum mês anterior
        q = '''
            SELECT COUNT(DISTINCT r1.motorista_codigo)
            FROM reciclagens r1
            WHERE r1.ano = ? AND r1.mes = ? AND EXISTS (
                SELECT 1 FROM reciclagens r2
                WHERE r2.motorista_codigo = r1.motorista_codigo
                  AND (r2.ano < r1.ano OR (r2.ano = r1.ano AND r2.mes < r1.mes))
            )
        ''' + op_ph
        cur.execute(q, [r['ano'], r['mes']] + ops)
        reincidentes = cur.fetchone()[0]

        ind = r['indicados'] or 0
        rea = r['realizados'] or 0
        result.append({
            "ano": r['ano'],
            "mes_num": r['mes'],
            "mes_nome": MESES_NOME.get(r['mes'], f"Mês {r['mes']}"),
            "motoristas_necessitam": r['motoristas_necessitam'],
            "indicados": ind,
            "realizados": rea,
            "recusados": r['recusados'] or 0,
            "taxa_aderencia": round(rea / ind * 100, 1) if ind else 0.0,
            "reincidentes": reincidentes,
        })

    conn.close()
    return result

def get_evolucao_por_operacao(operacao='', ano='', mes=''):
    """Evolução do volume de eventos por operação ao longo dos meses do escopo."""
    conn = get_db_connection()
    cur = conn.cursor()
    where, params = _filtros(operacao, ano, mes)
    cur.execute(f'''
        SELECT ano, mes, operacao, COUNT(*) AS eventos,
               SUM(CASE WHEN UPPER(status) IN ('CONCLUÍDO','CONCLUIDO') THEN 1 ELSE 0 END) AS realizados
        FROM reciclagens{where}
        GROUP BY ano, mes, operacao
        ORDER BY ano ASC, mes ASC, operacao ASC
    ''', params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# ── 3. Histórico individual + reincidência ──────────────────

def get_motorista_historico(codigo):
    """Linha do tempo individual + análise de reincidência.
    Complementa (não duplica) get_motorista_detail() de database.py.
    Responde: 'Os motoristas reciclados realmente melhoraram?' e
    'Os mesmos motoristas continuam reincidindo?'"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM motoristas WHERE codigo = ?", (codigo,))
    mot = cur.fetchone()
    if not mot:
        conn.close()
        return None
    motorista = dict(mot)

    cur.execute('''SELECT * FROM reciclagens WHERE motorista_codigo = ?
                   ORDER BY ano ASC, mes ASC, id ASC''', (codigo,))
    recs = [dict(r) for r in cur.fetchall()]
    conn.close()

    # ── Linha do tempo: EVENTO → INDICAÇÃO → REALIZAÇÃO (por mês de referência)
    meses_evento = []
    timeline = []
    for r in recs:
        ym = r['ano'] * 100 + r['mes']
        # reincidente neste mês = já existia evento em mês anterior
        reincidente_mes = len(meses_evento) > 0
        if ym not in meses_evento:
            meses_evento.append(ym)

        timeline.append({
            "reciclagem_id": r['id'],
            "ano": r['ano'],
            "mes": r['mes'],
            "mes_nome": MESES_NOME.get(r['mes'], f"Mês {r['mes']}"),
            "acao_corretiva": r['acao_corretiva'],
            "status": r['status'],
            "bucket": _bucket_status(r['status']),  # realizado|recusado|em_andamento|pendente
            "evento_mes_referencia": f"{MESES_NOME.get(r['mes'], r['mes'])}/{r['ano']}",
            "data_indicacao": r['data_envio'] or '',
            "responsavel": r.get('responsavel') or '',
            "data_realizacao": r['data_realizacao'] or '',
            "resultado": r.get('resultado') or '',
            "motivo_recusa": r.get('motivo_recusa') or '',
            "observacao": r['observacao'] or '',
            "instrutor": r['instrutor'] or '',
            "reincidente_no_mes": reincidente_mes,
        })

    # ── Análise de reincidência (histórico individual)
    meses_unicos = sorted(set(meses_evento))
    total_reincidencias = max(0, len(meses_unicos) - 1) if meses_unicos else 0

    meses_reincidiu = []
    seq_atual = 0
    prev = None
    for i, ym in enumerate(meses_unicos):
        if prev is not None and _prox_mes(prev) == ym:
            seq_atual += 1
        else:
            seq_atual = 1
        if i > 0:
            meses_reincidiu.append(ym)
        prev = ym

    max_seq = _streak_max(meses_unicos) if meses_unicos else 0

    regra = get_regras_config()
    n_consec = regra["reincidencia_meses_consecutivos"]
    em_alerta_reincidencia = max_seq >= n_consec and len(meses_unicos) >= 2

    # ── Evolução pós-reciclagem: eventos antes vs depois da 1ª realização
    primeira_realizacao = next(
        (r['data_realizacao'] for r in recs if r['data_realizacao']), None)
    eventos_antes, eventos_depois = 0, 0
    if primeira_realizacao:
        try:
            pr = str(primeira_realizacao)[:10].replace('-', '')
            pr_ym = int(pr[:4]) * 100 + int(pr[4:6])
            for r in recs:
                ym = r['ano'] * 100 + r['mes']
                # evento do mesmo mês da realização conta como "antes" (gerou a ação)
                if ym < pr_ym:
                    eventos_antes += 1
                elif ym > pr_ym:
                    eventos_depois += 1
        except (ValueError, TypeError):
            primeira_realizacao = None

    ultimo_ym = meses_unicos[-1] if meses_unicos else None

    def _fmt(ym):
        return f"{MESES_NOME.get(ym % 100, ym % 100)}/{ym // 100}" if ym else None

    return {
        "motorista": motorista,
        "total_registros": len(recs),
        "meses_com_evento": [_fmt(ym) for ym in meses_unicos],
        "total_reincidencias": total_reincidencias,
        "meses_que_reincidiu": [_fmt(ym) for ym in meses_reincidiu],
        "maior_sequencia_meses_consecutivos": max_seq,
        "em_alerta_reincidencia": em_alerta_reincidencia,
        "limiar_meses_consecutivos": n_consec,
        "regra_reincidencia_ativa": regra["regra_reincidencia_ativa"],
        "premiacao_percentual_impacto": regra["premiacao_percentual_impacto"] if em_alerta_reincidencia else None,
        "evolucao_pos_reciclagem": {
            "primeira_realizacao": primeira_realizacao,
            "eventos_antes_da_reciclagem": eventos_antes,
            "eventos_apos_reciclagem": eventos_depois,
            "melhorou": (eventos_depois < eventos_antes) if primeira_realizacao else None,
            "ultimo_mes_com_evento": _fmt(ultimo_ym),
        },
        "timeline": timeline,
    }

# ── 4. Lista de reincidentes (drill-down do dashboard) ──────

def get_reincidentes_detalhado(operacao='', ano='', mes='', apenas_alerta=False):
    """Motoristas reincidentes com meses, sequência e histórico.
    apenas_alerta=True filtra quem atinge a regra configurável de
    meses consecutivos (3 por padrão — NÃO validada)."""
    conn = get_db_connection()
    cur = conn.cursor()

    where, params = _filtros(operacao, ano, mes)
    cur.execute(f'SELECT DISTINCT motorista_codigo FROM reciclagens{where}', params)
    codigos = [r[0] for r in cur.fetchall()]
    conn.close()

    resultado = []
    for cod in codigos:
        h = get_motorista_historico(cod)
        if not h or h['total_registros'] < 2:
            continue
        if apenas_alerta and not h['em_alerta_reincidencia']:
            continue
        m = h['motorista']
        resultado.append({
            "codigo": cod,
            "nome": m['nome'],
            "operacao": m['operacao'],
            "gestor": m['gestor'],
            "faixa_risco": m['faixa_risco'],
            "indicados": h['total_registros'],
            "total_reincidencias": h['total_reincidencias'],
            "meses_que_reincidiu": h['meses_que_reincidiu'],
            "maior_sequencia": h['maior_sequencia_meses_consecutivos'],
            "em_alerta_reincidencia": h['em_alerta_reincidencia'],
        })

    resultado.sort(key=lambda x: (-x['total_reincidencias'], x['nome']))
    regra = get_regras_config()
    return {
        "limiar_meses_consecutivos": regra["reincidencia_meses_consecutivos"],
        "regra_reincidencia_ativa": regra["regra_reincidencia_ativa"],
        "premiacao_percentual_impacto": regra["premiacao_percentual_impacto"],
        "total": len(resultado),
        "motoristas": resultado,
    }
